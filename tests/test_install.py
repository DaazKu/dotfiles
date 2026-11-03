import importlib.machinery
import importlib.util
import io
import os
import shutil
import unittest
from unittest import mock

from support import INSTALL, REPO, HomeTestCase


def repo_files():
    source = os.path.join(REPO, "home")
    for root, _dirs, files in os.walk(source):
        for name in files:
            path = os.path.join(root, name)
            yield path, os.path.relpath(path, source)


def load_installer():
    loader = importlib.machinery.SourceFileLoader("dotfiles_install", INSTALL)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class InstallLinkTest(HomeTestCase):
    def assert_all_linked(self):
        for src, relative in repo_files():
            dst = os.path.join(self.home, relative)
            self.assertTrue(os.path.islink(dst), dst)
            self.assertEqual(os.readlink(dst), src)

    def test_clean_install_links_every_file(self):
        result = self.install()
        self.assert_all_linked()
        self.assertIn("already in place", result.stdout)

    def test_repeat_install_changes_nothing(self):
        self.install()
        before = {r: os.lstat(os.path.join(self.home, r)).st_ino for _s, r in repo_files()}
        result = self.install()
        after = {r: os.lstat(os.path.join(self.home, r)).st_ino for _s, r in repo_files()}
        self.assertEqual(before, after)
        self.assertIn("0 linked", result.stdout)

    def test_new_repo_file_is_linked_on_rerun(self):
        clone = os.path.join(self.tmp, "clone with space")
        shutil.copytree(REPO, clone, ignore=shutil.ignore_patterns(".git", ".worktrees"))
        installer = os.path.join(clone, "install")
        self.install(installer=installer)
        added = os.path.join(clone, "home", ".config", "new tool", "settings.conf")
        os.makedirs(os.path.dirname(added))
        open(added, "w").close()
        result = self.install(installer=installer)
        self.assertIn("1 linked", result.stdout)
        self.assertEqual(os.readlink(os.path.join(self.home, ".config", "new tool", "settings.conf")), added)

    def test_conflicts_are_reported_before_anything_changes(self):
        real_file = self.write(".bashrc", "existing\n")
        other = os.path.join(self.tmp, "other")
        open(other, "w").close()
        os.makedirs(os.path.join(self.home, ".config", "git"))
        os.symlink(other, os.path.join(self.home, ".config", "git", "config"))
        self.write(".local", "not a directory\n")

        result = self.install(check=False)

        self.assertEqual(result.returncode, 1)
        self.assertIn(real_file + " (file)", result.stdout)
        self.assertIn("config (symlink to " + other + ")", result.stdout)
        self.assertIn("parent " + os.path.join(self.home, ".local") + " is not a directory", result.stdout)
        with open(real_file) as handle:
            self.assertEqual(handle.read(), "existing\n")
        self.assertFalse(os.path.lexists(os.path.join(self.home, ".zshrc")))

    def test_dry_run_changes_nothing(self):
        result = self.install("--dry-run")
        self.assertIn("would link", result.stdout)
        self.assertEqual(os.listdir(self.home), [])

    def test_local_files_beside_links_are_left_alone(self):
        local = self.write(".config/git/local.gitconfig", "[user]\n\tname = x\n")
        self.install()
        self.assertFalse(os.path.islink(local))
        self.assertTrue(os.path.islink(os.path.join(self.home, ".config", "git", "config")))

    def test_linked_helper_is_executable(self):
        self.install()
        helper = os.path.join(self.home, ".local", "bin", "gh")
        self.assertTrue(os.access(helper, os.X_OK))
        result = self.run_cmd([helper, "--version"], check=False, env=self.env(PATH="/nonexistent"))
        self.assertEqual(result.returncode, 127)
        self.assertIn("no gh executable found", result.stderr)

class PackageCommandTest(HomeTestCase):
    """Package commands are checked without running a package manager."""

    def setUp(self):
        super().setUp()
        self.installer = load_installer()
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)

    def fake(self, *names):
        for name in names:
            path = os.path.join(self.bin, name)
            with open(path, "w") as handle:
                handle.write("#!/bin/sh\n")
            os.chmod(path, 0o755)

    def commands(self, system, euid=1000):
        with mock.patch.dict(os.environ, {"PATH": self.bin}), \
             mock.patch("platform.system", return_value=system), \
             mock.patch("os.geteuid", return_value=euid):
            return self.installer.package_commands(self.home)

    def test_macos_uses_homebrew(self):
        self.fake("brew")
        self.assertEqual(self.commands("Darwin"), [["brew", "install", "git", "gh", "tmux", "herdr"]])

    def test_macos_keeps_existing_herdr(self):
        self.fake("brew", "herdr")
        self.assertEqual(self.commands("Darwin"), [["brew", "install", "git", "gh", "tmux"]])

    def test_macos_without_homebrew_stops(self):
        with self.assertRaises(SystemExit) as raised:
            self.commands("Darwin")
        self.assertIn("https://brew.sh", str(raised.exception))

    def test_ubuntu_uses_apt_and_official_herdr_installer(self):
        self.fake("apt-get")
        self.assertEqual(self.commands("Linux"), [
            ["sudo", "apt-get", "update"],
            ["sudo", "apt-get", "install", "-y", "curl", "git", "gh", "tmux"],
            ["sh", "-c", "curl -fsSL https://herdr.dev/install.sh | sh"],
        ])

    def test_ubuntu_as_root_without_sudo_keeps_existing_herdr(self):
        self.fake("apt-get")
        self.write(".local/bin/herdr", "#!/bin/sh\n", mode=0o755)
        self.assertEqual(self.commands("Linux", euid=0), [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "curl", "git", "gh", "tmux"],
        ])

    def test_linux_without_apt_stops(self):
        with self.assertRaises(SystemExit) as raised:
            self.commands("Linux")
        self.assertIn("Ubuntu only", str(raised.exception))

    def test_reports_missing_tools_but_not_the_wrapper_as_gh(self):
        self.fake("git")
        self.install()
        with mock.patch.dict(os.environ, {"PATH": self.bin + ":" + os.path.join(self.home, ".local", "bin")}), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.installer.report_tools(self.home)
        self.assertEqual(out.getvalue(), "Missing tools: gh, tmux, herdr. Install them with: ./install --packages\n")

    def test_packages_dry_run_runs_nothing(self):
        self.fake("brew")
        with mock.patch.dict(os.environ, {"PATH": self.bin}), \
             mock.patch("platform.system", return_value="Darwin"), \
             mock.patch("subprocess.run") as run, \
             mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.installer.install_packages(self.home, dry_run=True)
        run.assert_not_called()
        self.assertEqual(out.getvalue(), "would run: brew install git gh tmux herdr\n")


if __name__ == "__main__":
    unittest.main()

import os
import unittest

from support import HomeTestCase, require

PROBE = r"""
printf 'PATH=%s\n' "$PATH"
if alias ll >/dev/null 2>&1; then echo alias=yes; else echo alias=no; fi
if command -v path_prepend >/dev/null 2>&1; then echo helper=yes; else echo helper=no; fi
printf 'gh=%s\n' "$(command -v gh)"
if [ -f "$HOME/order" ]; then printf 'order=%s\n' "$(tr '\n' ' ' < "$HOME/order")"; fi
"""

SNIPPET = r"""
if alias ll >/dev/null 2>&1; then shared=after-shared; else shared=before-shared; fi
echo "{name}:$shared" >> "$HOME/order"
path_prepend "$HOME/snippet bin"
"""

MODES = {
    "interactive": ["-i"],
    "login": ["-l"],
    "login interactive": ["-l", "-i"],
}


class ShellStartupMixin:
    shell = None
    conf_dir = None
    suffix = None

    def setUp(self):
        super().setUp()
        self.install()
        os.makedirs(os.path.join(self.home, "snippet bin"))
        # Written out of order to check that loading sorts them.
        for name in ("20-second", "10-first"):
            self.write(os.path.join(self.conf_dir, name + self.suffix), SNIPPET.format(name=name))
        self.write(os.path.join(self.conf_dir, "README.txt"), "not a snippet\n")

    def start(self, mode, path=None):
        env = self.env()
        if path is not None:
            env["PATH"] = path
        result = self.run_cmd([self.shell] + MODES[mode] + ["-c", PROBE], env=env)
        for problem in ("No such file", "not found", "command not found", "syntax error", "parse error"):
            self.assertNotIn(problem, result.stderr)
        return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)

    def path_entries(self, state):
        return state["PATH"].split(":")

    def test_interactive_shells_load_shared_then_sorted_snippets(self):
        for mode in ("interactive", "login interactive"):
            with self.subTest(mode=mode):
                order = os.path.join(self.home, "order")
                if os.path.exists(order):
                    os.remove(order)
                state = self.start(mode)
                self.assertEqual(state["alias"], "yes")
                self.assertEqual(state["helper"], "yes")
                self.assertEqual(state["order"], "10-first:after-shared 20-second:after-shared ")
                entries = self.path_entries(state)
                self.assertEqual(entries[0], os.path.join(self.home, "snippet bin"))
                self.assertEqual(entries[1], os.path.join(self.home, ".local", "bin"))

    def test_login_shell_sets_path_without_interactive_setup(self):
        state = self.start("login")
        self.assertEqual(state["alias"], "no")
        self.assertNotIn("order", state)
        self.assertEqual(self.path_entries(state)[0], os.path.join(self.home, ".local", "bin"))

    def test_path_has_no_duplicates_in_any_mode_or_nested_shell(self):
        local_bin = os.path.join(self.home, ".local", "bin")
        inherited = "/usr/bin:" + local_bin + ":/bin:" + local_bin
        for mode in MODES:
            for path in (None, inherited):
                with self.subTest(mode=mode, inherited=path is not None):
                    entries = self.path_entries(self.start(mode, path))
                    self.assertEqual(len(entries), len(set(entries)), entries)
                    self.assertIn(local_bin, entries[:2])

    def test_installed_gh_wrapper_wins_on_path(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assertEqual(self.start(mode)["gh"], os.path.join(self.home, ".local", "bin", "gh"))


@require("bash")
class BashStartupTest(ShellStartupMixin, HomeTestCase):
    shell = "bash"
    conf_dir = ".config/bash/conf.d"
    suffix = ".sh"


@require("zsh")
class ZshStartupTest(ShellStartupMixin, HomeTestCase):
    shell = "zsh"
    conf_dir = ".config/zsh/conf.d"
    suffix = ".zsh"


if __name__ == "__main__":
    unittest.main()

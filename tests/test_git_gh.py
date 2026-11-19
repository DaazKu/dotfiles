import json
import os
import signal
import unittest

from support import REPO, SYSTEM_PATH, HomeTestCase, require

# Records what the wrapper passed on: arguments, token variables and stdin.
FAKE_GH = r"""#!/bin/sh
python3 - "$@" <<'PY'
import json, os, sys
record = {
    "args": sys.argv[1:],
    "GH_TOKEN": os.environ.get("GH_TOKEN"),
    "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN"),
}
with open(os.environ["FAKE_GH_RECORD"], "w") as handle:
    json.dump(record, handle)
PY
echo "fake gh output"
[ -n "$FAKE_GH_SIGNAL" ] && kill -s "$FAKE_GH_SIGNAL" $$
exit "${FAKE_GH_EXIT:-0}"
"""

PERSONAL = "alex-example"
WORK = "alex-example-work"


@require("git")
class GitConfigTest(HomeTestCase):
    def setUp(self):
        super().setUp()
        self.install()
        for relative in (
            ".gitconfig",
            ".config/git/conf.d/identity-personal.gitconfig",
            ".config/git/conf.d/identity-work.gitconfig",
        ):
            self.copy_example(relative)

    def repo(self, relative):
        path = os.path.join(self.home, relative)
        os.makedirs(path)
        self.run_cmd(["git", "init", "-q", path])
        return path

    def git_config(self, cwd, key):
        return self.run_cmd(["git", "config", "--get", key], cwd=cwd).stdout.strip()

    def test_shared_defaults_apply(self):
        repo = self.repo("projects/app")
        self.assertEqual(self.git_config(repo, "init.defaultBranch"), "main")
        self.assertEqual(self.git_config(repo, "push.autoSetupRemote"), "true")
        branch = self.run_cmd(["git", "symbolic-ref", "--short", "HEAD"], cwd=repo).stdout.strip()
        self.assertEqual(branch, "main")

    def test_directory_selects_identity(self):
        self.assertEqual(self.git_config(self.repo("projects/app"), "user.name"), PERSONAL)
        work = self.repo("work/client app")
        self.assertEqual(self.git_config(work, "user.name"), WORK)
        self.assertEqual(self.git_config(work, "user.email"), "alex@work.example.com")
        self.assertEqual(self.git_config(self.home, "user.name"), PERSONAL)

    def test_manifest_fragments_extend_and_override_defaults(self):
        self.write(".config/git/conf.d/tools.gitconfig", "[fetch]\n\tprune = false\n[alias]\n\tst = status\n")
        with open(os.path.join(self.home, ".gitconfig"), "a") as handle:
            handle.write("[include]\n\tpath = ~/.config/git/conf.d/tools.gitconfig\n")
        repo = self.repo("projects/app")
        self.assertEqual(self.git_config(repo, "alias.st"), "status")
        self.assertEqual(self.git_config(repo, "fetch.prune"), "false")

    def test_global_writes_stay_out_of_the_repository(self):
        os.remove(os.path.join(self.home, ".gitconfig"))
        self.install()
        tracked = os.path.join(REPO, "home", ".config", "git", "config")
        with open(tracked) as handle:
            before = handle.read()
        self.run_cmd(["git", "config", "--global", "credential.helper", "!gh auth git-credential"])
        with open(tracked) as handle:
            self.assertEqual(handle.read(), before)
        with open(os.path.join(self.home, ".gitconfig")) as handle:
            self.assertIn("gh auth git-credential", handle.read())

    def test_global_writes_keep_directory_identities(self):
        repo = self.repo("work/client app")
        self.run_cmd(["git", "config", "--global", "credential.helper", "!gh auth git-credential"])
        self.assertEqual(self.git_config(repo, "credential.helper"), "!gh auth git-credential")
        self.assertEqual(self.git_config(repo, "user.name"), WORK)

    def test_missing_manifest_is_fine(self):
        os.remove(os.path.join(self.home, ".gitconfig"))
        repo = self.repo("projects/app")
        self.assertEqual(self.git_config(repo, "init.defaultBranch"), "main")
        result = self.run_cmd(["git", "config", "--get", "user.name"], cwd=repo, check=False)
        self.assertEqual(result.stdout, "")


@require("git")
class GhWrapperTest(HomeTestCase):
    def setUp(self):
        super().setUp()
        self.install()
        self.wrapper = os.path.join(self.home, ".local", "bin", "gh")
        self.fake_bin = os.path.join(self.tmp, "real bin")
        os.mkdir(self.fake_bin)
        fake = os.path.join(self.fake_bin, "gh")
        with open(fake, "w") as handle:
            handle.write(FAKE_GH)
        os.chmod(fake, 0o755)
        self.record = os.path.join(self.tmp, "record.json")
        self.tokens = os.path.join(self.tmp, "tokens")
        os.mkdir(self.tokens)
        self.write_token("personal", "personal-secret-token\n")
        self.write_token("work", "work-secret-token")
        self.write(".config/gh-wrapper/identities", (
            '[identity "%s"]\n\ttokenFile = %s/personal\n'
            '[identity "%s"]\n\ttokenFile = %s/work\n'
        ) % (PERSONAL, self.tokens, WORK, self.tokens))
        self.repo_dir = os.path.join(self.home, "repo")
        os.mkdir(self.repo_dir)
        self.run_cmd(["git", "init", "-q", self.repo_dir])

    def write_token(self, name, content):
        path = os.path.join(self.tokens, name)
        with open(path, "w") as handle:
            handle.write(content)
        os.chmod(path, 0o600)
        return path

    def set_identity(self, name):
        self.run_cmd(["git", "config", "user.name", name], cwd=self.repo_dir)

    def gh(self, *args, **env):
        environment = self.env(
            PATH=os.path.dirname(self.wrapper) + ":" + self.fake_bin + ":" + SYSTEM_PATH,
            FAKE_GH_RECORD=self.record,
        )
        environment.update(env)
        result = self.run_cmd([self.wrapper] + list(args), check=False, cwd=self.repo_dir, env=environment)
        with open(self.record) as handle:
            return result, json.load(handle)

    def assert_no_secret(self, text):
        self.assertNotIn("secret", text)

    def test_mapped_identity_injects_its_token_quietly(self):
        self.set_identity(WORK)
        result, seen = self.gh("api", "user")
        self.assertEqual(seen["GH_TOKEN"], "work-secret-token")
        self.assertEqual(result.stdout, "fake gh output\n")
        self.assertEqual(result.stderr, "")

    def test_token_file_whitespace_is_trimmed(self):
        self.set_identity(PERSONAL)
        _result, seen = self.gh("api", "user")
        self.assertEqual(seen["GH_TOKEN"], "personal-secret-token")

    def test_explicit_environment_tokens_win(self):
        self.set_identity(WORK)
        _result, seen = self.gh("api", "user", GH_TOKEN="explicit")
        self.assertEqual(seen["GH_TOKEN"], "explicit")
        _result, seen = self.gh("api", "user", GITHUB_TOKEN="explicit-github")
        self.assertIsNone(seen["GH_TOKEN"])
        self.assertEqual(seen["GITHUB_TOKEN"], "explicit-github")

    def test_identity_match_is_exact(self):
        self.set_identity(PERSONAL.upper())
        result, seen = self.gh("api", "user")
        self.assertIsNone(seen["GH_TOKEN"])
        self.assertEqual(result.stderr, "")

    def test_unmapped_or_missing_identity_uses_native_gh_auth(self):
        self.set_identity("someone-else")
        _result, seen = self.gh("auth", "status")
        self.assertIsNone(seen["GH_TOKEN"])
        self.run_cmd(["git", "config", "--unset", "user.name"], cwd=self.repo_dir)
        result, seen = self.gh("auth", "status")
        self.assertIsNone(seen["GH_TOKEN"])
        self.assertEqual(result.stderr, "")

    def test_missing_mapping_file_uses_native_gh_auth(self):
        os.remove(os.path.join(self.home, ".config/gh-wrapper/identities"))
        self.set_identity(WORK)
        result, seen = self.gh("api", "user")
        self.assertIsNone(seen["GH_TOKEN"])
        self.assertEqual(result.stderr, "")

    def test_missing_or_unreadable_token_warns_and_continues(self):
        self.set_identity(WORK)
        cases = {"missing": lambda: os.remove(os.path.join(self.tokens, "work")),
                 "empty": lambda: self.write_token("work", "\n")}
        if os.geteuid() != 0:
            cases["unreadable"] = lambda: os.chmod(self.write_token("work", "work-secret-token"), 0)
        for case, make in cases.items():
            with self.subTest(case=case):
                make()
                result, seen = self.gh("api", "user")
                self.assertEqual(result.returncode, 0)
                self.assertIsNone(seen["GH_TOKEN"])
                self.assertIn("gh-wrapper: warning: token file for \"%s\"" % WORK, result.stderr)
                self.assertIn(os.path.join(self.tokens, "work"), result.stderr)

    def test_arguments_and_exit_status_pass_through(self):
        args = ["issue", "create", "--title", "two words", "", "$HOME", "*", "quote's"]
        result, seen = self.gh(*args, FAKE_GH_EXIT="3")
        self.assertEqual(seen["args"], args)
        self.assertEqual(result.returncode, 3)

    def test_signals_pass_through(self):
        result, _seen = self.gh("run", "watch", FAKE_GH_SIGNAL="TERM")
        self.assertEqual(result.returncode, -signal.SIGTERM)

    def test_debug_explains_each_source_without_tokens(self):
        self.set_identity(WORK)
        result, _seen = self.gh("api", "user", GH_WRAPPER_DEBUG="1")
        self.assert_no_secret(result.stderr)
        self.assertIn('identity: "%s" (git user.name)' % WORK, result.stderr)
        self.assertIn("(loaded)", result.stderr)
        self.assertIn("token source: %s/work (mapped from" % self.tokens, result.stderr)
        self.assertIn("real gh: " + os.path.join(self.fake_bin, "gh"), result.stderr)

        result, _seen = self.gh("api", "user", GH_WRAPPER_DEBUG="1", GH_TOKEN="secret-explicit")
        self.assert_no_secret(result.stderr)
        self.assertIn("token source: GH_TOKEN from the environment", result.stderr)

        self.set_identity("someone-else")
        result, _seen = self.gh("api", "user", GH_WRAPPER_DEBUG="1")
        self.assertIn('no mapping for "someone-else"', result.stderr)

        os.remove(os.path.join(self.home, ".config/gh-wrapper/identities"))
        result, _seen = self.gh("api", "user", GH_WRAPPER_DEBUG="1")
        self.assertIn("(missing)", result.stderr)

    def test_example_mapping_matches_example_identities(self):
        self.copy_example(".config/gh-wrapper/identities")
        for relative in (".gitconfig", ".config/git/conf.d/identity-personal.gitconfig",
                         ".config/git/conf.d/identity-work.gitconfig"):
            self.copy_example(relative)
        self.write(".config/github-tokens/personal", "personal-secret-token\n", mode=0o600)
        self.run_cmd(["git", "config", "--unset", "user.name"], cwd=self.repo_dir, check=False)
        _result, seen = self.gh("api", "user")
        self.assertEqual(seen["GH_TOKEN"], "personal-secret-token")


@require("git")
@require("bash")
class EndToEndTest(HomeTestCase):
    """Login shell -> PATH -> gh wrapper -> Git includes -> identity -> token."""

    def test_shell_git_and_gh_work_together(self):
        self.install()
        for relative in (".gitconfig", ".config/git/conf.d/identity-personal.gitconfig",
                         ".config/git/conf.d/identity-work.gitconfig", ".config/gh-wrapper/identities"):
            self.copy_example(relative)
        self.write(".config/github-tokens/work", "work-secret-token\n", mode=0o600)
        # Login shells put ~/bin after the wrapper but ahead of Homebrew, whose real gh
        # would otherwise run on macOS.
        self.write("bin/gh", FAKE_GH, mode=0o755)
        repo = os.path.join(self.home, "work", "client")
        os.makedirs(repo)
        self.run_cmd(["git", "init", "-q", repo])
        record = os.path.join(self.tmp, "record.json")

        env = self.env(FAKE_GH_RECORD=record)
        self.run_cmd(["bash", "-l", "-c", 'cd "$HOME/work/client" && gh pr list'], env=env)

        with open(record) as handle:
            seen = json.load(handle)
        self.assertEqual(seen["args"], ["pr", "list"])
        self.assertEqual(seen["GH_TOKEN"], "work-secret-token")


if __name__ == "__main__":
    unittest.main()

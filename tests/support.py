"""Shared helpers: throwaway homes, a clean environment and the installer."""

import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
INSTALL = os.path.join(REPO, "install")
EXAMPLES = os.path.join(REPO, "examples")
SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def require(tool):
    """Skip a test when a tool is missing, except in CI, where it must exist."""
    if shutil.which(tool):
        return lambda test: test
    if os.environ.get("CI"):
        raise RuntimeError(tool + " is required in CI")
    return unittest.skip(tool + " is not installed")


class HomeTestCase(unittest.TestCase):
    """Each test gets a throwaway HOME whose path contains a space."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="dotfiles test "))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.home = os.path.join(self.tmp, "home dir")
        os.mkdir(self.home)

    def env(self, **extra):
        env = {
            "HOME": self.home,
            "PATH": SYSTEM_PATH,
            "TERM": "dumb",
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        env.update(extra)
        return env

    def run_cmd(self, args, check=True, **kwargs):
        kwargs.setdefault("env", self.env())
        kwargs.setdefault("cwd", self.home)
        result = subprocess.run(
            args, stdin=subprocess.DEVNULL, capture_output=True, text=True, **kwargs
        )
        if check and result.returncode != 0:
            self.fail("%r failed (%d):\n%s%s" % (args, result.returncode, result.stdout, result.stderr))
        return result

    def install(self, *args, check=True, installer=INSTALL):
        return self.run_cmd(["python3", installer] + list(args), check=check)

    def write(self, relative, content, mode=None):
        path = os.path.join(self.home, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write(content)
        if mode is not None:
            os.chmod(path, mode)
        return path

    def copy_example(self, relative):
        destination = os.path.join(self.home, relative)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy(os.path.join(EXAMPLES, relative), destination)

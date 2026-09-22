#!/usr/bin/env python3
"""Filesystem regressions for live-root finalization; these are not boot tests."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "overlays/omarchy-iso/builder/remove-login.py"
SPEC = importlib.util.spec_from_file_location("remove_login_builder", SCRIPT)
remove_login = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(remove_login)


class RemoveLoginFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="remove-login-regression-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "root"
        self.root.mkdir()
        self.evidence = self.base / "removed-login.json"
        self.write("usr/share/omarchy-iso/custom-build-status.json", '{"profile":"custom-no-login"}\n')
        # The finalizer inspects filesystem state, not ELF execution. This file
        # is only its required fixture marker; no test pretends to boot systemd.
        self.write("usr/lib/systemd/systemd", "systemd filesystem fixture\n")
        self.write("usr/lib/systemd/system/multi-user.target", "[Unit]\nDescription=Fixture\n")
        (self.root / "usr/lib/systemd/system/default.target").symlink_to("multi-user.target")
        self.write("etc/passwd", "root:x:0:0:root:/root:/bin/bash\ndaemon:x:2:2:daemon:/:/usr/bin/nologin\n")
        self.write("etc/shadow", "root:fixture-password-hash:1:0:99999:7:::\n")
        self.write("etc/group", "root:x:0:\ndaemon:x:2:\n")
        self.write("etc/gshadow", "root:!::\n")
        self.write("etc/subuid", "root:100000:65536\n")
        self.write("etc/subgid", "root:100000:65536\n")
        self.write("etc/nsswitch.conf", "passwd: files systemd\ngroup: files systemd\nhosts: files dns\n")

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def finalize(self):
        with contextlib.redirect_stdout(io.StringIO()):
            remove_login.finalize(self.root, self.evidence)
        return json.loads(self.evidence.read_text())

    def assert_missing(self, relative):
        path = self.root / relative
        self.assertFalse(path.exists() or path.is_symlink(), relative)

    def test_command_named_completions_and_nested_helpers_are_removed(self):
        paths = [
            "usr/share/bash-completion/completions/su",
            "usr/share/bash-completion/completions/login",
            "usr/share/bash-completion/completions/passwd",
            "usr/local/libexec/sshd",
            "opt/vendor/bin/useradd",
            "opt/vendor/lib/libnss_systemd.so.2",
            "usr/local/share/omarchy-iso-install",
        ]
        for relative in paths:
            self.write(relative, "authentication support fixture\n")
        self.write("etc/pam.d/login", "auth required pam_unix.so\n")
        self.write("usr/lib/security/pam_unix.so", "PAM module fixture\n")
        self.write("usr/lib/sysusers.d/example.conf", "u daemon 2\n")
        self.write("usr/lib/systemd/system/getty@.service", "[Service]\nExecStart=/usr/bin/agetty\n")
        self.write("usr/lib/systemd/system/example.service", "[Service]\nUser=daemon\nExecStart=/bin/true\n")
        result = self.finalize()
        for relative in paths:
            self.assert_missing(relative)
            self.assertIn(relative, result["removed_paths"])
        for name in ("passwd", "shadow", "group", "gshadow", "subuid", "subgid"):
            self.assert_missing("etc/" + name)
        self.assert_missing("etc/pam.d")
        self.assert_missing("usr/lib/security")
        self.assert_missing("usr/lib/sysusers.d")
        self.assert_missing("usr/lib/systemd/system/getty@.service")
        self.assert_missing("usr/lib/systemd/system/example.service")
        self.assertEqual(result["removed_accounts"], ["root", "daemon"])
        self.assertNotIn("fixture-password-hash", self.evidence.read_text())
        self.assertEqual(result["default_target"], "omarchy-no-login.target")
        self.assertIsNone(result["replacement_authentication"])
        self.assertFalse(result["vm_boot_tested"])
        self.assertFalse(result["pam_deny_or_service_masks_added"])
        units = self.root / "usr/lib/systemd/system"
        self.assertEqual((units / "default.target").readlink(), Path("omarchy-no-login.target"))
        target = (units / "omarchy-no-login.target").read_text()
        self.assertIn("DefaultDependencies=no", target)
        self.assertNotIn("ExecStart=", target)
        nss = (self.root / "etc/nsswitch.conf").read_text()
        for name in ("passwd", "group", "shadow", "gshadow", "initgroups"):
            self.assertIn(name + ": files\n", nss)
        self.assertNotIn("files systemd", nss)
        for tree in ("usr", "opt"):
            for path in (self.root / tree).rglob("*"):
                self.assertNotIn(path.name, remove_login.COMMANDS, str(path))

    def test_opt_provider_is_removed_even_when_no_usr_provider_exists(self):
        self.write("opt/vendor/bin/useradd", "account creator fixture\n")
        result = self.finalize()
        self.assert_missing("opt/vendor/bin/useradd")
        self.assertIn("opt/vendor/bin/useradd", result["removed_paths"])

    def test_command_symlink_is_removed_without_touching_external_target(self):
        external = self.base / "external-data"
        external.write_bytes(b"keep this exact external content\n")
        link = self.root / "opt/vendor/libexec/passwd"
        link.parent.mkdir(parents=True)
        link.symlink_to(external)
        result = self.finalize()
        self.assert_missing("opt/vendor/libexec/passwd")
        self.assertEqual(external.read_bytes(), b"keep this exact external content\n")
        self.assertIn("opt/vendor/libexec/passwd", result["removed_paths"])

    def test_shared_dependency_paths_and_unrelated_files_are_preserved(self):
        shared = self.write("usr/lib/libpam.so.0.85.1", "shared dependency fixture\n")
        alias = self.root / "usr/lib/libpam.so.0"
        alias.symlink_to("libpam.so.0.85.1")
        unrelated = self.write("usr/share/doc/retained-package/README", "unrelated data\n")
        self.finalize()
        self.assertEqual(shared.read_text(), "shared dependency fixture\n")
        self.assertTrue(alias.is_symlink())
        self.assertEqual(alias.readlink(), Path("libpam.so.0.85.1"))
        self.assertEqual(unrelated.read_text(), "unrelated data\n")


if __name__ == "__main__":
    unittest.main()

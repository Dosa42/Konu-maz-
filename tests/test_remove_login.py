#!/usr/bin/env python3
"""Filesystem and packing-order regressions; these are not boot/install tests."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "overlays/omarchy-iso/builder/remove-login.py"
AIROOTFS = SCRIPT.parent.parent / "configs/airootfs"
INITCPIO_HOOK = AIROOTFS / "usr/lib/initcpio/install/omarchy-no-login"
INITCPIO_STRIPPER = AIROOTFS / "usr/lib/omarchy-no-login/strip-initramfs.py"
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
        self.write("usr/lib/systemd/system/omarchy-installer.target", "[Unit]\nRequires=omarchy-installer.service\n")
        self.write("usr/lib/systemd/system/omarchy-installer.service", "[Service]\nExecStart=/usr/bin/omarchy-installer-session\n")
        (self.root / "usr/lib/systemd/system/default.target").symlink_to("multi-user.target")
        self.write("etc/passwd", "root:x:0:0:root:/root:/bin/bash\ndaemon:x:2:2:daemon:/:/usr/bin/nologin\n")
        self.write("etc/shadow", "root:fixture-password-hash:1:0:99999:7:::\n")
        self.write("etc/group", "root:x:0:\ndaemon:x:2:\ndisk:x:6:\ninput:x:998:\n")
        self.write("etc/gshadow", "root:!::\n")
        self.write("etc/subuid", "root:100000:65536\n")
        self.write("etc/subgid", "root:100000:65536\n")
        self.write("etc/nsswitch.conf", "passwd: files systemd\ngroup: files systemd\nhosts: files dns\n")

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def finalize(self, *, installed=False):
        with contextlib.redirect_stdout(io.StringIO()):
            remove_login.finalize(self.root, self.evidence, installed=installed)
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
            "usr/local/share/omarchy-provision-owner",
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
        self.assertEqual(result["default_target"], "omarchy-installer.target")
        self.assertEqual(result["installer"], "direct-tty1-service")
        self.assertIsNone(result["replacement_authentication"])
        self.assertFalse(result["vm_boot_tested"])
        self.assertFalse(result["pam_deny_or_service_masks_added"])
        units = self.root / "usr/lib/systemd/system"
        self.assertEqual((units / "default.target").readlink(), Path("omarchy-installer.target"))
        self.assertTrue((units / "omarchy-installer.service").is_file())
        self.assert_missing("usr/lib/systemd/system/omarchy-no-login.target")
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

    def test_installer_and_archinstall_library_survive_live_finalization(self):
        required = (
            "usr/bin/archinstall",
            "usr/bin/arch-chroot",
            "usr/bin/pacstrap",
            "usr/bin/omarchy-iso-install",
            "usr/bin/omarchy-install-dashboard",
            "usr/bin/omarchy-installer-session",
            "usr/lib/python3.14/site-packages/archinstall/lib/installer.py",
            "usr/share/omarchy-iso/orchestrator/archinstall_adapter.py",
            "usr/share/omarchy-iso/setup-form.sh",
            "usr/lib/omarchy-installer/configurator",
            "usr/lib/omarchy-installer/remove-login.py",
            "usr/lib/initcpio/install/omarchy-no-login",
            "usr/lib/omarchy-no-login/strip-initramfs.py",
            "usr/share/omarchy/install/hardware/all.sh",
        )
        for relative in required:
            self.write(relative, "required installer component\n")
        self.write("usr/share/omarchy/install/login/sddm.sh", "login setup\n")
        self.write("usr/share/omarchy/install/provisioning/setup-form.sh", "owner setup\n")
        self.write("usr/share/omarchy/install/config/lockscreen-pam.sh", "PAM setup\n")
        self.finalize()
        for relative in required:
            self.assertEqual((self.root / relative).read_text(), "required installer component\n", relative)
        for relative in ("usr/share/omarchy/install/login", "usr/share/omarchy/install/provisioning",
                         "usr/share/omarchy/install/config/lockscreen-pam.sh"):
            self.assert_missing(relative)

    def test_mount_tools_keep_execution_but_lose_setid_bits(self):
        for name in ("mount", "umount"):
            self.write("usr/bin/" + name, "required mount executable\n").chmod(0o6755)
        self.write("usr/bin/unrelated-setid-tool", "privileged helper\n").chmod(0o4755)
        result = self.finalize()
        for name in ("mount", "umount"):
            tool = self.root / "usr/bin" / name
            self.assertEqual(stat.S_IMODE(tool.stat().st_mode), 0o755)
            self.assertEqual(tool.read_text(), "required mount executable\n")
        self.assertEqual(result["cleared_privileged_bits"], ["usr/bin/mount", "usr/bin/umount"])
        self.assert_missing("usr/bin/unrelated-setid-tool")
        self.assertIn("usr/bin/unrelated-setid-tool", result["removed_privileged_files"])

    def test_udev_owner_and_group_are_numeric_before_accounts_disappear(self):
        rule = self.write("usr/lib/udev/rules.d/50-device.rules", (
            'KERNEL=="loop-control", GROUP="disk", OPTIONS+="static_node=loop-control"\n'
            'SUBSYSTEM=="input", OWNER:="daemon", GROUP = "input"\n'
            'KERNEL=="tty*", OWNER="root", GROUP="0"\n'
            'ENV{GROUP}="disk", ENV{OWNER}="daemon"\n'
            'GROUP=="disk", GROUP!="input"\n'
            'GROUP="$env{DYNAMIC_GROUP}", OWNER="%k"\n'
        ))
        result = self.finalize()
        self.assertEqual(rule.read_text(), (
            'KERNEL=="loop-control", GROUP="6", OPTIONS+="static_node=loop-control"\n'
            'SUBSYSTEM=="input", OWNER:="2", GROUP = "998"\n'
            'KERNEL=="tty*", OWNER="0", GROUP="0"\n'
            'ENV{GROUP}="disk", ENV{OWNER}="daemon"\n'
            'GROUP=="disk", GROUP!="input"\n'
            'GROUP="$env{DYNAMIC_GROUP}", OWNER="%k"\n'
        ))
        self.assertEqual(result["numeric_udev_rules"], ["usr/lib/udev/rules.d/50-device.rules"])
        self.assert_missing("etc/group")
        self.assert_missing("etc/passwd")

    def test_installed_target_keeps_home_and_nonlogin_enablement(self):
        home = self.root / "home"
        home.mkdir()
        identity = home.stat().st_ino
        self.write("usr/lib/systemd/system/storage.service", "[Service]\nExecStart=/usr/bin/true\n")
        self.write("usr/lib/systemd/system/sddm.service", "[Service]\nExecStart=/usr/bin/sddm\n")
        self.write("etc/systemd/system/numeric-service.service", "[Service]\nExecStart=/usr/bin/true\n")
        self.write("etc/systemd/system/owner-service.service", "[Service]\nUser=daemon\nExecStart=/usr/bin/true\n")
        wants = self.root / "etc/systemd/system/multi-user.target.wants"
        wants.mkdir()
        (wants / "storage.service").symlink_to("/usr/lib/systemd/system/storage.service")
        (wants / "sddm.service").symlink_to("/usr/lib/systemd/system/sddm.service")
        (self.root / "etc/systemd/system/default.target").symlink_to("/usr/lib/systemd/system/graphical.target")
        self.write("root/credentials", "obsolete root home\n")
        result = self.finalize(installed=True)
        self.assertEqual(home.stat().st_ino, identity, "preserve the actual mountpoint directory")
        self.assertTrue((wants / "storage.service").is_symlink())
        self.assertTrue((self.root / "etc/systemd/system/numeric-service.service").is_file())
        self.assert_missing("etc/systemd/system/owner-service.service")
        self.assert_missing("etc/systemd/system/multi-user.target.wants/sddm.service")
        self.assert_missing("usr/lib/systemd/system/sddm.service")
        self.assert_missing("etc/systemd/system/default.target")
        self.assert_missing("root")
        self.assertEqual((self.root / "usr/lib/systemd/system/default.target").readlink(), Path("multi-user.target"))
        self.assertEqual(result["default_target"], "multi-user.target")
        self.assertEqual(result["installer"], "disk-target")
        for name in remove_login.DATABASES:
            self.assert_missing("etc/" + name)


class InitcpioPackingOrderTests(unittest.TestCase):
    def test_hook_strips_late_files_before_image_builder(self):
        # Exercise the real shell hook and Python stripper on temporary files.
        # Only BusyBox's applet listing and the final packer are test doubles;
        # this verifies packing order, not a boot or a real initramfs archive.
        with tempfile.TemporaryDirectory(prefix="initcpio-packing-regression-") as directory:
            root = Path(directory) / "image"
            (root / "usr/lib").mkdir(parents=True)
            (root / "etc").mkdir()
            (root / "init").write_text(
                '#!/usr/bin/ash\nparse_cmdline </proc/cmdline\n'
                '# honor the old behavior of break=y as a synonym for break=premount\n'
                'break="$(getarg break)"\n'
                'if [ "${break}" = "y" ] || [ "${break}" = "premount" ]; then\n'
                '    launch_interactive_shell\nfi\n'
                'if [ "${break}" = "postmount" ]; then\n'
                '    launch_interactive_shell\nfi\n'
                '/usr/bin/switch_root /sysroot "$init" "$@"\n'
                'launch_interactive_shell --exec\n'
            )
            (root / "init_functions").write_text(
                'launch_interactive_shell() {\n    sh -i\n    exec sh -i\n}\n'
            )
            harness = r'''
die() { printf '%s\n' "$*" >&2; exit 1; }
function /usr/lib/initcpio/busybox() { printf '%s\n' sh ash mount halt; }
function /usr/bin/python() {
    [[ $1 == /usr/lib/omarchy-no-login/strip-initramfs.py ]]
    "$TEST_PYTHON" "$TEST_STRIPPER" "$2"
}
build_image() {
    [[ $1 == "$TEST_OUTPUT" ]]
    [[ ! -e "$BUILDROOT/etc/passwd" ]]
    [[ ! -e "$BUILDROOT/etc/pam.d" ]]
    [[ ! -e "$BUILDROOT/usr/bin/login" ]]
    [[ -f "$BUILDROOT/etc/hardware-firmware.conf" ]]
    printf '%s\n' packed-after-removal >"$1"
}
_hooks=(base udev omarchy-no-login)
_optgenimg=$TEST_OUTPUT
source "$TEST_HOOK"
build
# mkinitcpio adds FILES/BINARIES and --include payloads after build hooks.
mkdir -p "$BUILDROOT/etc/pam.d" "$BUILDROOT/usr/bin"
printf '%s\n' 'root:x:0:0::/:/bin/sh' >"$BUILDROOT/etc/passwd"
printf '%s\n' 'auth required pam_unix.so' >"$BUILDROOT/etc/pam.d/login"
printf '%s\n' 'late login executable fixture' >"$BUILDROOT/usr/bin/login"
printf '%s\n' 'hardware configuration retained' >"$BUILDROOT/etc/hardware-firmware.conf"
[[ -e "$BUILDROOT/etc/passwd" ]]
build_image "$TEST_OUTPUT"
'''
            output = Path(directory) / "packing-order.txt"
            env = dict(os.environ, BUILDROOT=str(root), TEST_PYTHON=sys.executable,
                       TEST_STRIPPER=str(INITCPIO_STRIPPER), TEST_HOOK=str(INITCPIO_HOOK),
                       TEST_OUTPUT=str(output))
            result = subprocess.run(["bash", "-eu", "-c", harness], env=env, text=True,
                                    capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(output.read_text(), "packed-after-removal\n")
            self.assertEqual((root / "etc/hardware-firmware.conf").read_text(), "hardware configuration retained\n")
            self.assertNotIn("launch_interactive_shell", (root / "init").read_text())
            self.assertIn("/usr/bin/switch_root /sysroot /sbin/init", (root / "init").read_text())


if __name__ == "__main__":
    unittest.main()

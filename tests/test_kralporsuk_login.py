#!/usr/bin/env python3
"""Real libcrypt verification and fail-closed login protocol regressions."""

import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest


LOGIN = Path(__file__).resolve().parents[1] / "overlays/omarchy-iso/configs/airootfs/usr/lib/kralporsuk-login"
sys.path.insert(0, str(LOGIN))
import auth
import supervisor

# OpenSSL SHA-512-crypt reference, generated independently of the verifier.
REFERENCE_HASH = "$6$KralTestSalt$UF.un8C/vZcxeGWvIFmx6GDDf7Y0lGn7wCrOY7Xl2CKDPLs/pLEkTiyMKmruqObkR./ApKxGnARcpnqdsuUeN/"


class KralporsukAuthenticationTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid() != 0:
            self.skipTest("Authentication files intentionally require ownership by UID 0.")
        temporary = tempfile.TemporaryDirectory(prefix="kralporsuk-auth-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "etc").mkdir()
        self.passwd = self.root / "etc/passwd"
        self.shadow = self.root / "etc/shadow"
        self.passwd.write_text("kralporsuk:x:0:0:kralporsuk:/root:/bin/bash\n")
        self.shadow.write_text(f"kralporsuk:{REFERENCE_HASH}:20000:0:99999:7:::\n")
        self.shadow.chmod(0o600)

    def test_actual_libcrypt_matches_reference_only_for_correct_password(self):
        auth.check_backend(self.root)
        self.assertTrue(auth.verify_password("0000", self.root))
        self.assertFalse(auth.verify_password("0001", self.root))
        self.assertFalse(auth.verify_password("", self.root))
        self.assertFalse(auth.verify_password("0000\0anything", self.root))

    def test_extra_account_and_root_alias_are_rejected(self):
        original = self.passwd.read_text()
        for extra in ("root:x:0:0:root:/root:/bin/bash\n", "daemon:x:1:1:daemon:/:/bin/false\n"):
            with self.subTest(extra=extra.split(":")[0]):
                self.passwd.write_text(original + extra)
                with self.assertRaises(auth.AuthenticationError):
                    auth.verify_password("0000", self.root)

    def test_non_root_uid_and_duplicate_shadow_are_rejected(self):
        self.passwd.write_text("kralporsuk:x:1000:0:kralporsuk:/root:/bin/bash\n")
        with self.assertRaises(auth.AuthenticationError):
            auth.verify_password("0000", self.root)
        self.passwd.write_text("kralporsuk:x:0:0:kralporsuk:/root:/bin/bash\n")
        self.shadow.write_text(self.shadow.read_text() * 2)
        with self.assertRaises(auth.AuthenticationError):
            auth.verify_password("0000", self.root)

    def test_locked_missing_null_and_unsupported_hashes_never_authenticate(self):
        for value in ("!", "", "*", "$not-a-real-hash$"):
            with self.subTest(value=value):
                self.shadow.write_text(f"kralporsuk:{value}:20000:0:99999:7:::\n")
                with self.assertRaises(auth.AuthenticationError):
                    auth.verify_password("0000", self.root)
        self.shadow.unlink()
        with self.assertRaises(auth.AuthenticationError):
            auth.verify_password("0000", self.root)

    def test_readable_shadow_and_linked_records_are_rejected(self):
        self.shadow.chmod(0o644)
        with self.assertRaises(auth.AuthenticationError):
            auth.verify_password("0000", self.root)
        self.shadow.chmod(0o600)
        real = self.root / "etc/other-shadow"
        self.shadow.rename(real)
        self.shadow.symlink_to(real)
        with self.assertRaises(auth.AuthenticationError):
            auth.verify_password("0000", self.root)

    def test_private_socket_password_request_uses_parent_real_verification(self):
        # Exercise framing and actual hashing over a real kernel socketpair.
        # These are isolated credential fixtures, never the host's /etc/shadow.
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        with parent, child:
            for password, expected in (("0001", "rejected"), ("0000", "authenticated")):
                child.send(json.dumps({"action": "password", "password": password}).encode())
                request = supervisor.decode_request(parent.recv(8192))
                response = supervisor.authenticate_request(request, root=self.root)
                parent.send(json.dumps(response).encode())
                self.assertEqual(json.loads(child.recv(8192))["result"], expected)

    def test_configuration_error_prevents_correct_password_from_authenticating(self):
        result = supervisor.authenticate_request(
            {"action": "password", "password": "0000"},
            root=self.root, configuration_error="Ongeldige configuratie.",
        )
        self.assertEqual(result["result"], "error")

    def test_only_fixed_modes_are_accepted(self):
        path = self.root / "etc/kralporsuk-login.json"
        for mode in ("live", "installed"):
            path.write_text(json.dumps({"mode": mode}))
            self.assertEqual(supervisor.load_mode(path), mode)
        for invalid in ({"mode": "shell"}, {"mode": "live", "command": "/bin/bash"}, [], {"mode": []}):
            path.write_text(json.dumps(invalid))
            with self.assertRaises(auth.AuthenticationError):
                supervisor.load_mode(path)


class LoginAuthorizationProtocolTests(unittest.TestCase):
    def test_window_close_exit_zero_and_greeter_crash_do_not_authorize(self):
        self.assertFalse(supervisor.session_authorized(False, 0))
        self.assertFalse(supervisor.session_authorized(False, 1))
        self.assertFalse(supervisor.session_authorized(True, 1))
        self.assertFalse(supervisor.session_authorized(True, -15))
        self.assertTrue(supervisor.session_authorized(True, 0))

    def test_protocol_cannot_supply_a_success_marker_or_command(self):
        for packet in (
            b'{"action":"authenticated"}',
            b'{"action":"password","password":"0000","command":"/bin/bash"}',
            b'{"action":"password","password":null}',
            b'{"action":"password","password":0}',
            b'{"action":"reboot","command":"/bin/bash"}',
            b'{"action":[]}',
            b"null", b"[]", b"broken", b"x" * 8193,
        ):
            with self.subTest(packet=packet[:60]):
                with self.assertRaises(auth.AuthenticationError):
                    supervisor.decode_request(packet)


if __name__ == "__main__":
    unittest.main()

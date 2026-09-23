"""Exercise the lock's actual JSON boundary and actual shared libcrypt verifier."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


AUTH = Path(__file__).resolve().parents[1] / 'overlays/omarchy-iso/configs/airootfs/usr/lib/kralporsuk-login'
sys.path.insert(0, str(AUTH))
SPEC = importlib.util.spec_from_file_location('kralporsuk_lock_verifier', AUTH / 'verify-lock.py')
LOCK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCK)


class LockVerifierProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='kralporsuk-lock-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'etc').mkdir()
        hashed = subprocess.run(['openssl', 'passwd', '-6', '-stdin'], input='0000\n',
                                text=True, capture_output=True, check=True).stdout.strip()
        (self.root / 'etc/passwd').write_text('kralporsuk:x:0:0:kralporsuk:/root:/bin/bash\n')
        shadow = self.root / 'etc/shadow'
        shadow.write_text(f'kralporsuk:{hashed}:19000:0:99999:7:::\n')
        shadow.chmod(0o600)

    def check(self, request):
        return LOCK.verify_request(io.BytesIO(request), root=self.root)

    def test_same_password_accepts_without_echoing_secret(self):
        self.assertEqual(self.check(b'{"password":"0000"}\n'), {'authenticated': True})
        self.assertEqual(self.check(b'{"password":"wrong"}\n'), {'authenticated': False})

    def test_malformed_oversized_and_alias_requests_cannot_unlock(self):
        for request in [b'not json\n', b'{"password":"0000"}', b'{}\n',
                        b'{"password":"0000","user":"root"}\n',
                        b'{"password":null}\n', b'{"password":42}\n',
                        json.dumps({'password': 'x' * 9000}).encode() + b'\n']:
            with self.subTest(request_length=len(request)):
                self.assertFalse(self.check(request)['authenticated'])

    def test_changed_account_or_insecure_shadow_cannot_unlock(self):
        (self.root / 'etc/shadow').chmod(0o644)
        self.assertEqual(self.check(b'{"password":"0000"}\n')['error'], 'authentication-unavailable')
        (self.root / 'etc/shadow').chmod(0o600)
        (self.root / 'etc/passwd').write_text('root:x:0:0:root:/root:/bin/bash\n')
        self.assertFalse(self.check(b'{"password":"0000"}\n')['authenticated'])


if __name__ == '__main__':
    unittest.main()

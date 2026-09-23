#!/usr/bin/env python3
"""One bounded stdin request, checked by the same verifier as the boot page.

No password may be supplied through argv or an environment variable. The JSON
response never contains the submitted value or the account's password hash.
"""
import json
from pathlib import Path
import sys

# Python -I excludes the script directory. This fixed, root-owned installation
# path is the only added import location; no caller-controlled search path.
sys.path.insert(0, '/usr/lib/kralporsuk-login')
from auth import AuthenticationError, verify_password


def verify_request(stream, root=Path('/')):
    raw = stream.readline(8193)
    if len(raw) > 8192 or not raw.endswith(b'\n'):
        return {'authenticated': False, 'error': 'invalid-request'}
    try:
        request = json.loads(raw)
    except (UnicodeError, ValueError):
        return {'authenticated': False, 'error': 'invalid-request'}
    if not isinstance(request, dict) or set(request) != {'password'}:
        return {'authenticated': False, 'error': 'invalid-request'}
    try:
        accepted = verify_password(request['password'], root=root)
    except (AuthenticationError, UnicodeError):
        return {'authenticated': False, 'error': 'authentication-unavailable'}
    return {'authenticated': accepted}


if __name__ == '__main__':
    result = verify_request(sys.stdin.buffer)
    sys.stdout.write(json.dumps(result, separators=(',', ':')) + '\n')
    raise SystemExit(0 if result['authenticated'] else 1)

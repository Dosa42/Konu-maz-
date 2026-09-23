"""The single local account's password verifier; no PAM or fallback backend."""

import ctypes
import ctypes.util
import hmac
import os
from pathlib import Path
import stat
import threading


ACCOUNT = "kralporsuk"
_CRYPT_LOCK = threading.Lock()


class AuthenticationError(Exception):
    """A missing or invalid authentication dependency, safe to show in the UI."""


def read_owned_file(path: Path, *, secret=False, limit=65536) -> str:
    """Reject links, non-files and writable configuration before reading it."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            forbidden = 0o077 if secret else 0o022
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & forbidden:
                raise AuthenticationError(f"Ongeldige eigenaar of rechten: {path.name}.")
            raw = handle.read(limit + 1)
        if len(raw) > limit:
            raise AuthenticationError(f"Bestand te groot: {path.name}.")
        return raw.decode("utf-8", errors="strict")
    except AuthenticationError:
        raise
    except (OSError, UnicodeError) as error:
        raise AuthenticationError(f"Kan {path.name} niet veilig lezen.") from error


def account_hash(root: Path = Path("/")) -> str:
    passwd = read_owned_file(root / "etc/passwd").splitlines()
    shadow = read_owned_file(root / "etc/shadow", secret=True).splitlines()
    # Empty lines, duplicate records, another account or an alias are invalid.
    if len(passwd) != 1 or len(shadow) != 1:
        raise AuthenticationError("Er moet precies één accountrecord voor kralporsuk bestaan.")
    user = passwd[0].split(":")
    secret = shadow[0].split(":")
    if len(user) != 7 or user[:4] != [ACCOUNT, "x", "0", "0"]:
        raise AuthenticationError("Het enige account moet kralporsuk met UID 0 en GID 0 zijn.")
    if len(secret) != 9 or secret[0] != ACCOUNT:
        raise AuthenticationError("Het wachtwoordrecord voor kralporsuk is ongeldig.")
    hashed = secret[1]
    if not hashed.startswith("$") or "\x00" in hashed or len(hashed) > 1024:
        raise AuthenticationError("Geen bruikbare wachtwoordhash voor kralporsuk.")
    return hashed


def crypt_backend():
    name = ctypes.util.find_library("crypt")
    if not name:
        raise AuthenticationError("De libcrypt-wachtwoordverificatie ontbreekt.")
    try:
        library = ctypes.CDLL(name, use_errno=True)
        function = library.crypt
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        function.restype = ctypes.c_char_p
        # Keep the loaded library alive alongside its C function.
        function._library = library
        return function
    except (OSError, AttributeError) as error:
        raise AuthenticationError("De libcrypt-wachtwoordverificatie kan niet starten.") from error


def check_backend(root: Path = Path("/")) -> None:
    account_hash(root)
    crypt_backend()


def verify_password(password: str, root: Path = Path("/")) -> bool:
    if not isinstance(password, str) or not password or "\x00" in password:
        return False
    encoded = password.encode("utf-8")
    if len(encoded) > 1024:
        return False
    expected = account_hash(root).encode("ascii")
    function = crypt_backend()
    # crypt() uses a static result buffer; copy it while holding the lock.
    with _CRYPT_LOCK:
        result = function(encoded, expected)
        if result is None or result.startswith(b"*"):
            raise AuthenticationError("Libcrypt accepteert deze wachtwoordhash niet.")
        actual = bytes(result)
    return hmac.compare_digest(actual, expected)

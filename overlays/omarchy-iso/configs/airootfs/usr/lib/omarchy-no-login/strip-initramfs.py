#!/usr/bin/env python3
"""Build-only finalization of the supported mkinitcpio BusyBox/udev image.

This removes shell entry points, not the interpreter required by /init. It
does not claim to remove Linux's UID 0 or authenticate a modified boot medium.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import stat
import sys


class UnsupportedImage(RuntimeError):
    pass


def rooted(root: Path, relative: str) -> Path:
    parts = Path(relative).parts
    if not parts or any(part in ("..", "/") for part in parts):
        raise UnsupportedImage(f"invalid image-relative path: {relative}")
    path = root
    # A final symlink can be unlinked, but never traverse a symlinked parent.
    for part in parts[:-1]:
        path /= part
        if path.is_symlink():
            raise UnsupportedImage(f"symlinked parent in image: {path}")
    return root.joinpath(*parts)


def read_regular(root: Path, relative: str) -> tuple[Path, str]:
    path = rooted(root, relative)
    if path.is_symlink() or not path.is_file():
        raise UnsupportedImage(f"expected regular script: {relative}")
    return path, path.read_text(encoding="utf-8")


def replace_one(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise UnsupportedImage(f"unsupported mkinitcpio structure: {label}")
    return text.replace(old, new, 1)


def remove_if_block(text: str, first_line: str, label: str) -> str:
    # These supported upstream blocks contain no nested if/fi. Restrict matching
    # to a single top-level block and explicitly reject an unexpected nesting.
    expression = re.compile(r"^" + re.escape(first_line) + r"\n(?P<body>.*?)^fi\n", re.M | re.S)
    matches = list(expression.finditer(text))
    if len(matches) != 1 or re.search(r"^\s*(?:if\b|fi\b)", matches[0]["body"], re.M):
        raise UnsupportedImage(f"unsupported mkinitcpio block: {label}")
    match = matches[0]
    return text[: match.start()] + text[match.end() :]


def remove(root: Path, relative: str) -> bool:
    path = rooted(root, relative)
    if path.is_symlink():
        path.unlink()
        return True
    if path.is_dir():
        # shutil.rmtree does not follow directory symlinks. On Linux its fd-based
        # implementation also prevents symlink races while walking the tree.
        if not shutil.rmtree.avoids_symlink_attacks:
            raise UnsupportedImage("safe directory removal is unavailable")
        shutil.rmtree(path)
        return True
    if path.exists():
        path.unlink()
        return True
    return False


def finalize(root: Path) -> None:
    init_path, init = read_regular(root, "init")
    functions_path, functions = read_regular(root, "init_functions")
    if not init.startswith("#!/usr/bin/ash\n"):
        raise UnsupportedImage("only the mkinitcpio BusyBox init is supported")
    function_re = re.compile(r"^launch_interactive_shell\(\) \{\n.*?^\}\n", re.M | re.S)
    found = list(function_re.finditer(functions))
    if len(found) != 1 or len(re.findall(r"\bsh -i\b", found[0].group())) != 2:
        raise UnsupportedImage("unsupported emergency-shell function")
    halt_function = """no_login_halt() {
    printf '%s\\n' 'Boot stopped: this image has no login or recovery shell.' >/dev/console
    halt -f
    # If the firmware cannot halt, remain inert instead of resuming boot.
    while :; do sleep 3600; done
}
"""
    functions = functions[: found[0].start()] + halt_function + functions[found[0].end() :]
    init = replace_one(
        init,
        "parse_cmdline </proc/cmdline\n",
        "parse_cmdline </proc/cmdline\n# This image has one fixed boot continuation.\ninit=/sbin/init\n",
        "kernel command-line parsing",
    )
    init = replace_one(
        init,
        '# honor the old behavior of break=y as a synonym for break=premount\nbreak="$(getarg break)"\n',
        "",
        "break argument",
    )
    init = remove_if_block(
        init, 'if [ "${break}" = "y" ] || [ "${break}" = "premount" ]; then', "premount shell"
    )
    init = remove_if_block(init, 'if [ "${break}" = "postmount" ]; then', "postmount shell")
    init = replace_one(
        init,
        '/usr/bin/switch_root /sysroot "$init" "$@"',
        '/usr/bin/switch_root /sysroot /sbin/init',
        "fixed switch_root target and no init argument forwarding",
    )
    init = init.replace("    # We fall back into a shell, but the shell has now PID 1\n", "")
    init = init.replace("    # This way, manual recovery is still possible.\n", "")
    init = init.replace('    echo "Bailing out, you are on your own. Good luck."\n', "")
    functions = functions.replace('        echo "You are now being dropped into an emergency shell."\n', "")

    updates: dict[Path, str] = {init_path: init, functions_path: functions}
    hooks = rooted(root, "hooks")
    if hooks.is_symlink():
        raise UnsupportedImage("symlinked hooks directory")
    if hooks.is_dir():
        for hook in sorted(hooks.iterdir()):
            path, content = read_regular(root, f"hooks/{hook.name}")
            updates[path] = content
    for path, content in updates.items():
        content = content.replace("launch_interactive_shell --exec", "no_login_halt")
        content = content.replace("launch_interactive_shell", "no_login_halt")
        # A future hook introducing its own interactive shell is unsupported.
        if re.search(r"\b(?:sh|ash|bash|dash|zsh)\s+-[^\s]*i\b", content):
            raise UnsupportedImage(f"interactive shell remains in {path.relative_to(root)}")
        updates[path] = content

    account_paths = [
        f"etc/{name}{suffix}"
        for name in ("passwd", "shadow", "group", "gshadow", "subuid", "subgid")
        for suffix in ("", "-", ".bak", ".old", ".pacnew", ".pacsave", ".pacorig")
    ]
    account_paths += [
        "etc/.pwd.lock", "etc/pam.conf", "etc/pam.d", "etc/security",
        "usr/lib/pam.d", "usr/lib/security", "etc/sysusers.d", "usr/lib/sysusers.d",
        "etc/userdb", "run/userdb", "usr/lib/userdb", "etc/default/useradd",
        "usr/share/factory/etc/passwd", "usr/share/factory/etc/group",
        "usr/share/factory/etc/shadow", "usr/share/factory/etc/gshadow",
    ]
    binaries = (
        "login", "getty", "agetty", "sulogin", "su", "runuser", "sudo", "doas",
        "sshd", "dropbear", "telnetd", "rlogind", "rshd", "passwd", "chpasswd",
        "useradd", "userdel", "usermod", "adduser", "deluser", "groupadd", "groupdel",
        "groupmod", "addgroup", "delgroup", "newusers", "newgrp", "chsh", "chfn",
        "systemd-sysusers", "systemd-firstboot", "systemd-homed", "systemd-userdbd",
        "systemd-userdb-load-credentials", "systemd-logind",
    )
    account_paths += [f"usr/bin/{name}" for name in binaries]
    account_paths += [f"usr/lib/systemd/{name}" for name in binaries if name.startswith("systemd-")]
    for lib in rooted(root, "usr/lib").glob("libnss_systemd.so*"):
        account_paths.append(str(lib.relative_to(root)))
    # Validate every path before making any modifications.
    for relative in account_paths:
        rooted(root, relative)
    nss = rooted(root, "etc/nsswitch.conf")
    if nss.is_symlink() or (nss.exists() and not nss.is_file()):
        raise UnsupportedImage("unsafe nsswitch.conf")

    for path, content in updates.items():
        mode = stat.S_IMODE(path.stat().st_mode)
        path.write_text(content, encoding="utf-8")
        path.chmod(mode)
    removed = [relative for relative in account_paths if remove(root, relative)]
    nss.write_text("passwd: files\ngroup: files\nshadow: files\ngshadow: files\nhosts: files dns\n", encoding="utf-8")
    nss.chmod(0o644)
    print(f"omarchy-no-login: removed {len(removed)} account/login paths; boot shell entry points removed")


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise UnsupportedImage("usage: strip-initramfs.py BUILDROOT")
        supplied = Path(sys.argv[1])
        if not supplied.is_absolute() or supplied.is_symlink():
            raise UnsupportedImage("BUILDROOT must be an absolute, non-symlink directory")
        root = supplied.resolve(strict=True)
        if root == Path("/") or not root.is_dir():
            raise UnsupportedImage("refusing invalid BUILDROOT")
        finalize(root)
        return 0
    except (UnsupportedImage, OSError, UnicodeError) as error:
        print(f"omarchy-no-login: ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

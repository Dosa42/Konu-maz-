#!/usr/bin/env python3
"""Seed the installed, sole UID 0 desktop before account/login removal.

Run on the live ISO with the mounted installation target as the sole argument.
This prepares actual Omarchy settings; it never creates an account or logs in.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys


def seed(target):
    root = Path(target).absolute()
    if root == Path('/') or root.is_symlink() or root != root.resolve():
        raise ValueError('Expected a separate real installation target')
    for relative in ('etc/skel', 'root', 'usr/share/omarchy', 'usr/lib/systemd/user'):
        path = root / relative
        if path.is_symlink():
            raise ValueError(f'Refusing symlinked profile path: {relative}')
    skel = root / 'etc/skel'
    home = root / 'root'
    if not (skel / '.config/hypr/hyprland.lua').is_file():
        raise FileNotFoundError('Omarchy settings package did not provide the Hyprland profile')
    if home.exists() and any(path.is_symlink() for path in home.rglob('*')):
        raise ValueError('Refusing to seed through an existing home symlink')
    shutil.copytree(skel, home, dirs_exist_ok=True, symlinks=True)
    home.chmod(0o700)

    config = home / '.config/hypr/hyprland.lua'
    source = config.read_text()
    anchor = 'require("default.hypr.omarchy")'
    if source.count(anchor) != 1:
        raise ValueError('Unexpected pinned Omarchy Hyprland bootstrap')
    source = source.replace(anchor, '''-- Session startup is owned by the authenticated UID 0 manager.
package.loaded["default.hypr.autostart"] = true
require("default.hypr.omarchy")
hl.on("hyprland.start", function()
  hl.exec_cmd("/usr/local/bin/kralporsuk-session-ready")
end)''', 1)
    config.write_text(source)

    # The direct compositor needs no UWSM compositor unit. Its original app
    # daemon, slices, D-Bus and PipeWire units still run under systemd --user.
    dropin = root / 'etc/systemd/user/graphical-session.target.d/10-kralporsuk.conf'
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text('[Unit]\nRefuseManualStart=no\nStopWhenUnneeded=no\n')

    # Upstream PipeWire's user units explicitly skip UID 0. This profile's
    # only authenticated desktop is UID 0, including its actual audio server.
    for unit in ('pipewire.service', 'pipewire.socket',
                 'pipewire-pulse.service', 'pipewire-pulse.socket'):
        if not (root / 'usr/lib/systemd/user' / unit).is_file():
            raise FileNotFoundError(f'Missing desktop audio unit: {unit}')
        audio_dropin = root / 'etc/systemd/user' / (unit + '.d') / '10-kralporsuk.conf'
        audio_dropin.parent.mkdir(parents=True, exist_ok=True)
        audio_dropin.write_text('[Unit]\nConditionUser=\nConditionUser=0\n')

    omarchy = root / 'usr/share/omarchy'
    logout = '''#!/bin/bash
# End this session and return to its only authentication page.
set -euo pipefail
exec /usr/bin/hyprctl dispatch exit
'''
    for name in ('omarchy-system-logout',):
        path = omarchy / 'bin' / name
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f'Missing pinned Omarchy session command: {name}')
        path.write_text(logout)
        path.chmod(0o755)
    lock_dir = omarchy / 'shell/plugins/lock'
    if not (lock_dir / 'Service.qml').is_file():
        raise FileNotFoundError('Missing pinned Omarchy lock service')
    replacement = root / 'usr/share/kralporsuk-session'
    shutil.copyfile(replacement / 'LockService.qml', lock_dir / 'Service.qml')
    shutil.copyfile(replacement / 'LockView.qml', lock_dir / 'LockView.qml')

    for name in ('Downloads', 'Documents', 'Pictures', 'Videos', 'Music', 'Projects'):
        (home / name).mkdir(exist_ok=True)
    (home / '.config/omarchy/themes').mkdir(parents=True, exist_ok=True)
    # Use the actual installed theme generator, not hand-written stand-ins.
    subprocess.run([
        'arch-chroot', str(root), '/usr/bin/env',
        'HOME=/root', 'USER=kralporsuk', 'LOGNAME=kralporsuk',
        'PATH=/usr/share/omarchy/bin:/usr/local/bin:/usr/bin',
        'OMARCHY_PATH=/usr/share/omarchy', 'OMARCHY_THEME_HEADLESS=1',
        'OMARCHY_THEME_SKIP_BACKGROUND=0',
        '/usr/bin/omarchy-theme-set', 'Tokyo Night',
    ], check=True)
    state = home / '.local/state/omarchy'
    state.mkdir(parents=True, exist_ok=True)
    (state / 'kralporsuk-session.json').write_text(json.dumps({
        'account': 'kralporsuk', 'uid': 0,
        'session': 'direct-hyprland-with-systemd-user',
        'authentication': 'kralporsuk-login',
        'lock_behavior': 'retain-session-with-same-account-password-verifier',
        'boot_tested': False,
    }, indent=2) + '\n')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: seed-profile.py INSTALLATION_TARGET')
    seed(sys.argv[1])

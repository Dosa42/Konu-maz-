#!/usr/bin/env python3
"""Remove authentication/accounts after package and boot-image construction.

Used by the ISO builder and by the installer before completing its disk target.
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat


DATABASES = ('passwd', 'shadow', 'group', 'gshadow', 'subuid', 'subgid')
AUTH_TREES = ('usr', 'opt')
COMMANDS = set('''
agetty getty login remote-login loginctl su runuser sudo sudoedit visudo doas
cloud-init cloud-init-per systemd-userdb-load-credentials
adduser deluser addgroup delgroup telnetd in.telnetd rlogind in.rlogind rshd in.rshd
sshd sshd-session sshd-auth sftp-server ssh-keysign dropbear dropbearmulti
passwd chpasswd newusers useradd usermod userdel groupadd groupmod groupdel
chage chfn chsh gpasswd newgrp sg newuidmap newgidmap vipw vigr pwconv
pwunconv grpconv grpunconv faillock unix_chkpwd unix_update pam_timestamp_check
pam_namespace_helper pamtester fprintd fprintd-enroll fprintd-verify
pkexec pkcheck pkttyagent polkit-agent-helper-1 polkitd accounts-daemon
sddm sddm-helper sddm-greeter sddm-greeter-qt6 gdm gdm-session-worker lightdm
greetd tuigreet ly xdm xlogin xinit startx systemd-sysusers systemd-firstboot
systemd-logind systemd-homed systemd-userdbd systemd-userwork systemd-user-runtime-dir
systemd-homework systemd-home-fallback-shell systemd-user-sessions
systemd-sulogin-shell sulogin systemd-stdio-bridge systemd-machined machinectl
homectl userdbctl systemd-getty-generator systemd-debug-generator
systemd-run0 run0
omarchy-provision-owner omarchy-provision-first-run omarchy-system-factory-reset
omarchy-provision-user omarchy-system-factory-reset-finish omarchy-apply-lock
omarchy-setup-security-fingerprint omarchy-setup-security-fido2
omarchy-setup-security-sshd omarchy-sudo-passwordless
'''.split())
UNIT_RE = re.compile(
    r'^(?:getty|serial-getty|console-getty|container-getty|console-shell|autovt|'
    r'rescue|emergency|debug-shell|sshd?|dropbear|sddm|gdm|lightdm|greetd|'
    r'xdm|xlogin|display-manager|fprintd|pcscd|polkit|accounts-daemon|'
    r'systemd-(?:sysusers|firstboot|logind|homed|homework|home-fallback-shell|userdbd|userdb-load-credentials|user-sessions|userwork|user-runtime-dir|'
    r'machined)|user@|cloud-|cloud-init|omarchy-(?:first|setup|provision))'
)
REMOVE_TREES = (
    'etc/pam.conf', 'etc/pam.d', 'usr/lib/pam.d', 'usr/lib/security', 'etc/security',
    'etc/ssh', 'usr/lib/ssh', 'etc/sudoers', 'etc/sudoers.d', 'usr/lib/sudo',
    'etc/polkit-1', 'usr/share/polkit-1', 'usr/lib/polkit-1',
    'etc/sddm.conf', 'etc/sddm.conf.d', 'usr/lib/sddm', 'usr/share/sddm',
    'etc/gdm', 'etc/lightdm', 'etc/greetd', 'etc/xdg/autostart',
    'etc/sysusers.d', 'usr/lib/sysusers.d', 'usr/local/lib/sysusers.d',
    'etc/userdb', 'usr/lib/userdb', 'var/lib/systemd/home', 'var/lib/AccountsService',
    'etc/cloud', 'usr/lib/cloud-init', 'var/lib/cloud',
    'etc/skel', 'etc/default/useradd', 'etc/login.defs',
    'root', 'home', 'etc/.pwd.lock', 'run/systemd/system', 'run/systemd/user', 'run/sysusers.d', 'run/userdb', 'etc/systemd/system', 'etc/systemd/user',
    'usr/lib/systemd/user', 'usr/share/omarchy/install/login',
    'usr/share/omarchy/install/provisioning', 'etc/omarchy/provisioning',
    'usr/share/omarchy/install/config/lockscreen-pam.sh',
    'usr/share/omarchy/install/config/increase-lockout-limit.sh',
    'usr/share/omarchy/install/user/first-run/setup-fingerprint.hook',
    'usr/lib/syslinux', 'usr/share/edk2-shell',
)


class Root:
    def __init__(self, path):
        raw = Path(path).absolute()
        if raw.is_symlink() or raw != raw.resolve() or raw == Path('/'):
            raise ValueError('Expected a separate real build root, without symlink components')
        self.path = raw
        marker = self.child('usr/share/omarchy-iso/custom-build-status.json')
        if marker.is_symlink() or not marker.is_file():
            raise ValueError('Expected a regular profile marker')
        if json.loads(marker.read_text()).get('profile') != 'custom-no-login':
            raise ValueError('Build root does not carry the custom-no-login profile marker')
        if not self.child('usr/lib/systemd/systemd').is_file():
            raise ValueError('Expected the real pacstrap root containing systemd')
        self.removed = []

    def child(self, relative):
        parts = PurePosixPath(relative).parts
        if not parts or relative.startswith('/') or '..' in parts:
            raise ValueError(f'Unsafe root-relative path: {relative}')
        current = self.path
        for part in parts[:-1]:
            current /= part
            if current.is_symlink():
                raise ValueError(f'Symlink parent is not traversed: {relative}')
        return self.path.joinpath(*parts)

    def remove(self, relative):
        path = self.child(relative)
        if not path.is_symlink() and not path.exists():
            return
        self.removed.append(relative)
        if path.is_symlink() or not path.is_dir():
            path.unlink()
        else:
            shutil.rmtree(path)

    def files(self, relative):
        base = self.child(relative)
        if base.is_symlink():
            # Arch aliases /usr/sbin to /usr/bin; the real tree is scanned once.
            resolved = base.resolve()
            if relative in ('usr/sbin', 'usr/local/sbin') and resolved == self.path / relative.replace('sbin', 'bin'):
                return
            raise ValueError(f'Refusing symlink scan root: {relative}')
        if not base.is_dir():
            return
        for directory, dirs, files in os.walk(base, followlinks=False):
            for name in list(dirs):
                path = Path(directory) / name
                if path.is_symlink():
                    dirs.remove(name)
                    yield path
            for name in files:
                yield Path(directory) / name

    def relative(self, path):
        return path.relative_to(self.path).as_posix()


def authentication_paths(root):
    # Packages also install command-named completions and helpers outside bin/lib.
    # Removal and verification must cover the same complete trees.
    for directory in AUTH_TREES:
        for entry in root.files(directory) or ():
            if (entry.name in COMMANDS or entry.name.startswith('libnss_systemd.so')
                    or entry.name.startswith('libnss_compat.so')):
                yield entry


def numeric_udev_ownership(root):
    """Preserve hardware rules after removing their named account databases."""
    identities = {}
    for kind, database in (('OWNER', 'passwd'), ('GROUP', 'group')):
        path = root.child('etc/' + database)
        if path.is_symlink():
            raise ValueError(f'Symlinked identity database: {database}')
        identities[kind] = {'root': '0'}
        if path.is_file():
            for line in path.read_text().splitlines():
                fields = line.split(':')
                if len(fields) > 2 and fields[2].isdigit():
                    identities[kind][fields[0]] = fields[2]
    changed = []
    assignment = re.compile(r'\b(OWNER|GROUP)(\s*(?::=|=)\s*)"([^"\n]+)"')
    for directory in ('etc/udev/rules.d', 'usr/lib/udev/rules.d'):
        for entry in root.files(directory) or ():
            if entry.is_symlink() or not entry.name.endswith('.rules'):
                continue
            original = entry.read_text()
            updated = assignment.sub(
                lambda match: match[1] + match[2] + '"' +
                identities[match[1]].get(match[3], match[3]) + '"', original)
            if updated != original:
                entry.write_text(updated)
                changed.append(root.relative(entry))
    return sorted(changed)


def finalize(path, evidence, *, installed=False):
    root = Root(path)
    # Preserve account names only as external build evidence, never password hashes.
    old_passwd = root.child('etc/passwd')
    if old_passwd.is_symlink():
        raise ValueError('Symlinked passwd evidence is not read')
    accounts = [line.split(':', 1)[0] for line in old_passwd.read_text().splitlines()] if old_passwd.is_file() else []
    numeric_rules = numeric_udev_ownership(root)
    for directory in ('etc', 'usr/lib', 'var/lib/extrausers', 'usr/share/factory/etc'):
        base = root.child(directory)
        if not base.is_dir():
            continue
        for entry in list(base.iterdir()):
            if any(entry.name == n or entry.name.startswith(n + suffix)
                   for n in DATABASES for suffix in ('-', '.', '~')):
                root.remove(root.relative(entry))
    for relative in REMOVE_TREES:
        # The installed /home may be a mounted Btrfs subvolume. No user was
        # created there; keep the mountpoint and non-login service enablement.
        if installed and relative in ('home', 'etc/systemd/system'):
            continue
        root.remove(relative)
    # Eliminate providers, tools and command-named support files in every install tree.
    for entry in list(authentication_paths(root)):
        root.remove(root.relative(entry))
    # Delete service definitions rather than replacing them with /dev/null masks.
    units = root.child('usr/lib/systemd/system')
    deleted_units = set()
    unit_trees = ('usr/lib/systemd/system', 'etc/systemd/system')
    for entry in [entry for tree in unit_trees for entry in root.files(tree) or ()]:
        if entry.is_symlink():
            continue
        text = entry.read_text(errors='replace')
        has_account = re.search(r'^\s*(?:User|Group|SocketUser|SocketGroup|SupplementaryGroups|DynamicUser)\s*=\s*\S+', text, re.M)
        if UNIT_RE.match(entry.name) or has_account:
            deleted_units.add(entry.name)
            root.remove(root.relative(entry))
    for tree in unit_trees:
        for directory, dirs, _ in os.walk(root.child(tree), followlinks=False):
            for name in list(dirs):
                if name.endswith('.d') and (UNIT_RE.match(name) or name[:-2] in deleted_units):
                    root.remove(root.relative(Path(directory) / name))
                    dirs.remove(name)
    # Vendor wants/aliases must not keep references to deleted units.
    for entry in [entry for tree in unit_trees for entry in root.files(tree) or ()]:
        if entry.is_symlink() and (UNIT_RE.match(entry.name)
                or Path(os.readlink(entry)).name in deleted_units):
            root.remove(root.relative(entry))
    # No generators or user sessions may synthesize gettys, debug shells or users.
    for directory in ('usr/lib/systemd/system-generators', 'etc/systemd/system-generators'):
        for entry in list(root.files(directory) or ()):
            if entry.name in COMMANDS:
                root.remove(root.relative(entry))
    for directory in ('usr/share/dbus-1/system-services', 'usr/share/dbus-1/system.d',
                      'etc/dbus-1/system.d', 'usr/share/dbus-1/services'):
        for entry in list(root.files(directory) or ()):
            if not entry.is_symlink():
                text = entry.read_text(errors='replace')
                if re.search(r'(?:login1|home1|userdb1|machine1|Accounts|PolicyKit1|fprint|sddm)', text):
                    root.remove(root.relative(entry))
    # Package hooks must not recreate local identities/provision the system at runtime.
    for directory in ('etc/pacman.d/hooks', 'usr/share/libalpm/hooks'):
        for entry in list(root.files(directory) or ()):
            if not entry.is_symlink() and re.search(
                    r'(?:sysusers|firstboot|useradd|groupadd|chpasswd|omarchy-root-shell)',
                    entry.read_text(errors='replace')):
                root.remove(root.relative(entry))
    # No NSS fallback to synthesized, network or compatibility account sources.
    nss = root.child('etc/nsswitch.conf')
    if nss.is_symlink() or (nss.exists() and not nss.is_file()):
        raise ValueError('Unsafe nsswitch.conf')
    text = nss.read_text() if nss.exists() else ''
    text = re.sub(r'^\s*(?:passwd|group|shadow|gshadow|initgroups):.*\n?', '', text, flags=re.M)
    nss.write_text(text.rstrip() + '\npasswd: files\ngroup: files\nshadow: files\ngshadow: files\ninitgroups: files\n')
    # The live image starts the installer directly; the installed system keeps
    # normal multi-user startup with the login/account providers removed.
    root.remove('usr/lib/systemd/system/omarchy-no-login.target')
    default_target = 'multi-user.target' if installed else 'omarchy-installer.target'
    if not (units / default_target).is_file():
        raise RuntimeError(f'Required boot target missing: {default_target}')
    root.remove('etc/systemd/system/default.target')
    default = units / 'default.target'
    root.remove(root.relative(default))
    default.symlink_to(default_target)
    # Remove SUID/SGID entry points remaining outside named provider packages.
    privileged = []
    cleared_privileges = []
    for directory in ('usr', 'opt'):
        for entry in list(root.files(directory) or ()):
            if not entry.is_symlink() and entry.is_file():
                mode = entry.stat().st_mode
                if mode & (stat.S_ISUID | stat.S_ISGID):
                    if root.relative(entry) in ('usr/bin/mount', 'usr/bin/umount'):
                        # Disk installation needs these tools. PID1 starts the
                        # installer as numeric UID 0, so set-id bits are unneeded.
                        entry.chmod(stat.S_IMODE(mode) & ~(stat.S_ISUID | stat.S_ISGID))
                        cleared_privileges.append(root.relative(entry))
                        continue
                    privileged.append(root.relative(entry))
                    root.remove(root.relative(entry))
    for name in DATABASES:
        if root.child('etc/' + name).exists():
            raise RuntimeError(f'Account database survived: {name}')
    if root.child('etc/pam.d').exists() or root.child('usr/lib/security').exists():
        raise RuntimeError('PAM service configuration or modules survived')
    survivors = sorted(root.relative(entry) for entry in authentication_paths(root))
    if survivors:
        raise RuntimeError('Authentication/account paths survived: ' + ', '.join(survivors))
    result = {
        'schema': 1, 'profile': 'custom-no-login', 'removed_accounts': accounts,
        'removed_paths': sorted(set(root.removed)), 'removed_privileged_files': privileged,
        'default_target': default_target,
        'cleared_privileged_bits': sorted(cleared_privileges),
        'numeric_udev_rules': numeric_rules,
        'installer': 'disk-target' if installed else 'direct-tty1-service',
        'replacement_authentication': None, 'pam_deny_or_service_masks_added': False,
        'scope': 'Installed target' if installed else 'Live installer filesystem; offline packages are sanitized after target installation.',
        'kernel_uid_zero_removed': False, 'vm_boot_tested': False,
    }
    Path(evidence).write_text(json.dumps(result, indent=2) + '\n')
    print(f'Removed {len(accounts)} local accounts and {len(root.removed)} paths; evidence: {evidence}')


def wire(source, destination):
    text = Path(source).read_text()
    anchor = '    _run_once _cleanup_pacstrap_dir\n    _run_once _prepare_airootfs_image\n'
    if text.count(anchor) != 1:
        raise ValueError('Pinned mkarchiso finalization boundary changed')
    replacement = (
        '    _run_once _cleanup_pacstrap_dir\n'
        '    python3 /builder/remove-login.py finalize "${pacstrap_dir}" /out/removed-login.json\n'
        '    _run_once _prepare_airootfs_image\n'
    )
    text = text.replace(anchor, replacement)
    # GRUB removes CLI/editor/rescue entry availability from the generated EFI image.
    # No superuser, password prompt or replacement authentication is configured.
    if text.count('--disable-shim-lock') != 2:
        raise ValueError('Pinned GRUB image construction changed')
    text = text.replace('--disable-shim-lock', '--disable-cli --disable-shim-lock')
    # Copy only the modules required by the one Syslinux menu, not PXE/memdisk
    # loaders, chainloaders, hardware-detection and interactive COM32 tools.
    lines = text.splitlines(keepends=True)
    removed_boot_copies = 0
    output = []
    for line in lines:
        if '${pacstrap_dir}/usr/lib/syslinux/bios/' in line and ('*.c32' in line or '/lpxelinux.0' in line or '/memdisk' in line):
            removed_boot_copies += 1
            if '*.c32' in line:
                output.append('    install -m 0644 -- "${pacstrap_dir}/usr/lib/syslinux/bios/"lib*.c32 "${pacstrap_dir}/usr/lib/syslinux/bios/ldlinux.c32" "${pacstrap_dir}/usr/lib/syslinux/bios/vesamenu.c32" "${isofs_dir}/boot/syslinux/"\n')
        else:
            output.append(line)
    if removed_boot_copies != 3:
        raise ValueError('Pinned Syslinux payload construction changed')
    text = ''.join(output)
    Path(destination).write_text(text)
    Path(destination).chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    for name in ('wire', 'finalize', 'finalize-installed'):
        command = sub.add_parser(name)
        command.add_argument('source')
        command.add_argument('output')
    args = parser.parse_args()
    if args.mode == 'wire':
        wire(args.source, args.output)
    else:
        finalize(args.source, args.output, installed=args.mode == 'finalize-installed')


if __name__ == '__main__':
    main()

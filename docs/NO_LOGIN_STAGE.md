# Current profile: one graphical login and the preserved installer

This file retains its historical name. The current authorized profile replaces
an intermediate no-account stage with exactly one root-privileged account:
`kralporsuk`, UID 0 / GID 0, temporary password `0000`. The password is represented
by a hash in the source configuration and the resulting `/etc/shadow`; no separate
`root` alias or additional system-account records are retained.

## Login and session flow

Both the live image and installed system default to `kralporsuk-login.target`.
A GTK4 login page runs under Cage with seatd. It verifies the sole account's
shadow hash through libxcrypt, without PAM, an existing display manager, getty,
console login or autologin.

The page can read USB information before authentication: actual sysfs descriptors,
vendor/product IDs, strings and device arrival/removal. This is device inspection,
not USB cryptographic authentication. No token protocol, signature verification
or successful authentication is fabricated.

After password authentication, the live image opens the preserved disk installer.
The installed system opens the real Hyprland desktop using a native UID 0 systemd
user manager. Logging out returns to the graphical login page.

## Installation

The installer retains keyboard, hostname, timezone, disk selection and disk-layout
confirmation. Optional LUKS encryption uses an explicitly entered disk passphrase,
independent of the graphical login password. The installer does not create another
user, root alias, first-owner setup, SSH login or autologin configuration.

The real package, filesystem, hardware and Limine/UKI setup remains in place.
Packages may temporarily create accounts during installation; the finalizer removes
those identities and old login facilities before writing the sole `kralporsuk`
account and group. The completed target uses the same graphical login policy.

The dashboard retains progress and the successful-install reboot prompt.
Cancellation or failure offers fixed retry/reboot/power-off controls. Retrying
opens the wizard and disk confirmation again instead of silently reusing an old
confirmed layout. It does not offer a shell.

## Retained removal policy

Previous local account databases, backups and factory copies are removed before
the final account is written. Previous PAM configuration/modules, console login,
SSH server, display-manager/authentication providers, account-creation hooks and
their service entry points remain removed. Required graphical session services
are configured for the sole numeric UID/GID rather than additional identities.

The final initramfs hook still strips login/account providers and recovery-shell
branches from both the live and installed initramfs. Boot failure paths halt
instead of opening a shell; continuation is fixed to `/sbin/init`. Explicitly
selected LUKS disk unlocking remains available.

The live medium retains one normal BIOS Syslinux entry and one UEFI GRUB entry.
Alternative boot entries, UEFI shell and memory-test routes remain removed. GRUB
EFI images use `--disable-cli` without adding a bootloader account or password.

## Limits and evidence

- `kralporsuk` is the root-privileged account: UID 0 semantics remain fully active.
  Account naming does not reduce that privilege.
- Applications that refuse UID 0 are not forced to run by silently disabling
  their sandbox. Full desktop application compatibility is not guaranteed.
- Required shared-library ABIs remain, including `libpam.so` where linked by
  systemd. The new password verifier does not use PAM.
- Offline package archives retain upstream payloads. Final account/login policy
  is applied after package installation, not asserted for every archive.
- The boot medium is not signed or made immutable by this work; protection against
  replacing it is separate. USB inspection does not implement USB signer login.

Build reports describe final account/login cleanup and the configured default
target. A successful build, source check or ISO catalogue inspection does not
validate graphical boot, USB hardware, disk installation or a desktop session.
`vm_boot_tested` and `usb_signer_tested` remain false until actual tests are recorded.
Earlier successful builds with a different login policy do not validate this one.

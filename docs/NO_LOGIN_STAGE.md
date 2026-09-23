# Intermediate stage: installer without accounts or login

The requested order is removal of existing accounts/login first, cryptographic
login later. The live installer is retained and starts directly on tty1 through
systemd. Removing the installer and replacing normal startup with an empty target
in the earlier revision was an error; this revision restores installation.
No temporary login password, signer stub, denial-only PAM module, hidden account
or service mask is introduced.

## Live boot and installation

- The live default is `omarchy-installer.target`. It starts basic system services,
  device discovery and `omarchy-installer.service` with a controlling tty1.
  There is no getty, login program, autologin or interactive root shell.
- The wizard retains keyboard, hostname, timezone, disk selection and disk-layout
  confirmation. It does not ask for a username, local-account password or root
  credentials. Optional encryption asks for a separate LUKS disk passphrase;
  that passphrase unlocks storage and is not installed as a login credential.
- The real installer uses the bundled packages, configures supported hardware,
  filesystems and Limine/UKI boot files. It does not stage first-owner provisioning,
  SSH account access or desktop autologin.
- The dashboard retains installation progress and the successful-install reboot
  prompt. Cancellation or failure returns to fixed retry, reboot and power-off
  controls. Retry opens the wizard and confirmation again; it never silently
  reuses a previously confirmed disk layout. No shell is offered on failure.
- Before installation completes, the target finalizer removes package-created
  accounts and login facilities. The installed default is `multi-user.target`,
  with no desktop, getty or login session. It does not restart the live installer.

## Removal applied to the image and installation

The finalizer removes local passwd/shadow/group/gshadow/subuid/subgid databases,
backups and factory copies, including root and system-account records. It removes
login/account-management commands, PAM configuration and modules, SSH server and
display-manager entry points, authentication providers, account-creation hooks,
user homes and their systemd units/drop-ins. Account lookup uses only the now-absent
local databases; NSS account synthesis and userdb entry points are removed.

Device-rule ownership names are converted to their original numeric IDs before
account deletion so device discovery does not depend on those records. Remaining
SUID/SGID executables are removed; required `mount` and `umount` remain with their
privilege bits cleared. The installer already runs under numeric UID 0.

The final `omarchy-no-login` mkinitcpio hook strips account/login providers and
interactive recovery-shell branches from the generated live and target initramfs.
Boot failure paths halt instead of opening a shell, and continuation is fixed to
`/sbin/init`. Explicitly selected LUKS disk unlocking remains available.

The live image has one normal BIOS Syslinux entry and one UEFI GRUB entry. Other
profile entries, UEFI shell and memory-test routes are removed. GRUB EFI images
use `--disable-cli` to remove editing, command-line and rescue interfaces without
adding a bootloader user or password.

## Boundaries and evidence

- Linux still uses numeric credentials, including UID 0 for PID 1 and the direct
  installer. Deleting account records does not remove kernel privilege semantics.
- Required shared-library ABIs, including `libpam.so` where linked by systemd,
  remain. PAM configurations, authentication modules and login callers are removed;
  this is not a claim that every related instruction disappears from every library.
- Shell interpreters remain for fixed boot/build/installer scripts. There is no
  supplied interactive shell entry point. The medium is not signed or made
  immutable by this work; protection against replacing its contents is separate.
- Offline package archives retain upstream payloads. The removal policy is applied
  after those packages are installed, rather than asserted for the archives.
- The manual build workflow does not install an OS. Running the live installer
  writes the disk layout explicitly selected and confirmed in its wizard.

The ISO build writes `removed-login.json` next to the ISO, and the build manifest
hashes it. The completed installation records its own removal evidence at
`/usr/share/omarchy-iso/installed-no-login-evidence.json`. Reports contain removed
account names, paths, cleared privilege bits and the selected default target, not
password hashes. Unexpected source structure or surviving account/login providers
stop the relevant build or installation phase.

Patch application, syntax checks and ISO catalogue inspection are not a boot or
installation test. `vm_boot_tested` and `usb_signer_tested` remain false unless real
tests are performed and recorded. The earlier successful inert-image build does
not validate this restored installer.

# Intermediate stage: remove existing accounts and login

The owner's requested order is removal first, cryptographic authentication later.
This profile deliberately has no usable login or installer. No temporary password,
signer stub, PAM denial module, replacement login, hidden account or service mask
is introduced.

## What the build changes

1. Keep package compilation and boot-image generation in the build environment.
   Build-container identities are not accounts in the resulting ISO.
2. Run the `omarchy-no-login` mkinitcpio install hook last. It removes account
   records, PAM service configuration/modules and login tools from the generated
   initramfs; physically removes pre/post-mount shell branches and replaces boot
   failure shell calls with a halt. It fixes the continuation to `/sbin/init`.
   The BusyBox binary is checked for compiled-in login/account applets.
3. Generate one BIOS Syslinux entry and one UEFI GRUB entry. Remove the other
   profile entries and inherited alternatives. Omit UEFI shell and memory-test
   packages from the live root. Build both GRUB EFI images with `--disable-cli`,
   which removes access to editing, command-line and rescue interfaces without
   configuring an authentication prompt or a bootloader user.
4. Invoke `builder/remove-login.py` from the **pinned** mkarchiso source, after
   package operations and copying boot files, immediately before rootfs packing.
   This deletes all local passwd/shadow/group/gshadow/subuid/subgid records and
   their backups/factory copies, including root and system-account records.
5. Delete the supplied login/account-management commands, PAM configurations and
   modules, SSH server entry points, display-manager/authentication providers,
   privilege-entry executables, account-creation hooks, home directories and
   installer/provisioning entry points. Remove their systemd units and drop-ins.
   Command-name removal covers all of `/usr` and `/opt`, including shell
   completions and helpers in nonstandard locations. Account-dependent units
   are also removed. Clear existing local enablement.
6. Restrict account lookup to the now-absent local files; remove NSS systemd
   account synthesis and userdb service entry points. Delete SUID/SGID files
   remaining in `/usr` and `/opt`.
7. Set `omarchy-no-login.target` as the default target, without normal service,
   desktop, getty or installer dependencies. Remove the initramfs build helpers
   from the final rootfs. No boot-time root helper is installed.

The full normal Omarchy installer/desktop does **not** operate in this intermediate
stage. It must be integrated with the owner's future authentication before it is
enabled again. Simply removing a username does not make its former services work;
this stage does not start them with substitute identities.

## Exact boundaries

- Linux still uses numeric credentials, including UID 0 for PID 1. Deleting root's
  account record does not remove the kernel's UID 0 semantics or systemd's internal
  name for that UID. No local root account/password or root login is retained.
- General shared-library ABIs needed to load installed programs, including
  `libpam.so` where linked by systemd, are retained. PAM service configurations,
  authentication modules and login entry points are removed. This is not a claim
  that every authentication-related machine instruction vanished from every library.
- The shell interpreter remains for noninteractive ArchISO boot scripts. Provided
  interactive entry points are removed. The boot medium is not signed or made
  immutable by this change; replacing its bootloader/initramfs remains outside
  this stage. No claim of protection against modified media is made.
- Offline package archives remain inert build inputs. They contain upstream
  package payloads and are **not** an installed system with this removal applied.
  The ISO's executable installer is removed; nothing automatically installs those
  packages or recreates their accounts at boot.
- The normal manual workflow remains manual. This change does not flash a device,
  overwrite an installed OS, enroll a key, or add the later cryptographic login.

## Evidence and verification

Every real ISO build writes `removed-login.json` next to the ISO. It records the
actual account names removed, removed paths and privilege-entry files. It contains
no password hashes. The build manifest requires and hashes that report. Unexpected
mkarchiso/mkinitcpio structure or failure to remove requested paths stops the build;
the build does not silently fall back to the original authentication configuration.
Removal and the final provider check scan the same trees with the same predicate;
any surviving provider paths are listed explicitly in the build error.

Source preparation, patch application and syntax checks do not demonstrate a
successful boot. `vm_boot_tested` and `usb_signer_tested` remain false unless a real
boot/authentication test is performed and recorded. The older successful build
35571598298 predates this removal stage.

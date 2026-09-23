# Omarchy custom ISO build

Private build repository for a real x86_64 Omarchy development ISO, with pinned upstream sources, ordered patches, local package recipes, and a manual GitHub Actions workflow.

**Build:** Actions → **Build private Omarchy custom ISO** → **Run workflow**.

Read [OMARCHY.md](OMARCHY.md) for the build commands, dependency tools, artifact outputs and source-editing workflow.

Current stage: the live ISO starts the disk installer directly on tty1 through `omarchy-installer.target`, without a login or local account. The installer retains disk selection, keyboard, hostname, timezone and optional LUKS encryption. Existing login facilities and all local account records, including root and system accounts, are removed from both the live image and the completed disk installation. The installed system uses `multi-user.target` with no desktop or login session. Cryptographic login comes later; boot and installation have not been verified by a VM test.

See [the removal stage](docs/NO_LOGIN_STAGE.md) for exact scope and build evidence. The [USB signer integration](docs/USB_SIGNER_INTEGRATION.md) is a later step.

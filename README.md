# Omarchy custom ISO build

Private build repository for a real x86_64 Omarchy development ISO, with pinned upstream sources, ordered patches, local package recipes, and a manual GitHub Actions workflow.

**Build:** Actions → **Build private Omarchy custom ISO** → **Run workflow**.

Read [OMARCHY.md](OMARCHY.md) for the build commands, dependency tools, artifact outputs and source-editing workflow.

Current stage: remove existing login facilities and all local account records, including root and system accounts. The image boots to `omarchy-no-login.target`; it provides no login, desktop session or interactive installer. Cryptographic authentication is deliberately not added yet.

See [the removal stage](docs/NO_LOGIN_STAGE.md) for exact scope and build evidence. The [USB signer integration](docs/USB_SIGNER_INTEGRATION.md) is a later step.

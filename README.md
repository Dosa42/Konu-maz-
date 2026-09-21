# Omarchy custom ISO build

Private build repository for a real x86_64 Omarchy installation ISO, with pinned upstream sources, ordered patches, local package recipes, and a manual GitHub Actions workflow.

**Build:** Actions → **Build private Omarchy custom ISO** → **Run workflow**.

Read [OMARCHY.md](OMARCHY.md) for the build commands, dependency tools, artifact outputs and source-editing workflow.

Current status: the ISO build infrastructure is implemented. USB-signer-only authentication still requires integration with the real device protocol and PAM adapter; the development image retains upstream authentication. See [USB signer integration](docs/USB_SIGNER_INTEGRATION.md) and the [exact source-file investigation](docs/Omarchy_USB_signer_exacte_bronbestanden.md).

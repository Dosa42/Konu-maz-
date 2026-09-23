# Omarchy custom ISO build

Private build repository for a real x86_64 Omarchy development ISO, with pinned upstream sources, ordered patches, local package recipes, and a manual GitHub Actions workflow.

**Build:** Actions → **Build private Omarchy custom ISO** → **Run workflow**.

Read [OMARCHY.md](OMARCHY.md) for the build commands, dependency tools, artifact outputs and source-editing workflow.

Current profile: one graphical login for `kralporsuk` (UID 0 / GID 0), with the explicitly selected temporary password `0000`. Both the live ISO and installed system use `kralporsuk-login.target`. After authentication, the live image opens the preserved installer; the installed system opens Hyprland. USB device information is readable before login, but USB cryptographic authentication is not implemented. No extra root alias, system accounts or autologin are retained. Boot, installation and desktop operation still require real testing.

See [the current login profile](docs/NO_LOGIN_STAGE.md) for exact scope and validation limits. The [USB signer integration](docs/USB_SIGNER_INTEGRATION.md) is a later step.

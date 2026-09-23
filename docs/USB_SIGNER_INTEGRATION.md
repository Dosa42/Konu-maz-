# USB reading and signer integration status

The current profile has one GTK4 graphical password login for `kralporsuk`
(UID 0 / GID 0), with the explicitly selected temporary password `0000`. The sole
shadow hash is checked through libxcrypt, without PAM or another login provider.
Both live and installed systems start at this login page; successful authentication
opens the installer or installed Hyprland desktop, respectively.

Before login, the page reads actual Linux sysfs USB descriptors, vendor/product
IDs, strings and hotplug changes. Seeing a USB device does not verify a signature
or prove possession of a signing key. USB cryptographic authentication is not
implemented, and no device protocol or successful signer response is invented.

The later goal is integration with the owner's ML-DSA-65/87 USB signer. Previously
inspected artifacts contain UAGL cryptographic source, AArch64 assembly/objects/
static libraries and worker code. The examined worker handles secret-key payloads
through stdin/stdout; that does not establish a USB token key-handle protocol.
No private-key material or crypto archive has been copied into this repository.

Remaining integration decisions are:

- The actual USB firmware protocol and host transport interface.
- The verifier ABI and host architecture support for both ML-DSA parameter sets.
- Device/key enrollment and the authentication entry point that will replace the
  temporary password pathway.
- Corresponding login, session, installer, reset and update policy changes.
- Separate protected key release if the signer must also unlock preboot LUKS.

Real package recipes belong in `overlays/omarchy-pkgs/pkgbuilds/`, with package
names in `overlays/omarchy-iso/builder/custom-local.packages` and source patches in
`patches/series.json`. The builder can include those packages without fabricating
a signer implementation.

Optional LUKS disk encryption is independent of the temporary graphical login.
It does not turn USB device reading into authentication. See [the current profile](NO_LOGIN_STAGE.md).
Source checks and ISO creation do not demonstrate working USB hardware, graphical
boot, installation or desktop operation; hardware and signer tests remain pending.

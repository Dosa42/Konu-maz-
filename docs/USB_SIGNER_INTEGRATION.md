# USB signer integration status

The requested final policy is local authentication using only the owner's ML-DSA-65/87 USB signer, with password, fingerprint, independent FIDO and autologin alternatives removed from the intended login/unlock paths. The build environment in this repository is ready to carry those source changes; the authentication implementation itself is not supplied by the upstream ISO builder.

The previously inspected artifacts contain real UAGL cryptographic source, AArch64 assembly/objects/static libraries and worker code. The examined worker protocol uses stdin/stdout and handles secret-key payloads; it is not evidence of an existing USB token key-handle protocol. This does not establish that other user-owned builds are absent. No private-key material or crypto archive has been copied into this repository.

The integration still requires identification of:

- The actual USB firmware/device protocol and host transport interface.
- The selected verifier ABI and host architecture strategy for both ML-DSA parameter sets.
- An actual PAM entry point using that transport/verifier and locally managed account/key registration.
- The corresponding Omarchy SDDM/Quickshell, installer, first-boot, reset and update patches listed in the source investigation.
- Separate protected key release if preboot LUKS unlock is also to require the signer.

Place the real package recipes in `overlays/omarchy-pkgs/pkgbuilds/`, list their names in `overlays/omarchy-iso/builder/custom-local.packages`, and record existing-source edits in `patches/series.json`. The builder will compile and include them rather than substituting mirror packages of the same names.

The current ISO metadata says `authentication: upstream-unmodified`. Update this only with the real authentication implementation and its actual verification results. Successful source preparation, compilation or ISO catalogue inspection does not demonstrate USB authentication on hardware.

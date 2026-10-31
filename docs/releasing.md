# Releasing

Run both test suites and `scripts/build_mac_app.sh`. Release configuration is the
default; `BUILD_CONFIGURATION=debug` opts out. Package the app with
`ditto -c -k --sequesterRsrc --keepParent dist/StoicImporter.app output.zip`.
Verify with `codesign --verify --deep --strict` and publish SHA-256 checksums.
Label architecture, signing and preview status explicitly.

Current builds use ad-hoc signing (`codesign --sign -`), without Developer ID or
notarization. Shortcut signing is separate. Do not include backups, receipts,
requests, local logs or development screenshots in Git history or release assets.
Only synthetic test data belongs in the public repository.

For smoother distribution, sign with a Developer ID Application certificate,
enable hardened runtime with reviewed entitlements, submit to Apple's notary
service, staple the ticket and verify the downloaded archive with Gatekeeper.
Keep private signing keys and notary credentials outside the repo and logs.
See [Developer ID](https://developer.apple.com/developer-id/) and
[notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

Journal bridge installation on other devices remains unverified. Never run
Journal creation actions automatically in CI.

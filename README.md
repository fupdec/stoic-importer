# Stoic Importer

A local macOS app for moving your Stoic journal to Apple Journal.
[Русский](README.ru.md) · [Downloads](https://github.com/fupdec/stoic-importer/releases)

Open your original Stoic ZIP, review text and photos, then transfer selected
entries or queue all eligible entries. Preserves original timestamps, supports
multiple photos, and keeps local receipts to block automatic resends.
The source archive stays unchanged. No AI, analytics, or hosted diary processing.

## Install

**Early preview for Apple silicon.** The maintainer reports working bulk import
with photos on their Mac; compatibility on other users' devices is unverified.
Writing requires Apple Journal and a compatible Shortcuts action (macOS 26+;
development checks used macOS 27). Archive browsing targets macOS 14+.

1. Download the app ZIP and `StoicMacWriterV3.shortcut` from
   [Releases](https://github.com/fupdec/stoic-importer/releases).
2. Extract the ZIP and move `StoicImporter.app` to Applications.
3. Open it. This preview is **ad-hoc signed, without Developer ID or Apple
   notarization**. If macOS blocks the first launch and you trust the download,
   use **System Settings → Privacy & Security → Open Anyway**, then confirm Open.
   [Apple's instructions](https://support.apple.com/en-gb/102445).
4. Install the shortcut as **StoicMacWriterV3** and select that name in the app.
   **Some Macs reject this Journal shortcut as unsupported.** Installation via
   iPhone and iCloud Shortcuts sync has been used in development, but this release
   is not verified on other devices. If installation fails, stop before importing.
5. Open a Stoic ZIP. Transfer one reviewed entry first and check actual text,
   date and every photo in Journal before starting the queue.

[Installation and limitations](docs/installation.md).

## Limits

- A successful shortcut return does not independently prove Journal persistence.
  Check Journal after an interrupted transfer before resetting a receipt.
- Existing/manual Journal entries are not discovered or updated. Reimporting can
  create duplicates. Deleting a Journal entry does not remove its app receipt.
- Location import is experimental source work and **is not enabled in this release**.
- Never upload personal backups, previews or app data to public issues.
- Independent project; not affiliated with Stoic or Apple.

## Build

Use Xcode 26+ with its macOS SDK, Swift 6, and Python 3. No Intel binary is supplied;
build on your target architecture. The release configuration is the default.

```sh
./scripts/test.sh
python3 -m unittest discover -s Tests/ShortcutTests
./scripts/build_mac_app.sh
open dist/StoicImporter.app
```

The build uses an ad-hoc signature and does not notarize the app.
[Releasing](docs/releasing.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md).
MIT licensed.

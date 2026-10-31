# Installation and limitations

## First launch on macOS

The release app uses an ad-hoc code signature, without Developer ID or an Apple
notarization ticket. Signing the separate `.shortcut` file does not notarize the app.

After downloading and moving the app to Applications, try opening it once.
If Gatekeeper blocks it as an unidentified developer/unverified app and you trust
this download, use System Settings → Privacy & Security → Open Anyway, then Open.
Follow [Apple's current instructions](https://support.apple.com/en-gb/102445).
A managed Mac can restrict exceptions. Do not globally disable Gatekeeper.
A malware or damaged-file warning needs investigation, not this procedure.

You can also build the public source using Xcode 26+ and Swift 6. Local builds use
an ad-hoc signature too; this is not Apple verification.

## Journal bridge

Install the release's shortcut as `StoicMacWriterV3`. New app installations default
to that name; existing users should check their saved shortcut setting.
Journal import requires macOS 26+ and a compatible Journal action.

Some Macs refuse generated Journal shortcuts with “features not supported on this
device.” This is separate from Gatekeeper. An iPhone-installed/authored shortcut
synced through iCloud has worked in development; new users' devices remain
unverified. Stop before import if installation fails. Report OS versions and error
text, without diary data.

Transfer one reviewed entry and verify its text, displayed date and all photos.
Queue import is sequential. Pause/Stop cannot roll back a Journal write. Check
ambiguous attempts in Journal before resetting their receipts and retrying.

## Privacy and limits

ZIP parsing and conversion run locally. The source ZIP is unchanged. Application
Support stores transfer history and receipts. Temporary prepared requests contain
plaintext and photos during transfer. Journal/Shortcuts may use your Apple/iCloud
services; the project has no hosted diary processing or telemetry.

Existing/manual entries are not automatically discovered or edited. Reimporting
can duplicate entries. Deleting a Journal entry does not clear its app receipt.
Location transfer is not enabled in this preview.

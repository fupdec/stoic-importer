# Journal bridge

Install `StoicMacWriterV3.shortcut` from GitHub Releases as **StoicMacWriterV3**.
See [installation](../docs/installation.md) for known compatibility limits.
The signed file is a release asset, not a tracked source file.

`StoicMacWriterV3.plist` is generated source. The builder is
`scripts/build_mac_writer_shortcut.py`; it also writes an unsigned binary into
the system temporary directory. Apple's `shortcuts sign` signs the shortcut,
not the app.

`HistoricalDateProbe.plist` is a synthetic template used by builders and tests.
Running it creates a Journal entry; it is not an installation step. Other builders
are development tools, including experimental location support.

Journal action adapted from jeffd/DayOneToJournal, commit
`29246b9f03712ccf512216c32c2d356b30931b57` (MIT; see UPSTREAM-LICENSE).

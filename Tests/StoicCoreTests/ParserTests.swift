import Foundation
import Testing
import ZIPFoundation
@testable import StoicCore

struct ParserTests {
    func fixture() throws -> Data {
        try Data(contentsOf: Bundle.module.url(forResource: "entries", withExtension: "json", subdirectory: "Fixtures")!)
    }
    func withZIP(_ files: [(String, Data)], operation: (URL) throws -> Void) throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let url = folder.appendingPathComponent("synthetic.zip")
        do {
            let archive = try Archive(url: url, accessMode: .create)
            for (name, data) in files {
                try archive.addEntry(with: name, type: .file, uncompressedSize: Int64(data.count), compressionMethod: .deflate) { offset, count in
                    data.subdata(in: Int(offset)..<min(Int(offset) + count, data.count))
                }
            }
        }
        try operation(url)
    }
    @Test func readsNestedZIPAndAnswers() throws {
        try withZIP([("backup/entries.json", fixture()), ("photos/example.jpg", Data([1,2,3]))]) { url in
            let backup = try StoicBackupReader().read(url)
            #expect(backup.entries.map(\.id) == ["synthetic-1", "synthetic-2"])
            #expect(backup.entries[1].text.contains("## What helped?\n\nA walk."))
            #expect(backup.entries[1].originalTimestamp == "2024-03-31T03:15:00+03:00")
            #expect(backup.attachmentPaths == ["photos/example.jpg"])
            #expect(backup.entries[0].date < backup.entries[1].date)
        }
    }
    @Test func missingAttachmentAppearsInArchiveReview() throws {
        let source = Data(#"{"entries":[{"id":"missing-photo","date":"2024-01-01T00:00:00Z","text":"Keep this text","attachments":["photos/missing.jpg"]}]}"#.utf8)
        try withZIP([("entries.json", source)]) { url in
            let entry = try #require(StoicBackupReader().read(url).entries.first)
            #expect(entry.missingPhotoPaths == ["photos/missing.jpg"])
            #expect(entry.needsArchiveReview)
            #expect(!entry.transferReviewReasons.isEmpty)
        }
    }
    @Test func rejectsTraversal() throws {
        try withZIP([("../outside.json", fixture())]) { url in
            #expect(throws: BackupError.unsafePath) { try StoicBackupReader().read(url) }
        }
    }
    @Test func rejectsOversizedMember() throws {
        var limits = StoicBackupReader.Limits(); limits.maxJSONBytes = 10
        try withZIP([("entries.json", fixture())]) { url in
            #expect(throws: BackupError.resourceLimit) { try StoicBackupReader(limits: limits).read(url) }
        }
    }
    @Test func rejectsUnknownSchema() throws {
        try withZIP([("metadata.json", Data("{\"unknown\":[]}".utf8))]) { url in
            #expect(throws: BackupError.unsupportedFormat) { try StoicBackupReader().read(url) }
        }
    }
    @Test func rejectsDuplicateIDsAcrossFiles() throws {
        try withZIP([("a.json", fixture()), ("b.json", fixture())]) { url in
            #expect(throws: BackupError.duplicateID) { try StoicBackupReader().read(url) }
        }
    }
    @Test func rejectsDamagedJSON() throws {
        try withZIP([("entries.json", Data("{".utf8))]) { url in
            #expect(throws: BackupError.invalidRecord) { try StoicBackupReader().read(url) }
        }
    }
    @Test func preservesInstantAcrossOffsets() {
        #expect(JournalEntryConverter.parseDate("2001-02-03T12:34:56+03:00") == JournalEntryConverter.parseDate("2001-02-03T09:34:56Z"))
        #expect(JournalEntryConverter.parseDate("2001-02-03T12:34:56") == nil)
    }
    @Test func rejectsIncompleteRecord() throws {
        #expect(throws: BackupError.invalidRecord) {
            try JournalEntryConverter().convert(Data("{\"entries\":[{\"id\":\"x\",\"date\":\"yesterday\",\"text\":\"Synthetic\"}]}".utf8))
        }
    }
    @Test func rejectsDamagedZIP() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: url) }
        try Data("not zip".utf8).write(to: url)
        #expect(throws: BackupError.invalidArchive) { try StoicBackupReader().read(url) }
    }
    @Test func importDisabledUntilVerified() async {
        let capability = await UnverifiedJournalBackend().capability()
        #expect(!capability.canImport)
    }
}

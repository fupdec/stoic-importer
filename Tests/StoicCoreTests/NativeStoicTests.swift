import Foundation
import Testing
@testable import StoicCore

struct NativeStoicTests {
    func data(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value) }
    func collections(assets: [[String: Any]] = [], refs: [String] = []) throws -> [String: Data] {
        ["answers.json": try data([["uuid": "a", "timestamp": 1000000, "text": "Synthetic answer", "question": "Question", "routine": "r", "assets": refs]]),
         "routines.json": try data([["uuid": "r", "questions": ["Question"]]]),
         "assets.json": try data(assets)]
    }
    @Test func joinsRoutineAndRetainsTimestamp() throws {
        let converted = try NativeStoicConverter.convert(collections(), files: [])
        let entries = try #require(converted)
        #expect(entries.count == 1)
        #expect(entries[0].id == "r")
        #expect(entries[0].text == "Question\n\nSynthetic answer")
        #expect(entries[0].date == Date(timeIntervalSince1970: 1000))
        #expect(entries[0].reviewReasons.isEmpty)
    }
    @Test func missingPhotoKeepsEntryAndBlocksTransfer() throws {
        let input = try collections(assets: [["uuid": "p", "answer": "a", "type": "image", "relativePath": "photos/x.png"]], refs: ["p"])
        let entries = try #require(try NativeStoicConverter.convert(input, files: []))
        let entry = try #require(entries.first)
        #expect(entry.text.contains("Synthetic answer"))
        #expect(entry.missingPhotoPaths == ["photos/x.png"])
        #expect(!entry.transferReviewReasons.isEmpty)
    }
    @Test func orphanTextIsPreservedWithSourceNote() throws {
        var input = try collections(); input.removeValue(forKey: "routines.json")
        let entry = try #require(NativeStoicConverter.convert(input, files: [])?.first)
        #expect(entry.reviewReasons.isEmpty)
        #expect(!entry.notes.isEmpty)
        #expect(entry.kind == "checkin")
    }
    @Test func structuredUnknownPromptNeedsReviewAndKeepsSource() throws {
        let input = ["answers.json": try data([["uuid": "a", "routine": "r", "timestamp": 1000, "question": "36068DAC-970F-4231-9E5E-7F4182A050E3", "text": "[1,2]"]]),
                     "routines.json": try data([["uuid": "r"]])]
        let entry = try #require(NativeStoicConverter.convert(input, files: [])?.first)
        #expect(entry.text == "[1,2]")
        #expect(!entry.reviewReasons.isEmpty)
    }
    @Test func bridgeWritesPreparedPayloadAndPhoto() throws {
        let tests = ParserTests()
        try tests.withZIP([("backup/photos/x.png", Data([1,2,3]))]) { url in
            let parent = url.deletingLastPathComponent()
            let entry = JournalEntry(id: "synthetic", date: Date(timeIntervalSince1970: 1000), originalTimestamp: "1970-01-01T00:16:40Z", timeZone: nil, text: "Synthetic", attachmentPaths: ["backup/photos/x.png"])
            let folder = try BridgeRequest.prepare(entry: entry, archiveURL: url, parent: parent)
            defer { try? FileManager.default.removeItem(at: folder) }
            let payload = try JSONDecoder().decode(BridgePayload.self, from: Data(contentsOf: folder.appendingPathComponent("entry.json")))
            #expect(payload.attachmentCount == 1)
            #expect(payload.date == entry.originalTimestamp)
            #expect(try Data(contentsOf: folder.appendingPathComponent(try #require(payload.attachmentFileNames.first))) == Data([1,2,3]))
        }
    }
    @Test func bridgePreparesAllPhotosInSourceOrderWithUniqueNames() throws {
        try ParserTests().withZIP([("a/photo.png", Data([1, 2])), ("b/photo.png", Data([3, 4])), ("photo.heic", Data([5, 6]))]) { url in
            let entry = JournalEntry(id: "photos", date: Date(), originalTimestamp: "2026-10-29T00:00:00Z", timeZone: nil, text: "All photos", attachmentPaths: ["b/photo.png", "photo.heic", "a/photo.png"])
            let folder = try BridgeRequest.prepare(entry: entry, archiveURL: url, parent: url.deletingLastPathComponent())
            defer { try? FileManager.default.removeItem(at: folder) }
            let payload = try JSONDecoder().decode(BridgePayload.self, from: Data(contentsOf: folder.appendingPathComponent("entry.json")))
            #expect(payload.schema == "stoic-mac-bridge-v2")
            #expect(payload.attachmentCount == 3)
            #expect(Set(payload.attachmentFileNames).count == 3)
            for (name, expected) in zip(payload.attachmentFileNames, [Data([3, 4]), Data([5, 6]), Data([1, 2])]) {
                #expect(try Data(contentsOf: folder.appendingPathComponent(name)) == expected)
            }
        }
    }
    @Test func missingLaterPhotoRemovesEntirePreparedRequest() throws {
        try ParserTests().withZIP([("photo.png", Data([1]))]) { url in
            let parent = url.deletingLastPathComponent().appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: parent) }
            let entry = JournalEntry(id: "photos", date: Date(), originalTimestamp: "", timeZone: nil, text: "All photos", attachmentPaths: ["photo.png", "missing.png"])
            #expect(throws: BackupError.invalidRecord) { try BridgeRequest.prepare(entry: entry, archiveURL: url, parent: parent) }
            let remaining = try FileManager.default.contentsOfDirectory(atPath: parent.path)
            #expect(remaining.isEmpty)
        }
    }
    @Test func multipleNativePhotosNoLongerBlockImport() throws {
        let input = try collections(assets: [
            ["uuid": "p1", "answer": "a", "type": "image", "relativePath": "one.png"],
            ["uuid": "p2", "answer": "a", "type": "image", "relativePath": "two.png"]
        ], refs: ["p2", "p1"])
        let entry = try #require(NativeStoicConverter.convert(input, files: ["one.png", "two.png"])?.first)
        #expect(entry.attachmentPaths == ["two.png", "one.png"])
        #expect(entry.reviewReasons.isEmpty)
    }

    @Test func bridgeBlocksReviewRequiredRecord() throws {
        var entry = JournalEntry(id: "synthetic", date: Date(), originalTimestamp: "", timeZone: nil, text: "Synthetic", attachmentPaths: [])
        entry.reviewReasons = ["Unresolved"]
        #expect(throws: BackupError.invalidRecord) {
            try BridgeRequest.prepare(entry: entry, archiveURL: URL(fileURLWithPath: "/missing.zip"), parent: FileManager.default.temporaryDirectory)
        }
    }
    @Test func nativeZIPIsRecognized() throws {
        try ParserTests().withZIP(try collections().map { ("backup/" + $0.key, $0.value) }) { url in
            let backup = try StoicBackupReader().read(url)
            #expect(backup.entries.first?.id == "r")
        }
    }
}

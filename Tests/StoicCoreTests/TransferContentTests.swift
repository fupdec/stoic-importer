import Foundation
import Testing
@testable import StoicCore

struct TransferContentTests {
    @Test func unreadableValuesDoNotBlockReadableText() throws {
        var entry = JournalEntry(id: "readable", date: Date(), originalTimestamp: "2026-10-29T12:00:00Z", timeZone: nil, text: "Body\n[1,2]", attachmentPaths: [])
        entry.blocks = [EntryBlock(text: "Body"), EntryBlock(text: "[1,2]", isUnresolved: true)]
        entry.reviewReasons = ["Ответ содержит rich text без обычного текста.", "Незавершённая рутина."]
        let folder = try BridgeRequest.prepare(entry: entry, archiveURL: URL(fileURLWithPath: "/unused.zip"), parent: FileManager.default.temporaryDirectory)
        defer { try? FileManager.default.removeItem(at: folder) }
        let payload = try JSONDecoder().decode(BridgePayload.self, from: Data(contentsOf: folder.appendingPathComponent("entry.json")))
        #expect(payload.text == "Body")
        #expect(entry.reviewReasons.count == 2)
        #expect(entry.transferReviewReasons.isEmpty)
    }

    @Test func photoOnlyRecordCanBePrepared() throws {
        try ParserTests().withZIP([("photo.jpg", Data([1, 2, 3]))]) { archive in
            var entry = JournalEntry(id: "photo", date: Date(), originalTimestamp: "2026-10-29T12:00:00Z", timeZone: nil, text: "", attachmentPaths: ["photo.jpg"])
            entry.reviewReasons = ["Нет обычного текста; проверьте исходную запись.", "Ответ содержит rich text без обычного текста."]
            let folder = try BridgeRequest.prepare(entry: entry, archiveURL: archive, parent: FileManager.default.temporaryDirectory)
            defer { try? FileManager.default.removeItem(at: folder) }
            let payload = try JSONDecoder().decode(BridgePayload.self, from: Data(contentsOf: folder.appendingPathComponent("entry.json")))
            #expect(payload.text.isEmpty)
            #expect(payload.attachmentCount == 1)
        }
    }

    @Test func unreadableOnlyRecordStillCannotBeSent() {
        var entry = JournalEntry(id: "empty", date: Date(), originalTimestamp: "", timeZone: nil, text: "[1,2]", attachmentPaths: [])
        entry.blocks = [EntryBlock(text: "[1,2]", isUnresolved: true)]
        #expect(throws: BackupError.invalidRecord) {
            try BridgeRequest.prepare(entry: entry, archiveURL: URL(fileURLWithPath: "/unused.zip"), parent: FileManager.default.temporaryDirectory)
        }
    }
}

import Foundation
import Testing
@testable import StoicCore

struct EntryRevisionTests {
    @Test func copyPreservesSourceAndUsesExplicitSelections() throws {
        var source = JournalEntry(id: "source", date: Date(timeIntervalSince1970: 1000), originalTimestamp: "original", timeZone: nil, text: "body", attachmentPaths: ["photo.jpg", "bad.pdf"])
        source.blocks = [EntryBlock(text: "body"), EntryBlock(text: "[1,2]", isUnresolved: true)]
        source.reviewReasons = ["unsupported photo"]
        source.sourceJSON = "original JSON"
        var draft = EntryRevision(source: source)
        draft.title = "New title"
        draft.text = "Fixed body"
        draft.date = Date(timeIntervalSince1970: 2000)
        draft.photoPaths = ["photo.jpg"]
        draft.answerIndices = [0]
        let copy = try draft.applying(to: source)
        #expect(source.text == "body")
        #expect(source.reviewReasons == ["unsupported photo"])
        #expect(copy.sourceJSON == source.sourceJSON)
        #expect(copy.id == source.id)
        #expect(copy.reviewReasons.isEmpty)
        #expect(copy.attachmentPaths == ["photo.jpg"])
        #expect(copy.originalTimestamp == "1970-01-01T00:33:20.000Z")
        #expect(copy.journalText().contains("New title\n\nFixed body\n\n1, 2"))
        #expect(copy.journalText() == copy.journalText(includeUnresolved: true))
        #expect(try JSONDecoder().decode(EntryRevision.self, from: JSONEncoder().encode(draft)) == draft)
    }
    @Test func rejectsEmptyTextAndInvalidSelections() {
        let source = JournalEntry(id: "source", date: Date(), originalTimestamp: "original", timeZone: nil, text: "", attachmentPaths: ["bad.pdf"])
        var draft = EntryRevision(source: source)
        #expect(throws: BackupError.self) { try draft.applying(to: source) }
        draft.text = "Fixed"
        #expect(throws: BackupError.self) { try draft.applying(to: source) }
        draft.photoPaths = []
        draft.answerIndices = [99]
        #expect(throws: BackupError.self) { try draft.applying(to: source) }
    }
}

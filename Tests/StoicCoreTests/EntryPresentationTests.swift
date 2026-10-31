import Foundation
import Testing
@testable import StoicCore

struct EntryPresentationTests {
    func entry() -> JournalEntry {
        JournalEntry(id: "synthetic", date: Date(timeIntervalSince1970: 1000), originalTimestamp: "1970-01-01T00:16:40.000Z", timeZone: nil, text: "Original", attachmentPaths: [])
    }
    @Test func archiveReviewIncludesNonBlockingDataAndEmptyEntries() {
        var value = entry()
        value.blocks = [EntryBlock(text: "[0,5]", isUnresolved: true)]
        #expect(value.needsArchiveReview)
        #expect(!value.hasTransferContent)
        #expect(value.transferReviewReasons.isEmpty)
        value.blocks.append(EntryBlock(text: "Readable text"))
        #expect(value.hasTransferContent)
        #expect(value.needsArchiveReview)
        value.reviewReasons = ["Отсутствует фотография: photos/missing.jpg"]
        #expect(value.missingPhotoPaths == ["photos/missing.jpg"])
        #expect(!value.transferReviewReasons.isEmpty)
        value.reviewReasons = []
        value.blocks = []
        value.notes = ["Unknown tag"]
        #expect(value.needsArchiveReview)
    }

    @Test func removesEmptyMarkdownHeadingAndKeepsBody() {
        #expect(EntryPresentation.clean("# \n\n## A walk\n- In the park\n2. Keep this number") == "A walk\n• In the park\n2. Keep this number")
    }
    @Test func hidesPromptOnlyEntriesButKeepsAnswersAndPhotos() {
        var value = entry()
        value.blocks = [EntryBlock(heading: "How was your day?", text: "  \n")]
        #expect(!value.hasJournalContent)
        value.blocks = [EntryBlock(text: "[0,5]", isUnresolved: true)]
        #expect(!value.hasJournalContent)
        value.blocks.append(EntryBlock(heading: "What happened?", text: "A peaceful morning."))
        #expect(value.hasJournalContent)
        value.blocks = [EntryBlock(text: "[0,5]", isUnresolved: true)]
        var photo = JournalEntry(id: "photo", date: value.date, originalTimestamp: value.originalTimestamp, timeZone: nil, text: "", attachmentPaths: ["photos/morning.jpg"])
        photo.blocks = value.blocks
        #expect(photo.hasJournalContent)
        value.reviewReasons = ["Ответ содержит rich text без обычного текста."]
        #expect(value.hasJournalContent)
    }

    @Test func richTextNeedingReviewKeepsItsOriginalSource() throws {
        let rich: [String: Any] = ["format": "unknown", "content": "Original formatted answer"]
        let answers: [[String: Any]] = [["uuid": "rich", "timestamp": 1000, "richText": rich]]
        let data = try JSONSerialization.data(withJSONObject: answers)
        let converted = try NativeStoicConverter.convert(["answers.json": data], files: [])
        let value = try #require(converted?.first)
        #expect(value.hasJournalContent)
        #expect(!value.reviewReasons.isEmpty)
        let source = try #require(value.sourceJSON)
        let object = try #require(JSONSerialization.jsonObject(with: Data(source.utf8)) as? [String: Any])
        let linked = try #require(object["answers"] as? [[String: Any]])
        #expect((linked.first?["richText"] as? [String: String])?["content"] == "Original formatted answer")
        let roundTrip = try JSONDecoder().decode(JournalEntry.self, from: JSONEncoder().encode(value))
        #expect(roundTrip.sourceJSON == source)
    }
    @Test func sourceValuesStaySeparateAndAreHiddenByDefault() {
        var value = entry()
        value.title = "Утренние заметки"
        value.blocks = [EntryBlock(text: "## A walk\nFresh air."), EntryBlock(text: "[0,5]", isUnresolved: true)]
        #expect(value.hasReadableText)
        #expect(value.previewText == "A walk\nFresh air.")
        #expect(value.journalText(includeUnresolved: true).contains("Ответ 1: 0, 5"))
        #expect(value.journalText().hasPrefix("A walk\nFresh air."))
        #expect(!value.journalText().contains("Ответ 1"))
        #expect(value.unresolvedBlocks.first?.text == "[0,5]")
        #expect(value.text == "Original")
    }
    @Test func firstLineTitleIsNotDuplicated() {
        var value = entry(); value.blocks = [EntryBlock(text: "# A walk\nFresh air.")]
        #expect(value.displayTitle == "A walk")
        #expect(value.journalText() == "A walk\nFresh air.")
    }
    @Test func titleUsesFirstSentenceOrParagraphWithinFiftyCharacters() {
        var value = entry()
        value.kind = "evening"; value.title = "Вечерние заметки"
        value.blocks = [EntryBlock(text: "Сегодня хороший день. Потом пошёл дождь.")]
        #expect(value.displayTitle == "Сегодня хороший день.")
        value.blocks = [EntryBlock(text: "Первый абзац без точки\n\nВторой абзац.")]
        #expect(value.displayTitle == "Первый абзац без точки")
        let long = String(repeating: "🌿", count: 65)
        value.blocks = [EntryBlock(text: long)]
        #expect(value.readingTitle == nil)
        #expect(value.journalText().contains(long))
        value.blocks = [EntryBlock(text: "[0,5]", isUnresolved: true), EntryBlock(text: ""), EntryBlock(text: "Живой текст! Ещё текст.")]
        #expect(value.displayTitle == "Живой текст!")
        #expect(!value.journalText().contains("Вечерние заметки"))
    }

    @Test func longOpeningStaysInBodyWithoutTruncation() {
        var value = entry()
        let opening = "Было приятно встретиться с коллегами, познакомились и пообщались"
        value.blocks = [EntryBlock(text: opening + "\n\nПродолжение.")]
        #expect(value.readingTitle == nil)
        #expect(value.journalText().hasPrefix(opening + "\n\nПродолжение."))
        #expect(value.readableBlocks.first?.text == opening + "\n\nПродолжение.")
        let fifty = String(repeating: "я", count: 50)
        value.blocks = [EntryBlock(text: fifty + "\n\nПродолжение.")]
        #expect(value.readingTitle == fifty)
        value.blocks = [EntryBlock(text: fifty + "я\n\nПродолжение.")]
        #expect(value.readingTitle == nil)
    }

    @Test func shortEntriesKeepBodyAndDoNotRequireAHeading() {
        var value = entry()
        value.blocks = [EntryBlock(text: "Короткая запись.")]
        #expect(value.readingTitle == nil)
        #expect(value.readableBlocks.first?.text == "Короткая запись.")
        #expect(value.journalText() == "Короткая запись.")
        value.blocks = [EntryBlock(text: "Первый абзац\n\nПродолжение записи.")]
        #expect(value.readingTitle == "Первый абзац")
        #expect(value.readableBlocks.first?.text == "Первый абзац\n\nПродолжение записи.")
        value.blocks = [EntryBlock(text: "[0,5]", isUnresolved: true)]
        #expect(value.readingTitle == nil)
    }

    @Test func mixedRoutineCanBeImportedWithoutGuessingPrompts() throws {
        func data(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value) }
        let input = ["answers.json": try data([
            ["uuid": "a", "routine": "r", "timestamp": 1000, "question": UUID().uuidString, "text": "[0,5]"],
            ["uuid": "b", "routine": "r", "timestamp": 2000, "question": UUID().uuidString, "text": "A peaceful morning."]
        ]), "routines.json": try data([["uuid": "r", "type": "morning", "isCompleted": true]])]
        let converted = try NativeStoicConverter.convert(input, files: [])
        let value = try #require(converted?.first)
        #expect(value.reviewReasons.isEmpty)
        #expect(value.presentationTitle(language: .russian) == "A peaceful morning.")
        #expect(value.unresolvedBlocks.count == 1)
        #expect(value.journalText().contains("A peaceful morning."))
        #expect(value.date == Date(timeIntervalSince1970: 1))
    }
}

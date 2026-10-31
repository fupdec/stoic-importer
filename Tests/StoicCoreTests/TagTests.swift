import Foundation
import Testing
@testable import StoicCore

struct TagTests {
    @Test func importsLinkedTagsAndNamedOptionsThroughZIP() throws {
        func data(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value) }
        let files: [(String, Data)] = [
            ("answers.json", try data([["uuid": "a", "timestamp": 1000, "text": "A walk", "tags": ["Health"], "selectedOptions": ["o"]]])),
            ("journal-entries.json", try data([["uuid": "j", "timestamp": 1000, "answers": ["a"], "tags": ["t", "#health"]]])),
            ("tags.json", try data([["uuid": "t", "name": "Travel"]])),
            ("question-options.json", try data([["uuid": "o", "title": "Fresh air"]]))
        ]
        try ParserTests().withZIP(files) { url in
            let entry = try #require(StoicBackupReader().read(url).entries.first)
            #expect(entry.displayTags == ["Travel", "health", "Fresh air"])
            #expect(entry.journalText().hasSuffix("#Travel · #health · #Fresh air"))
            #expect(entry.previewText == "A walk")
        }
    }

    @Test func unknownAndLocalizationKeyOptionsAreNotGuessed() throws {
        func data(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value) }
        let entry = try #require(NativeStoicConverter.convert([
            "answers.json": try data([["uuid": "a", "timestamp": 1000, "text": "A walk", "selectedOptions": ["missing", "o"]]]),
            "question-options.json": try data([["uuid": "o", "title": "question-option-focus-25-title"]])
        ], files: [])?.first)
        #expect(entry.tags.isEmpty)
        #expect(entry.notes.count == 3) // Source note and both unresolved references.
        #expect(entry.reviewReasons.isEmpty)
    }

    @Test func entryKindsDoNotAddAutomaticTags() {
        var entry = JournalEntry(id: "a", date: Date(), originalTimestamp: "", timeZone: nil, text: "Body", attachmentPaths: [])
        for kind in ["morning", "evening", "checkin", "journal"] {
            entry.kind = kind
            #expect(entry.journalText() == "Body")
            #expect(entry.importTags(language: .english).isEmpty)
        }
        entry.tags = ["Travel"]
        #expect(entry.journalText().hasSuffix("#Travel"))
    }

    @Test func simpleFormatNormalizesTagsAndOldExportsStillDecode() throws {
        let json = Data(#"{"entries":[{"id":"a","date":"2026-10-27T12:00:00Z","text":"A walk","tags":[" #Travel ","travel","","Fresh\nair"]}]}"#.utf8)
        let entry = try #require(JournalEntryConverter().convert(json)?.first)
        #expect(entry.tags == ["Travel", "Fresh air"])
        var object = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(entry)) as? [String: Any])
        object.removeValue(forKey: "tags")
        let legacy = try JSONDecoder().decode(JournalEntry.self, from: JSONSerialization.data(withJSONObject: object))
        #expect(legacy.tags.isEmpty)
        #expect(legacy.text == entry.text)
    }
}

import Foundation
import Testing
@testable import StoicCore

struct LocalizationTests {
    @Test func everyKeyHasFourCompleteTranslationsWithMatchingArguments() throws {
        let pattern = try NSRegularExpression(pattern: #"%(?:\d+\$)?[d@]"#)
        func arguments(_ value: String) -> [String] {
            let range = NSRange(value.startIndex..., in: value)
            return pattern.matches(in: value, range: range).map { (value as NSString).substring(with: $0.range) }
        }
        for (key, translations) in AppLocalization.catalog {
            #expect(translations.count == AppLanguage.allCases.count)
            for translation in translations {
                #expect(!translation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                #expect(arguments(translation) == arguments(key))
            }
        }
    }
    @Test func entryCountsUseLanguageSpecificGrammar() {
        #expect(AppLocalization.entryCount(1, language: .english) == "1 entry")
        #expect(AppLocalization.entryCount(2, language: .english) == "2 entries")
        #expect(AppLocalization.entryCount(1, language: .spanish) == "1 entrada")
        #expect(AppLocalization.entryCount(0, language: .spanish) == "0 entradas")
        #expect(AppLocalization.entryCount(2, language: .chinese) == "2 个条目")
        #expect(AppLocalization.entryCount(21, language: .russian) == "21 запись")
        #expect(AppLocalization.entryCount(12, language: .russian) == "12 записей")
        #expect(AppLocalization.entryCount(344, language: .russian) == "344 записи")
    }
    @Test func generatedHeadingsTranslateWithoutChangingSourceContentOrDates() {
        var entry = JournalEntry(id: "synthetic", date: Date(timeIntervalSince1970: 1234), originalTimestamp: "1970-01-01T00:20:34.000Z", timeZone: nil, text: "Мой исходный текст", attachmentPaths: [])
        entry.kind = "morning"; entry.title = "Утренние заметки"
        entry.blocks = [EntryBlock(heading: "Мой вопрос", text: "Мой исходный текст"), EntryBlock(text: "[0,5]", isUnresolved: true)]
        for language in AppLanguage.allCases {
            let output = entry.journalText(includeUnresolved: true, language: language)
            #expect(output.contains("Мой исходный текст"))
            #expect(output.contains("Мой вопрос"))
            #expect(output.contains(AppLocalization.text("Дополнительные ответы Stoic", language: language)))
            #expect(entry.originalTimestamp == "1970-01-01T00:20:34.000Z")
        }
        #expect(entry.presentationTitle(language: .english) == "Мой исходный текст")
        #expect(entry.presentationTitle(language: .spanish) == "Мой исходный текст")
        #expect(entry.presentationTitle(language: .chinese) == "Мой исходный текст")
    }
    @Test func titlesComeFromSourceTextRegardlessOfStoredTitle() {
        var entry = JournalEntry(id: "synthetic", date: Date(), originalTimestamp: "", timeZone: nil, text: "Дневник", attachmentPaths: [])
        #expect(entry.presentationTitle(language: .english) == "Дневник")
        entry.title = "Утренние заметки" // Explicit custom title on a standalone journal entry.
        #expect(entry.presentationTitle(language: .english) == "Дневник")
    }
    @Test func eveningTimeKeepsItsMeridiemInEnglish() throws {
        let date = try #require(ISO8601DateFormatter().date(from: "2026-04-28T18:00:00Z"))
        let zone = try #require(TimeZone(secondsFromGMT: 0))
        let english = AppLocalization.time(date, language: .english, timeZone: zone)
        #expect(english.contains("PM"))
        #expect(english.contains("6:00"))
        #expect(AppLocalization.time(date, language: .russian, timeZone: zone) == "18:00")
    }
    @Test func formattingUsesTheSelectedLanguage() {
        #expect(AppLocalization.format("%d из %d", language: .spanish, 2, 4) == "2 de 4")
        #expect(AppLocalization.format("Ответ %d", language: .chinese, 3) == "回答 3")
        #expect(AppLanguage(rawValue: "zh-Hans") == .chinese)
    }
}

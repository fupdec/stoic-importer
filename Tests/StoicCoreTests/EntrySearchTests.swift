import Foundation
import Testing
@testable import StoicCore

struct EntrySearchTests {
    func entry() -> JournalEntry {
        var entry = JournalEntry(id: "test", date: Date(timeIntervalSince1970: 100_000), originalTimestamp: "", timeZone: nil, text: "Прогулка", attachmentPaths: [])
        entry.kind = "morning"
        entry.editedTitle = "Путешествие"
        entry.blocks = [EntryBlock(heading: "Планы", text: "Café у моря")]
        entry.tags = ["Отдых", "Семья"]
        return entry
    }
    @Test func wordsMatchAcrossTitleBodyHeadingsAndTags() {
        var search = EntrySearch()
        search.query = "  ПУТЕШЕСТВИЕ\n cafe планы отдых  "
        #expect(search.matches(entry()))
        search.query += " отсутствует"
        #expect(!search.matches(entry()))
        search.query = " \n "
        #expect(search.matches(entry()))
    }
    @Test func filtersCombineAndRequireAllSelectedTags() {
        var search = EntrySearch()
        search.kind = "morning"; search.tags = ["отдых", "Семья"]
        #expect(search.matches(entry()))
        search.tags.insert("Работа")
        #expect(!search.matches(entry()))
        search.tags = []; search.kind = "evening"
        #expect(!search.matches(entry()))
    }
    @Test func dateRangeIncludesEntireBoundaryDays() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        var search = EntrySearch()
        let date = entry().date
        search.startDate = date.addingTimeInterval(3600)
        search.endDate = calendar.startOfDay(for: date)
        #expect(search.matches(entry(), calendar: calendar))
        search.endDate = date.addingTimeInterval(-86400)
        #expect(!search.matches(entry(), calendar: calendar))
        search.endDate = nil; search.startDate = date.addingTimeInterval(86400)
        #expect(!search.matches(entry(), calendar: calendar))
    }
}

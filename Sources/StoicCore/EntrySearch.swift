import Foundation

/// All words must occur in the entry; dates include both boundary days.
public struct EntrySearch: Equatable, Sendable {
    public var query = ""
    public var startDate: Date?
    public var endDate: Date?
    public var kind = ""
    public var tags: Set<String> = []
    public init() {}

    public static func words(_ query: String) -> [String] {
        query.split(whereSeparator: \.isWhitespace).map(String.init)
    }

    public func matches(_ entry: JournalEntry, calendar: Calendar = .current) -> Bool {
        if let startDate, entry.date < calendar.startOfDay(for: startDate) { return false }
        if let endDate {
            let day = calendar.startOfDay(for: endDate)
            guard let nextDay = calendar.date(byAdding: .day, value: 1, to: day), entry.date < nextDay else { return false }
        }
        if !kind.isEmpty && entry.kind != kind { return false }
        if !tags.allSatisfy({ tag in entry.displayTags.contains { $0.compare(tag, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame } }) { return false }
        let words = Self.words(query)
        guard !words.isEmpty else { return true }
        let content = ([entry.editedTitle ?? "", entry.title, entry.text] + entry.readableBlocks.flatMap { [$0.heading, $0.text] } + entry.displayTags).joined(separator: "\n")
        return words.allSatisfy { content.range(of: $0, options: [.caseInsensitive, .diacriticInsensitive]) != nil }
    }
}

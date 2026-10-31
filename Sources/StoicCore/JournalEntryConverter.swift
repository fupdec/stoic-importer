import Foundation

/// Explicit, provisional adapter. No heuristic recursive scraping of arbitrary JSON.
/// Actual Stoic exports need local schema verification before compatibility is claimed.
public struct JournalEntryConverter: Sendable {
    public init() {}
    private struct Record: Decodable {
        let id: String
        let date: String
        let text: String?
        let timeZone: String?
        let answers: [Answer]?
        let attachments: [String]?
        let tags: [String]?
    }
    private struct Answer: Decodable { let question: String; let answer: String }
    private struct Envelope: Decodable { let entries: [Record] }

    public func convert(_ data: Data) throws -> [JournalEntry]? {
        let root: Any
        do { root = try JSONSerialization.jsonObject(with: data) }
        catch { throw BackupError.invalidRecord }
        guard let object = root as? [String: Any], object["entries"] != nil else { return nil }
        let envelope: Envelope
        do { envelope = try JSONDecoder().decode(Envelope.self, from: data) }
        catch { throw BackupError.invalidRecord }
        return try envelope.entries.map { record in
            guard !record.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  let date = Self.parseDate(record.date),
                  record.timeZone == nil || TimeZone(identifier: record.timeZone!) != nil
            else { throw BackupError.invalidRecord }
            let blocks = [record.text ?? ""] + (record.answers ?? []).map { "## \($0.question)\n\n\($0.answer)" }
            let text = blocks.filter { !$0.isEmpty }.joined(separator: "\n\n")
            guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw BackupError.invalidRecord }
            let paths = record.attachments ?? []
            guard paths.allSatisfy(StoicBackupReader.isSafePath) else { throw BackupError.unsafePath }
            var entry = JournalEntry(id: record.id, date: date, originalTimestamp: record.date,
                                timeZone: record.timeZone, text: text, attachmentPaths: paths)
            entry.tags = EntryPresentation.normalizedTags(record.tags ?? [])
            return entry
        }
    }

    public static func parseDate(_ value: String) -> Date? {
        // Require an explicit offset: never guess a missing timezone or numeric epoch.
        guard value.range(of: #"T.*(?:Z|[+-]\d{2}:\d{2})$"#, options: .regularExpression) != nil else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: value) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: value)
    }
}

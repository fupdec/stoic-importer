import Foundation

/// A transfer copy. The source record and archive are never modified.
public struct EntryRevision: Codable, Equatable, Sendable {
    public var title: String
    public var text: String
    public var date: Date
    public var answerIndices: Set<Int>
    public var photoPaths: Set<String>

    public init(source: JournalEntry, includeUnresolved: Bool = false) {
        title = source.editedTitle ?? source.readingTitle ?? ""
        text = source.readableBlocks.map { block in
            block.heading.isEmpty ? block.text : block.heading + "\n\n" + block.text
        }.joined(separator: "\n\n")
        date = source.date
        answerIndices = includeUnresolved ? Set(source.unresolvedBlocks.indices) : []
        photoPaths = Set(source.attachmentPaths)
    }

    public func applying(to source: JournalEntry) throws -> JournalEntry {
        guard date.timeIntervalSince1970.isFinite,
              (0...253402300799).contains(date.timeIntervalSince1970),
              answerIndices.isSubset(of: Set(source.unresolvedBlocks.indices)),
              photoPaths.isSubset(of: Set(source.attachmentPaths)) else { throw BackupError.invalidRecord }
        var sections = [EntryPresentation.clean(text)].filter { !$0.isEmpty }
        for index in source.unresolvedBlocks.indices where answerIndices.contains(index) {
            sections.append(EntryPresentation.structuredValue(source.unresolvedBlocks[index].text))
        }
        let body = sections.joined(separator: "\n\n")
        guard !body.isEmpty else { throw BackupError.invalidRecord }
        let paths = source.attachmentPaths.filter { photoPaths.contains($0) }
        guard paths.allSatisfy({ StoicBackupReader.isSafePath($0) && ["jpg", "jpeg", "png", "heic"].contains(URL(fileURLWithPath: $0).pathExtension.lowercased()) }) else { throw BackupError.invalidRecord }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var copy = JournalEntry(id: source.id, date: date, originalTimestamp: formatter.string(from: date), timeZone: source.timeZone, text: body, attachmentPaths: paths)
        copy.editedTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        copy.kind = source.kind
        copy.tags = source.tags
        copy.notes = source.notes
        copy.sourceJSON = source.sourceJSON
        copy.photoLocations = source.photoLocations.filter { photoPaths.contains($0.key) }
        return copy
    }
}

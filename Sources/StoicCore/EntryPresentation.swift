import Foundation

public struct EntryBlock: Codable, Equatable, Sendable {
    public let heading: String
    public let text: String
    public let isUnresolved: Bool
    public init(heading: String = "", text: String, isUnresolved: Bool = false) {
        self.heading = heading; self.text = text; self.isUnresolved = isUnresolved
    }
}

public extension JournalEntry {
    var missingPhotoPaths: [String] {
        reviewReasons.compactMap { $0.hasPrefix("Отсутствует фотография: ") ? String($0.dropFirst("Отсутствует фотография: ".count)) : nil }
    }
    var archiveReviewDetails: [String] {
        var details = reviewReasons + notes
        if !hasReadableText && attachmentPaths.isEmpty { details.append("Нет содержимого для переноса.") }
        return Array(Set(details)).sorted()
    }
    var needsArchiveReview: Bool { !archiveReviewDetails.isEmpty || !unresolvedBlocks.isEmpty }
    var hasTransferContent: Bool { hasReadableText || !attachmentPaths.isEmpty }

    /// Omitted source values do not prevent transferring readable text or photos.
    var transferReviewReasons: [String] {
        reviewReasons.filter {
            !["Незавершённая рутина.",
              "Ответ содержит rich text без обычного текста.",
              "Нет обычного текста; проверьте исходную запись.",
              "В записи только нерасшифрованные значения. Проверьте их перед импортом."].contains($0)
        }
    }

    var readableBlocks: [EntryBlock] {
        blocks.isEmpty ? [EntryBlock(text: text)] : blocks.filter { !$0.isUnresolved }
    }
    var unresolvedBlocks: [EntryBlock] { blocks.filter(\.isUnresolved) }
    var hasReadableText: Bool { readableBlocks.contains { !EntryPresentation.clean($0.text).isEmpty } }
    /// Hide empty prompts and unresolved-only check-ins, while keeping photo entries.
    var hasJournalContent: Bool {
        hasReadableText || !attachmentPaths.isEmpty || reviewReasons.contains("Ответ содержит rich text без обычного текста.")
    }
    private var contentTitle: String? {
        guard let first = readableBlocks.map({ EntryPresentation.clean($0.text) }).first(where: { !$0.isEmpty }) else { return nil }
        let paragraph = first.components(separatedBy: "\n").first ?? first
        var sentence = paragraph
        paragraph.enumerateSubstrings(in: paragraph.startIndex..<paragraph.endIndex, options: .bySentences) { value, _, _, stop in
            if let value { sentence = value }
            stop = true
        }
        let candidate = sentence.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !candidate.isEmpty, candidate.count <= 50 else { return nil }
        return candidate
    }
    /// A short entry stays body text instead of becoming a heading with an empty body.
    var readingTitle: String? {
        if let editedTitle, !editedTitle.isEmpty { return editedTitle }
        guard let title = contentTitle else { return nil }
        let body = readableBlocks.map { EntryPresentation.clean($0.text) }.filter { !$0.isEmpty }.joined(separator: "\n\n")
        return body == title ? nil : title
    }
    var displayTitle: String { presentationTitle(language: .russian) }
    func presentationTitle(language: AppLanguage) -> String {
        (editedTitle.flatMap { $0.isEmpty ? nil : $0 } ?? contentTitle) ?? AppLocalization.text("Отметка Stoic", language: language)
    }
    func kindTag(language: AppLanguage) -> String {
        let label = switch kind {
        case "morning": "Утро"
        case "evening": "Вечер"
        case "checkin": "Момент"
        default: "Заметка"
        }
        return AppLocalization.text(label, language: language)
    }
    func importTags(language: AppLanguage) -> [String] {
        displayTags
    }
    var displayTags: [String] { EntryPresentation.normalizedTags(tags) }
    var previewText: String {
        readableBlocks.map { EntryPresentation.clean($0.text) }.filter { !$0.isEmpty }.joined(separator: " · ")
    }
    /// Plain text is deliberate: Journal's message field does not promise Markdown rendering.
    func journalText(includeUnresolved: Bool = false, language: AppLanguage = .russian) -> String {
        var sections: [String] = []
        for block in readableBlocks {
            let body = EntryPresentation.clean(block.text)
            guard !body.isEmpty else { continue }
            let heading = EntryPresentation.clean(block.heading)
            sections.append(heading.isEmpty ? body : heading + "\n\n" + body)
        }
        if includeUnresolved && !unresolvedBlocks.isEmpty {
            let values = unresolvedBlocks.enumerated().map { offset, block in
                AppLocalization.format("Ответ %d", language: language, offset + 1) + ": " + EntryPresentation.structuredValue(block.text)
            }.joined(separator: "\n")
            sections.append(AppLocalization.text("Дополнительные ответы Stoic", language: language) + "\n\n" + AppLocalization.text("Названия вопросов отсутствуют в экспорте. Исходные значения:", language: language) + "\n" + values)
        }
        if !importTags(language: language).isEmpty { sections.append(importTags(language: language).map { "#" + $0 }.joined(separator: " · ")) }
        let body = sections.joined(separator: "\n\n")
        guard !body.isEmpty else { return "" }
        // Do not duplicate a first-line title already present in the source body.
        guard let heading = readingTitle else { return body }
        return body.components(separatedBy: "\n").first == heading ? body : heading + "\n\n" + body
    }
}

public enum EntryPresentation {
    public static func normalizedTags(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.compactMap { source in
            let value = source.trimmingCharacters(in: .whitespacesAndNewlines)
                .replacingOccurrences(of: "^#+", with: "", options: .regularExpression)
                .split(whereSeparator: \.isWhitespace).joined(separator: " ")
            guard !value.isEmpty, seen.insert(value.lowercased()).inserted else { return nil }
            return value
        }
    }
    public static func clean(_ source: String) -> String {
        source.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n")
            .components(separatedBy: "\n").compactMap { line -> String? in
                let value = line.trimmingCharacters(in: .whitespaces)
                if value.range(of: #"^#{1,6}\s*$"#, options: .regularExpression) != nil { return nil }
                return line.replacingOccurrences(of: #"^\s*#{1,6}\s+"#, with: "", options: .regularExpression)
                    .replacingOccurrences(of: #"^\s*[-*+]\s+"#, with: "• ", options: .regularExpression)
            }.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }
    public static func structuredValue(_ source: String) -> String {
        guard let object = try? JSONSerialization.jsonObject(with: Data(source.utf8), options: .fragmentsAllowed) else { return source }
        if let values = object as? [Any] {
            return values.map { value in
                if value is [Any] || value is [String: Any], let bytes = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), let string = String(data: bytes, encoding: .utf8) { return string }
                return String(describing: value)
            }.joined(separator: ", ")
        }
        return source
    }
}

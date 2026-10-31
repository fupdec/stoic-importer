import Foundation
import CoreFoundation

/// Adapter for the linked collections in a native Stoic export.
struct NativeStoicConverter {
    static func convert(_ collections: [String: Data], files: [String]) throws -> [JournalEntry]? {
        guard collections["answers.json"] != nil else { return nil }
        func records(_ name: String, required: Bool = true) throws -> [[String: Any]] {
            guard let data = collections[name] else {
                if required { throw BackupError.unsupportedFormat }; return []
            }
            guard let result = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else { throw BackupError.invalidRecord }
            return result
        }
        func identifier(_ record: [String: Any]) throws -> String {
            guard let id = record["uuid"] as? String, !id.isEmpty else { throw BackupError.invalidRecord }
            return id
        }
        func index(_ records: [[String: Any]]) throws -> [String: [String: Any]] {
            var result: [String: [String: Any]] = [:]
            for r in records {
                let id = try identifier(r)
                guard result.updateValue(r, forKey: id) == nil else { throw BackupError.duplicateID }
            }
            return result
        }
        func plainText(_ record: [String: Any]) -> String? {
            if let text = record["text"] as? String, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return text }
            guard let attributed = record["attributedText"] as? [String: Any],
                  let runs = attributed["runs"] as? [[String: Any]], !runs.isEmpty,
                  runs.allSatisfy({ $0["text"] is String }) else { return nil }
            return runs.compactMap { $0["text"] as? String }.joined()
        }
        let answers = try records("answers.json")
        let answerMap = try index(answers)
        let assets = try index(records("assets.json", required: false))
        let tagMap = try index(records("tags.json", required: false))
        let optionMap = try index(records("question-options.json", required: false))
        func tags(_ record: [String: Any], notes: inout [String]) throws -> [String] {
            var result: [String] = []
            if let raw = record["tags"] {
                guard let values = raw as? [String] else { throw BackupError.invalidRecord }
                for value in values {
                    if let tag = tagMap[value] {
                        guard let name = tag["name"] as? String ?? tag["title"] as? String else { throw BackupError.invalidRecord }
                        result.append(name)
                    } else if UUID(uuidString: value) == nil { result.append(value) }
                    else { notes.append("Не удалось определить название тега: " + value) }
                }
            }
            if let raw = record["selectedOptions"] {
                guard let values = raw as? [String] else { throw BackupError.invalidRecord }
                for value in values {
                    if let option = optionMap[value], let title = option["title"] as? String,
                       !title.hasPrefix("question-option-"), !title.isEmpty {
                        result.append(title)
                    } else { notes.append("Не удалось определить название выбранного варианта Stoic: " + value) }
                }
            }
            return result
        }
        var used = Set<String>(), sourceIDs = Set<String>(), result: [JournalEntry] = []
        func build(_ record: [String: Any], linked: [[String: Any]], routine: Bool, orphan: Bool = false) throws {
            let id = try identifier(record)
            guard sourceIDs.insert(id).inserted else { throw BackupError.duplicateID }
            var reasons: [String] = []
            var notes: [String] = orphan ? ["Отдельный ответ Stoic: связь с записью или рутиной отсутствует в экспорте."] : []
            var entryTags = try tags(record, notes: &notes)
            var presentation: [EntryBlock] = []
            if routine, record["isCompleted"] as? Bool == false { reasons.append("Незавершённая рутина.") }
            var blocks: [String] = [], paths: [String] = []
            var photoLocations: [String: PhotoLocation] = [:]
            if !orphan, let text = plainText(record), !text.isEmpty { blocks.append(text); presentation.append(EntryBlock(text: text)) }
            var stamps: [Double] = []
            for answer in linked {
                if !orphan { entryTags += try tags(answer, notes: &notes) }
                let aid = try identifier(answer)
                guard used.insert(aid).inserted else { throw BackupError.invalidRecord }
                guard let stamp = answer["timestamp"] as? Double, stamp.isFinite, stamp >= 0, stamp <= 253402300799999 else { throw BackupError.invalidRecord }
                stamps.append(stamp)
                if let text = plainText(answer), !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    let question = answer["question"] as? String ?? ""
                    let unresolved = UUID(uuidString: question) != nil
                    let structured = unresolved && (try? JSONSerialization.jsonObject(with: Data(text.utf8), options: .fragmentsAllowed)) != nil
                    if structured { notes.append("В экспорте нет названий некоторых вопросов. Их значения сохранены отдельно.") }
                    presentation.append(EntryBlock(heading: !question.isEmpty && !unresolved ? question : "", text: text, isUnresolved: structured))
                    blocks.append((!question.isEmpty && !unresolved ? question + "\n\n" : "") + text)
                } else if answer["richText"] != nil || answer["attributedText"] != nil { reasons.append("Ответ содержит rich text без обычного текста.") }
                if let refs = answer["assets"], !(refs is [String]) { throw BackupError.invalidRecord }
                for ref in answer["assets"] as? [String] ?? [] {
                    guard let asset = assets[ref], asset["answer"] as? String == aid,
                          let path = asset["relativePath"] as? String, StoicBackupReader.isSafePath(path) else { throw BackupError.invalidRecord }
                    let matches = files.filter { $0 == path || $0.hasSuffix("/" + path) }
                    guard matches.count <= 1 else { throw BackupError.invalidRecord }
                    if matches.isEmpty {
                        reasons.append("Отсутствует фотография: " + path)
                        continue
                    }
                    paths.append(matches[0])
                    if asset["type"] as? String == "image",
                       let metadata = asset["metadata"] as? [String: Any],
                       let latitude = metadata["latitude"] as? Double,
                       let longitude = metadata["longitude"] as? Double,
                       let latNumber = metadata["latitude"] as? NSNumber,
                       let lonNumber = metadata["longitude"] as? NSNumber,
                       CFGetTypeID(latNumber) != CFBooleanGetTypeID(), CFGetTypeID(lonNumber) != CFBooleanGetTypeID(),
                       let location = PhotoLocation(latitude: latitude, longitude: longitude) {
                        photoLocations[matches[0]] = location
                    }
                    if asset["type"] as? String != "image" { reasons.append("Вложение не является изображением.") }
                }
            }
            let stamp: Double
            if routine || orphan {
                guard let first = stamps.min() else { throw BackupError.invalidRecord }; stamp = first
            } else {
                guard let own = record["timestamp"] as? Double, own.isFinite, own >= 0, own <= 253402300799999 else { throw BackupError.invalidRecord }; stamp = own
            }
            let text = blocks.joined(separator: "\n\n")
            if text.isEmpty { reasons.append("Нет обычного текста; проверьте исходную запись.") }
            if paths.contains(where: { !["jpg", "jpeg", "png", "heic"].contains(URL(fileURLWithPath: $0).pathExtension.lowercased()) }) {
                reasons.append("Неподдерживаемое расширение изображения.")
            }
            let date = Date(timeIntervalSince1970: stamp / 1000)
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            var entry = JournalEntry(id: id, date: date, originalTimestamp: formatter.string(from: date), timeZone: nil, text: text, attachmentPaths: paths)
            entry.tags = EntryPresentation.normalizedTags(entryTags)
            entry.photoLocations = photoLocations
            entry.blocks = presentation
            entry.kind = routine ? (record["type"] as? String ?? "routine") : (orphan ? "checkin" : "journal")
            entry.notes = Array(Set(notes)).sorted()
            let source = try JSONSerialization.data(withJSONObject: ["record": record, "answers": linked], options: [.prettyPrinted, .sortedKeys])
            entry.sourceJSON = String(data: source, encoding: .utf8)
            if !entry.hasReadableText && !reasons.contains("Ответ содержит rich text без обычного текста.") {
                reasons.append("В записи только нерасшифрованные значения. Проверьте их перед импортом.")
            }
            entry.reviewReasons = Array(Set(reasons)).sorted()
            result.append(entry)
        }
        for record in try records("journal-entries.json", required: false) {
            if let refs = record["answers"], !(refs is [String]) { throw BackupError.invalidRecord }
            let linked = try (record["answers"] as? [String] ?? []).map { key in
                guard let value = answerMap[key] else { throw BackupError.invalidRecord }; return value
            }
            try build(record, linked: linked, routine: false)
        }
        for record in try records("routines.json", required: false) {
            let id = try identifier(record)
            let linked = answers.filter { $0["routine"] as? String == id }
            if linked.isEmpty { continue }
            let order = record["questions"] as? [String] ?? []
            let sorted = linked.enumerated().sorted { a, b in
                let ai = order.firstIndex(of: a.element["question"] as? String ?? "") ?? order.count
                let bi = order.firstIndex(of: b.element["question"] as? String ?? "") ?? order.count
                return ai == bi ? a.offset < b.offset : ai < bi
            }.map(\.element)
            try build(record, linked: sorted, routine: true)
        }
        for answer in answers where !used.contains(try identifier(answer)) {
            try build(answer, linked: [answer], routine: false, orphan: true)
        }
        return result
    }
}

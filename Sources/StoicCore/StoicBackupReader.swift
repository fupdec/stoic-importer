import Foundation
import ZIPFoundation

public struct StoicBackupReader: Sendable {
    public struct Limits: Sendable {
        public var maxArchiveBytes = 512 * 1024 * 1024
        public var maxMembers = 20_000
        public var maxJSONBytes = 32 * 1024 * 1024
        public var maxTotalJSONBytes = 128 * 1024 * 1024
        public var maxExpandedBytes: UInt64 = 2 * 1024 * 1024 * 1024
        public init() {}
    }
    public let limits: Limits
    public init(limits: Limits = Limits()) { self.limits = limits }
    public static func isSafePath(_ path: String) -> Bool {
        !path.isEmpty && !path.hasPrefix("/") && !path.contains("\\") && !path.contains("\0") &&
        !path.split(separator: "/", omittingEmptySubsequences: false).contains("..") &&
        !path.contains(":")
    }
    public func read(_ url: URL) throws -> Backup {
        let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
        guard size <= limits.maxArchiveBytes else { throw BackupError.resourceLimit }
        let archive: Archive
        do { archive = try Archive(url: url, accessMode: .read) }
        catch { throw BackupError.invalidArchive }
        var entries: [JournalEntry] = [], attachments: [String] = []
        var paths = Set<String>(), ids = Set<String>()
        var members = 0, jsonCount = 0, totalJSON = 0
        var expanded: UInt64 = 0
        var recognized = false
        var nativeCollections: [String: Data] = [:]
        for member in archive {
            members += 1
            guard members <= limits.maxMembers else { throw BackupError.resourceLimit }
            guard Self.isSafePath(member.path), member.type != .symlink,
                  paths.insert(member.path).inserted else { throw BackupError.unsafePath }
            guard member.uncompressedSize <= limits.maxExpandedBytes - expanded else { throw BackupError.resourceLimit }
            expanded += member.uncompressedSize
            guard member.type == .file else { continue }
            guard member.path.lowercased().hasSuffix(".json") else {
                attachments.append(member.path); continue
            }
            guard member.uncompressedSize <= UInt64(limits.maxJSONBytes) else { throw BackupError.resourceLimit }
            var data = Data()
            do {
                let checksum = try archive.extract(member) { chunk in
                    guard chunk.count <= limits.maxJSONBytes - data.count,
                          chunk.count <= limits.maxTotalJSONBytes - totalJSON else { throw BackupError.resourceLimit }
                    data.append(chunk); totalJSON += chunk.count
                }
                guard checksum == member.checksum else { throw BackupError.invalidArchive }
            } catch let error as BackupError { throw error }
              catch { throw BackupError.invalidArchive }
            jsonCount += 1
            let basename = URL(fileURLWithPath: member.path).lastPathComponent
            if ["answers.json", "assets.json", "journal-entries.json", "routines.json", "tags.json", "question-options.json"].contains(basename) {
                guard nativeCollections.updateValue(data, forKey: basename) == nil else { throw BackupError.unsupportedFormat }
                continue
            }
            if let converted = try JournalEntryConverter().convert(data) {
                recognized = true
                for entry in converted {
                    guard ids.insert(entry.id).inserted else { throw BackupError.duplicateID }
                    entries.append(entry)
                }
            }
        }
        if let native = try NativeStoicConverter.convert(nativeCollections, files: attachments) {
            guard !recognized else { throw BackupError.unsupportedFormat }
            recognized = true
            entries = native
        }
        guard recognized else { throw BackupError.unsupportedFormat }
        let available = Set(attachments)
        for index in entries.indices {
            for path in entries[index].attachmentPaths where !available.contains(path) {
                entries[index].reviewReasons.append("Отсутствует фотография: " + path)
            }
        }
        // Keep individual source entries and timestamps; grouping belongs to a later opt-in converter.
        return Backup(entries: entries.sorted { $0.date == $1.date ? $0.id < $1.id : $0.date < $1.date },
                      attachmentPaths: attachments.sorted(), jsonFileCount: jsonCount)
    }
}

import Foundation
import ZIPFoundation

public struct BridgePayload: Codable, Sendable {
    public let schema: String
    public let sourceID: String
    public let date: String
    public let text: String
    public let attachmentCount: Int
    public let attachmentFileNames: [String]
    public let location: PhotoLocation?
    public let locationFileName: String
}

public enum BridgeRequest {
    /// A fresh private folder is the only input to the shortcut. No archive parsing on device.
    public static func prepare(entry: JournalEntry, archiveURL: URL, parent: URL, includeUnresolved: Bool = false, language: AppLanguage = .russian) throws -> URL {
        guard entry.transferReviewReasons.isEmpty, (entry.hasReadableText || !entry.attachmentPaths.isEmpty) else { throw BackupError.invalidRecord }
        let folder = parent.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        do {
            var filenames: [String] = []
            var archive: Archive?
            if !entry.attachmentPaths.isEmpty {
                let opened: Archive = try Archive(url: archiveURL, accessMode: .read)
                archive = opened
            }
            for (index, path) in entry.attachmentPaths.enumerated() {
                guard StoicBackupReader.isSafePath(path) else { throw BackupError.unsafePath }
                let ext = URL(fileURLWithPath: path).pathExtension.lowercased()
                guard ["jpg", "jpeg", "png", "heic"].contains(ext) else { throw BackupError.invalidRecord }
                guard let archive, let member = archive[path], member.type == .file else { throw BackupError.invalidRecord }
                guard member.uncompressedSize <= 32 * 1024 * 1024 else { throw BackupError.resourceLimit }
                var bytes = Data()
                let crc = try archive.extract(member) { chunk in
                    guard bytes.count + chunk.count <= 32 * 1024 * 1024 else { throw BackupError.resourceLimit }
                    bytes.append(chunk)
                }
                guard crc == member.checksum else { throw BackupError.invalidArchive }
                let filename = String(format: "photo-%05d.", index + 1) + ext
                filenames.append(filename)
                try bytes.write(to: folder.appendingPathComponent(filename), options: .atomic)
                try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: folder.appendingPathComponent(filename).path)
            }
            if let location = entry.location {
                try PhotoLocationFile.write(location, to: folder.appendingPathComponent("location.jpg"))
            }
            let payload = BridgePayload(schema: "stoic-mac-bridge-v2", sourceID: entry.id, date: entry.originalTimestamp,
                                        text: entry.journalText(includeUnresolved: includeUnresolved, language: language), attachmentCount: entry.attachmentPaths.count, attachmentFileNames: filenames, location: entry.location,
                                        locationFileName: entry.location == nil ? "" : "location.jpg")
            let target = folder.appendingPathComponent("entry.json")
            try JSONEncoder().encode(payload).write(to: target, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: target.path)
            return folder
        } catch {
            try? FileManager.default.removeItem(at: folder)
            throw error
        }
    }
}

public extension BridgeRequest {
    static func imageData(path: String, archiveURL: URL) throws -> Data {
        guard StoicBackupReader.isSafePath(path), ["jpg", "jpeg", "png", "heic"].contains(URL(fileURLWithPath: path).pathExtension.lowercased()) else { throw BackupError.unsafePath }
        let archive = try Archive(url: archiveURL, accessMode: .read)
        guard let member = archive[path], member.type == .file, member.uncompressedSize <= 32 * 1024 * 1024 else { throw BackupError.resourceLimit }
        var data = Data()
        let crc = try archive.extract(member) { chunk in
            guard data.count + chunk.count <= 32 * 1024 * 1024 else { throw BackupError.resourceLimit }
            data.append(chunk)
        }
        guard crc == member.checksum else { throw BackupError.invalidArchive }
        return data
    }
}

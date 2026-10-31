import Foundation

public struct PhotoLocation: Codable, Equatable, Sendable {
    public let latitude: Double
    public let longitude: Double

    public init?(latitude: Double, longitude: Double) {
        guard latitude.isFinite, longitude.isFinite,
              (-90...90).contains(latitude), (-180...180).contains(longitude) else { return nil }
        self.latitude = latitude
        self.longitude = longitude
    }

    public var coordinateText: String { "\(latitude), \(longitude)" }
}

public struct JournalEntry: Codable, Identifiable, Equatable, Sendable {
    public let id: String
    public let date: Date
    public let originalTimestamp: String
    public let timeZone: String?
    public let text: String
    public let attachmentPaths: [String]
    public var reviewReasons: [String] = []
    public var editedTitle: String? = nil
    public var title: String = ""
    public var kind: String = "journal"
    public var blocks: [EntryBlock] = []
    public var notes: [String] = []
    public var tags: [String] = []
    public var sourceJSON: String? = nil
    public var photoLocations: [String: PhotoLocation] = [:]
    /// Only the first attached photo chooses the entry location; never fall through.
    public var location: PhotoLocation? { attachmentPaths.first.flatMap { photoLocations[$0] } }
}

public struct Backup: Sendable {
    public let entries: [JournalEntry]
    public let attachmentPaths: [String]
    public let jsonFileCount: Int
}

public enum BackupError: Error, Equatable, LocalizedError {
    case invalidArchive, unsafePath, resourceLimit, unsupportedFormat, invalidRecord, duplicateID
    public var errorDescription: String? {
        switch self {
        case .invalidArchive: "The ZIP is damaged, encrypted, or unreadable."
        case .unsafePath: "The archive contains an unsafe path or link."
        case .resourceLimit: "The archive exceeds the configured safety limits."
        case .unsupportedFormat: "No supported entry collection was found. This backup version needs an adapter."
        case .invalidRecord: "An entry has an invalid ID, date, timezone, or text. Nothing was imported."
        case .duplicateID: "Duplicate source IDs were found. Nothing was imported."
        }
    }
}

public struct ImportCapability: Sendable {
    public let canImport: Bool
    public let explanation: String
    public static let unverified = Self(canImport: false, explanation: "Journal Shortcuts integration is unverified on this Mac. Export JSON or verify the synthetic probe first.")
}

public protocol JournalImportBackend: Sendable {
    func capability() async -> ImportCapability
    func importEntry(_ entry: JournalEntry) async throws
}

/// No production writes until the historical-date probe has been verified.
public struct UnverifiedJournalBackend: JournalImportBackend {
    public init() {}
    public func capability() async -> ImportCapability { .unverified }
    public func importEntry(_ entry: JournalEntry) async throws { throw BackupError.unsupportedFormat }
}

extension JournalEntry {
    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(String.self, forKey: .id)
        date = try values.decode(Date.self, forKey: .date)
        originalTimestamp = try values.decode(String.self, forKey: .originalTimestamp)
        timeZone = try values.decodeIfPresent(String.self, forKey: .timeZone)
        text = try values.decode(String.self, forKey: .text)
        attachmentPaths = try values.decode([String].self, forKey: .attachmentPaths)
        reviewReasons = try values.decodeIfPresent([String].self, forKey: .reviewReasons) ?? []
        editedTitle = try values.decodeIfPresent(String.self, forKey: .editedTitle)
        title = try values.decodeIfPresent(String.self, forKey: .title) ?? ""
        kind = try values.decodeIfPresent(String.self, forKey: .kind) ?? "journal"
        blocks = try values.decodeIfPresent([EntryBlock].self, forKey: .blocks) ?? []
        notes = try values.decodeIfPresent([String].self, forKey: .notes) ?? []
        tags = try values.decodeIfPresent([String].self, forKey: .tags) ?? []
        sourceJSON = try values.decodeIfPresent(String.self, forKey: .sourceJSON)
        photoLocations = try values.decodeIfPresent([String: PhotoLocation].self, forKey: .photoLocations) ?? [:]
    }
}

import Foundation

/// Durable identity and order only; diary content stays in the source archive.
public struct TransferQueue: Codable, Equatable, Sendable {
    public let archiveDigest: String
    public let entryIDs: [String]
    public init(archiveDigest: String, entryIDs: [String]) {
        self.archiveDigest = archiveDigest
        var seen = Set<String>()
        self.entryIDs = entryIDs.filter { seen.insert($0).inserted }
    }
    public static func completed(_ receipt: String?) -> Bool {
        receipt == "returned" || receipt == "confirmed"
    }
    public static func needsReview(_ receipt: String?) -> Bool {
        receipt != nil && !completed(receipt) && receipt != "not-started"
    }
}

import Foundation
import Testing
@testable import StoicCore

struct TransferQueueTests {
    @Test func persistencePreservesOrderAndArchive() throws {
        let queue = TransferQueue(archiveDigest: "archive-a", entryIDs: ["b", "a", "b", "c"])
        let restored = try JSONDecoder().decode(TransferQueue.self, from: JSONEncoder().encode(queue))
        #expect(restored == queue)
        #expect(restored.entryIDs == ["b", "a", "c"])
        #expect(restored.archiveDigest == "archive-a")
    }
    @Test func ambiguousResultsBlockResume() {
        #expect(TransferQueue.needsReview("pending"))
        #expect(TransferQueue.needsReview("unexpected-state"))
        #expect(!TransferQueue.needsReview(nil))
        #expect(!TransferQueue.needsReview("not-started"))
        #expect(!TransferQueue.needsReview("confirmed"))
        #expect(!TransferQueue.needsReview("returned"))
        #expect(!TransferQueue.completed("pending"))
        #expect(!TransferQueue.completed("not-started"))
        #expect(TransferQueue.completed("returned"))
        #expect(TransferQueue.completed("confirmed"))
    }
}

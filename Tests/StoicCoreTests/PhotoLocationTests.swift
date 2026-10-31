import Foundation
import ImageIO
import Testing
@testable import StoicCore

struct PhotoLocationTests {
    func entry(first: [String: Any]?, second: [String: Any]? = nil) throws -> JournalEntry {
        let tests = NativeStoicTests()
        let assets: [[String: Any]] = [
            ["uuid": "p1", "answer": "a", "type": "image", "relativePath": "one.png", "metadata": first ?? [:]],
            ["uuid": "p2", "answer": "a", "type": "image", "relativePath": "two.png", "metadata": second ?? [:]]
        ]
        return try #require(NativeStoicConverter.convert(tests.collections(assets: assets, refs: ["p1", "p2"]), files: ["one.png", "two.png"])?.first)
    }

    @Test func firstPhotoWinsAndLaterPhotosNeverSupplyMissingLocation() throws {
        let first = ["latitude": 41.0, "longitude": 29.0]
        let second = ["latitude": -33.0, "longitude": -70.0]
        #expect(try entry(first: first, second: second).location == PhotoLocation(latitude: 41, longitude: 29))
        #expect(try entry(first: nil, second: second).location == nil)
        #expect(try entry(first: ["latitude": 91.0, "longitude": 0.0], second: second).location == nil)
        #expect(try entry(first: ["latitude": true, "longitude": false], second: second).location == nil)
        #expect(try entry(first: ["latitude": 0, "longitude": 0]).location == PhotoLocation(latitude: 0, longitude: 0))
    }

    @Test func revisionKeepsSourceOrderAndUsesFirstRemainingPhoto() throws {
        let source = try entry(first: ["latitude": 41.0, "longitude": 29.0], second: ["latitude": -33.0, "longitude": -70.0])
        var revision = EntryRevision(source: source)
        #expect(try revision.applying(to: source).location == source.location)
        revision.photoPaths = ["two.png"]
        #expect(try revision.applying(to: source).location == PhotoLocation(latitude: -33, longitude: -70))
        revision.photoPaths = []
        #expect(try revision.applying(to: source).location == nil)
    }

    @Test func bridgeWritesSeparateGPSCarrierAndDoesNotAttachIt() throws {
        try ParserTests().withZIP([("one.png", Data([1])), ("two.png", Data([2]))]) { archive in
            let source = try entry(first: ["latitude": -33.25, "longitude": -70.75])
            let folder = try BridgeRequest.prepare(entry: source, archiveURL: archive, parent: archive.deletingLastPathComponent())
            defer { try? FileManager.default.removeItem(at: folder) }
            let payload = try JSONDecoder().decode(BridgePayload.self, from: Data(contentsOf: folder.appendingPathComponent("entry.json")))
            #expect(payload.location == source.location)
            #expect(payload.locationFileName == "location.jpg")
            #expect(payload.attachmentCount == 2)
            #expect(!payload.attachmentFileNames.contains("location.jpg"))
            let image = try #require(CGImageSourceCreateWithURL(folder.appendingPathComponent("location.jpg") as CFURL, nil))
            let properties = try #require(CGImageSourceCopyPropertiesAtIndex(image, 0, nil) as? [String: Any])
            let gps = try #require(properties[kCGImagePropertyGPSDictionary as String] as? [String: Any])
            #expect(gps[kCGImagePropertyGPSLatitudeRef as String] as? String == "S")
            #expect(gps[kCGImagePropertyGPSLongitudeRef as String] as? String == "W")
            #expect(abs((gps[kCGImagePropertyGPSLatitude as String] as? Double ?? 0) - 33.25) < 0.000001)
        }
    }
}

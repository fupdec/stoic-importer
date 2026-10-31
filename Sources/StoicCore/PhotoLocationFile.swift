import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

/// A private GPS carrier for Shortcuts' native Image → Location conversion.
/// It is never included among the entry's photo attachments.
enum PhotoLocationFile {
    static func write(_ location: PhotoLocation, to url: URL) throws {
        guard PhotoLocation(latitude: location.latitude, longitude: location.longitude) != nil,
              let context = CGContext(data: nil, width: 1, height: 1, bitsPerComponent: 8,
                                      bytesPerRow: 4, space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue),
              let image = context.makeImage(),
              let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.jpeg.identifier as CFString, 1, nil)
        else { throw BackupError.invalidRecord }
        let gps: [CFString: Any] = [
            kCGImagePropertyGPSLatitude: abs(location.latitude),
            kCGImagePropertyGPSLatitudeRef: location.latitude < 0 ? "S" : "N",
            kCGImagePropertyGPSLongitude: abs(location.longitude),
            kCGImagePropertyGPSLongitudeRef: location.longitude < 0 ? "W" : "E"
        ]
        CGImageDestinationAddImage(destination, image, [kCGImagePropertyGPSDictionary: gps] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw BackupError.invalidRecord }
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
}

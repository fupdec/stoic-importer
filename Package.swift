// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "StoicToAppleJournal", platforms: [.macOS(.v14)],
    products: [.library(name: "StoicCore", targets: ["StoicCore"]), .executable(name: "stoic-importer", targets: ["StoicImporter"]), .executable(name: "StoicImporterApp", targets: ["StoicMacApp"])],
    dependencies: [.package(url: "https://github.com/weichsel/ZIPFoundation.git", from: "0.9.20")],
    targets: [
        .target(name: "StoicCore", dependencies: [.product(name: "ZIPFoundation", package: "ZIPFoundation")]),
        .executableTarget(name: "StoicImporter", dependencies: ["StoicCore"]),
        .executableTarget(name: "StoicMacApp", dependencies: ["StoicCore"]),
        .testTarget(name: "StoicCoreTests", dependencies: ["StoicCore", .product(name: "ZIPFoundation", package: "ZIPFoundation")], resources: [.copy("Fixtures")])
    ])

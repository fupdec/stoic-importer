import Foundation
import Darwin
import StoicCore

// Phase 0/1 diagnostic CLI. Diary content is only written to an explicitly chosen export.
@main struct StoicImporter {
    static func main() {
        let args = Array(CommandLine.arguments.dropFirst())
        guard args.count == 1 || (args.count == 3 && args[1] == "--export") else {
            print("Usage: stoic-importer backup.zip [--export destination.json]")
            return
        }
        do {
            let backup = try StoicBackupReader().read(URL(fileURLWithPath: args[0]))
            print("Entries: \(backup.entries.count); JSON files: \(backup.jsonFileCount); other files: \(backup.attachmentPaths.count)")
            print(ImportCapability.unverified.explanation)
            if args.count == 3 {
                let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
                encoder.dateEncodingStrategy = .iso8601
                let output = URL(fileURLWithPath: args[2])
                // Exclusive create: do not replace backups or previous exports.
                let data = try encoder.encode(backup.entries)
                let descriptor = open(output.path, O_WRONLY | O_CREAT | O_EXCL, mode_t(0o600))
                guard descriptor >= 0 else { throw CocoaError(.fileWriteUnknown) }
                let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
                do {
                    try handle.write(contentsOf: data)
                    try handle.synchronize()
                    try handle.close()
                } catch {
                    try? handle.close()
                    try? FileManager.default.removeItem(at: output)
                    throw error
                }
                print("Local intermediate JSON saved. This is not an Apple Journal import format.")
            }
        } catch {
            // Never print decoder diagnostics, archive paths, or diary text.
            let message = (error as? BackupError)?.errorDescription ?? "Could not read the backup or write the export."
            FileHandle.standardError.write(Data((message + "\n").utf8)); exit(1)
        }
    }
}

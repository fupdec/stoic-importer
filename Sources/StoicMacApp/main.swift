import SwiftUI
import AppKit
import UniformTypeIdentifiers
import CryptoKit
import StoicCore

@main
struct StoicMacApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var model = ImportModel()
    var body: some Scene {
        WindowGroup("Stoic Importer") { ImportView(model: model).frame(minWidth: 1020, minHeight: 680) }
            .defaultSize(width: 1320, height: 860)
            .windowStyle(.titleBar)
            .windowToolbarStyle(.unified)
            .commands {
                CommandGroup(replacing: .newItem) {
                    Button(L("Открыть архив Stoic…"), action: model.chooseArchive).keyboardShortcut("o").disabled(model.busy)
                }
            }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        if let url = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
           let icon = NSImage(contentsOf: url) {
            NSApplication.shared.applicationIconImage = icon
        }
    }
}

struct TransferEvent: Codable, Identifiable {
    var id = UUID()
    let date: Date
    let state: String
    let detail: String?
}

@MainActor
final class ImportModel: ObservableObject {
    @Published var entries: [JournalEntry] = [] { didSet { refreshList() } }
    @Published var selection: String?
    @Published var status = "Выберите ZIP-архив Stoic. Обработка выполняется на Mac."
    @Published var busy = false
    @Published var choosingArchive = false
    @Published var archiveName = ""
    @Published var onlyPhotos = false { didSet { refreshList() } }
    @Published private(set) var transferHistory: [String: [TransferEvent]] = [:]
    @Published var receipts: [String: String] = [:] { didSet { refreshList() } }
    @Published var shortcutName = {
        let saved = UserDefaults.standard.string(forKey: "writerShortcut")
        return saved == nil || saved == "StoicMacWriter" ? "StoicMacWriterV3" : saved!
    }() {
        didSet { UserDefaults.standard.set(shortcutName, forKey: "writerShortcut") }
    }
    @Published var language = currentLanguage {
        didSet {
            UserDefaults.standard.set(language.rawValue, forKey: "appLanguage")
            refreshList()
        }
    }
    let includeUnresolved = false
    var localizedStatus: String {
        if status.hasPrefix("Записей: ") {
            return LF("Записей: %d. Требуют проверки: %d. Исходный часовой пояс может отсутствовать в экспорте.", entries.count, entries.filter { $0.needsArchiveReview }.count)
        }
        return L(status)
    }
    @Published var search = "" { didSet { refreshList() } }
    @Published var searchOptions = EntrySearch() { didSet { refreshList() } }
    var availableTags: [String] { Array(Set(entries.flatMap(\.displayTags))).sorted { $0.localizedStandardCompare($1) == .orderedAscending } }
    func resetSearch() { search = ""; searchOptions = EntrySearch(); onlyPhotos = false }
    @Published var filter = EntryFilter.readable { didSet { refreshList() } }
    @Published var newestFirst = true { didSet { refreshList() } }
    @Published private(set) var visibleEntries: [JournalEntry] = []
    private func refreshList() {
        var criteria = searchOptions
        criteria.query = search
        let filtered = entries.filter { entry in
            let match = criteria.matches(entry) && (!onlyPhotos || !entry.attachmentPaths.isEmpty)
            switch filter {
            case .all: return match
            case .readable: return match && entry.hasReadableText
            case .ready: return match && entry.hasTransferContent && entry.transferReviewReasons.isEmpty && receipt(entry) == nil
            case .review: return match && entry.needsArchiveReview
            case .imported: return match && receipt(entry) != nil
            }
        }
        visibleEntries = newestFirst ? Array(filtered.reversed()) : filtered
    }
    func count(for filter: EntryFilter) -> Int {
        switch filter {
        case .all: return entries.count
        case .readable: return entries.filter(\.hasReadableText).count
        case .ready: return readyCount
        case .review: return entries.filter { $0.needsArchiveReview }.count
        case .imported: return entries.filter { receipt($0) != nil }.count
        }
    }
    var photoCount: Int { entries.filter { !$0.attachmentPaths.isEmpty }.count }
    func moveSelection(by step: Int, extending: Bool = false) {
        guard !visibleEntries.isEmpty else { return }
        let current = visibleEntries.firstIndex { $0.id == selection } ?? (step > 0 ? -1 : visibleEntries.count)
        selectEntry(visibleEntries[min(max(current + step, 0), visibleEntries.count - 1)].id, extending: extending, toggling: false)
    }
    var confirmedCount: Int { entries.filter { receipt($0) == "confirmed" }.count }
    var readyCount: Int { batchEntries.count }
    func receiptLabel(_ entry: JournalEntry) -> String {
        switch receipt(entry) {
        case "confirmed": return L("Подтверждено")
        case "returned": return L("Отправлено")
        case "pending": return L("Ожидает проверки")
        case "not-started": return L("Не удалось запустить команду")
        case .some: return L("Отправлялось ранее")
        case nil: return entry.transferReviewReasons.isEmpty ? L("Готово к импорту") : L("Нужна проверка")
        }
    }
    func photos(for entry: JournalEntry) async -> [Data] {
        guard let archiveURL else { return [] }
        return await Task.detached {
            entry.attachmentPaths.prefix(12).compactMap { try? BridgeRequest.imageData(path: $0, archiveURL: archiveURL) }
        }.value
    }
    private var originals: [String: JournalEntry] = [:]
    @Published private(set) var revisions: [String: EntryRevision] = [:]
    func original(for entry: JournalEntry) -> JournalEntry { originals[entry.id] ?? entry }
    private var revisionsURL: URL? {
        archiveDigest.map { root.appendingPathComponent("revisions-" + $0 + ".json") }
    }
    func saveRevision(_ revision: EntryRevision, for entry: JournalEntry) throws {
        guard !busy, receipt(entry) == nil, let revisionsURL, let archiveURL else { throw BackupError.invalidRecord }
        let copy = try revision.applying(to: original(for: entry))
        for path in copy.attachmentPaths { _ = try BridgeRequest.imageData(path: path, archiveURL: archiveURL) }
        var next = revisions; next[entry.id] = revision
        try JSONEncoder().encode(next).write(to: revisionsURL, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: revisionsURL.path)
        revisions = next
        entries = entries.map { $0.id == entry.id ? copy : $0 }
    }
    func restoreOriginal(_ entry: JournalEntry) throws {
        guard !busy, receipt(entry) == nil, let revisionsURL else { throw BackupError.invalidRecord }
        var next = revisions; next.removeValue(forKey: entry.id)
        try JSONEncoder().encode(next).write(to: revisionsURL, options: .atomic)
        revisions = next
        entries = entries.map { $0.id == entry.id ? original(for: entry) : $0 }
    }
    private var archiveURL: URL?
    private var archiveDigest: String?
    private var process: Process?
    private let root: URL
    private let ledgerURL: URL
    private var historyURL: URL { root.appendingPathComponent("transfer-history.json") }
    private var queueURL: URL { root.appendingPathComponent("transfer-queue.json") }
    @Published private(set) var transferQueue: TransferQueue?
    @Published var checkedIDs: Set<String> = []
    @Published var showingQueue = false
    @Published private(set) var pauseRequested = false
    private var queueReadable = true
    var selected: JournalEntry? { entries.first { $0.id == selection } }
    init() {
        root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("StoicImporter", isDirectory: true)
        ledgerURL = root.appendingPathComponent("receipts.json")
        do {
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            if FileManager.default.fileExists(atPath: historyURL.path) {
                transferHistory = try JSONDecoder().decode([String: [TransferEvent]].self, from: Data(contentsOf: historyURL))
            }
            if FileManager.default.fileExists(atPath: ledgerURL.path) {
                receipts = try JSONDecoder().decode([String: String].self, from: Data(contentsOf: ledgerURL))
            }
            if FileManager.default.fileExists(atPath: queueURL.path) {
                do { transferQueue = try JSONDecoder().decode(TransferQueue.self, from: Data(contentsOf: queueURL)) }
                catch { queueReadable = false; status = "Не удалось прочитать очередь переноса." }
            }
            if receipts.values.contains("pending") { status = "Есть незавершённая отправка. Проверьте Дневник перед повтором." }
        } catch { status = "Не удалось прочитать журнал прогресса. Отправка заблокирована."; ledgerReadable = false }
    }
    private var ledgerReadable = true
    func key(_ entry: JournalEntry) -> String { SHA256.hash(data: Data(entry.id.utf8)).map { String(format: "%02x", $0) }.joined() }
    func receipt(_ entry: JournalEntry) -> String? { receipts[key(entry)] }
    func events(for entry: JournalEntry) -> [TransferEvent] { transferHistory[key(entry)] ?? [] }
    func record(_ entry: JournalEntry, state: String, detail: String? = nil) throws {
        var next = transferHistory
        next[key(entry), default: []].append(TransferEvent(date: Date(), state: state, detail: detail))
        try JSONEncoder().encode(next).write(to: historyURL, options: .atomic)
        transferHistory = next
    }
    func save(_ entry: JournalEntry, state: String) throws {
        var next = receipts; next[key(entry)] = state
        try JSONEncoder().encode(next).write(to: ledgerURL, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: ledgerURL.path)
        receipts = next
        try record(entry, state: state)
    }
    func chooseArchive() {
        guard !busy, !choosingArchive else { return }
        choosingArchive = true
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.zip]
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = false
        let completion: @MainActor (NSApplication.ModalResponse) -> Void = { [weak self] result in
            self?.choosingArchive = false
            guard result == .OK, let url = panel.url else { return }
            self?.loadArchive(url)
        }
        if let window = NSApp.keyWindow { panel.beginSheetModal(for: window, completionHandler: completion) }
        else { panel.begin(completionHandler: completion) }
    }
    func restoreArchive() {
        guard entries.isEmpty, !busy, let path = UserDefaults.standard.string(forKey: "lastArchivePath"),
              FileManager.default.fileExists(atPath: path) else { return }
        loadArchive(URL(fileURLWithPath: path))
    }
    private func loadArchive(_ url: URL) {
        busy = true; status = "Чтение архива…"
        Task {
            do {
                let loaded = try await Task.detached { () -> (Backup, String) in
                    let digest = try Self.digest(url)
                    return (try StoicBackupReader().read(url), digest)
                }.value
                archiveURL = url; archiveDigest = loaded.1; archiveName = url.lastPathComponent
                originals = Dictionary(uniqueKeysWithValues: loaded.0.entries.map { ($0.id, $0) })
                revisions = [:]
                if let revisionsURL, FileManager.default.fileExists(atPath: revisionsURL.path) {
                    revisions = try JSONDecoder().decode([String: EntryRevision].self, from: Data(contentsOf: revisionsURL))
                }
                entries = try loaded.0.entries.map { source in
                    try revisions[source.id]?.applying(to: source) ?? source
                }
                checkedIDs = []
                selection = visibleEntries.first?.id
                UserDefaults.standard.set(url.path, forKey: "lastArchivePath")
                status = "Записей: \(entries.count). Требуют проверки: \(entries.filter { $0.needsArchiveReview }.count). Исходный часовой пояс может отсутствовать в экспорте."
            } catch {
                entries = []; originals = [:]; revisions = [:]; selection = nil
                archiveURL = nil; archiveDigest = nil
                status = (error as? BackupError)?.errorDescription ?? "Не удалось прочитать архив."
            }
            busy = false
        }
    }
    nonisolated static func digest(_ url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
        var hash = SHA256()
        while let data = try handle.read(upToCount: 1024 * 1024), !data.isEmpty { hash.update(data: data) }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }
    var singleTransferBlockReason: String? {
        guard let entry = selected else { return "Выберите запись." }
        if busy { return "Дождитесь завершения текущей операции." }
        if !ledgerReadable { return "Не удалось прочитать журнал прогресса. Отправка заблокирована." }
        if !queueReadable { return "Не удалось прочитать очередь переноса." }
        if receipts.values.contains(where: { TransferQueue.needsReview($0) }) {
            return "Сначала проверьте результат предыдущей отправки в очереди."
        }
        if !entry.transferReviewReasons.isEmpty { return "Причина указана выше" }
        if !entry.hasReadableText && entry.attachmentPaths.isEmpty { return "В записи нет текста и фотографий." }
        if receipt(entry) != nil { return "Проверьте результат" }
        if shortcutName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Укажите имя команды в настройках." }
        if archiveURL == nil || archiveDigest == nil { return "Откройте архив Stoic." }
        return nil
    }
    var canSend: Bool { singleTransferBlockReason == nil }
    var singleTransferNeedsReview: Bool {
        receipts.values.contains(where: { TransferQueue.needsReview($0) })
    }
    var batchCompleted: Int { queuedEntries.filter { TransferQueue.completed(receipt($0)) }.count }
    var batchTotal: Int { transferQueue?.entryIDs.count ?? 0 }
    private var stopRequested = false
    var batchEntries: [JournalEntry] {
        entries.filter { $0.transferReviewReasons.isEmpty && ($0.hasReadableText || !$0.attachmentPaths.isEmpty) && receipt($0) == nil }
            .sorted { $0.date == $1.date ? $0.id < $1.id : $0.date < $1.date }
    }
    var queueMatchesArchive: Bool { transferQueue?.archiveDigest == archiveDigest && archiveDigest != nil }
    var queuedEntries: [JournalEntry] {
        guard queueMatchesArchive, let transferQueue else { return [] }
        let byID = Dictionary(uniqueKeysWithValues: entries.map { ($0.id, $0) })
        return transferQueue.entryIDs.compactMap { byID[$0] }
    }
    var blockedEntry: JournalEntry? { queuedEntries.first { TransferQueue.needsReview(receipt($0)) } ?? entries.first { TransferQueue.needsReview(receipt($0)) } }
    var queueIncomplete: Bool { transferQueue != nil && (batchCompleted < batchTotal || !queueMatchesArchive) }
    var canSendBatch: Bool {
        ledgerReadable && queueReadable && !busy && archiveURL != nil && !batchEntries.isEmpty && !queueIncomplete
    }
    var canResumeQueue: Bool {
        ledgerReadable && queueReadable && !busy && queueMatchesArchive && queuedEntries.count == batchTotal && batchCompleted < batchTotal && blockedEntry == nil &&
        !receipts.values.contains(where: { TransferQueue.needsReview($0) }) &&
        queuedEntries.filter { !TransferQueue.completed(receipt($0)) }.allSatisfy { $0.transferReviewReasons.isEmpty } &&
        !shortcutName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    private var selectionAnchor: String?
    func selectEntry(_ id: String, extending extendOverride: Bool? = nil, toggling toggleOverride: Bool? = nil) {
        let modifiers = NSApp.currentEvent?.modifierFlags ?? NSEvent.modifierFlags
        let extending = extendOverride ?? modifiers.contains(.shift)
        checkedIDs = EntrySelection.selecting(id, in: visibleEntries.map(\.id), selected: checkedIDs,
            anchor: selectionAnchor ?? selection, extending: extending, toggling: toggleOverride ?? modifiers.contains(.command))
        if !extending { selectionAnchor = id }
        selection = checkedIDs.contains(id) ? id : visibleEntries.first(where: { checkedIDs.contains($0.id) })?.id
    }
    func selectAllVisible() {
        checkedIDs = Set(visibleEntries.map(\.id))
        if selection == nil { selection = visibleEntries.first?.id }
        selectionAnchor = selection
    }
    func clearSelection() { checkedIDs = []; selection = nil; selectionAnchor = nil }
    func reconcileSelection() {
        checkedIDs.formIntersection(visibleEntries.map(\.id))
        if checkedIDs.isEmpty, let selection, visibleEntries.contains(where: { $0.id == selection }) { checkedIDs.insert(selection) }
        if !visibleEntries.contains(where: { $0.id == selection }) {
            selection = visibleEntries.first(where: { checkedIDs.contains($0.id) })?.id ?? visibleEntries.first?.id
            if let selection { checkedIDs.insert(selection) }
        }
        if !visibleEntries.contains(where: { $0.id == selectionAnchor }) { selectionAnchor = selection }
    }
    func prepareQueue(all: Bool = false) {
        guard canSendBatch, let archiveDigest else { return }
        let chosen = batchEntries.filter { all || checkedIDs.contains($0.id) }
        guard !chosen.isEmpty else { return }
        let queue = TransferQueue(archiveDigest: archiveDigest, entryIDs: chosen.map(\.id))
        do {
            try JSONEncoder().encode(queue).write(to: queueURL, options: [.atomic, .completeFileProtectionUnlessOpen])
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: queueURL.path)
            transferQueue = queue; showingQueue = true
        } catch { status = "Не удалось сохранить очередь переноса." }
    }
    func send() {
        guard canSend, let entry = selected else { return }
        // A single transfer does not replace or resume the saved batch queue.
        sendEntries([entry])
    }
    func sendBatch() { prepareQueue(all: true) }
    func resumeQueue() {
        guard canResumeQueue else { return }
        sendEntries(queuedEntries.filter { !TransferQueue.completed(receipt($0)) })
    }
    func discardQueue() {
        guard !busy else { return }
        do {
            if FileManager.default.fileExists(atPath: queueURL.path) { try FileManager.default.removeItem(at: queueURL) }
            transferQueue = nil
        } catch { status = "Не удалось сохранить очередь переноса." }
    }
    func removeFromQueue(_ entry: JournalEntry) {
        guard !busy, receipt(entry) == nil, let old = transferQueue else { return }
        let next = TransferQueue(archiveDigest: old.archiveDigest, entryIDs: old.entryIDs.filter { $0 != entry.id })
        do {
            try JSONEncoder().encode(next).write(to: queueURL, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: queueURL.path)
            transferQueue = next
        } catch { status = "Не удалось сохранить очередь переноса." }
    }
    func pause() { pauseRequested = true }
    private func sendEntries(_ queue: [JournalEntry]) {
        guard let archiveURL, let archiveDigest else { return }
        let writer = shortcutName
        let importLanguage = language
        let includeDetails = includeUnresolved
        busy = true; stopRequested = false; pauseRequested = false
        status = "Подготовка выбранной записи…"
        Task { [self] in
            defer { process = nil; busy = false }
            var attemptedEntry: JournalEntry?
            do {
                guard try await Task.detached(operation: { try Self.digest(archiveURL) }).value == archiveDigest else { throw BackupError.invalidArchive }
                for entry in queue {
                    if pauseRequested { status = "Очередь на паузе. Можно продолжить позже."; return }
                    if stopRequested { status = "Перенос остановлен. Проверьте последнюю запись в Дневнике."; return }
                    guard receipt(entry) == nil || receipt(entry) == "not-started" else { return }
                    attemptedEntry = entry
                    try record(entry, state: "preparing")
                    let parent = root.appendingPathComponent("Requests", isDirectory: true)
                    let folder = try await Task.detached {
                        try BridgeRequest.prepare(entry: entry, archiveURL: archiveURL, parent: parent, includeUnresolved: includeDetails, language: importLanguage)
                    }.value
                    defer { try? FileManager.default.removeItem(at: folder) }
                    if pauseRequested { status = "Очередь на паузе. Можно продолжить позже."; return }
                    if stopRequested { status = "Перенос остановлен. Проверьте последнюю запись в Дневнике."; return }
                    selection = entry.id
                    let diagnosticURL = folder.appendingPathComponent("shortcut-error.log")
                    try Data().write(to: diagnosticURL, options: .atomic)
                    let diagnosticHandle = try FileHandle(forWritingTo: diagnosticURL)
                    defer { try? diagnosticHandle.close() }
                    // Commit before invoking the writer; ambiguous results block automatic retries.
                    try save(entry, state: "pending")
                    let task = Process()
                    task.executableURL = URL(fileURLWithPath: "/usr/bin/shortcuts")
                    task.arguments = ["run", writer, "--input-path", folder.path]
                    task.standardOutput = FileHandle.nullDevice; task.standardError = diagnosticHandle
                    process = task
                    status = "Команда запущена. Завершите её в Командах и проверьте Дневник."
                    let code: Int32
                    do {
                        code = try await withCheckedThrowingContinuation { continuation in
                            task.terminationHandler = { finished in continuation.resume(returning: finished.terminationStatus) }
                            do { try task.run() }
                            catch { task.terminationHandler = nil; continuation.resume(throwing: error) }
                        }
                    } catch {
                        process = nil
                        try save(entry, state: "not-started")
                        try record(entry, state: "not-started", detail: error.localizedDescription)
                        throw error
                    }
                    process = nil
                    guard code == 0 else {
                        try? diagnosticHandle.synchronize()
                        let diagnosticReader = try FileHandle(forReadingFrom: diagnosticURL)
                        defer { try? diagnosticReader.close() }
                        let diagnosticData = try diagnosticReader.read(upToCount: 16_384) ?? Data()
                        let diagnostic = String(decoding: diagnosticData, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
                        let summary = LF("Команда завершилась с кодом %d. Результат неизвестен — проверьте Дневник.", code)
                        try record(entry, state: "pending", detail: diagnostic.isEmpty ? summary : summary + "\n" + diagnostic)
                        status = "Команда прервалась или недоступна. Результат неизвестен: проверьте Дневник. Автоповтор отключён."
                        return
                    }
                    do { try save(entry, state: "returned") }
                    catch {
                        try? record(entry, state: "pending", detail: error.localizedDescription)
                        status = "Команда завершилась, но прогресс не сохранён. Проверьте Дневник."; return
                    }
                    if pauseRequested { status = "Очередь на паузе. Можно продолжить позже."; return }
                    if stopRequested { status = "Перенос остановлен. Проверьте последнюю запись в Дневнике."; return }
                }
                status = "Перенос завершён. Проверьте записи, даты и фотографии в Дневнике."
            } catch {
                if let attemptedEntry { try? record(attemptedEntry, state: "error", detail: error.localizedDescription) }
                status = "Отправка не выполнена. Проверьте установленную команду и журнал прогресса."
            }
        }
    }
    func confirm() {
        guard let entry = selected, !busy, receipt(entry) != nil, receipt(entry) != "confirmed" else { return }
        do { try save(entry, state: "confirmed"); status = "Запись отмечена как проверенная в Дневнике." }
        catch { status = "Не удалось сохранить подтверждение." }
    }
    func allowRetry() {
        guard let entry = selected, !busy, receipt(entry) != nil else { return }
        let alert = NSAlert(); alert.messageText = L("Запись точно отсутствует в Дневнике?")
        alert.informativeText = L("Повторная отправка может создать дубль. Сбросьте отметку только после проверки в Дневнике.")
        alert.addButton(withTitle: L("Отмена")); alert.addButton(withTitle: L("Проверил: записи нет"))
        guard alert.runModal() == .alertSecondButtonReturn else { return }
        do {
            var next = receipts; next.removeValue(forKey: key(entry))
            try JSONEncoder().encode(next).write(to: ledgerURL, options: .atomic)
            receipts = next
            try record(entry, state: "retry")
            status = "Повторная отправка разрешена вручную."
        } catch { status = "Не удалось обновить прогресс." }
    }
    func stop() { stopRequested = true; if process?.isRunning == true { process?.terminate() } }
}

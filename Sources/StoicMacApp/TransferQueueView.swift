import SwiftUI
import StoicCore

struct TransferQueueView: View {
    @ObservedObject var model: ImportModel
    @Environment(\.dismiss) private var dismiss
    @State private var history = false
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(L("Очередь и история переноса")).font(.title2)
                Spacer()
                Button(L("Закрыть")) { dismiss() }.keyboardShortcut(.cancelAction)
            }
            Text(L("Записи переносятся от старых к новым. Пауза действует после текущей записи. Очередь сохраняется автоматически; после перезапуска нажмите «Продолжить»."))
                .font(.callout).foregroundStyle(.secondary)
            Text(LF("Отправлено: %d из %d", model.batchCompleted, model.batchTotal)).monospacedDigit()
            Text(model.localizedStatus).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            if model.transferQueue != nil && !model.queueMatchesArchive {
                Text(L("Откройте исходный архив очереди, чтобы продолжить.")).foregroundStyle(.orange)
            }
            if let blocked = model.blockedEntry {
                Text(L("Результат неизвестен. Проверьте запись в Дневнике перед продолжением. При остановке команды дождитесь завершения её работы в Командах."))
                    .foregroundStyle(.orange)
                HStack {
                    Button(L("Запись есть в Дневнике")) { model.selection = blocked.id; model.confirm() }
                    Button(L("Записи нет — разрешить повтор…")) { model.selection = blocked.id; model.allowRetry() }
                }.disabled(model.busy)
            }
            Picker(L("Показать"), selection: $history) {
                Text(L("Очередь переноса")).tag(false)
                Text(L("История переноса")).tag(true)
            }.pickerStyle(.segmented)
            HStack(spacing: 20) {
                Label("\(model.entries.filter { model.receipt($0) == "returned" }.count) " + L("Отправлено"), systemImage: "paperplane.fill")
                Label("\(model.entries.filter { TransferQueue.needsReview(model.receipt($0)) }.count) " + L("Ожидает проверки"), systemImage: "clock")
                Label("\(model.confirmedCount) " + L("Подтверждено"), systemImage: "checkmark.seal.fill").foregroundStyle(.green)
            }.font(.caption)
            Text(L("Отправлено — команда завершилась. Подтвердите результат после проверки записи в Дневнике."))
                .font(.caption).foregroundStyle(.secondary)
            List(history ? model.entries.filter { model.receipt($0) != nil || !model.events(for: $0).isEmpty } : model.queuedEntries) { entry in
                VStack(alignment: .leading, spacing: 6) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(entry.presentationTitle(language: model.language)).lineLimit(2)
                        Text(JournalDates.full(entry.date)).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if !entry.attachmentPaths.isEmpty { Label("\(entry.attachmentPaths.count)", systemImage: "photo") }
                    Text(model.receiptLabel(entry)).font(.caption.weight(.semibold))
                        .foregroundStyle(model.receipt(entry) == "confirmed" ? Color.green : Color.accentColor)
                    if model.receipt(entry) == nil {
                        Button { model.removeFromQueue(entry) } label: { Image(systemName: "minus.circle") }.disabled(model.busy).help(L("Убрать из очереди"))
                    }
                    Button { model.selection = entry.id; dismiss() } label: { Image(systemName: "book") }.help(L("Откройте воспоминание"))
                }
                if let latest = model.events(for: entry).last {
                    Text(latest.date.formatted(.dateTime.day().month().year().hour().minute().second().locale(model.language.locale)))
                        .font(.caption).foregroundStyle(.secondary)
                    if let detail = latest.detail { Text(detail).font(.caption).foregroundStyle(.orange).textSelection(.enabled) }
                }
                if !model.events(for: entry).isEmpty {
                    DisclosureGroup(L("История попыток")) {
                        TransferEventsView(events: model.events(for: entry), language: model.language)
                    }.font(.caption)
                } else if model.receipt(entry) != nil {
                    Text(L("Время прошлой попытки не сохранено")).font(.caption).foregroundStyle(.secondary)
                }
                }.padding(.vertical, 4)
            }
            HStack {
                Button(L("Убрать очередь"), action: model.discardQueue).disabled(model.busy || model.transferQueue == nil)
                Spacer()
                if model.busy {
                    Button(L(model.pauseRequested ? "Пауза после текущей записи" : "Пауза"), action: model.pause).disabled(model.pauseRequested)
                    Button(L("Остановить"), action: model.stop)
                } else {
                    Button(L("Продолжить"), action: model.resumeQueue).buttonStyle(.borderedProminent).disabled(!model.canResumeQueue)
                }
            }
        }.padding(24).frame(width: 780, height: 580)
    }
}

struct TransferEventsView: View {
    let events: [TransferEvent]
    let language: AppLanguage
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(events.reversed()) { event in
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text(label(event.state)).fontWeight(.medium)
                        Spacer()
                        Text(event.date.formatted(.dateTime.day().month().year().hour().minute().second().locale(language.locale)))
                            .foregroundStyle(.secondary)
                    }
                    if let detail = event.detail {
                        Text(detail).foregroundStyle(.orange).textSelection(.enabled)
                    }
                }
            }
        }.font(.caption).padding(.vertical, 6)
    }
    private func label(_ state: String) -> String {
        switch state {
        case "preparing": L("Начало попытки")
        case "returned": L("Отправлено")
        case "confirmed": L("Подтверждено")
        case "pending": L("Ожидает проверки")
        case "not-started": L("Не удалось запустить команду")
        case "retry": L("Повторная отправка разрешена вручную.")
        default: L("Ошибка переноса")
        }
    }
}

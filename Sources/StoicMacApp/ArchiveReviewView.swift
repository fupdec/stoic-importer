import SwiftUI
import StoicCore

struct ArchiveReviewView: View {
    @ObservedObject var model: ImportModel
    let openEntry: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    private var attention: [JournalEntry] { model.entries.filter(\.needsArchiveReview) }
    private var missing: [JournalEntry] { model.entries.filter { !$0.missingPhotoPaths.isEmpty } }
    private var unresolved: [JournalEntry] {
        model.entries.filter { !$0.unresolvedBlocks.isEmpty || !$0.notes.isEmpty || $0.reviewReasons.contains("Ответ содержит rich text без обычного текста.") }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(L("Проверка архива")).font(.title2.bold())
                    Text(model.archiveName).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button(L("Закрыть")) { dismiss() }.keyboardShortcut(.cancelAction)
            }
            HStack(spacing: 24) {
                metric("Готовы к переносу", model.readyCount, "checkmark.circle")
                metric("Нужна проверка", attention.count, "exclamationmark.circle")
                metric("Отсутствуют фотографии", missing.count, "photo")
                metric("Нераспознанные данные", unresolved.count, "questionmark.circle")
            }
            Text(L("Счётчики проблем показывают количество записей и могут пересекаться. Предупреждения не всегда мешают переносу доступного текста.")).font(.caption).foregroundStyle(.secondary)
            Divider()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 20) {
                    if attention.isEmpty {
                        Label(L("Проблем не найдено"), systemImage: "checkmark.seal").foregroundStyle(.green)
                    }
                    ForEach(attention) { entry in
                        Button {
                            dismiss()
                            openEntry(entry.id)
                        } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text(entry.date.formatted(date: .abbreviated, time: .shortened)).foregroundStyle(.secondary)
                                    Text(entry.presentationTitle(language: model.language)).fontWeight(.semibold)
                                    Spacer()
                                    Image(systemName: "arrow.up.right")
                                }
                                ForEach(entry.archiveReviewDetails, id: \.self) { detail in
                                    Text(L(detail)).font(.callout)
                                }
                                ForEach(Array(entry.unresolvedBlocks.enumerated()), id: \.offset) { index, block in
                                    Text(LF("Ответ %d", index + 1) + ": " + EntryPresentation.structuredValue(block.text))
                                        .font(.system(.callout, design: .monospaced))
                                }
                            }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                                .contentShape(Rectangle())
                        }.buttonStyle(.plain).help(L("Откройте воспоминание"))
                    }
                }
            }
        }.padding(24).frame(minWidth: 780, idealWidth: 880, minHeight: 520, idealHeight: 680)
    }

    private func metric(_ title: String, _ count: Int, _ symbol: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(count.formatted(), systemImage: symbol).font(.title2).monospacedDigit()
            Text(L(title)).font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

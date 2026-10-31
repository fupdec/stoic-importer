import SwiftUI
import StoicCore

struct EntryEditor: View {
    let entry: JournalEntry
    @ObservedObject var model: ImportModel
    @Environment(\.dismiss) private var dismiss
    @State private var draft: EntryRevision
    @State private var failed = false

    init(entry: JournalEntry, model: ImportModel) {
        self.entry = entry
        self.model = model
        _draft = State(initialValue: model.revisions[entry.id] ?? EntryRevision(source: entry, includeUnresolved: model.includeUnresolved))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(L("Редактировать копию")).font(.title2)
            Text(L("Исходник сохранён. В Дневник будет отправлена эта копия.")).font(.callout).foregroundStyle(.secondary)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    TextField(L("Заголовок"), text: $draft.title)
                    DatePicker(L("Дата"), selection: $draft.date, in: Date(timeIntervalSince1970: 0)...Date(timeIntervalSince1970: 253402300799), displayedComponents: [.date, .hourAndMinute])
                    Text(L("Текст")).font(.headline)
                    TextEditor(text: $draft.text).font(.body).frame(minHeight: 220).border(.secondary.opacity(0.3))
                    if !entry.unresolvedBlocks.isEmpty {
                        Text(L("Дополнительные ответы")).font(.headline)
                        Text(L("Выбранные ответы будут добавлены к тексту копии.")).font(.caption).foregroundStyle(.secondary)
                        ForEach(Array(entry.unresolvedBlocks.enumerated()), id: \.offset) { index, block in
                            Toggle(isOn: Binding(get: { draft.answerIndices.contains(index) }, set: { if $0 { draft.answerIndices.insert(index) } else { draft.answerIndices.remove(index) } })) {
                                Text(LF("Ответ %d", index + 1) + ": " + EntryPresentation.structuredValue(block.text)).textSelection(.enabled)
                            }
                        }
                    }
                    if !entry.attachmentPaths.isEmpty {
                        Text(L("Фотографии")).font(.headline)
                        ForEach(entry.attachmentPaths, id: \.self) { path in
                            Toggle(path, isOn: Binding(get: { draft.photoPaths.contains(path) }, set: { if $0 { draft.photoPaths.insert(path) } else { draft.photoPaths.remove(path) } }))
                        }
                    }
                    if failed { Text(L("Не удалось сохранить копию. Проверьте текст и выбранные фотографии.")).foregroundStyle(.red) }
                }.padding(4)
            }
            HStack {
                Button(L("Отмена")) { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button(L("Сохранить копию")) {
                    do { try model.saveRevision(draft, for: entry); dismiss() } catch { failed = true }
                }.keyboardShortcut(.defaultAction).disabled((try? draft.applying(to: entry)) == nil)
            }
        }.padding(24).frame(width: 650, height: 650)
    }
}

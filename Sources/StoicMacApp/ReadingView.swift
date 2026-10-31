import SwiftUI
import AppKit
import ImageIO
import UniformTypeIdentifiers
import StoicCore

struct ReadingView: View {
    let entry: JournalEntry
    @ObservedObject var model: ImportModel
    @Binding var readingSize: Double
    @State private var images: [NSImage] = []
    @State private var loadingImages = false
    @State private var journalPreview = false
    @State private var copied = false
    @State private var photoIndex: Int?
    @State private var showingSource = false
    @State private var sourceError = false
    @State private var editing = false
    @State private var revisionError = false
    @Environment(\.colorScheme) private var colorScheme
    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    heading
                    revisionActions
                    if !entry.transferReviewReasons.isEmpty { warnings }
                    if journalPreview {
                        VStack(alignment: .leading, spacing: 14) {
                            Label(L("ТЕКСТ ДЛЯ ДНЕВНИКА"), systemImage: "square.and.arrow.up").font(.system(size: 9, weight: .semibold)).tracking(1.2).foregroundStyle(.tertiary)
                            Text(searchHighlight(entry.journalText(includeUnresolved: model.includeUnresolved, language: model.language), query: model.search)).font(.system(size: readingSize)).lineSpacing(8).textSelection(.enabled)
                        }
                    } else { prose }
                    if !entry.attachmentPaths.isEmpty { photographs }
                    if !entry.unresolvedBlocks.isEmpty { additionalAnswers }
                    sourceDetails
                    HStack {
                        Rectangle().fill(Color.primary.opacity(0.08)).frame(height: 1)
                        Image(systemName: "sparkle").font(.system(size: 9)).foregroundStyle(Color.journalAccent.opacity(0.5))
                        Rectangle().fill(Color.primary.opacity(0.08)).frame(height: 1)
                    }.padding(.vertical, 16).accessibilityHidden(true)
                }.frame(maxWidth: 650, alignment: .leading).padding(.horizontal, 44).padding(.top, 34).padding(.bottom, 30).frame(maxWidth: .infinity)
            }.safeAreaInset(edge: .bottom, spacing: 0) { actionBar.padding(.horizontal, 22).padding(.bottom, 18).padding(.top, 8) }
        }.background(Color(nsColor: .textBackgroundColor))
            .toolbar { readingToolbar }
            .task(id: entry.id + entry.attachmentPaths.joined(separator: "|")) { await loadImages() }
            .sheet(isPresented: $showingSource) {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Text(L("Исходные данные записи")).font(.headline)
                        Spacer()
                        Button(L("Закрыть")) { showingSource = false }.keyboardShortcut(.cancelAction)
                    }
                    Text(L("Здесь показаны исходная запись и связанные ответы из архива Stoic. Сверьте их с записью в Stoic перед переносом.")).font(.callout).foregroundStyle(.secondary)
                    ScrollView([.horizontal, .vertical]) {
                        Text(sourceText).font(.system(size: 12, design: .monospaced)).textSelection(.enabled).padding(12)
                    }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    Button(L("Сохранить исходник…")) { saveSource() }
                }.padding(24).frame(minWidth: 650, idealWidth: 800, minHeight: 450, idealHeight: 600)
            }
            .sheet(isPresented: $editing) { EntryEditor(entry: model.original(for: entry), model: model) }
            .alert(L("Не удалось сохранить копию. Проверьте текст и выбранные фотографии."), isPresented: $revisionError) { Button("OK", role: .cancel) {} }
            .alert(L("Не удалось сохранить исходник."), isPresented: $sourceError) { Button("OK", role: .cancel) {} }
            .sheet(isPresented: Binding(get: { photoIndex != nil }, set: { if !$0 { photoIndex = nil } })) {
                VStack(spacing: 16) {
                    HStack { Text(L("Фотографии")).font(.headline); Spacer(); Button(L("Закрыть")) { photoIndex = nil }.keyboardShortcut(.cancelAction) }
                    if let index = photoIndex, images.indices.contains(index) {
                        Image(nsImage: images[index]).resizable().scaledToFit().frame(maxWidth: .infinity, maxHeight: .infinity)
                        HStack {
                            Button { photoIndex = max(0, index - 1) } label: { Image(systemName: "chevron.left") }.disabled(index == 0)
                            Text(LF("%d из %d", index + 1, images.count)).font(.caption).monospacedDigit().frame(width: 90)
                            Button { photoIndex = min(images.count - 1, index + 1) } label: { Image(systemName: "chevron.right") }.disabled(index == images.count - 1)
                        }
                    }
                }.padding(24).frame(minWidth: 650, idealWidth: 850, minHeight: 500, idealHeight: 650)
            }
    }
    @ToolbarContentBuilder
    private var readingToolbar: some ToolbarContent {
        ToolbarItem(placement: .automatic) {
            Picker(L("Предпросмотр"), selection: $journalPreview) {
                Text(L("Запись")).tag(false)
                Text(L("Для Дневника")).tag(true)
            }.pickerStyle(.segmented).labelsHidden().frame(width: 180)
        }
        ToolbarItem(placement: .automatic) {
            Menu {
                Button(L("Увеличить текст")) { readingSize = min(23, readingSize + 1) }
                Button(L("Уменьшить текст")) { readingSize = max(14, readingSize - 1) }
                Button(L("Обычный размер")) { readingSize = 17 }
            } label: { Text("Aa") }.help(L("Размер текста"))
        }
        ToolbarItem(placement: .automatic) {
            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(entry.journalText(includeUnresolved: model.includeUnresolved, language: model.language), forType: .string)
                copied = true
            } label: {
                Label(copied ? L("Текст скопирован") : L("Скопировать текст для Дневника"), systemImage: copied ? "checkmark" : "doc.on.doc")
            }.help(copied ? L("Текст скопирован") : L("Скопировать текст для Дневника"))
        }
    }
    private var revisionActions: some View {
        HStack {
            Button(L("Посмотреть исходник")) { showingSource = true }
            Button(L(model.revisions[entry.id] == nil ? "Редактировать копию" : "Изменить копию")) { editing = true }
            if model.revisions[entry.id] != nil {
                Text(L("Изменённая копия")).font(.caption).foregroundStyle(.secondary)
                Button(L("Вернуть оригинал")) {
                    do { try model.restoreOriginal(entry) } catch { revisionError = true }
                }
            }
        }.disabled(model.busy || model.receipt(entry) != nil)
    }
    private var heading: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(spacing: 8) {
                Spacer()
                if model.receipt(entry) == "confirmed" {
                    Label(L("Проверено"), systemImage: "checkmark.circle.fill").font(.system(size: 10)).foregroundStyle(.green)
                }
            }
            if let title = entry.readingTitle {
                Text(searchHighlight(title, query: model.search)).foregroundStyle(entry.transferReviewReasons.isEmpty ? .primary : .secondary).font(.system(size: 35, weight: .medium, design: .serif)).tracking(-0.7).lineSpacing(4).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
            }
            HStack(spacing: 8) {
                Text(JournalDates.full(entry.date)).font(.system(size: 12))
                Circle().frame(width: 2, height: 2)
                Text(JournalDates.time(entry.date)).font(.system(size: 12))
                if !entry.attachmentPaths.isEmpty {
                    Circle().frame(width: 2, height: 2)
                    Label("\(entry.attachmentPaths.count)", systemImage: "photo").font(.system(size: 11))
                }
            }.foregroundStyle(.tertiary)
            if !entry.displayTags.isEmpty { EntryTags(tags: entry.displayTags, query: model.search) }
            Rectangle().fill(Color.journalAccent.opacity(0.4)).frame(width: 30, height: 2).padding(.top, 3)
        }
    }
    private var prose: some View {
        VStack(alignment: .leading, spacing: 25) {
            ForEach(Array(entry.readableBlocks.enumerated()), id: \.offset) { index, block in
                let text = EntryPresentation.clean(block.text)
                if !text.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        if !block.heading.isEmpty {
                            Text(searchHighlight(EntryPresentation.clean(block.heading), query: model.search)).font(.system(size: readingSize - 2, weight: .semibold)).foregroundStyle(.secondary)
                        }
                        Text(searchHighlight(text, query: model.search)).foregroundStyle(entry.transferReviewReasons.isEmpty ? .primary : .secondary).font(.system(size: readingSize, weight: .regular, design: .serif)).lineSpacing(9).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            if !entry.hasReadableText && model.includeUnresolved { Text(L("В этой записи нет обычного текста. Исходные значения доступны ниже.")).font(.callout).foregroundStyle(.secondary).lineSpacing(5) }
        }
    }
    private var warnings: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(L("Нужна проверка"), systemImage: "exclamationmark.circle").font(.system(size: 12, weight: .semibold))
            ForEach(entry.transferReviewReasons, id: \.self) { Text(L($0)).font(.system(size: 11)).lineSpacing(4) }
            Button { showingSource = true } label: {
                Label(L("Посмотреть исходник"), systemImage: "doc.text.magnifyingglass")
            }.padding(.top, 4)
        }.foregroundStyle(Color(nsColor: .secondaryLabelColor)).padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.orange.opacity(0.07), in: RoundedRectangle(cornerRadius: 14))
            .overlay(alignment: .leading) { RoundedRectangle(cornerRadius: 2).fill(Color.orange.opacity(0.55)).frame(width: 2).padding(.vertical, 14) }
    }
    private var photographs: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(L("ФОТОГРАФИИ")).font(.system(size: 9, weight: .semibold)).tracking(1.4).foregroundStyle(.tertiary)
                Spacer()
                if loadingImages { ProgressView().controlSize(.mini) }
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 200), spacing: 12)], spacing: 12) {
                ForEach(Array(images.enumerated()), id: \.offset) { index, image in
                    Button { photoIndex = index } label: {
                        Image(nsImage: image).resizable().scaledToFit().frame(maxWidth: .infinity).frame(maxHeight: 340)
                            .clipShape(RoundedRectangle(cornerRadius: 14))
                    }.buttonStyle(.plain).help(L("Открыть фотографию")).accessibilityLabel(LF("Фотография %d", index + 1))
                }
            }
            if !loadingImages && images.count < entry.attachmentPaths.count {
                Text(LF("Предпросмотр: %d из %d. Некоторые вложения не удалось показать; максимум — 12 фото.", images.count, entry.attachmentPaths.count)).font(.caption).foregroundStyle(.secondary)
            }
        }
    }
    private var additionalAnswers: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 14) {
                Text(L("В экспорте нет названий этих вопросов. Мы сохраняем значения, не угадывая их смысл.")).font(.system(size: 11)).foregroundStyle(.secondary).lineSpacing(4)
                ForEach(Array(entry.unresolvedBlocks.enumerated()), id: \.offset) { index, block in
                    HStack(alignment: .top) {
                        Text(LF("Ответ %d", index + 1)).foregroundStyle(.tertiary).frame(width: 70, alignment: .leading)
                        Text(EntryPresentation.structuredValue(block.text)).foregroundStyle(.secondary).textSelection(.enabled)
                    }.font(.system(size: 12))
                }
                Text(L(model.includeUnresolved ? "Эти значения включены в перенос. Можно изменить в общих настройках." : "Эти значения не переносятся. Можно изменить в общих настройках."))
                    .font(.system(size: 10)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }.padding(.top, 16)
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "text.badge.plus").foregroundStyle(.tertiary)
                Text(L("Дополнительные ответы")).font(.system(size: 12, weight: .medium)).foregroundStyle(.secondary)
                Text("\(entry.unresolvedBlocks.count)").font(.system(size: 10)).foregroundStyle(.tertiary)
            }
        }.padding(16).background(Color.primary.opacity(0.025), in: RoundedRectangle(cornerRadius: 14))
    }
    private var sourceDetails: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 8) {
                Text(LF("Время: %@", entry.originalTimestamp))
                Text(L("Дневник отображает этот момент в текущем часовом поясе. Для утренних и вечерних заметок взято время самого раннего ответа."))
                ForEach(entry.notes, id: \.self) { Text(L($0)) }
            }.font(.system(size: 10)).foregroundStyle(.secondary).lineSpacing(4).textSelection(.enabled).padding(.top, 12)
        } label: { Label(L("Об исходной записи"), systemImage: "info.circle").font(.system(size: 10)) }.foregroundStyle(.tertiary)
    }
    private var actionBar: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let latest = model.events(for: entry).last {
                Text(latest.date.formatted(.dateTime.day().month().year().hour().minute().second().locale(model.language.locale)))
                    .font(.caption).foregroundStyle(.secondary)
                if let detail = latest.detail { Text(detail).font(.caption).foregroundStyle(.orange).textSelection(.enabled) }
            }
            if !model.events(for: entry).isEmpty {
                DisclosureGroup(L("История попыток")) {
                    ScrollView { TransferEventsView(events: model.events(for: entry), language: model.language) }
                        .frame(maxHeight: 160)
                }.font(.caption)
            }
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                if model.receipt(entry) == "confirmed" {
                    Label(L("Перенос подтверждён"), systemImage: "checkmark.seal.fill").foregroundStyle(.green).font(.system(size: 11, weight: .medium))
                } else if model.receipt(entry) != nil {
                    Text(model.receiptLabel(entry)).font(.system(size: 11, weight: .medium))
                    Text(L("Текст, дату и фотографии")).font(.system(size: 9)).foregroundStyle(.secondary)
                } else {
                    Text(model.canSend ? L("Готово к переносу") : L("Пока нельзя перенести")).font(.system(size: 11, weight: .medium))
                    Text(L(model.singleTransferBlockReason ?? "С исходной датой записи")).font(.system(size: 9)).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 10)
            if model.receipt(entry) != nil {
                Menu {
                    Button(L("Запись удалена — разрешить повтор…"), action: model.allowRetry)
                } label: { Image(systemName: "ellipsis").frame(width: 26, height: 26) }.menuStyle(.borderlessButton).fixedSize().disabled(model.busy).help(L("Дополнительные действия"))
                if model.receipt(entry) != "confirmed" {
                    Button(L("Запись есть в Дневнике"), action: model.confirm).buttonStyle(PrimaryAction()).disabled(model.busy)
                }
            } else if model.singleTransferNeedsReview {
                Button { model.showingQueue = true } label: {
                    Label(L("Открыть очередь"), systemImage: "list.bullet.rectangle")
                }.buttonStyle(PrimaryAction()).disabled(model.busy)
            } else {
                Button(action: model.send) { Label(L("В Дневник"), systemImage: "arrow.up.forward") }.buttonStyle(PrimaryAction())
                    .disabled(!model.canSend).opacity(model.canSend ? 1 : 0.45)
                    .help(L(model.singleTransferBlockReason ?? "В Дневник"))
            }
        }
        }.padding(.horizontal, 18).padding(.vertical, 13).frosted(22)
    }
    private func loadImages() async {
        images = []; loadingImages = true
        let data = await model.photos(for: entry)
        guard !Task.isCancelled else { return }
        images = data.compactMap { bytes in
            guard let source = CGImageSourceCreateWithData(bytes as CFData, nil),
                  let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 1400, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary) else { return nil }
            return NSImage(cgImage: thumbnail, size: .zero)
        }
        loadingImages = false
    }
    private var sourceText: String {
        let original = model.original(for: entry)
        if let source = original.sourceJSON { return source }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return (try? encoder.encode(original)).flatMap { String(data: $0, encoding: .utf8) } ?? entry.text
    }
    private func saveSource() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = "stoic-entry.json"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do { try Data(sourceText.utf8).write(to: url, options: .atomic) }
        catch { sourceError = true }
    }
}

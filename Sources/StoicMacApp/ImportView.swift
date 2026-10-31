import SwiftUI
import StoicCore

enum EntryFilter: String, CaseIterable, Identifiable {
    case readable = "Дневник", all = "Все записи", ready = "Готовы к переносу", review = "Нужна проверка", imported = "Отправленные"
    var id: String { rawValue }
    var navigationLabel: String {
        switch self { case .ready: "К переносу"; case .review: "Проверить"; default: rawValue }
    }
    var symbol: String {
        switch self {
        case .readable: "book.pages"
        case .all: "square.stack"
        case .ready: "tray.and.arrow.up"
        case .review: "exclamationmark.circle"
        case .imported: "checkmark.circle"
        }
    }
}

struct ImportView: View {
    @ObservedObject var model: ImportModel
    @AppStorage("readingSize") private var readingSize = 17.0
    @AppStorage("appearance") private var appearance = "system"
    @State private var settings = false
    @State private var archiveReview = false
    @State private var searchFilters = false
    @State private var columnVisibility: NavigationSplitViewVisibility = .all
    @State private var visibleLimit = 60
    @FocusState private var searchFocused: Bool
    @FocusState private var listFocused: Bool
    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            navigation
                .navigationSplitViewColumnWidth(min: 190, ideal: 224, max: 280)
        } content: {
            entryList
                .navigationTitle(L(model.filter.rawValue))
                .toolbar { listToolbar }
                .navigationSplitViewColumnWidth(min: 270, ideal: 320, max: 420)
        } detail: {
            VStack(spacing: 0) {
                if model.entries.isEmpty {
                    welcome.frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let entry = model.selected {
                    ReadingView(entry: entry, model: model, readingSize: $readingSize)
                        .id(entry.id + "-" + model.language.rawValue)
                } else {
                    selectionPlaceholder.frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                Divider()
                statusBar
            }.frame(minWidth: 400, maxWidth: .infinity, maxHeight: .infinity)
                .toolbar { windowToolbar }
        }
            .navigationSplitViewStyle(.balanced)
            .tint(.accentColor)
            .environment(\.locale, model.language.locale)
            .preferredColorScheme(appearance == "system" ? nil : (appearance == "dark" ? .dark : .light))
            .sheet(isPresented: $model.showingQueue) { TransferQueueView(model: model) }
            .sheet(isPresented: $archiveReview) {
                ArchiveReviewView(model: model) { id in
                    model.resetSearch()
                    model.filter = .all
                    DispatchQueue.main.async { model.selection = id }
                }
            }
            .task { model.restoreArchive() }
            .onChange(of: model.search) {
                visibleLimit = 60
                model.reconcileSelection()
            }
            .onChange(of: model.visibleEntries.map(\.id)) { model.reconcileSelection() }
            .onChange(of: model.filter) { visibleLimit = 60; model.reconcileSelection() }
            .onChange(of: model.searchOptions) { visibleLimit = 60; model.reconcileSelection() }
            .onChange(of: model.onlyPhotos) { visibleLimit = 60; model.reconcileSelection() }
            .background {
                VStack {
                    Button(L("Найти запись")) { searchFocused = true }.keyboardShortcut("f")
                    Button(L("Выбрать все видимые")) { model.selectAllVisible() }.keyboardShortcut("a").disabled(!listFocused)
                }.hidden()
            }
    }
    @ToolbarContentBuilder
    private var windowToolbar: some ToolbarContent {
        if #available(macOS 26, *) {
            ToolbarSpacer(.flexible, placement: .primaryAction)
        } else {
            ToolbarItem(placement: .automatic) { Spacer() }
        }
        ToolbarItem(placement: .primaryAction) {
            Button(action: model.chooseArchive) {
                Label(L("Открыть архив"), systemImage: "folder")
            }.help(L("Открыть архив"))
                .disabled(model.busy || model.choosingArchive)
        }
        ToolbarItem(placement: .primaryAction) {
            Button { settings.toggle() } label: {
                Label(L("Настройки"), systemImage: "slider.horizontal.3")
            }.help(L("Настройки"))
                .popover(isPresented: $settings, arrowEdge: .bottom) { settingsPanel }
        }
    }
    @ToolbarContentBuilder
    private var listToolbar: some ToolbarContent {
        ToolbarItem(placement: .primaryAction) {
            Button { archiveReview = true } label: {
                Label(L("Проверка архива"), systemImage: "checklist")
            }.disabled(model.entries.isEmpty || model.busy)
        }
        ToolbarItem(placement: .primaryAction) {
            Menu {
                Button(L("Очередь и история переноса")) { model.showingQueue = true }
                Button(LF("Выбранные записи (%d)", model.checkedIDs.count)) { model.prepareQueue() }
                    .disabled(!model.canSendBatch || model.checkedIDs.isEmpty)
                Button(LF("Перенести все готовые (%d)", model.readyCount), action: model.sendBatch).disabled(!model.canSendBatch)
                Button(L("Выбрать все видимые")) {
                    model.selectAllVisible()
                }.disabled(model.busy)
                Button(L("Снять выделение")) { model.clearSelection() }.disabled(model.busy)
            } label: { Label(L("Очередь и история переноса"), systemImage: "list.bullet.rectangle") }
        }
        ToolbarItem(placement: .automatic) {
            Menu {
                Button(L("Сначала новые")) { model.newestFirst = true }
                Button(L("Сначала старые")) { model.newestFirst = false }
            } label: {
                Label(L("Порядок записей"), systemImage: "arrow.up.arrow.down")
            }.help(L("Порядок записей"))
        }
    }
    private var navigation: some View {
        List(selection: Binding<EntryFilter?>(get: { model.filter }, set: { if let value = $0 { model.filter = value } })) {
            Section(L("БИБЛИОТЕКА")) {
                ForEach(EntryFilter.allCases, id: \.self) { filter in
                    HStack {
                        Label(L(filter.navigationLabel), systemImage: filter.symbol)
                        Spacer()
                        Text(model.count(for: filter).formatted()).font(.caption).monospacedDigit().foregroundStyle(.secondary)
                    }.tag(filter)
                }
            }
            if !model.entries.isEmpty {
                Section(model.archiveName) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(L("Перенос записей")).font(.subheadline)
                        ProgressView(value: Double(model.confirmedCount), total: Double(max(1, model.entries.count)))
                        Text(LF("%d из %d", model.confirmedCount, model.entries.count)).font(.caption).foregroundStyle(.secondary)
                    }.padding(.vertical, 6)
                }
            }
        }.listStyle(.sidebar)
            .safeAreaInset(edge: .bottom) {
                Label(L("Архив остаётся у вас"), systemImage: "lock.shield")
                    .font(.caption).foregroundStyle(.secondary).padding(14)
            }
    }
    private var entryList: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(spacing: 6) {
                HStack(spacing: 8) {
                    HStack(spacing: 6) {
                        Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                        TextField(L("Поиск по записям"), text: $model.search)
                            .textFieldStyle(.plain).focused($searchFocused)
                        if !model.search.isEmpty {
                            Button { model.search = "" } label: {
                                Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                            }.buttonStyle(.plain).help(L("Очистить поиск"))
                        }
                    }.font(.system(size: 12)).padding(.horizontal, 8).frame(height: 28)
                        .background(Color.primary.opacity(0.045), in: RoundedRectangle(cornerRadius: 7))
                    Button { searchFilters.toggle() } label: {
                        Image(systemName: model.searchOptions == EntrySearch() ? "line.3.horizontal.decrease.circle" : "line.3.horizontal.decrease.circle.fill")
                            .font(.system(size: 15))
                            .foregroundStyle(model.searchOptions == EntrySearch() ? Color.secondary : Color.journalAccent)
                            .frame(width: 26, height: 28)
                    }.buttonStyle(.plain).help(L("Фильтры поиска")).accessibilityLabel(L("Фильтры поиска"))
                        .popover(isPresented: $searchFilters) { searchFilterPanel }
                }
                HStack(spacing: 6) {
                    Text(model.checkedIDs.count > 1 ? LF("Выбрано: %d", model.checkedIDs.count) : JournalDates.count(model.visibleEntries.count))
                        .foregroundStyle(.secondary)
                    Spacer(minLength: 4)
                    if model.searchOptions != EntrySearch() {
                        Button(L("Сбросить фильтры")) { model.searchOptions = EntrySearch() }
                            .buttonStyle(.plain).foregroundStyle(Color.journalAccent)
                    }
                    Button { model.onlyPhotos.toggle() } label: {
                        Label(L("С фото"), systemImage: "photo")
                            .foregroundStyle(model.onlyPhotos ? Color.journalAccent : .secondary)
                    }.buttonStyle(.plain).help(L("Показать только записи с фотографиями"))
                        .accessibilityValue(model.onlyPhotos ? L("Включено") : L("Выключено"))
                }.font(.system(size: 10)).frame(height: 16)
            }.padding(.horizontal, 12).padding(.top, 8).padding(.bottom, 7)
            Divider().opacity(0.35)
            if model.visibleEntries.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "text.page.slash").font(.title2).foregroundStyle(.tertiary)
                    Text(L("Ничего не найдено")).font(.callout)
                    Button(L("Сбросить поиск и фильтры")) { model.resetSearch() }.font(.caption).buttonStyle(.plain).foregroundStyle(Color.journalAccent)
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 5) {
                            ForEach(Array(model.visibleEntries.prefix(visibleLimit).enumerated()), id: \.element.id) { index, entry in
                                if startsYear(index, entry) {
                                    HStack(spacing: 12) {
                                        Text(JournalDates.year(entry.date))
                                            .font(.system(size: 18, weight: .medium, design: .serif))
                                        Rectangle().fill(Color.primary.opacity(0.1)).frame(height: 1)
                                    }.foregroundStyle(.secondary).padding(.horizontal, 13).padding(.top, 12).padding(.bottom, 2)
                                        .accessibilityAddTraits(.isHeader)
                                }
                                if startsMonth(index, entry) {
                                    Text(JournalDates.monthName(entry.date))
                                        .font(.system(size: 10, weight: .semibold)).foregroundStyle(.tertiary).padding(.horizontal, 13).padding(.top, 10).padding(.bottom, 3)
                                }
                                Button { listFocused = true; model.selectEntry(entry.id) } label: {
                                    EntryRow(entry: entry, status: model.receiptLabel(entry), confirmed: model.receipt(entry) == "confirmed", selected: model.checkedIDs.contains(entry.id), language: model.language, query: model.search).id(model.language)
                                }.buttonStyle(.plain).id(entry.id).accessibilityElement(children: .combine)
                                    .accessibilityAddTraits(model.checkedIDs.contains(entry.id) ? .isSelected : [])

                            }
                            if model.visibleEntries.count > visibleLimit {
                                Button(L("Показать ещё")) { visibleLimit += 60 }.buttonStyle(.plain).font(.caption).foregroundStyle(Color.journalAccent).frame(maxWidth: .infinity).padding(18)
                            }
                        }.padding(.horizontal, 8).padding(.bottom, 20)
                    }.focusable().focused($listFocused)
                    .onKeyPress(keys: [.upArrow, .downArrow, "a"], phases: [.down, .repeat]) { press in
                        if press.key == "a" {
                            guard press.modifiers.contains(.command) else { return .ignored }
                            model.selectAllVisible()
                            return .handled
                        }
                        model.moveSelection(by: press.key == .downArrow ? 1 : -1, extending: press.modifiers.contains(.shift))
                        return .handled
                    }.onChange(of: model.selection) {
                        if let selected = model.selection, let index = model.visibleEntries.firstIndex(where: { $0.id == selected }) {
                            visibleLimit = max(visibleLimit, index + 1)
                            proxy.scrollTo(selected)
                        }
                    }
                }
            }
        }.background(Color(nsColor: .controlBackgroundColor))
    }
    private var searchFilterPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(L("Фильтры поиска")).font(.headline)
            Toggle(L("С даты"), isOn: Binding(get: { model.searchOptions.startDate != nil }, set: { model.searchOptions.startDate = $0 ? (model.entries.map(\.date).min() ?? Date()) : nil }))
            if model.searchOptions.startDate != nil {
                DatePicker(L("С даты"), selection: Binding(get: { model.searchOptions.startDate ?? Date() }, set: { model.searchOptions.startDate = $0 }), displayedComponents: .date)
            }
            Toggle(L("По дату"), isOn: Binding(get: { model.searchOptions.endDate != nil }, set: { model.searchOptions.endDate = $0 ? (model.entries.map(\.date).max() ?? Date()) : nil }))
            if model.searchOptions.endDate != nil {
                DatePicker(L("По дату"), selection: Binding(get: { model.searchOptions.endDate ?? Date() }, set: { model.searchOptions.endDate = $0 }), displayedComponents: .date)
            }
            Picker(L("Тип записи"), selection: $model.searchOptions.kind) {
                Text(L("Все типы")).tag("")
                ForEach(Array(Set(model.entries.map(\.kind))).sorted(), id: \.self) { kind in
                    Text(L(kind == "morning" ? "Утро" : kind == "evening" ? "Вечер" : kind == "checkin" ? "Момент" : kind == "journal" ? "Заметка" : kind)).tag(kind)
                }
            }
            if !model.availableTags.isEmpty {
                Text(L("Теги: все выбранные")).font(.caption).foregroundStyle(.secondary)
                ScrollView {
                    VStack(alignment: .leading) {
                        ForEach(model.availableTags, id: \.self) { tag in
                            Toggle(tag, isOn: Binding(get: { model.searchOptions.tags.contains(tag) }, set: { if $0 { model.searchOptions.tags.insert(tag) } else { model.searchOptions.tags.remove(tag) } }))
                        }
                    }
                }.frame(maxHeight: 180)
            }
            Button(L("Сбросить фильтры")) { model.searchOptions = EntrySearch() }
        }.padding(20).frame(width: 310)
    }
    private func startsYear(_ index: Int, _ entry: JournalEntry) -> Bool {
        index == 0 || !Calendar.current.isDate(entry.date, equalTo: model.visibleEntries[index - 1].date, toGranularity: .year)
    }
    private func startsMonth(_ index: Int, _ entry: JournalEntry) -> Bool {
        index == 0 || !Calendar.current.isDate(entry.date, equalTo: model.visibleEntries[index - 1].date, toGranularity: .month)
    }
    private var selectionPlaceholder: some View {
        VStack(spacing: 16) {
            Image(systemName: "book.pages").font(.system(size: 42, weight: .ultraLight)).foregroundStyle(Color.journalAccent.opacity(0.6))
            Text(L("Откройте воспоминание")).font(.system(size: 25, weight: .medium, design: .serif))
            Text(L("Выберите запись слева, чтобы прочитать её\nи подготовить к переносу в Дневник.")).font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center).lineSpacing(5)
        }
    }
    private var welcome: some View {
        VStack(spacing: 25) {
            ZStack {
                Circle().fill(Color.journalAccent.opacity(0.07)).frame(width: 160, height: 160)
                RoundedRectangle(cornerRadius: 25).fill(.regularMaterial).frame(width: 92, height: 110).rotationEffect(.degrees(-9)).offset(x: -9, y: -3)
                Image(systemName: "book.closed.fill").font(.system(size: 66, weight: .light)).foregroundStyle(Color.journalAccent).rotationEffect(.degrees(7))
            }
            VStack(spacing: 13) {
                Text(L("Каждая запись —\nчасть вашей истории.")).font(.system(size: 40, weight: .medium, design: .serif)).multilineTextAlignment(.center).lineSpacing(3)
                Text(L("Перенесите воспоминания из Stoic в Apple Дневник.\nС текстом, фотографиями и теми самыми датами."))
                    .font(.system(size: 14)).foregroundStyle(.secondary).multilineTextAlignment(.center).lineSpacing(6)
            }
            Button(action: model.chooseArchive) { Label(L("Выбрать архив Stoic"), systemImage: "folder") }.buttonStyle(PrimaryAction()).disabled(model.busy || model.choosingArchive)
            HStack(spacing: 22) {
                Label(L("Исходные даты"), systemImage: "calendar")
                Label(L("Фотографии"), systemImage: "photo")
                Label(L("На вашем Mac"), systemImage: "lock")
            }.font(.system(size: 10)).foregroundStyle(.tertiary).padding(.top, 10)
        }.padding(30)
    }
    private var statusBar: some View {
        HStack(spacing: 8) {
            if model.busy { ProgressView().controlSize(.mini) }
            else { Circle().fill(Color.journalAccent.opacity(0.5)).frame(width: 5, height: 5) }
            if model.batchTotal > 0 {
                Text(LF("Отправлено: %d из %d", model.batchCompleted, model.batchTotal)).font(.caption).monospacedDigit()
            }
            Text(model.localizedStatus).font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(2).textSelection(.enabled)
            Spacer(minLength: 8)
            if model.busy && model.batchTotal > 0 {
                Button(L(model.pauseRequested ? "Пауза после текущей записи" : "Пауза"), action: model.pause).disabled(model.pauseRequested)
                Button(L("Остановить"), action: model.stop).font(.caption).buttonStyle(.plain)
            }
            if model.transferQueue != nil { Button(L("Очередь и история переноса")) { model.showingQueue = true }.font(.caption) }
        }.padding(.horizontal, 14).padding(.vertical, 8)
    }
    private var settingsPanel: some View {
        VStack(alignment: .leading, spacing: 20) {
            Label(L("Настройки"), systemImage: "slider.horizontal.3").font(.title3.weight(.semibold))
            VStack(alignment: .leading, spacing: 8) {
                Text(L("ВНЕШНИЙ ВИД")).font(.system(size: 9, weight: .semibold)).tracking(1.3).foregroundStyle(.tertiary)
                Text(L("Тема")).font(.callout).fixedSize(horizontal: true, vertical: false)
                Picker(L("Тема"), selection: $appearance) { Text(L("Системная")).tag("system"); Text(L("Светлая")).tag("light"); Text(L("Тёмная")).tag("dark") }.pickerStyle(.segmented).labelsHidden()
                HStack { Text(L("Размер текста")).font(.callout); Spacer(); Stepper("\(Int(readingSize))", value: $readingSize, in: 14...23).fixedSize() }
            }
            Divider()
            VStack(alignment: .leading, spacing: 8) {
                Text(L("ЯЗЫК ПРИЛОЖЕНИЯ")).font(.system(size: 9, weight: .semibold)).tracking(1.3).foregroundStyle(.tertiary)
                Picker(L("Язык"), selection: $model.language) {
                    ForEach(AppLanguage.allCases) { language in Text(language.name).tag(language) }
                }
                Text(L("Язык интерфейса не меняет тексты ваших записей.")).font(.caption).foregroundStyle(.secondary)
            }
            Divider()
            VStack(alignment: .leading, spacing: 8) {
                Text(L("ПЕРЕНОС В ДНЕВНИК")).font(.system(size: 9, weight: .semibold)).tracking(1.3).foregroundStyle(.tertiary)
                TextField(L("Имя команды на Mac"), text: $model.shortcutName).textFieldStyle(.roundedBorder)
            }
            Text(L("Дневник показывает исходное время в текущем часовом поясе. Для утренних и вечерних заметок используется самый ранний ответ.")).font(.caption).foregroundStyle(.tertiary)
        }.padding(24).frame(width: 350).disabled(model.busy)
    }
}

struct EntryRow: View {
    let entry: JournalEntry
    let status: String
    let confirmed: Bool
    let selected: Bool
    let language: AppLanguage
    var query = ""
    @State private var hover = false
    var body: some View {
        let unavailable = !entry.transferReviewReasons.isEmpty
        HStack(alignment: .top, spacing: 11) {
            VStack(spacing: 3) {
                Text(JournalDates.day(entry.date)).font(.system(size: 21, weight: .light, design: .rounded)).lineLimit(1)
                Text(JournalDates.weekday(entry.date)).font(.system(size: 8, weight: .medium)).foregroundStyle(.tertiary)
            }.frame(width: 29).padding(.top, 2)
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 5) {
                    Spacer()
                    if confirmed { Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).font(.system(size: 10)) }
                    else if !entry.transferReviewReasons.isEmpty { Image(systemName: "exclamationmark.circle").foregroundStyle(.orange).font(.system(size: 10)) }
                    if !entry.attachmentPaths.isEmpty { Label("\(entry.attachmentPaths.count)", systemImage: "photo").font(.system(size: 9)).foregroundStyle(.tertiary) }
                }
                if let title = entry.readingTitle {
                    Text(searchHighlight(title, query: query)).font(.system(size: 13, weight: .semibold)).lineLimit(2).foregroundStyle(unavailable ? .secondary : .primary)
                }
                Text(searchHighlight(entry.previewText.isEmpty ? L("Данные из Stoic") : String(entry.previewText.prefix(130)), query: query)).font(.system(size: 11)).foregroundStyle(unavailable ? .tertiary : .secondary).lineLimit(2).lineSpacing(3)
                if !entry.displayTags.isEmpty { EntryTags(tags: entry.displayTags, compact: true, query: query) }
                if confirmed || !entry.transferReviewReasons.isEmpty || status != L("Готово к импорту") {
                    Text(status).font(.system(size: 9)).foregroundStyle(confirmed ? Color.green : .secondary)
                }
            }
        }.padding(13).frame(maxWidth: .infinity, alignment: .leading)
            .background(selected ? Color.journalAccent.opacity(0.13) : (hover ? Color.primary.opacity(0.035) : .clear), in: RoundedRectangle(cornerRadius: 13))
            .overlay(RoundedRectangle(cornerRadius: 13).strokeBorder(selected ? Color.journalAccent.opacity(0.16) : .clear, lineWidth: 1))
            .contentShape(Rectangle()).onHover { hover = $0 }
    }
}

import SwiftUI
import StoicCore

extension Color {
    static let journalAccent = Color(red: 0.48, green: 0.40, blue: 0.79)
}

struct FrostedSurface: ViewModifier {
    let radius: CGFloat
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @ViewBuilder func body(content: Content) -> some View {
        if reduceTransparency {
            content.background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: radius))
        } else if #available(macOS 26, *) {
            content.glassEffect(.regular, in: RoundedRectangle(cornerRadius: radius))
        } else {
            content.background(.regularMaterial, in: RoundedRectangle(cornerRadius: radius))
        }
    }
}

extension View {
    func frosted(_ radius: CGFloat = 20) -> some View { modifier(FrostedSurface(radius: radius)) }
}

struct PrimaryAction: ButtonStyle {
    @ViewBuilder func makeBody(configuration: Configuration) -> some View {
        if #available(macOS 26, *) {
            configuration.label.font(.system(size: 13, weight: .semibold))
                .padding(.horizontal, 17).padding(.vertical, 11)
                .glassEffect(.regular.tint(.journalAccent).interactive(), in: Capsule())
                .opacity(configuration.isPressed ? 0.75 : 1)
        } else {
            configuration.label.font(.system(size: 13, weight: .semibold))
                .padding(.horizontal, 17).padding(.vertical, 11)
                .background(Color.journalAccent.opacity(0.18), in: Capsule())
                .opacity(configuration.isPressed ? 0.75 : 1)
        }
    }
}

struct IconAction: View {
    let symbol: String
    let help: String
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Image(systemName: symbol).font(.system(size: 13, weight: .medium))
                .frame(width: 32, height: 32).contentShape(Circle())
        }.buttonStyle(.plain).help(help).accessibilityLabel(help)
    }
}

struct KindStyle {
    let label: String
    let symbol: String
    let color: Color
    @MainActor init(_ kind: String) {
        switch kind {
        case "morning": label = L("Утро"); symbol = "sun.horizon.fill"; color = .orange
        case "evening": label = L("Вечер"); symbol = "moon.stars.fill"; color = .indigo
        case "checkin": label = L("Момент"); symbol = "sparkle"; color = .teal
        default: label = L("Заметка"); symbol = "book.closed.fill"; color = .journalAccent
        }
    }
}

/// Dates follow the selected application language.
@MainActor
enum JournalDates {
    static func year(_ date: Date) -> String { date.formatted(.dateTime.year().locale(currentLanguage.locale)) }
    static func monthName(_ date: Date) -> String { date.formatted(.dateTime.month(.wide).locale(currentLanguage.locale)).capitalized }
    static func month(_ date: Date) -> String { date.formatted(.dateTime.month(.wide).year().locale(currentLanguage.locale)).capitalized }
    static func day(_ date: Date) -> String { String(Calendar.current.component(.day, from: date)) }
    static func weekday(_ date: Date) -> String { date.formatted(.dateTime.weekday(.abbreviated).locale(currentLanguage.locale)).uppercased() }
    static func full(_ date: Date) -> String { date.formatted(.dateTime.day().month(.wide).year().locale(currentLanguage.locale)) }
    static func time(_ date: Date) -> String { AppLocalization.time(date, language: currentLanguage) }
    static func count(_ value: Int) -> String {
        AppLocalization.entryCount(value, language: currentLanguage)
    }
}

/// A continuous native sidebar surface, extending into the titlebar and window edges.
struct SidebarMaterial: NSViewRepresentable {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = .sidebar
        view.blendingMode = .behindWindow
        view.state = .followsWindowActiveState
        return view
    }
    func updateNSView(_ view: NSVisualEffectView, context: Context) {
        view.material = .sidebar
        view.state = reduceTransparency ? .inactive : .followsWindowActiveState
    }
}

/// Tags keep their natural width and wrap with the reading pane.
struct EntryTags: View {
    let tags: [String]
    var compact = false
    var query = ""
    var body: some View {
        TagFlow(spacing: compact ? 5 : 7) {
            ForEach(Array((compact ? Array(tags.prefix(3)) : tags).enumerated()), id: \.offset) { _, tag in
                Text(searchHighlight("#" + tag, query: query))
                    .font(.system(size: compact ? 9 : 11, weight: .medium))
                    .foregroundStyle(Color.journalAccent)
                    .lineLimit(1).truncationMode(.tail)
                    .padding(.horizontal, compact ? 7 : 10).padding(.vertical, compact ? 4 : 6)
                    .background(Color.journalAccent.opacity(0.09), in: Capsule())
                    .help(tag)
            }
            if compact && tags.count > 3 {
                Text("+\(tags.count - 3)").font(.system(size: 9)).foregroundStyle(.secondary)
                    .padding(.vertical, 4).help(tags.dropFirst(3).joined(separator: ", "))
            }
        }
    }
}

private struct TagFlow: Layout {
    let spacing: CGFloat
    private func positions(_ subviews: Subviews, width: CGFloat) -> ([CGRect], CGSize) {
        var frames: [CGRect] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0, usedWidth: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(ProposedViewSize(width: width, height: nil))
            if x > 0 && x + size.width > width {
                x = 0; y += rowHeight + spacing; rowHeight = 0
            }
            frames.append(CGRect(origin: CGPoint(x: x, y: y), size: size))
            usedWidth = max(usedWidth, x + size.width)
            x += size.width + spacing; rowHeight = max(rowHeight, size.height)
        }
        return (frames, CGSize(width: usedWidth, height: y + rowHeight))
    }
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        positions(subviews, width: proposal.width ?? .greatestFiniteMagnitude).1
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let frames = positions(subviews, width: bounds.width).0
        for (view, frame) in zip(subviews, frames) {
            view.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY), proposal: ProposedViewSize(frame.size))
        }
    }
}


struct EntryKindTag: View {
    let kind: String
    var muted = false
    var compact = false
    var body: some View {
        let style = KindStyle(kind)
        Label(style.label, systemImage: style.symbol)
            .font(.system(size: compact ? 9 : 10, weight: .medium))
            .foregroundStyle(muted ? Color.secondary : style.color)
            .padding(.horizontal, compact ? 7 : 10)
            .padding(.vertical, compact ? 4 : 6)
            .background((muted ? Color.primary : style.color).opacity(muted ? 0.035 : 0.09), in: Capsule())
    }
}


struct QuietWindowTitle: ViewModifier {
    @ViewBuilder func body(content: Content) -> some View {
        if #available(macOS 15, *) {
            content.toolbar(removing: .title)
        } else {
            content.navigationTitle("")
        }
    }
}

func searchHighlight(_ source: String, query: String) -> AttributedString {
    var result = AttributedString(source)
    for word in EntrySearch.words(query) {
        var start = source.startIndex
        while start < source.endIndex,
              let range = source.range(of: word, options: [.caseInsensitive, .diacriticInsensitive], range: start..<source.endIndex) {
            if let attributedRange = Range(range, in: result) {
                result[attributedRange].backgroundColor = Color.yellow.opacity(0.4)
                result[attributedRange].foregroundColor = Color.primary
            }
            start = range.upperBound
        }
    }
    return result
}

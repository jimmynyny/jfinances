import JFinancesKit
import SwiftUI

/// A tab's page: the desk-coloured background, panels in a column with the
/// dashboard's 16pt gutter, and pull to refresh. A tab's root draws its own
/// large title in the top row (no navigation bar: nothing sits beside it, so the
/// bar's empty row would push everything down); a pushed screen (`inline`)
/// keeps the bar for its back button. Blur lives in Settings.
/// A plain stack, not a lazy one: a screen holds a few panels, and a lazy stack
/// unloads a panel scrolled away, so its loader starts over at skeleton height
/// and a tall one (an account's details) can bounce in and out of view forever.
struct Screen<Content: View>: View {
    @Environment(AppModel.self) private var model
    let title: String
    let inline: Bool
    let content: Content

    init(_ title: String, inline: Bool = false, @ViewBuilder content: () -> Content) {
        self.title = title
        self.inline = inline
        self.content = content()
    }

    var body: some View {
        ScrollView {
            PanelStack {
                if !inline { TabTitle(title).panelSpan() }
                content
            }
            .padding(.horizontal, JF.gutter)
            .padding(.vertical, 12)
        }
        .scrollIndicators(.hidden)
        .background(JF.page)
        .refreshable { await model.pullToRefresh() }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(inline ? .inline : .automatic)
        .toolbar(inline ? .automatic : .hidden, for: .navigationBar)
        .statusBarBackdrop(!inline)
    }
}

extension View {
    /// The page colour behind the status bar, so what scrolls under it stays
    /// out of the clock's way on a screen without a navigation bar.
    @ViewBuilder func statusBarBackdrop(_ on: Bool = true) -> some View {
        if on {
            safeAreaInset(edge: .top, spacing: 0) {
                Color.clear.frame(height: 0).background(JF.page.opacity(0.96).ignoresSafeArea(edges: .top))
            }
        } else {
            self
        }
    }
}

/// A screen's panels: one column on a phone (exactly a VStack), and where the
/// screen is wide (an iPad, the open iPhone Duo) two or three columns, each
/// panel dropped into the shortest. `panelSpan()` keeps a row (a title, the
/// slice controls, a note) across all of them. Columns follow the width the
/// stack is given, not the device, so a pane beside a list stays one column.
struct PanelStack: Layout {
    var spacing: CGFloat = 12

    static func columns(for width: CGFloat) -> Int {
        width >= 1100 ? 3 : width >= 700 ? 2 : 1
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0
        let frames = place(width: width, subviews: subviews)
        return CGSize(width: width, height: frames.map(\.maxY).max() ?? 0)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for (frame, view) in zip(place(width: bounds.width, subviews: subviews), subviews) {
            view.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                       proposal: ProposedViewSize(width: frame.width, height: frame.height))
        }
    }

    private func place(width: CGFloat, subviews: Subviews) -> [CGRect] {
        let n = Self.columns(for: width)
        let colWidth = (width - spacing * CGFloat(n - 1)) / CGFloat(n)
        var tops = Array(repeating: CGFloat(0), count: n)
        var frames: [CGRect] = []
        for view in subviews {
            let spans = n == 1 || view[PanelSpan.self]
            let size = view.sizeThatFits(ProposedViewSize(width: spans ? width : colWidth, height: nil))
            if spans {
                let top = tops.max() ?? 0
                let y = top > 0 ? top + spacing : 0
                frames.append(CGRect(x: 0, y: y, width: min(size.width, width), height: size.height))
                if size.height > 0 { tops = Array(repeating: y + size.height, count: n) }
            } else {
                let i = tops.indices.min { tops[$0] < tops[$1] }!
                let y = tops[i] > 0 ? tops[i] + spacing : 0
                frames.append(CGRect(x: CGFloat(i) * (colWidth + spacing), y: y, width: colWidth, height: size.height))
                if size.height > 0 { tops[i] = y + size.height }
            }
        }
        return frames
    }
}

private struct PanelSpan: LayoutValueKey {
    static let defaultValue = false
}

extension View {
    /// Across every column of a wide `PanelStack`.
    func panelSpan() -> some View { layoutValue(key: PanelSpan.self, value: true) }
}

/// Wide screens (an iPad, the open iPhone Duo): a list on the left, what was
/// picked in it on the right, each with its own navigation. A phone (or the
/// Duo folded) never gets here: the tab pushes instead.
struct TwoPane<List: View, Detail: View>: View {
    let list: List
    let detail: Detail

    init(@ViewBuilder list: () -> List, @ViewBuilder detail: () -> Detail) {
        self.list = list()
        self.detail = detail()
    }

    var body: some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                list.frame(width: min(440, max(340, geo.size.width * 0.4)))
                Rectangle().fill(JF.line).frame(width: 1).ignoresSafeArea()
                detail.frame(maxWidth: .infinity)
            }
        }
        .background(JF.page)
    }
}

/// The right pane before anything is picked.
struct PickPrompt: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "sidebar.left").font(.system(size: 28)).foregroundStyle(JF.ink3)
            Fine(text)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(JF.page)
        .toolbar(.hidden, for: .navigationBar)
    }
}

/// A tab root's title, where the navigation bar's large title would be, one row higher.
struct TabTitle: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(JFFont.sans(32, .semibold))
            .foregroundStyle(JF.ink)
            .accessibilityAddTraits(.isHeader)
    }
}

enum LoadState<T> {
    case loading
    case failed(String)
    case loaded(T)
}

/// Loads `T` when it appears and whenever `id` or the app's refresh token
/// changes; keeps showing the last value (dimmed) while a new one loads, and
/// routes API errors through the model so a dead token signs the phone out.
struct Loader<T, Content: View>: View {
    @Environment(AppModel.self) private var model
    let id: AnyHashable
    let height: CGFloat
    let load: () async throws -> T
    let content: (T) -> Content
    @State private var state: LoadState<T> = .loading
    @State private var reloading = false

    init(id: AnyHashable = 0, height: CGFloat = 120, load: @escaping () async throws -> T,
         @ViewBuilder content: @escaping (T) -> Content) {
        self.id = id
        self.height = height
        self.load = load
        self.content = content
    }

    var body: some View {
        Group {
            switch state {
            case .loading: Skeleton(height: height)
            case .failed(let message): ErrorNote(message) { Task { await run() } }
            case .loaded(let value): content(value).opacity(reloading ? 0.55 : 1)
            }
        }
        .task(id: TaskKey(id: id, token: model.refreshToken)) { await run() }
    }

    private struct TaskKey: Hashable { let id: AnyHashable; let token: UUID }

    private func run() async {
        if case .loaded = state { reloading = true }
        defer { reloading = false }
        do {
            let value = try await load()
            state = .loaded(value)
        } catch is CancellationError {
            return
        } catch let e as APIError {
            if case .transport(let s) = e, s.lowercased().contains("cancel") { return }
            model.handle(e)
            if case .loaded = state { return }  // keep the last good value on screen
            state = .failed(e.errorDescription ?? "Something went wrong.")
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}

struct Skeleton: View {
    let height: CGFloat

    var body: some View {
        Rectangle()
            .fill(JF.panel2)
            .frame(maxWidth: .infinity)
            .frame(height: height)
            .accessibilityLabel("Loading")
    }
}

struct ErrorNote: View {
    let message: String
    let retry: (() -> Void)?

    init(_ message: String, retry: (() -> Void)? = nil) {
        self.message = message
        self.retry = retry
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle").foregroundStyle(JF.neg)
            VStack(alignment: .leading, spacing: 6) {
                Text(message).font(JFFont.sans(14)).foregroundStyle(JF.ink)
                if let retry {
                    Button("Try again", action: retry).font(JFFont.mono(12, .medium))
                }
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(JF.negWash)
    }
}

/// A row of mono chips, the dashboard's small segmented control.
struct Chips<V: Hashable>: View {
    let options: [(V, String)]
    @Binding var value: V

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(options.enumerated()), id: \.offset) { i, opt in
                let on = opt.0 == value
                Button {
                    value = opt.0
                } label: {
                    Text(opt.1)
                        .font(JFFont.mono(11, .medium))
                        .foregroundStyle(on ? JF.accentInk : JF.ink2)
                        .padding(.horizontal, 7)
                        .frame(minHeight: 24)
                        .background(on ? JF.accent : JF.panel)
                }
                .buttonStyle(.plain)
                if i < options.count - 1 { Rectangle().fill(JF.line).frame(width: 1, height: 24) }
            }
        }
        .overlay(Rectangle().strokeBorder(JF.line, lineWidth: 1))
        .accessibilityElement(children: .contain)
    }
}

/// The dashboard's primary button: accent fill, square, a flat offset shadow.
struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        let pressed = configuration.isPressed
        configuration.label
            .font(JFFont.sans(16, .semibold))
            .foregroundStyle(JF.accentInk)
            .frame(maxWidth: .infinity, minHeight: 50)
            .background(JF.accent)
            .overlay(Rectangle().strokeBorder(JF.lineStrong, lineWidth: 1))
            .background(Rectangle().fill(JF.lineStrong).offset(x: pressed ? 0 : 2, y: pressed ? 0 : 2))
            .offset(x: pressed ? 2 : 0, y: pressed ? 2 : 0)
    }
}

struct QuietButtonStyle: ButtonStyle {
    var destructive = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(JFFont.sans(15, .medium))
            .foregroundStyle(destructive ? JF.neg : JF.ink)
            .frame(maxWidth: .infinity, minHeight: 46)
            .background(configuration.isPressed ? JF.panel2 : JF.panel)
            .overlay(Rectangle().strokeBorder(JF.line, lineWidth: 1))
    }
}

/// A note in the mono caption style, for "as of" lines and fine print.
struct Fine: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text).font(JFFont.mono(11, relativeTo: .caption2)).foregroundStyle(JF.ink3)
    }
}

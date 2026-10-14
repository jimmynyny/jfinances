import JFinancesKit
import SwiftUI

/// A tab's page: the desk-coloured background, panels in a column with the
/// dashboard's 16pt gutter, pull to refresh, and the blur switch top-right.
struct Screen<Content: View>: View {
    @Environment(AppModel.self) private var model
    let title: String
    let content: Content

    init(_ title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                content
            }
            .padding(.horizontal, JF.gutter)
            .padding(.vertical, 12)
        }
        .scrollIndicators(.hidden)
        .background(JF.page)
        .refreshable { await model.pullToRefresh() }
        .navigationTitle(title)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { BlurButton() } }
    }
}

/// The web's top-right "blur" switch.
struct BlurButton: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Button {
            model.blur.toggle()
        } label: {
            Text("blur")
                .font(JFFont.mono(13, .medium))
                .foregroundStyle(model.blur ? JF.accent : JF.ink2)
        }
        .accessibilityLabel(model.blur ? "Show numbers" : "Blur numbers")
        .accessibilityAddTraits(model.blur ? .isSelected : [])
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

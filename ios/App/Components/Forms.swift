import JFinancesKit
import SwiftUI

// The phone's forms, in the design system's dress: a sheet with Cancel and
// Save, fields with a mono caption over them, choices as menus or chips. Every
// edit on the phone goes through one of these, as the web's go through
// @mooney/ui's Drawer and Input.

/// A sheet that edits something: a title, Cancel, Save (disabled until the form
/// is valid; a spinner while it saves), the error if saving failed. `save`
/// throws to keep the sheet open; returning dismisses it and reloads every
/// screen (the model's refresh token), so lists show the change.
struct FormSheet<Content: View>: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let title: String
    var saveLabel = "Save"
    var canSave = true
    var destructive = false
    let save: () async throws -> Void
    @ViewBuilder let content: Content
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let error { ErrorNote(error) }
                    content
                }
                .padding(.horizontal, JF.gutter)
                .padding(.vertical, 12)
            }
            .scrollIndicators(.hidden)
            .scrollDismissesKeyboard(.interactively)
            .background(JF.page)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.disabled(saving)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        Task { await run() }
                    } label: {
                        if saving { ProgressView() } else { Text(saveLabel).fontWeight(.semibold) }
                    }
                    .tint(destructive ? JF.neg : JF.accent)
                    .disabled(!canSave || saving)
                }
            }
        }
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled(saving)
    }

    private func run() async {
        saving = true
        error = nil
        defer { saving = false }
        do {
            try await save()
            model.changed()
            dismiss()
        } catch let e as APIError {
            model.handle(e)
            error = e.errorDescription
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}

/// A caption and a text field, with help under it, or what is wrong with it.
struct Field: View {
    let label: String
    @Binding var text: String
    var placeholder = ""
    var mono = false
    var keyboard: UIKeyboardType = .default
    var capitalization: TextInputAutocapitalization = .sentences
    var help: String?
    var error: String?
    var uppercase = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(JFFont.mono(11)).foregroundStyle(JF.ink3)
            TextField(placeholder, text: $text)
                .font(mono ? JFFont.mono(15) : JFFont.sans(15))
                .foregroundStyle(JF.ink)
                .keyboardType(keyboard)
                .textInputAutocapitalization(uppercase ? .characters : capitalization)
                .autocorrectionDisabled(mono || uppercase)
                .padding(.horizontal, 12)
                .frame(height: 42)
                .background(JF.panel2)
                .overlay(Rectangle().strokeBorder(error == nil ? JF.line : JF.neg, lineWidth: 1))
                .onChange(of: text) { _, v in if uppercase, v != v.uppercased() { text = v.uppercased() } }
            if let error {
                Text(error).font(JFFont.mono(11)).foregroundStyle(JF.neg)
            } else if let help, !help.isEmpty {
                Text(help).font(JFFont.mono(11)).foregroundStyle(JF.ink3).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// A caption over a row of chips, the small segmented choice.
struct ChoiceField<V: Hashable>: View {
    let label: String
    let options: [(V, String)]
    @Binding var value: V
    var help: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(JFFont.mono(11)).foregroundStyle(JF.ink3)
            ScrollView(.horizontal) { Chips(options: options, value: $value) }.scrollIndicators(.hidden)
            if let help, !help.isEmpty {
                Text(help).font(JFFont.mono(11)).foregroundStyle(JF.ink3).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// A caption over a menu button, for a long list of choices (categories, groups).
struct MenuField<Options: View>: View {
    let label: String
    let current: String
    var help: String?
    @ViewBuilder let options: Options

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(JFFont.mono(11)).foregroundStyle(JF.ink3)
            Menu {
                options
            } label: {
                HStack {
                    Text(current).font(JFFont.sans(15)).foregroundStyle(JF.ink).lineLimit(1)
                    Spacer()
                    Image(systemName: "chevron.up.chevron.down").font(.system(size: 11, weight: .semibold)).foregroundStyle(JF.ink3)
                }
                .padding(.horizontal, 12)
                .frame(height: 42)
                .background(JF.panel2)
                .overlay(Rectangle().strokeBorder(JF.line, lineWidth: 1))
            }
            if let help, !help.isEmpty {
                Text(help).font(JFFont.mono(11)).foregroundStyle(JF.ink3).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// A switch with a title and a line of help.
struct ToggleRow: View {
    let title: String
    var help: String?
    @Binding var on: Bool

    var body: some View {
        Toggle(isOn: $on) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(JFFont.sans(15, .medium)).foregroundStyle(JF.ink)
                if let help { Fine(help) }
            }
        }
        .tint(JF.accent)
    }
}

/// A caption over a date picker, optional: "today" until one is chosen.
struct DateField: View {
    let label: String
    @Binding var date: Date?
    var help: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(JFFont.mono(11)).foregroundStyle(JF.ink3)
            HStack {
                if let d = date {
                    DatePicker("", selection: Binding(get: { d }, set: { date = $0 }), in: ...Date(), displayedComponents: .date)
                        .labelsHidden()
                    Spacer()
                    Button("Clear") { date = nil }.font(JFFont.mono(12, .medium))
                } else {
                    Button("Pick a date") { date = Date() }.font(JFFont.sans(15)).foregroundStyle(JF.ink)
                    Spacer()
                }
            }
            .padding(.horizontal, 12)
            .frame(minHeight: 42)
            .background(JF.panel2)
            .overlay(Rectangle().strokeBorder(JF.line, lineWidth: 1))
            if let help { Text(help).font(JFFont.mono(11)).foregroundStyle(JF.ink3).fixedSize(horizontal: false, vertical: true) }
        }
    }
}

/// Numbers as typed by a person: "$1,234.50", "6.125%", " 30000 ".
enum Parse {
    static func number(_ raw: String) -> Double? {
        let cleaned = raw.replacingOccurrences(of: "[$,%\\s]", with: "", options: .regularExpression)
        guard !cleaned.isEmpty else { return nil }
        return Double(cleaned)
    }

    /// A number the server will store with two decimals, as typed.
    static func money(_ raw: String) -> Double? { number(raw) }
}

/// A destructive action behind a confirmation, as the dashboard's drawers ask.
struct DangerButton: View {
    let title: String
    let question: String
    let message: String
    let confirm: String
    let action: () async -> Void
    @State private var asking = false
    @State private var working = false

    var body: some View {
        Button {
            asking = true
        } label: {
            HStack(spacing: 8) {
                if working { ProgressView().tint(JF.neg) }
                Text(title)
            }
        }
        .buttonStyle(QuietButtonStyle(destructive: true))
        .disabled(working)
        .confirmationDialog(question, isPresented: $asking, titleVisibility: .visible) {
            Button(confirm, role: .destructive) {
                Task {
                    working = true
                    await action()
                    working = false
                }
            }
        } message: {
            Text(message)
        }
    }
}

/// A short confirmation that something happened, at the bottom of the screen.
struct ToastView: View {
    let text: String
    var body: some View {
        Text(text)
            .font(JFFont.mono(12, .medium))
            .foregroundStyle(JF.accentInk)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(JF.ink)
            .overlay(Rectangle().strokeBorder(JF.lineStrong, lineWidth: 1))
    }
}

extension View {
    /// Shows `text` for a moment when it is set, then clears it.
    func toast(_ text: Binding<String?>) -> some View {
        overlay(alignment: .bottom) {
            if let t = text.wrappedValue {
                ToastView(text: t)
                    .padding(.bottom, 90)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .task {
                        try? await Task.sleep(for: .seconds(2.2))
                        withAnimation { text.wrappedValue = nil }
                    }
            }
        }
        .animation(.easeInOut(duration: 0.2), value: text.wrappedValue)
    }
}

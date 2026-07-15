import SwiftUI

/// Text field + Send button, matching the web client's `<form>` composer:
/// mono field, uppercase letter-spaced button, cyan glow on focus/press.
struct ComposerView: View {
    @Binding var text: String
    var isSending: Bool
    var onSend: () -> Void

    @FocusState private var focused: Bool

    var body: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("", text: $text, axis: .vertical)
                .font(.system(size: 15.5))
                .foregroundStyle(Color.jarvisInk)
                .tint(Color.jarvisCyan)
                .lineLimit(1...5)
                .padding(.horizontal, 13)
                .padding(.vertical, 11)
                .background(Color.jarvisVoidRaised)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .strokeBorder(focused ? Color.jarvisCyan : Color.jarvisLineHot, lineWidth: 1)
                )
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .shadow(color: focused ? Color.jarvisCyan.opacity(0.4) : .clear, radius: 6)
                .focused($focused)
                .placeholder(when: text.isEmpty) {
                    Text("Ask Jarvis…")
                        .font(JarvisFont.data(14))
                        .foregroundStyle(Color.jarvisLine)
                        .padding(.horizontal, 17)
                        .padding(.vertical, 11)
                }
                .onSubmit(onSend)

            Button(action: onSend) {
                Text("SEND")
                    .font(JarvisFont.hud(11, bold: false))
                    .tracking(2.5)
            }
            .buttonStyle(SendButtonStyle())
            .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
        }
        .padding(.vertical, 14)
        .overlay(alignment: .top) {
            Rectangle().fill(Color.jarvisLine).frame(height: 1)
        }
    }
}

struct SendButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(Color.jarvisVoid)
            .padding(.horizontal, 22)
            .frame(height: 46)
            .background(Color.jarvisCyan.opacity(configuration.isPressed ? 0.85 : 1))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .shadow(color: isEnabled ? Color.jarvisCyan.opacity(0.4) : .clear, radius: 6)
            .opacity(isEnabled ? 1 : 0.4)
    }
}

private extension View {
    @ViewBuilder
    func placeholder(when shouldShow: Bool, @ViewBuilder placeholder: () -> some View) -> some View {
        ZStack(alignment: .leading) {
            if shouldShow { placeholder() }
            self
        }
    }
}

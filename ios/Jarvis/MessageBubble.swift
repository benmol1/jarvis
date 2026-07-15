import SwiftUI

/// One chat bubble. Jarvis speaks in cyan (left-aligned), you answer in
/// gold (right-aligned) — matching `.msg.jarvis` / `.msg.you` in the web
/// client, including the accent border on the speaker's side.
struct MessageBubble: View {
    let message: ChatMessage
    var onCopy: (() -> Void)? = nil

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 24) }

            VStack(alignment: .leading, spacing: 5) {
                Text(who)
                    .font(JarvisFont.data(9, weight: .medium))
                    .tracking(2)
                    .foregroundStyle(whoColor)

                if message.isCalculating {
                    HStack(spacing: 11) {
                        if message.toolName != nil {
                            ProcessingRing(diameter: 20)
                        } else {
                            CalculatingRing(diameter: 20)
                        }
                        CalculatingLabel(text: message.toolName.map { "Calling <\($0)>" } ?? "Calculating")
                            .font(JarvisFont.data(13))
                            .lineLimit(1)
                    }
                    .fixedSize(horizontal: true, vertical: false)
                    .foregroundStyle(Color.jarvisWireframe)
                } else {
                    bodyText
                        .font(message.role == .user ? .system(size: 15.5) : JarvisFont.data(13))
                        .foregroundStyle(textColor)
                        .fixedSize(horizontal: false, vertical: true)

                    if message.isDraft, let onCopy {
                        Button(action: onCopy) {
                            Text("COPY")
                                .font(JarvisFont.hud(10, bold: false))
                                .tracking(1.5)
                        }
                        .buttonStyle(MiniButtonStyle())
                        .padding(.top, 2)
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 11)
            .background(bubbleBackground)
            .overlay(bubbleBorder)
            .clipShape(RoundedRectangle(cornerRadius: 10))

            if message.role != .user { Spacer(minLength: 24) }
        }
    }

    /// Jarvis's replies may contain `**bold**` markdown from the model — render
    /// it properly instead of showing the literal asterisks. User text is
    /// shown as plain text (it's never markdown, and we want it in a plain font).
    private var bodyText: Text {
        guard message.role != .user,
            let attributed = try? AttributedString(
                markdown: message.text,
                options: AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
            )
        else { return Text(message.text) }
        return Text(attributed)
    }

    private var who: String {
        switch message.role {
        case .user: return "YOU"
        case .jarvis: return message.isError ? "SYSTEM" : "JARVIS"
        case .approvals: return ""
        }
    }

    private var whoColor: Color {
        if message.isError { return .jarvisAlert }
        return message.role == .user ? .jarvisGold : .jarvisCyan
    }

    private var textColor: Color {
        if message.isError { return Color(red: 1, green: 0.85, blue: 0.83) }
        return message.role == .user ? Color(red: 1, green: 0.90, blue: 0.74) : .jarvisInk
    }

    private var bubbleBackground: some View {
        Group {
            if message.isError {
                Color.jarvisAlert.opacity(0.12)
            } else if message.role == .user {
                LinearGradient(
                    colors: [Color(red: 0.24, green: 0.16, blue: 0.04, opacity: 0.42),
                             Color(red: 0.11, green: 0.08, blue: 0.02, opacity: 0.42)],
                    startPoint: .top, endPoint: .bottom
                )
            } else {
                LinearGradient(
                    colors: [Color.jarvisLineHot.opacity(0.28), Color.jarvisPanel.opacity(0.55)],
                    startPoint: .top, endPoint: .bottom
                )
            }
        }
    }

    private var bubbleBorder: some View {
        let accent = message.isError ? Color.jarvisAlert : (message.role == .user ? Color.jarvisGold : Color.jarvisCyan)
        let base = message.isError ? Color.jarvisAlert : (message.role == .user ? Color(red: 0.73, green: 0.51, blue: 0.23) : Color.jarvisLineHot)
        return RoundedRectangle(cornerRadius: 10)
            .strokeBorder(base, lineWidth: 1)
            .overlay(alignment: message.role == .user ? .trailing : .leading) {
                Rectangle().fill(accent).frame(width: 2)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
            }
    }
}

struct MiniButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(Color.jarvisVoid)
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .background(Color.jarvisCyan)
            .clipShape(RoundedRectangle(cornerRadius: 5))
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

import SwiftUI

/// Foreign-event changes Jarvis proposed but didn't apply. One Approve
/// button each; approving POSTs to /apply, which does the actual write.
/// Mirrors the web client's `renderApprovals`.
struct ApprovalsBubble: View {
    let message: ChatMessage
    let onApprove: (Int) -> Void

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 10) {
                Text("NEEDS YOUR APPROVAL")
                    .font(JarvisFont.data(9, weight: .medium))
                    .tracking(2)
                    .foregroundStyle(Color.jarvisCyan)

                ForEach(Array((message.pendingActions ?? []).enumerated()), id: \.offset) { index, action in
                    HStack(spacing: 14) {
                        Text(action.label)
                            .font(.system(size: 14))
                            .foregroundStyle(Color.jarvisInk)
                        Spacer()
                        approveButton(for: index)
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 11)
            .background(
                LinearGradient(
                    colors: [Color.jarvisLineHot.opacity(0.28), Color.jarvisPanel.opacity(0.55)],
                    startPoint: .top, endPoint: .bottom
                )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(Color.jarvisLineHot, lineWidth: 1)
                    .overlay(alignment: .leading) {
                        Rectangle().fill(Color.jarvisCyan).frame(width: 2)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                    }
            )
            .clipShape(RoundedRectangle(cornerRadius: 10))

            Spacer(minLength: 24)
        }
    }

    @ViewBuilder
    private func approveButton(for index: Int) -> some View {
        let state = message.approvalStates?[index] ?? .pending
        switch state {
        case .pending:
            Button("APPROVE") { onApprove(index) }
                .buttonStyle(MiniButtonStyle())
                .font(JarvisFont.hud(10))
                .tracking(1.5)
        case .applying:
            Text("…")
                .font(JarvisFont.data(11))
                .foregroundStyle(Color.jarvisCyan)
        case .approved:
            Text("APPROVED ✓")
                .font(JarvisFont.data(10, weight: .medium))
                .tracking(1)
                .foregroundStyle(Color.jarvisCyan)
        case .failed:
            Button("RETRY") { onApprove(index) }
                .buttonStyle(MiniButtonStyle())
                .font(JarvisFont.hud(10))
                .tracking(1.5)
        }
    }
}

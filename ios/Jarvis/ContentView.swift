import SwiftUI

struct ContentView: View {
    @StateObject private var viewModel = ChatViewModel()

    var body: some View {
        ZStack {
            background

            VStack(spacing: 0) {
                HeaderView(activity: viewModel.headerActivity)

                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 14) {
                            ForEach(viewModel.messages) { message in
                                Group {
                                    if message.role == .approvals {
                                        ApprovalsBubble(message: message) { index in
                                            viewModel.approve(messageID: message.id, actionIndex: index)
                                        }
                                    } else {
                                        MessageBubble(message: message) {
                                            UIPasteboard.general.string = message.text
                                        }
                                    }
                                }
                                .id(message.id)
                            }
                        }
                        .padding(.vertical, 18)
                    }
                    .onChange(of: viewModel.messages.count) {
                        guard let last = viewModel.messages.last else { return }
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }

                ComposerView(text: $viewModel.inputText, isSending: viewModel.isSending) {
                    viewModel.send()
                }
            }
            .padding(.horizontal, 12)
        }
        .preferredColorScheme(.dark)
    }

    private var background: some View {
        ZStack {
            Color.jarvisVoid
            RadialGradient(
                colors: [Color(red: 0.04, green: 0.13, blue: 0.20), .clear],
                center: UnitPoint(x: 0.5, y: -0.1), startRadius: 0, endRadius: 420
            )
            RadialGradient(
                colors: [Color(red: 0.03, green: 0.10, blue: 0.14), .clear],
                center: UnitPoint(x: 1.0, y: 1.0), startRadius: 0, endRadius: 380
            )
        }
        .ignoresSafeArea()
    }
}

#Preview {
    ContentView()
}

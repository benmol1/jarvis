import Foundation

// ponytail: hardcoded tailnet URL, swap for a settings field if the Pi's hostname changes often
private let backendBaseURL = URL(string: "http://raspberry-pi:8000")!

@MainActor
final class ChatViewModel: ObservableObject {
    @Published private(set) var messages: [ChatMessage] = []
    @Published var inputText = ""
    @Published private(set) var isSending = false

    // Session memory: this client holds the conversation and replays it each
    // call, same as the web client. Lives as long as the app process does.
    private var history: [Turn] = []

    func send() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isSending else { return }
        inputText = ""

        messages.append(ChatMessage(role: .user, text: text))
        let pendingID = UUID()
        messages.append(ChatMessage(id: pendingID, role: .jarvis, isCalculating: true))

        Task {
            isSending = true
            defer { isSending = false }
            await stream(message: text, pendingID: pendingID)
        }
    }

    private func stream(message: String, pendingID: UUID) async {
        do {
            var request = URLRequest(url: backendBaseURL.appendingPathComponent("chat"))
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(
                ChatRequestBody(message: message, history: history)
            )

            let (bytes, response) = try await URLSession.shared.bytes(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                throw URLError(.badServerResponse)
            }

            var final: StreamEvent?
            for try await line in bytes.lines {
                guard let data = line.data(using: .utf8),
                    let event = try? JSONDecoder().decode(StreamEvent.self, from: data)
                else { continue }

                if event.type == "tool" {
                    update(pendingID) {
                        $0.isCalculating = true
                        $0.toolName = event.name
                    }
                } else if event.type == "final" {
                    final = event
                }
            }

            guard let final else { throw URLError(.cannotParseResponse) }

            update(pendingID) {
                $0.isCalculating = false
                $0.toolName = nil
                $0.text = final.reply ?? ""
                $0.isDraft = final.isDraft ?? false
            }

            if let pending = final.pending, !pending.isEmpty {
                var approvals = ChatMessage(role: .approvals)
                approvals.pendingActions = pending
                approvals.approvalStates = Array(repeating: .pending, count: pending.count)
                messages.append(approvals)
            }

            history.append(Turn(role: "user", content: message))
            history.append(Turn(role: "assistant", content: final.reply ?? ""))
        } catch {
            update(pendingID) {
                $0.isCalculating = false
                $0.toolName = nil
                $0.isError = true
                $0.text = "Error: \(error.localizedDescription)"
            }
        }
    }

    private func update(_ id: UUID, _ mutate: (inout ChatMessage) -> Void) {
        guard let idx = messages.firstIndex(where: { $0.id == id }) else { return }
        mutate(&messages[idx])
    }

    func approve(messageID: UUID, actionIndex: Int) {
        guard let msgIdx = messages.firstIndex(where: { $0.id == messageID }),
            let action = messages[msgIdx].pendingActions?[actionIndex]
        else { return }

        messages[msgIdx].approvalStates?[actionIndex] = .applying

        Task {
            do {
                var request = URLRequest(url: backendBaseURL.appendingPathComponent("apply"))
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONEncoder().encode(action)

                let (_, response) = try await URLSession.shared.data(for: request)
                guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode)
                else { throw URLError(.badServerResponse) }

                guard let idx = self.messages.firstIndex(where: { $0.id == messageID }) else { return }
                self.messages[idx].approvalStates?[actionIndex] = .approved
            } catch {
                guard let idx = self.messages.firstIndex(where: { $0.id == messageID }) else { return }
                self.messages[idx].approvalStates?[actionIndex] = .failed(error.localizedDescription)
            }
        }
    }
}

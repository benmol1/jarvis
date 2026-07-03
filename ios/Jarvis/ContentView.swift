import SwiftUI

// ponytail: hardcoded tailnet URL, swap for a settings field if the Pi's hostname changes often
private let backendURL = URL(string: "http://jarvis-pi:8000/chat")!

struct ChatRequest: Encodable { let message: String }
struct ChatResponse: Decodable { let reply: String }

struct ContentView: View {
    @State private var message = ""
    @State private var reply = ""
    @State private var isSending = false

    var body: some View {
        VStack(spacing: 16) {
            Text(reply)
                .frame(maxWidth: .infinity, alignment: .leading)
            Spacer()
            HStack {
                TextField("Message", text: $message)
                    .textFieldStyle(.roundedBorder)
                Button("Send") { send() }
                    .disabled(message.isEmpty || isSending)
            }
        }
        .padding()
    }

    private func send() {
        isSending = true
        Task {
            defer { isSending = false }
            do {
                var request = URLRequest(url: backendURL)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONEncoder().encode(ChatRequest(message: message))

                let (data, _) = try await URLSession.shared.data(for: request)
                reply = try JSONDecoder().decode(ChatResponse.self, from: data).reply
            } catch {
                reply = "Error: \(error.localizedDescription)"
            }
        }
    }
}

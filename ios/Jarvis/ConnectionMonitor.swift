import Foundation

/// How we're currently reaching the Pi. Mirrors the classification the
/// backend's `/health` derives from the request's source IP (private LAN
/// range vs Tailscale's CGNAT range) — the client just displays whatever it
/// says, rather than guessing from which address it dialled.
enum ConnectionStatus: Equatable {
    case local, tailnet, unknown, offline

    fileprivate init(serverValue: String) {
        switch serverValue {
        case "local": self = .local
        case "tailnet": self = .tailnet
        default: self = .unknown
        }
    }

    var label: String {
        switch self {
        case .local: return "LOCAL"
        case .tailnet: return "TAILNET"
        case .unknown: return "ONLINE"
        case .offline: return "OFFLINE"
        }
    }
}

private struct HealthResponse: Decodable {
    let connection: String
}

/// Polls `/health` on a timer so the header can show local vs tailnet vs
/// offline — same backend URL the chat view model already talks to, so
/// there's no second address to keep in sync.
@MainActor
final class ConnectionMonitor: ObservableObject {
    @Published private(set) var status: ConnectionStatus = .offline

    private let healthURL: URL
    private var pollTask: Task<Void, Never>?

    init(baseURL: URL = backendBaseURL, pollInterval: Duration = .seconds(15)) {
        healthURL = baseURL.appendingPathComponent("health")
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.check()
                try? await Task.sleep(for: pollInterval)
            }
        }
    }

    deinit {
        pollTask?.cancel()
    }

    private func check() async {
        var request = URLRequest(url: healthURL)
        request.timeoutInterval = 5

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode)
            else { throw URLError(.badServerResponse) }
            let health = try JSONDecoder().decode(HealthResponse.self, from: data)
            status = ConnectionStatus(serverValue: health.connection)
        } catch {
            status = .offline
        }
    }
}

import Foundation

/// One turn of session history, replayed to the backend each request — it's
/// stateless, so the client holds the conversation (mirrors the web client's
/// `history` array).
struct Turn: Codable {
    let role: String
    let content: String
}

struct ChatRequestBody: Encodable {
    let message: String
    let history: [Turn]
}

/// A foreign-event change Jarvis proposed but didn't apply — queued for
/// approval. Encodable so the same value can be POSTed straight to /apply
/// (mirrors the web client sending the whole `item` back, label included;
/// the backend ignores the extra field).
struct PendingAction: Codable, Equatable {
    let action: String
    let calendarId: String
    let eventId: String
    let start: String?
    let end: String?
    let destinationCalendarId: String?
    let label: String

    enum CodingKeys: String, CodingKey {
        case action, label, start, end
        case calendarId = "calendar_id"
        case eventId = "event_id"
        case destinationCalendarId = "destination_calendar_id"
    }
}

/// One line of the /chat NDJSON stream: either a "tool" progress notice or
/// the terminal "final" line with the reply.
struct StreamEvent: Decodable {
    let type: String
    let name: String?
    let reply: String?
    let pending: [PendingAction]?
    let isDraft: Bool?

    enum CodingKeys: String, CodingKey {
        case type, name, reply, pending
        case isDraft = "is_draft"
    }
}

enum ApprovalState: Equatable {
    case pending, applying, approved
    case failed(String)
}

struct ChatMessage: Identifiable {
    enum Role { case user, jarvis, approvals }

    let id: UUID
    var role: Role
    var text: String
    var isCalculating: Bool
    var toolName: String?
    var isDraft: Bool
    var isError: Bool
    var pendingActions: [PendingAction]?
    var approvalStates: [ApprovalState]?

    init(
        id: UUID = UUID(),
        role: Role,
        text: String = "",
        isCalculating: Bool = false,
        toolName: String? = nil,
        isDraft: Bool = false,
        isError: Bool = false,
        pendingActions: [PendingAction]? = nil,
        approvalStates: [ApprovalState]? = nil
    ) {
        self.id = id
        self.role = role
        self.text = text
        self.isCalculating = isCalculating
        self.toolName = toolName
        self.isDraft = isDraft
        self.isError = isError
        self.pendingActions = pendingActions
        self.approvalStates = approvalStates
    }
}

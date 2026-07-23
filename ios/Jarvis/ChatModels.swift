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
    // Live GPS for the current_location tool, when a fix is available (see
    // LocationProvider). Omitted (rather than sent as 0,0 or similar) when
    // permission isn't granted or no fix arrives in time — the backend falls
    // back to the home-LAN heuristic in that case.
    let lat: Double?
    let lon: Double?
}

/// A change Jarvis proposed but didn't apply — queued for approval (a foreign-
/// event edit, or anything that invites other people). Encodable so the same
/// value can be POSTed straight to /apply (mirrors the web client sending the
/// whole `item` back, extra fields and all). `id` ties it to the server's
/// persisted queue so /apply can clear it once applied; `eventId` is absent for
/// a queued create_event, so both it and the field-edit properties are optional.
struct PendingAction: Codable, Equatable {
    let id: String?
    let action: String
    let calendarId: String
    let eventId: String?
    let summary: String?
    let start: String?
    let end: String?
    let title: String?
    let location: String?
    let description: String?
    let attendees: [String]?
    let destinationCalendarId: String?
    let label: String

    enum CodingKeys: String, CodingKey {
        case id, action, label, summary, start, end, title, location, description, attendees
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

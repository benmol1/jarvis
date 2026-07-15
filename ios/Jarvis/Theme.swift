import SwiftUI

/// Jarvis Interface (Mark I) — colors and fonts, mirroring the tokens in
/// DESIGN.md and backend/static/index.html so web and iOS read as one machine.
extension Color {
    static let jarvisVoid = Color("Void")
    static let jarvisVoidRaised = Color("VoidRaised")
    static let jarvisPanel = Color("Panel")
    static let jarvisLine = Color("Line")
    static let jarvisLineHot = Color("LineHot")
    static let jarvisCyan = Color("JarvisCyan")
    static let jarvisWireframe = Color("Wireframe")
    static let jarvisHologram = Color("Hologram")
    static let jarvisGold = Color("StarkGold")
    static let jarvisAlert = Color("Alert")
    static let jarvisInk = Color("Ink")
}

enum JarvisFont {
    /// Display / wordmark / headings — Orbitron.
    static func hud(_ size: CGFloat, bold: Bool = false) -> Font {
        .custom(bold ? "Orbitron-Bold" : "Orbitron-Medium", size: size)
    }

    /// Chrome / data / readouts — JetBrains Mono.
    static func data(_ size: CGFloat, weight: DataWeight = .regular) -> Font {
        .custom(weight.postScriptName, size: size)
    }

    enum DataWeight {
        case regular, medium, bold

        var postScriptName: String {
            switch self {
            case .regular: return "JetBrainsMonoRoman-Regular"
            case .medium: return "JetBrainsMonoRoman-Medium"
            case .bold: return "JetBrainsMonoRoman-Bold"
            }
        }
    }
}

extension View {
    /// The signature cyan glow behind headline text and active chrome.
    func cyanGlow(radiusSmall: CGFloat = 3, radiusLarge: CGFloat = 11) -> some View {
        self
            .shadow(color: Color.jarvisCyan.opacity(0.55), radius: radiusSmall)
            .shadow(color: Color.jarvisCyan.opacity(0.22), radius: radiusLarge)
    }
}

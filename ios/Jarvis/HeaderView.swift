import SwiftUI

/// Matches the web client's `<header>`: spinning arc-reactor mark, glowing
/// "JARVIS" wordmark, and a breathing "Online" status pill.
struct HeaderView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var spin: Double = 0
    @State private var breathe: Double = 0.45

    var body: some View {
        HStack(alignment: .center, spacing: 14) {
            arcReactorMark
                .frame(width: 34, height: 34)

            VStack(alignment: .leading, spacing: 2) {
                Text("JARVIS")
                    .font(JarvisFont.hud(20, bold: true))
                    .tracking(6)
                    .foregroundStyle(Color.jarvisHologram)
                    .cyanGlow()
                Text("INTERFACE // MARK I")
                    .font(JarvisFont.data(9, weight: .medium))
                    .tracking(2)
                    .foregroundStyle(Color.jarvisCyan.opacity(0.55))
            }

            Spacer()

            HStack(spacing: 8) {
                Circle()
                    .fill(Color.jarvisCyan)
                    .frame(width: 7, height: 7)
                    .cyanGlow(radiusSmall: 2, radiusLarge: 5)
                    .opacity(breathe)
                Text("ONLINE")
                    .font(JarvisFont.data(9, weight: .medium))
                    .tracking(2)
            }
            .foregroundStyle(Color.jarvisCyan)
        }
        .padding(.horizontal, 4)
        .padding(.vertical, 12)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Color.jarvisLine).frame(height: 1)
        }
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.linear(duration: 8).repeatForever(autoreverses: false)) {
                spin = 360
            }
            withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true)) {
                breathe = 1.0
            }
        }
    }

    private var arcReactorMark: some View {
        ZStack {
            Circle().stroke(Color.jarvisLine, lineWidth: 2)
            Circle()
                .trim(from: 0, to: 0.7)
                .stroke(Color.jarvisWireframe, lineWidth: 2)
                .rotationEffect(.degrees(spin))
            Circle()
                .trim(from: 0, to: 0.6)
                .stroke(Color.jarvisCyan, lineWidth: 2)
                .padding(6)
                .rotationEffect(.degrees(-spin * 1.4))
            Circle()
                .fill(Color.jarvisHologram)
                .frame(width: 6, height: 6)
        }
    }
}

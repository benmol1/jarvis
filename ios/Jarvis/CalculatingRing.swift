import SwiftUI

/// The signature "Jarvis is working" gesture — a rotating cyan arc, matching
/// the web client's `.calc .ring` component. Respects Reduce Motion.
struct CalculatingRing: View {
    var diameter: CGFloat = 22

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var rotation: Double = 0

    var body: some View {
        ZStack {
            Circle()
                .stroke(Color.jarvisLine, lineWidth: 2.5)
            Circle()
                .trim(from: 0, to: 0.3)
                .stroke(Color.jarvisCyan, style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                .rotationEffect(.degrees(rotation))
        }
        .frame(width: diameter, height: diameter)
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.linear(duration: 1.6).repeatForever(autoreverses: false)) {
                rotation = 360
            }
        }
    }
}

/// "Processing" tier — used while an actual tool call is in flight, distinct
/// from the plain "Thinking" ring. Matches the design proposal's dual
/// counter-rotating arcs + gold ring + pulsing core. Respects Reduce Motion.
struct ProcessingRing: View {
    var diameter: CGFloat = 22

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var rotation: Double = 0
    @State private var counterRotation: Double = 0
    @State private var pulse: Double = 0.5

    var body: some View {
        ZStack {
            Circle()
                .trim(from: 0, to: 0.42)
                .stroke(Color.jarvisCyan, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                .rotationEffect(.degrees(rotation))
            Circle()
                .trim(from: 0, to: 0.5)
                .stroke(Color.jarvisWireframe, lineWidth: 2)
                .padding(diameter * 0.132)
                .rotationEffect(.degrees(-counterRotation))
            Circle()
                .stroke(Color.jarvisGold.opacity(0.7), lineWidth: 1.5)
                .padding(diameter * 0.265)
            Circle()
                .fill(Color.jarvisHologram)
                .frame(width: diameter * 0.18, height: diameter * 0.18)
                .opacity(pulse)
        }
        .frame(width: diameter, height: diameter)
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.linear(duration: 2.4).repeatForever(autoreverses: false)) {
                rotation = 360
            }
            withAnimation(.linear(duration: 3.6).repeatForever(autoreverses: false)) {
                counterRotation = 360
            }
            withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) {
                pulse = 1.0
            }
        }
    }
}

/// "Calculating…" text with an animated dot trio, mirroring the web client's
/// `.dots` CSS animation. Drawn as circles rather than literal "." characters
/// — JetBrains Mono's ligature table collapses three periods into a single
/// ellipsis glyph mid-animation, which looked like a glitch.
struct CalculatingLabel: View {
    var text: String

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var dotCount = 0

    private let timer = Timer.publish(every: 0.35, on: .main, in: .common).autoconnect()

    var body: some View {
        HStack(spacing: 4) {
            Text(text)
            HStack(spacing: 3) {
                ForEach(0..<3) { i in
                    Circle()
                        .frame(width: 3.5, height: 3.5)
                        .opacity(i < dotCount ? 1 : 0.18)
                }
            }
        }
        .onReceive(timer) { _ in
            guard !reduceMotion else { return }
            dotCount = (dotCount + 1) % 4
        }
    }
}

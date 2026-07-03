# Jarvis iOS

Written on Windows without Xcode, so this isn't a buildable `.xcodeproj` —
it's the two source files a minimal SwiftUI App project needs.

To use: File → New → App in Xcode (name it `Jarvis`, interface: SwiftUI),
then replace the generated `JarvisApp.swift` / `ContentView.swift` with the
ones in `Jarvis/`. Edit `backendURL` in `ContentView.swift` once the Pi's
tailnet hostname is known.

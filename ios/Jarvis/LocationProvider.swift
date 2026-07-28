import CoreLocation

/// One-shot best-effort location fixes for the current_location tool — not
/// continuous tracking, since Jarvis only needs "where is Ben right now" at
/// the moment he sends a message, not an ongoing feed. Never throws and never
/// blocks more than a few seconds: a denied permission or a stalled GPS fix
/// must not stop a chat message from sending, so callers just get nil.
final class LocationProvider: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private let lock = NSLock()
    private var pending: ((CLLocationCoordinate2D?) -> Void)?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func currentCoordinate() async -> CLLocationCoordinate2D? {
        if manager.authorizationStatus == .notDetermined {
            manager.requestWhenInUseAuthorization()
            // Authorization arrives asynchronously via the delegate; give Ben a
            // moment to respond to the prompt rather than failing immediately.
            try? await Task.sleep(for: .seconds(2))
        }
        guard manager.authorizationStatus == .authorizedWhenInUse
            || manager.authorizationStatus == .authorizedAlways
        else { return nil }

        return await withCheckedContinuation { continuation in
            lock.lock()
            pending = { continuation.resume(returning: $0) }
            lock.unlock()

            manager.requestLocation()

            Task {
                try? await Task.sleep(for: .seconds(3))
                self.fire(nil)
            }
        }
    }

    /// Resolves the in-flight continuation exactly once, whichever of
    /// requestLocation's callbacks or the timeout fires first.
    private func fire(_ coordinate: CLLocationCoordinate2D?) {
        lock.lock()
        let callback = pending
        pending = nil
        lock.unlock()
        callback?(coordinate)
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        fire(locations.last?.coordinate)
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        fire(nil)
    }
}

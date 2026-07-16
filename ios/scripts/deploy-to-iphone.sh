#!/bin/bash
# Build, install, and launch the Jarvis app on a connected physical iPhone.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT="$IOS_DIR/Jarvis.xcodeproj"
SCHEME="Jarvis"
BUNDLE_ID="com.bmolyneaux.jarvis"
CONFIGURATION="Debug"

echo "==> Looking for a connected iPhone..."
DEVICES_JSON="$SCRIPT_DIR/.devices.json"
xcrun devicectl list devices --json-output "$DEVICES_JSON" >/dev/null

DEVICE_INFO="$(python3 -c "
import json
with open('$DEVICES_JSON') as f:
    data = json.load(f)
for dev in data['result']['devices']:
    props = dev.get('connectionProperties', {})
    if props.get('pairingState') == 'paired':
        print(dev['identifier'])
        print(dev['deviceProperties']['name'])
        break
")"
rm -f "$DEVICES_JSON"

DEVICE_ID="$(echo "$DEVICE_INFO" | sed -n '1p')"
DEVICE_NAME="$(echo "$DEVICE_INFO" | sed -n '2p')"

if [ -z "$DEVICE_ID" ]; then
  echo "No paired iPhone found. Plug in your device, unlock it, and trust this Mac, then try again."
  exit 1
fi

echo "==> Found device: $DEVICE_NAME ($DEVICE_ID)"

DERIVED_DATA="$SCRIPT_DIR/.derivedData"

echo "==> Building $SCHEME for device..."
xcodebuild \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration "$CONFIGURATION" \
  -destination "platform=iOS,name=$DEVICE_NAME" \
  -derivedDataPath "$DERIVED_DATA" \
  build

APP_PATH="$(find "$DERIVED_DATA/Build/Products/$CONFIGURATION-iphoneos" -maxdepth 1 -iname "*.app" | head -1)"

if [ -z "$APP_PATH" ]; then
  echo "Build succeeded but couldn't locate the .app bundle in $DERIVED_DATA/Build/Products/$CONFIGURATION-iphoneos"
  exit 1
fi

echo "==> Installing $APP_PATH on $DEVICE_NAME..."
xcrun devicectl device install app --device "$DEVICE_ID" "$APP_PATH"

echo "==> Launching $BUNDLE_ID on $DEVICE_NAME..."
xcrun devicectl device process launch --device "$DEVICE_ID" "$BUNDLE_ID"

echo "==> Done."

#!/bin/bash
set -euo pipefail

APP_NAME="TranscribeOne"
VERSION="1.0.0"

echo "=== Building ${APP_NAME} v${VERSION} ==="

# Step 1: Clean previous builds
echo "Cleaning previous builds..."
rm -rf build/ dist/

# Step 2: Build with PyInstaller
echo "Building .app bundle..."
python3 -m PyInstaller TranscribeOne.spec --noconfirm

# Step 3: Verify the .app was created
APP_PATH="dist/${APP_NAME}.app"
if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: ${APP_PATH} not found!"
    exit 1
fi
echo "App bundle created: ${APP_PATH}"

# Step 4: Create DMG
echo "Creating DMG..."
DMG_NAME="${APP_NAME}-${VERSION}.dmg"
DMG_TEMP="dist/${APP_NAME}-temp.dmg"
DMG_FINAL="dist/${DMG_NAME}"

# Create temporary DMG
hdiutil create -size 200m -fs HFS+ -volname "${APP_NAME}" "$DMG_TEMP" -quiet

# Mount it
MOUNT_DIR=$(hdiutil attach "$DMG_TEMP" -nobrowse | tail -1 | awk '{print $3}')

# Copy the .app into the DMG
cp -R "$APP_PATH" "${MOUNT_DIR}/"

# Create symlink to /Applications for drag-to-install
ln -s /Applications "${MOUNT_DIR}/Applications"

# Unmount
hdiutil detach "$MOUNT_DIR" -quiet

# Convert to compressed final DMG
hdiutil convert "$DMG_TEMP" -format UDZO -o "$DMG_FINAL" -quiet

# Clean up temp
rm -f "$DMG_TEMP"

echo ""
echo "=== Build complete ==="
echo "  App: ${APP_PATH}"
echo "  DMG: ${DMG_FINAL}"
echo ""
echo "Note: The app is unsigned. On first launch, right-click > Open"
echo "      or go to System Settings > Privacy & Security to allow it."

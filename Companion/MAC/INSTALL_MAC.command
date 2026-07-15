#!/bin/bash
# ============================================================
#  Companion — Mac Installer
#  Double-click this file in Finder to install.
# ============================================================
clear
echo ""
echo "  ========================================="
echo "   Companion — Installing for Mac"
echo "  ========================================="
echo ""

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

INSTALL_DIR="$HOME/Applications/Companion"
PYTHON=""

# ── 1. Find Python ───────────────────────────────────────────
echo "  [1/5] Checking Python..."
for candidate in python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo ""
    echo "  ❌ Python 3 not found!"
    echo ""
    echo "  Install it from: https://www.python.org/downloads/"
    echo "  Or run: brew install python3"
    echo ""
    echo "  Then double-click this file again."
    echo ""
    read -n 1 -s -r -p "  Press any key to close..."
    exit 1
fi
echo "     Found: $PYTHON ($($PYTHON --version 2>&1))"

# ── 2. Install dependencies ─────────────────────────────────
echo "  [2/5] Installing dependencies..."
$PYTHON -m pip install --quiet --upgrade pip 2>/dev/null
$PYTHON -m pip install --quiet PySide6 pynput 2>/dev/null
echo "     Done"

# ── 3. Copy files to ~/Applications/Companion ───────────────
echo "  [3/5] Installing Companion..."
mkdir -p "$INSTALL_DIR"
for f in companion.py store.py editors.py muse.py sfx.py; do
    if [ -f "$DIR/$f" ]; then
        cp "$DIR/$f" "$INSTALL_DIR/"
    fi
done
# Copy data folder (SFX, etc.)
if [ -d "$DIR/data" ]; then
    cp -R "$DIR/data" "$INSTALL_DIR/" 2>/dev/null
fi
echo "     Installed to: $INSTALL_DIR"

# ── 4. Create launcher app (double-clickable in Finder) ──────
echo "  [4/5] Creating Companion.app..."
APP_DIR="$HOME/Applications/Companion.app"
MACOS_DIR="$APP_DIR/Contents/MacOS"
RESOURCES_DIR="$APP_DIR/Contents/Resources"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

# Info.plist
cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Companion</string>
    <key>CFBundleDisplayName</key>
    <string>Companion</string>
    <key>CFBundleIdentifier</key>
    <string>io.artlist.Companion</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>launch.sh</string>
    <key>LSBackgroundOnly</key>
    <false/>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
PLIST

# Launcher script inside the .app
cat > "$MACOS_DIR/launch.sh" << LAUNCHER
#!/bin/bash
cd "$INSTALL_DIR"
exec $PYTHON "$INSTALL_DIR/companion.py" &
disown
LAUNCHER
chmod +x "$MACOS_DIR/launch.sh"

# Generate icon if possible
if [ -f "$DIR/companion.ico" ]; then
    $PYTHON -c "
from PIL import Image
import os, tempfile, subprocess
img = Image.open('$DIR/companion.ico')
sizes = [16, 32, 64, 128, 256, 512]
iconset = os.path.join(tempfile.gettempdir(), 'Companion.iconset')
os.makedirs(iconset, exist_ok=True)
for s in sizes:
    resized = img.resize((s, s), Image.LANCZOS)
    resized.save(os.path.join(iconset, f'icon_{s}x{s}.png'))
    r2 = img.resize((s*2, s*2), Image.LANCZOS)
    r2.save(os.path.join(iconset, f'icon_{s}x{s}@2x.png'))
subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', '$RESOURCES_DIR/AppIcon.icns'], check=True)
" 2>/dev/null && {
        # Add icon reference to plist
        /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$APP_DIR/Contents/Info.plist" 2>/dev/null
    }
fi

echo "     Created: $APP_DIR"

# ── 5. Set up auto-start at login ────────────────────────────
echo "  [5/5] Setting auto-start at login..."
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$PLIST_DIR/io.artlist.Companion.plist"
mkdir -p "$PLIST_DIR"

cat > "$PLIST_FILE" << LAUNCHPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.artlist.Companion</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$INSTALL_DIR/companion.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
LAUNCHPLIST

echo "     Companion will start automatically at login"

# ── Launch it now ────────────────────────────────────────────
echo ""
echo "  ========================================="
echo "   ✅ Installation complete!"
echo "  ========================================="
echo ""
echo "   • Companion.app is in ~/Applications"
echo "   • It will start automatically at login"
echo "   • Double-tap Option (Alt) to wake/sleep"
echo "   • Ctrl+Option+Q to quit"
echo ""
echo "  Starting Companion now..."
echo ""

cd "$INSTALL_DIR"
$PYTHON companion.py &
disown

sleep 2
echo "  Companion is running! You can close this window."
echo ""
read -n 1 -s -r -p "  Press any key to close..."

#!/bin/bash
# ============================================================
#  Build Companion.app + Companion.dmg for macOS
#
#  Run on a Mac:
#    chmod +x build_mac.sh && ./build_mac.sh
#
#  Prerequisites (one-time):
#    pip3 install pyinstaller pillow PySide6 pynput
# ============================================================
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo ""
echo "  ========================================="
echo "   Companion — macOS Build"
echo "  ========================================="
echo ""

# ── 1. Generate .icns from .ico ───────────────────────────────
ICON_ARG=""
if [ -f companion.ico ]; then
    echo "  [1/3] Converting icon..."
    python3 -c "
from PIL import Image
import os, tempfile, subprocess
img = Image.open('companion.ico')
sizes = [16, 32, 64, 128, 256, 512]
iconset = os.path.join(tempfile.gettempdir(), 'Companion.iconset')
os.makedirs(iconset, exist_ok=True)
for s in sizes:
    resized = img.resize((s, s), Image.LANCZOS)
    resized.save(os.path.join(iconset, f'icon_{s}x{s}.png'))
    r2 = img.resize((s*2, s*2), Image.LANCZOS)
    r2.save(os.path.join(iconset, f'icon_{s}x{s}@2x.png'))
subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', 'companion.icns'], check=True)
" 2>/dev/null && ICON_ARG="--icon companion.icns" || echo "  (icon conversion skipped)"
else
    echo "  [1/3] No .ico found, skipping icon"
fi

# ── 2. PyInstaller → .app bundle ─────────────────────────────
echo "  [2/3] Building Companion.app..."
python3 -m PyInstaller --noconfirm --windowed --name Companion \
    $ICON_ARG \
    --add-data "data/SFX:SFX" \
    --hidden-import pynput.keyboard._darwin \
    --hidden-import pynput.mouse._darwin \
    --osx-bundle-identifier io.artlist.Companion \
    companion.py

# ── 3. DMG with drag-to-Applications ─────────────────────────
echo "  [3/3] Creating DMG..."
rm -f dist/Companion.dmg

STAGING=$(mktemp -d)
cp -R dist/Companion.app "$STAGING/"
ln -s /Applications "$STAGING/Applications"

hdiutil create -volname "Companion" \
    -srcfolder "$STAGING" \
    -ov -format UDZO \
    "dist/Companion.dmg"

rm -rf "$STAGING"

echo ""
echo "  ========================================="
echo "   Done! → dist/Companion.dmg"
echo "  ========================================="
echo ""
echo "  Send this one file to anyone with a Mac."
echo "  They open the DMG, drag to Applications,"
echo "  and double-click. It auto-starts on login."
echo ""

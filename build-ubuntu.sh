#!/usr/bin/env bash
set -e

echo "=== Corpus - Ubuntu build ==="

# System dependencies
echo "[1/4] Installing system dependencies..."
sudo apt update -qq
sudo apt install -y \
  nodejs npm python3 python3-pip \
  libgtk-3-0 libnotify4 libnss3 libxss1 libxtst6 \
  xdg-utils libatspi2.0-0 libuuid1 libsecret-1-0 fuse

# Python dependencies
echo "[2/4] Installing Python dependencies..."
python3 -m pip install --user opencv-python numpy pillow requests pandas matplotlib

# Node dependencies
echo "[3/4] Installing Node.js dependencies..."
npm install

# Build AppImage
echo "[4/4] Building AppImage..."
npm run package:ubuntu:appimage

echo ""
echo "=== Build complete ==="
APPIMAGE=$(ls dist/*.AppImage 2>/dev/null | head -1)
if [ -n "$APPIMAGE" ]; then
  chmod +x "$APPIMAGE"
  echo "AppImage: $APPIMAGE"
  echo ""
  echo "Run with:"
  echo "  env -u ELECTRON_RUN_AS_NODE PYTHON=python3 ./$APPIMAGE"
  echo ""
  echo "  (If launching from a VSCode terminal, env -u ELECTRON_RUN_AS_NODE prevents"
  echo "   VSCode from forcing the Electron binary into Node mode.)"
else
  echo "WARNING: No AppImage was found in dist/. Check the electron-builder output."
  exit 1
fi

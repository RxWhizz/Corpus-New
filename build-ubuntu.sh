#!/usr/bin/env bash
set -e

echo "=== Corpus — build para Ubuntu ==="

# Dependencias del sistema
echo "[1/4] Instalando dependencias del sistema..."
sudo apt update -qq
sudo apt install -y \
  nodejs npm python3 python3-pip \
  libgtk-3-0 libnotify4 libnss3 libxss1 libxtst6 \
  xdg-utils libatspi2.0-0 libuuid1 libsecret-1-0 fuse

# Dependencias Python
echo "[2/4] Instalando dependencias Python..."
python3 -m pip install --user opencv-python numpy pillow requests pandas matplotlib

# Dependencias Node
echo "[3/4] Instalando dependencias Node.js..."
npm install

# Build AppImage
echo "[4/4] Generando AppImage..."
npm run package:ubuntu:appimage

echo ""
echo "=== Build completado ==="
APPIMAGE=$(ls dist/*.AppImage 2>/dev/null | head -1)
if [ -n "$APPIMAGE" ]; then
  chmod +x "$APPIMAGE"
  echo "AppImage: $APPIMAGE"
  echo ""
  echo "Ejecutar con:"
  echo "  env -u ELECTRON_RUN_AS_NODE PYTHON=python3 ./$APPIMAGE"
  echo ""
  echo "  (Si lanzas desde VSCode terminal, usa env -u ELECTRON_RUN_AS_NODE para"
  echo "   evitar que VSCode ponga el binario en modo Node en vez de app Electron.)"
else
  echo "ADVERTENCIA: No se encontró AppImage en dist/. Revisa la salida de electron-builder."
  exit 1
fi

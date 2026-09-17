#!/usr/bin/env bash
# =============================================================================
# BLITZ CNC (Qt6) - Script di setup ambiente per Cloud Agent
# Idempotente: puo' essere eseguito piu' volte senza effetti collaterali.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# -----------------------------------------------------------------------------
# 1. Dipendenze di sistema: librerie Qt6/xcb, OpenGL, xvfb e toolchain di build
#    (necessarie per PySide6 headless e per compilare estensioni C come RPi.GPIO)
# -----------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  python3-venv python3-dev build-essential \
  libegl1 libgl1 libglib2.0-0 libdbus-1-3 \
  libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
  libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-xfixes0 \
  libxcb-shape0 libxcb-sync1 libxcb-cursor0 \
  xvfb x11-xserver-utils

# -----------------------------------------------------------------------------
# 2. Ambiente virtuale Python
# -----------------------------------------------------------------------------
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip

# -----------------------------------------------------------------------------
# 3. Dipendenze Python (GUI Qt6 + strumenti di test)
# -----------------------------------------------------------------------------
pip install -r requirements-qt6.txt -r requirements-test.txt

# -----------------------------------------------------------------------------
# 4. Configurazione dei percorsi di import.
#    L'app usa sia import con prefisso "qt6_app.ui_qt.*" sia import diretti
#    "ui_qt.*": entrambe le radici devono essere sul sys.path. Un file .pth
#    nel site-packages del venv le rende disponibili automaticamente, cosi'
#    "pytest" e "python qt6_app/main_qt.py" funzionano senza settare PYTHONPATH.
# -----------------------------------------------------------------------------
SITE_PACKAGES="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
{
  echo "$REPO_ROOT"
  echo "$REPO_ROOT/qt6_app"
} > "$SITE_PACKAGES/blitz_paths.pth"

echo "[install] Setup completato. Attiva l'ambiente con: source .venv/bin/activate"

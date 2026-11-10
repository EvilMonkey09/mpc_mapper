#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# MPC Mapper – baut eine fertige macOS-App ("MPC Mapper.app")
#
# Benutzung: Doppelklick im Finder.
# Klappt der Doppelklick nicht: Terminal öffnen, "bash " tippen (mit
# Leerzeichen), diese Datei ins Terminal ziehen, Enter.
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
APP_NAME="MPC Mapper"
BUILD_VENV="$PROJECT_DIR/.venv-build"

say_step() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }
fail() {
    printf '\n\033[1;31mFEHLER: %s\033[0m\n' "$1"
    printf '\nDrücke Enter, um dieses Fenster zu schließen.'
    read -r _ || true
    exit 1
}
trap 'fail "Unerwarteter Fehler in Zeile $LINENO. Bitte den Text oben abfotografieren."' ERR

# 1. Python prüfen ----------------------------------------------------------
say_step "Prüfe Python …"
if ! command -v python3 >/dev/null 2>&1; then
    open "https://www.python.org/downloads/" || true
    fail "Python 3 ist nicht installiert. Die Download-Seite wurde geöffnet: Python installieren und dieses Skript danach erneut starten."
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    fail "Python $(python3 -V 2>&1) ist zu alt. Bitte Python 3.9 oder neuer von python.org installieren."
fi
echo "Gefunden: $(python3 -V 2>&1) ($(uname -m))"

# 2. Build-Umgebung anlegen -------------------------------------------------
say_step "Richte Build-Umgebung ein (beim ersten Mal ein paar Minuten) …"
if [ ! -x "$BUILD_VENV/bin/python" ]; then
    python3 -m venv "$BUILD_VENV"
fi
"$BUILD_VENV/bin/python" -m pip install --upgrade pip --quiet
"$BUILD_VENV/bin/python" -m pip install -r requirements.txt "pyinstaller>=6.0" --quiet

# 3. App bauen --------------------------------------------------------------
say_step "Baue \"$APP_NAME.app\" …"
rm -rf build dist iconbuild
# App-Icon (.icns) aus dem 1024er PNG erzeugen
ICONSET=iconbuild/AppIcon.iconset
mkdir -p "$ICONSET"
for sz in 16 32 128 256 512; do
    sips -z $sz $sz mpc_mapper/assets/icon.png --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null
    sips -z $((sz*2)) $((sz*2)) mpc_mapper/assets/icon.png --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o iconbuild/AppIcon.icns
# mido lädt seinen MIDI-Treiber (rtmidi) erst zur Laufzeit per Name –
# deshalb muss er ausdrücklich mit eingepackt werden.
"$BUILD_VENV/bin/pyinstaller" \
    --noconfirm --clean --log-level WARN \
    --windowed \
    --icon iconbuild/AppIcon.icns \
    --name "$APP_NAME" \
    --osx-bundle-identifier "com.mpcmapper.app" \
    --paths "$PROJECT_DIR" \
    --hidden-import mido.backends.rtmidi \
    --hidden-import rtmidi \
    --add-data "ma3_plugin:ma3_plugin" \
    --add-data "mappings:mappings" \
    --add-data "mpc_mapper/assets:mpc_mapper/assets" \
    packaging/launcher.py

APP_PATH="$PROJECT_DIR/dist/$APP_NAME.app"
[ -d "$APP_PATH" ] || fail "Die App wurde nicht erzeugt."

# 4. In den Programme-Ordner kopieren -----------------------------------------
say_step "Kopiere die App in den Programme-Ordner …"
if [ -w /Applications ]; then
    TARGET_DIR="/Applications"
else
    TARGET_DIR="$HOME/Applications"
    mkdir -p "$TARGET_DIR"
fi
rm -rf "$TARGET_DIR/$APP_NAME.app"
cp -R "$APP_PATH" "$TARGET_DIR/"

# Die grandMA3-Plugin-Dateien zum Kopieren auf den USB-Stick griffbereit legen
mkdir -p "$PROJECT_DIR/dist/grandMA3-Plugin"
cp ma3_plugin/APC_Feedback.xml ma3_plugin/APC_Feedback.lua "$PROJECT_DIR/dist/grandMA3-Plugin/"

trap - ERR
printf '\n\033[1;32mFertig!\033[0m "%s" liegt jetzt in %s.\n' "$APP_NAME" "$TARGET_DIR"
echo "Die Plugin-Dateien für das Pult liegen in: $PROJECT_DIR/dist/grandMA3-Plugin"
echo
echo "Du kannst dieses Fenster jetzt schließen. Die App startest du wie jedes"
echo "andere Programm (Launchpad oder Programme-Ordner)."
open -R "$TARGET_DIR/$APP_NAME.app" || true
printf '\nDrücke Enter, um dieses Fenster zu schließen.'
read -r _ || true

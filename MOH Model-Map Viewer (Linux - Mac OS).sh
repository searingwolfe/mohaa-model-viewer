#!/usr/bin/env bash
# ==============================================================================
#  MOH Model-Map Viewer (Linux - Mac OS).sh   (Linux and macOS)
#  Starts the MOHAA Map Viewer or Model Viewer, picked from a menu: 1 / 2, or
#  Up / Down and Enter or Space (1, the Map Viewer, is selected at first); Q or Esc quits.
#  Pass a .bsp / .map / .bak file to open it in the Map Viewer, or a .skd / .tik
#  in the Model Viewer: the menu is skipped then.
#
#  Steps (the terminal pauses ONCE, at the very end, when run interactively):
#    1. Python 3.8 or newer with tkinter (python3 first, then python3.x on PATH).
#    2. The menu (bin/mohaa_envcheck.py menu), unless a file was given.
#    3. Packages vendored into bin/libs-linux (bin/libs-mac on macOS) by
#       bin/mohaa_envcheck.py with "python -m pip install --target". This works on
#       distributions that block pip system-wide (Ubuntu / Kubuntu 23.04+, PEP 668):
#       nothing is installed into the system Python.
#    4. Starts the program and waits for it to close. Logs: output/logs/.
#  Started without a terminal (double-clicked in a Linux file manager), it reopens
#  itself in one so the menu can be answered. Written for bash 3.2, the one macOS
#  ships, as well as newer ones.
# ==============================================================================
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF="$HERE/$(basename "${BASH_SOURCE[0]}")"
BIN="$HERE/bin"
case "$(uname -s)" in
    Darwin) LIBS="$BIN/libs-mac" ;;
    *)      LIBS="$BIN/libs-linux" ;;
esac
EXIT_CODE=0
FIRST=""
MODE=""
for a in "$@"; do
    case "$(printf '%s' "$a" | tr '[:upper:]' '[:lower:]')" in
        *.bsp|*.map|*.bak) MODE="map" ;;
        *.skd|*.tik) MODE="model" ;;
        *) continue ;;
    esac
    FIRST="$a"
    break
done

finish() {
    echo
    if [ "$EXIT_CODE" -eq 0 ]; then echo "[OK] Done."
    else echo "[ERROR] Finished with exit code $EXIT_CODE. Details: $HERE/output/logs" >&2; fi
    if [ -t 0 ]; then read -r -p "Press Enter to exit..." _; fi
    exit "$EXIT_CODE"
}

# No terminal (double-clicked in a file manager): reopen in one, so the menu can be
# answered. A file passed in goes along. If no terminal program is found, carry on:
# a file still opens; the menu, with nothing to read keys from, quits.
if [ ! -t 0 ] && [ -z "${MOHAA_IN_TERMINAL:-}" ]; then
    export MOHAA_IN_TERMINAL=1
    if [ "$(uname -s)" = "Darwin" ]; then
        [ -z "$FIRST" ] && exec open -a Terminal "$SELF"
    else
        for t in x-terminal-emulator konsole gnome-terminal xfce4-terminal mate-terminal xterm; do
            command -v "$t" >/dev/null 2>&1 || continue
            case "$t" in
                gnome-terminal)               exec "$t" -- "$SELF" ${FIRST:+"$FIRST"} ;;
                xfce4-terminal|mate-terminal) exec "$t" -x "$SELF" ${FIRST:+"$FIRST"} ;;
                *)                            exec "$t" -e "$SELF" ${FIRST:+"$FIRST"} ;;
            esac
        done
    fi
fi

for f in mohaa_common.py mohaa_envcheck.py; do
    if [ ! -f "$BIN/$f" ]; then
        echo "[ERROR] $f was not found in $BIN." >&2
        echo "        Download the program again from https://github.com/searingwolfe/mohaa-model-viewer" >&2
        EXIT_CODE=1; finish
    fi
done

# 1. Python 3.8+ with tkinter: the first candidate that passes wins.
PY=""; NOTK=""; OLD=""
for c in python3 python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3.8; do
    p="$(command -v "$c" 2>/dev/null)" || continue
    if ! "$p" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 8) else 1)' 2>/dev/null; then
        OLD="$p"; continue
    fi
    if ! "$p" -c 'import tkinter' 2>/dev/null; then NOTK="$p"; continue; fi
    PY="$p"; break
done
if [ -z "$PY" ]; then
    echo "[ERROR] The MOHAA Map Viewer and Model Viewer need Python 3.8 or newer, with tkinter." >&2
    [ -n "$OLD" ] && echo "        $OLD is too old." >&2
    if [ -n "$NOTK" ]; then
        echo "        $NOTK has no tkinter. Install it with one of:" >&2
        echo "          sudo apt install python3-tk        (Debian / Ubuntu / Kubuntu / Mint)" >&2
        echo "          sudo dnf install python3-tkinter   (Fedora / RHEL)" >&2
        echo "          sudo pacman -S tk                  (Arch)" >&2
        echo "          brew install python-tk             (macOS)" >&2
    fi
    EXIT_CODE=1; finish
fi

# 2. Which program: the menu, unless a file was given. 11 = Map Viewer,
#    12 = Model Viewer, 10 = quit; anything else is an error.
if [ -z "$MODE" ]; then
    "$PY" "$BIN/mohaa_envcheck.py" menu
    rc=$?
    case "$rc" in
        10) exit 0 ;;
        11) MODE="map" ;;
        12) MODE="model" ;;
        *)  echo "[ERROR] The menu stopped unexpectedly (exit code $rc)." >&2; EXIT_CODE=1; finish ;;
    esac
fi
if [ "$MODE" = "map" ]; then
    NAME="Map Viewer"
    LAUNCHER="mohaa_map_launcher.py"
    FILES="mohaa_map_launcher.py mohaa_map_view.py mohaa_map_page.py mohaa_bsp.py mohaa_entdefs.py mohaa_map_actor.py mohaa_launcher.py mohaa_view.py mohaa_textures.py"
else
    NAME="Model Viewer"
    LAUNCHER="mohaa_launcher.py"
    FILES="mohaa_launcher.py mohaa_view.py mohaa_textures.py"
fi
printf '\033]0;MOHAA %s\007' "$NAME"
echo "[OK] $("$PY" -c 'import sys; print("Python %d.%d" % sys.version_info[:2])'): $PY"
echo

for f in $FILES; do
    if [ ! -f "$BIN/$f" ]; then
        echo "[ERROR] $f was not found in $BIN." >&2
        echo "        Download the program again from https://github.com/searingwolfe/mohaa-model-viewer" >&2
        EXIT_CODE=1; finish
    fi
done

# 3. Packages into the vendored libs folder.
if ! "$PY" "$BIN/mohaa_envcheck.py" deps "$LIBS"; then
    echo >&2
    echo "[ERROR] A required package could not be installed (see the lines above)." >&2
    EXIT_CODE=1; finish
fi
echo

# 4. The program.
echo "Starting the $NAME ..."
if [ -n "$FIRST" ]; then "$PY" "$BIN/$LAUNCHER" "$FIRST"; else "$PY" "$BIN/$LAUNCHER"; fi
EXIT_CODE=$?
finish

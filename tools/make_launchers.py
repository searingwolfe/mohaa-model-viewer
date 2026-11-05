#!/usr/bin/env python3
"""Generate the two RUN launchers, one per system, each starting either program:
    MOH Model-Map Viewer (Windows x86-x64).bat   (Windows)
    MOH Model-Map Viewer (Linux - Mac OS).sh    (Linux and macOS)
A menu picks the Map Viewer (1) or the Model Viewer (2); a file dropped on the launcher (or
passed to it) skips the menu and opens in the program for its kind. The menu itself is
bin/mohaa_envcheck.py's "menu" command, so it works the same on every system.
The .bat is written with CRLF line endings and ASCII only; the .sh with LF and the
executable bit. Edit the BAT / SH templates or the PROGRAMS list below, never the generated
files, then run:   python tools/make_launchers.py   and   python tests/check_batch_files.py
Optional argument: the project folder (default: the parent of this tools/ folder)."""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# the launchers of earlier versions (one per program and system, then the first pair's
# names), which these two replace
OLD = ["RUN -- Medal of Honor Model Viewer.bat", "RUN -- Medal of Honor Map Viewer.bat",
       "RUN -- Medal of Honor Model Viewer.sh", "RUN -- Medal of Honor Map Viewer.sh",
       "RUN -- Medal of Honor Viewer.bat", "RUN -- Medal of Honor Viewer.sh"]
COMMON = ["mohaa_common.py", "mohaa_envcheck.py"]          # needed before the menu
PROGRAMS = {
    "map": dict(NAME="Map Viewer", EXTS=[".bsp", ".map", ".bak"], LAUNCHER="mohaa_map_launcher.py",
                FILES=["mohaa_map_launcher.py", "mohaa_map_view.py", "mohaa_map_page.py", "mohaa_bsp.py",
                       "mohaa_entdefs.py", "mohaa_launcher.py", "mohaa_view.py", "mohaa_textures.py"]),
    "model": dict(NAME="Model Viewer", EXTS=[".skd", ".tik"], LAUNCHER="mohaa_launcher.py",
                  FILES=["mohaa_launcher.py", "mohaa_view.py", "mohaa_textures.py"]),
}

BAT = r'''@echo off
REM ============================================================================
REM  MOH Model-Map Viewer (Windows x86-x64).bat
REM  Starts the MOHAA Map Viewer or Model Viewer, picked from a menu: 1 / 2, or
REM  Up / Down and Enter (1, the Map Viewer, is selected at first); Q or Esc quits.
REM  Drop a .bsp / .map / .bak file onto this to open it in the Map Viewer, or a
REM  .skd / .tik in the Model Viewer: the menu is skipped then. Expects the scripts
REM  in the bin\ folder next to this file.
REM
REM  Steps, in order. When the program's window opens, this window closes by
REM  itself; if anything goes wrong it stays open and pauses ONCE, at the end.
REM    1. Python 3.8 or newer with tkinter. If there is none, it offers to run
REM       bin\python_installer_updater.bat (Y/N; waits for your answer).
REM    2. The menu (bin\mohaa_envcheck.py menu), unless a file was dropped.
REM    3. Packages, vendored into bin\libs (never into Python itself), checked and
REM       installed by bin\mohaa_envcheck.py with "python -m pip --target":
REM       Pillow 10.3+ (required), and on Windows 8.1+ the optional embedded 3D
REM       pane packages (pythonnet, pywebview 4.4.1, tkwebview2).
REM    4. Starts the program without a console (mohaa_envcheck.py start) and waits
REM       until its window is open, then closes. Everything this window printed is
REM       saved in output\logs\run_map.log (run_model.log) and shown at the top of
REM       the program's Output pane. Errors and the full log: output\logs\.
REM  All version checks, installs and the menu live in mohaa_envcheck.py; this
REM  file only orchestrates (hardened coding practice: logic in Python, not batch).
REM ============================================================================

REM Arguments are read before delayed expansion is turned on, so a ! in a path
REM survives. They're walked one at a time with shift, because expanding them all
REM at once leaves them unquoted and splits a file name containing an ampersand.
REM The first file of a kind the programs open decides which one starts. No
REM parenthesized blocks here, so a ) in a path such as "Program Files (x86)"
REM can't break the parse.
setlocal DisableDelayedExpansion
title MOHAA Viewer
set "EXIT_CODE=0"
set "BIN=%~dp0bin"
set "LIBS=%~dp0bin\libs"
set "FIRST="
set "MODE="
:argloop
if "%~1"=="" goto argdone
@ARGTESTS@if defined MODE if not defined FIRST set "FIRST=%~1"
shift
goto argloop
:argdone
setlocal EnableDelayedExpansion

for %%F in (@COMMON@) do (
    if not exist "!BIN!\%%F" (
        echo [ERROR] %%F was not found in the bin folder next to this file.
        echo         Download the program again from https://github.com/searingwolfe/mohaa-model-viewer
        set "EXIT_CODE=1"
        goto end
    )
)

REM Scratch file for reading one line of Python output, unique per run so two
REM launchers started together can't read each other's answer. Python is run directly
REM and its output read back with set /p, rather than through for /f, which runs the
REM command via cmd /c and mangles a quoted interpreter path.
set "R_OUT=%TEMP%\mohaa_run_%RANDOM%%RANDOM%.txt"
set "R_TRIED="

REM ----------------------------------------------------------------------------
REM  1. PYTHON 3.8+ WITH TKINTER  (both programs need it, so it comes first)
REM ----------------------------------------------------------------------------
:find_python
set "R_PY="
set "R_VER="
set "R_NUM="
set "R_OLD="
set "R_NOTK="
REM The py launcher's default interpreter first, since it's normally the newest.
where py >nul 2>nul
if errorlevel 1 goto search_more
py -3 -c "import sys;print(sys.executable)" 1>"%R_OUT%" 2>nul
if errorlevel 1 goto search_more
set "R_CAND="
set /p R_CAND=<"%R_OUT%"
if defined R_CAND call :consider "!R_CAND!"
if defined R_PY goto python_ok
:search_more
REM Then python.exe on PATH and the default install folders. PATH is checked for
REM completeness, but a Python installed moments ago by the installer is only on
REM the PATH of new windows, so the folders are searched as well.
for /f "delims=" %%P in ('where python 2^>nul') do call :consider "%%P"
for /f "delims=" %%P in ('where python3 2^>nul') do call :consider "%%P"
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :consider "%%~D\python.exe"
for /d %%D in ("%ProgramFiles%\Python3*") do call :consider "%%~D\python.exe"
if defined R_PY goto python_ok
if defined R_TRIED goto python_still_missing

echo  The MOHAA Map Viewer and Model Viewer need Python 3.8 or newer, with tkinter.
if defined R_OLD echo  Found Python !R_OLD!, which is too old.
if defined R_NOTK echo  Found Python !R_NOTK!, but it was installed without tkinter ^(tcl/tk^).
if not defined R_OLD if not defined R_NOTK echo  No Python installation was found.
echo.
echo    Y = install it now. Runs bin\python_installer_updater.bat, which downloads
echo        Python from python.org and installs the viewers' packages.
echo    N = stop here, so you can install it yourself from
echo        https://www.python.org/downloads/  ^(tick "tcl/tk" and "Add python.exe to PATH"^)
echo.
choice /c YN /m "Install Python now"
if errorlevel 2 goto declined
set "R_TRIED=1"
echo.
call "!BIN!\python_installer_updater.bat" /fromrun
echo.
goto find_python

:declined
echo [INFO] Python was not installed. Install it from https://www.python.org/downloads/
echo        ^(tick "tcl/tk"^), then run this file again.
set "EXIT_CODE=1"
goto end

:python_still_missing
echo [ERROR] Python 3.8 or newer with tkinter still wasn't found. If it was just
echo         installed, close this window and run this file again. Otherwise install
echo         it from https://www.python.org/downloads/ and tick "tcl/tk".
set "EXIT_CODE=1"
goto end

:python_ok

REM ----------------------------------------------------------------------------
REM  2. WHICH PROGRAM  (the menu, unless a file was dropped)
REM  mohaa_envcheck.py menu exits 11 for the Map Viewer, 12 for the Model Viewer,
REM  10 to quit; anything else is an error. Compared exactly: "if errorlevel N"
REM  would mean N or higher.
REM ----------------------------------------------------------------------------
if defined MODE goto mode_set
"!R_PY!" "!BIN!\mohaa_envcheck.py" menu
set "R_RC=!errorlevel!"
if "!R_RC!"=="10" goto end
if "!R_RC!"=="11" set "MODE=map"
if "!R_RC!"=="12" set "MODE=model"
if defined MODE goto mode_set
echo [ERROR] The menu stopped unexpectedly ^(exit code !R_RC!^).
set "EXIT_CODE=1"
goto end

:mode_set
if /i "!MODE!"=="map" goto mode_map
@SET_model@goto mode_done
:mode_map
@SET_map@:mode_done
title MOHAA !R_NAME!
echo [OK] Python !R_VER!: !R_PY!
echo.

for %%F in (!R_FILES!) do (
    if not exist "!BIN!\%%F" (
        echo [ERROR] %%F was not found in the bin folder next to this file.
        echo         Download the program again from https://github.com/searingwolfe/mohaa-model-viewer
        set "EXIT_CODE=1"
        goto end
    )
)

REM ----------------------------------------------------------------------------
REM  3. PACKAGES  (into bin\libs; required Pillow, optional embedded pane)
REM ----------------------------------------------------------------------------
"!R_PY!" "!BIN!\mohaa_envcheck.py" deps "!LIBS!" --embed --log !R_LOG!
if errorlevel 1 goto deps_failed
echo.
goto launch

:deps_failed
echo.
echo [ERROR] A required package could not be installed ^(see the lines above^).
echo         Check your internet connection and run this file again.
set "EXIT_CODE=1"
goto end

REM ----------------------------------------------------------------------------
REM  4. START THE PROGRAM  (without a console; this window closes once it is open)
REM ----------------------------------------------------------------------------
:launch
echo Starting the !R_NAME! ... ^(this window closes once it is open^)
if defined FIRST goto launch_with_file
"!R_PY!" "!BIN!\mohaa_envcheck.py" start !R_LOG! "!BIN!\!R_LAUNCHER!"
set "EXIT_CODE=!errorlevel!"
goto end
:launch_with_file
"!R_PY!" "!BIN!\mohaa_envcheck.py" start !R_LOG! "!BIN!\!R_LAUNCHER!" "!FIRST!"
set "EXIT_CODE=!errorlevel!"
goto end

REM ----------------------------------------------------------------------------
REM  The end: closes when the program started (or Quit was picked), else pauses
REM  once to show why.
REM ----------------------------------------------------------------------------
:end
if defined R_OUT del "%R_OUT%" 1>nul 2>&1
if "!EXIT_CODE!"=="0" exit /b 0
echo.
echo [ERROR] Finished with exit code !EXIT_CODE!. Details: "%~dp0output\logs"
pause
exit /b !EXIT_CODE!

REM ============================================================================
REM  :consider "<path to python.exe>"
REM  Keeps the newest candidate that is Python 3.8+ with tkinter in R_PY / R_VER.
REM  Records rejected versions in R_OLD / R_NOTK for the message above. Microsoft
REM  Store aliases under WindowsApps are skipped: they only open the Store.
REM ============================================================================
:consider
if not exist "%~1" goto :eof
echo "%~1" | find /i "\WindowsApps\" 1>nul
if not errorlevel 1 goto :eof
set "R_CN="
REM Prints the version as major*100+minor (3.12 is 312), then fails with exit code 1
REM if tkinter can't be imported.
"%~1" -c "import sys;print(sys.version_info[0]*100+sys.version_info[1]);import tkinter" 1>"%R_OUT%" 2>nul
set "R_TK=!errorlevel!"
set /p R_CN=<"%R_OUT%"
if not defined R_CN goto :eof
set /a R_CNUM=R_CN, R_CMAJ=R_CN/100, R_CMIN=R_CN%%100
set "R_CV=!R_CMAJ!.!R_CMIN!"
if !R_CNUM! LSS 308 goto consider_old
if not "!R_TK!"=="0" goto consider_notk
if defined R_NUM if !R_CNUM! LEQ !R_NUM! goto :eof
set "R_PY=%~1"
set "R_VER=!R_CV!"
set "R_NUM=!R_CNUM!"
goto :eof
:consider_old
set "R_OLD=!R_CV!"
goto :eof
:consider_notk
set "R_NOTK=!R_CV!"
goto :eof
'''

SH = r'''#!/usr/bin/env bash
# ==============================================================================
#  MOH Model-Map Viewer (Linux - Mac OS).sh   (Linux and macOS)
#  Starts the MOHAA Map Viewer or Model Viewer, picked from a menu: 1 / 2, or
#  Up / Down and Enter (1, the Map Viewer, is selected at first); Q or Esc quits.
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
        @SH_map@) MODE="map" ;;
        @SH_model@) MODE="model" ;;
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

for f in @COMMON@; do
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
@SHSET_map@else
@SHSET_model@fi
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
'''


def bat_set(p, log):
    """The batch lines that set one program's name, log name, launcher and files."""
    return ('set "R_NAME=%s"\nset "R_LOG=%s"\nset "R_LAUNCHER=%s"\nset "R_FILES=%s"\n'
            % (p["NAME"], log, p["LAUNCHER"], " ".join(p["FILES"])))


def sh_set(p):
    """The shell lines that set one program's name, launcher and files."""
    return ('    NAME="%s"\n    LAUNCHER="%s"\n    FILES="%s"\n' % (p["NAME"], p["LAUNCHER"], " ".join(p["FILES"])))


def main():
    """Write both launchers and remove the four old ones from the project folder."""
    tests = "".join('if not defined MODE if /i "%%~x1"=="%s" set "MODE=%s"\n' % (e, m)
                    for m in ("map", "model") for e in PROGRAMS[m]["EXTS"])
    b = (BAT.replace("@ARGTESTS@", tests).replace("@COMMON@", " ".join(COMMON))
            .replace("@SET_map@", bat_set(PROGRAMS["map"], "map"))
            .replace("@SET_model@", bat_set(PROGRAMS["model"], "model")))
    b = b.replace("\r\n", "\n").replace("\n", "\r\n")
    p = os.path.join(ROOT, "MOH Model-Map Viewer (Windows x86-x64).bat")
    with open(p, "wb") as f:
        f.write(b.encode("ascii"))
    sh = (SH.replace("@COMMON@", " ".join(COMMON))
            .replace("@SH_map@", "|".join("*" + e for e in PROGRAMS["map"]["EXTS"]))
            .replace("@SH_model@", "|".join("*" + e for e in PROGRAMS["model"]["EXTS"]))
            .replace("@SHSET_map@", sh_set(PROGRAMS["map"]))
            .replace("@SHSET_model@", sh_set(PROGRAMS["model"])))
    p2 = os.path.join(ROOT, "MOH Model-Map Viewer (Linux - Mac OS).sh")
    with open(p2, "wb") as f:
        f.write(sh.encode("ascii"))
    os.chmod(p2, 0o755)
    print("wrote", p, "and", p2)
    for name in OLD:
        old = os.path.join(ROOT, name)
        if os.path.isfile(old):
            os.remove(old)
            print("removed", old)


if __name__ == "__main__":
    main()

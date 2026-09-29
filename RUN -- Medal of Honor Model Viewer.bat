@echo off
REM ============================================================================
REM  RUN -- Medal of Honor Model Viewer.bat
REM  Starts the MOHAA Model Viewer launcher. Drop a .skd/.tik file onto this to
REM  open it directly, or double-click to browse for one. Expects the scripts in
REM  the bin\ folder next to this file.
REM
REM  Before starting the launcher it checks, in order:
REM    1. Python 3.8 or newer with tkinter. If there is none, it offers to run
REM       bin\python_installer_updater.bat, or closes so you can install it yourself.
REM    2. Pillow 10.3 or newer, which decodes the game's textures. Installed with pip
REM       if missing; required.
REM    3. pythonnet, pywebview 4.4.1 and tkwebview2 for the embedded 3D pane, on
REM       Windows 8.1 and newer. Installed if missing; optional, since models open
REM       in the default browser without them.
REM    4. The Microsoft Edge WebView2 Runtime the embedded pane runs on. Only
REM       reported; it ships with Windows 10 and 11.
REM  Then it starts the launcher without a console window and this window closes.
REM ============================================================================

REM Arguments are read before delayed expansion is turned on, so a ! in a path
REM survives. They're walked one at a time with shift, because expanding them all
REM at once leaves them unquoted and splits a file name containing an ampersand.
setlocal DisableDelayedExpansion
set "BIN=%~dp0bin"
set "FIRST="
:argloop
if "%~1"=="" goto argdone
if not defined FIRST if /i "%~x1"==".skd" set "FIRST=%~1"
if not defined FIRST if /i "%~x1"==".tik" set "FIRST=%~1"
shift
goto argloop
:argdone
setlocal EnableDelayedExpansion

for %%F in (mohaa_launcher.py mohaa_view.py mohaa_textures.py) do (
    if not exist "!BIN!\%%F" (
        echo %%F was not found in the bin folder next to this file.
        echo Download the program again from https://github.com/searingwolfe/mohaa-model-viewer
        pause
        exit /b 1
    )
)

REM Scratch file for reading one line of Python output. Python is run directly and
REM its output read back with set /p, rather than through for /f, which runs the
REM command via cmd /c and mangles a quoted interpreter path.
set "R_OUT=%TEMP%\mohaa_run_check.txt"
set "R_TRIED="

REM ----------------------------------------------------------------------------
REM  1. PYTHON 3.8+ WITH TKINTER
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
py -3 -c "import sys;print(sys.executable)" > "%R_OUT%" 2>nul
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
echo.
echo  MOHAA Model Viewer needs Python 3.8 or newer, installed with tkinter.
if defined R_OLD echo  Found Python !R_OLD!, which is too old.
if defined R_NOTK echo  Found Python !R_NOTK!, but it was installed without tkinter ^(tcl/tk^).
if not defined R_OLD if not defined R_NOTK echo  No Python installation was found.
echo.
echo    Y = install it now. Runs bin\python_installer_updater.bat, which downloads
echo        Python from python.org and installs the viewer's packages.
echo    N = close this window and install it yourself from
echo        https://www.python.org/downloads/  ^(tick "tcl/tk" and "Add python.exe to PATH"^)
echo.
choice /c YN /m "Install Python now"
if errorlevel 2 goto cleanup_fail
set "R_TRIED=1"
echo.
call "!BIN!\python_installer_updater.bat" /fromrun
echo.
goto find_python

:python_still_missing
echo.
echo Python 3.8 or newer with tkinter still wasn't found. If it was just installed,
echo close this window and run this file again. Otherwise install it from
echo https://www.python.org/downloads/ and tick "tcl/tk" in the installer.
pause
goto cleanup_fail

:python_ok
echo Using Python !R_VER!: !R_PY!

REM ----------------------------------------------------------------------------
REM  2. PILLOW 10.3+  (required)
REM ----------------------------------------------------------------------------
set "R_PIL=import PIL,sys;v=tuple(int(x) for x in PIL.__version__.split('.')[:2]);sys.exit(0 if v>=(10,3) else 1)"
"!R_PY!" -c "!R_PIL!" >nul 2>nul
if not errorlevel 1 goto pillow_ok

echo.
echo Pillow 10.3 or newer is missing; it's needed to show textures. Installing it now...
echo.
REM Some Python builds ship without pip; ensurepip adds it.
"!R_PY!" -m pip --version >nul 2>nul
if errorlevel 1 "!R_PY!" -m ensurepip --upgrade >nul 2>nul
"!R_PY!" -m pip install --upgrade "Pillow>=10.3.0"
"!R_PY!" -c "!R_PIL!" >nul 2>nul
if not errorlevel 1 goto pillow_ok
echo.
echo Standard install did not work; retrying as a per-user install...
"!R_PY!" -m pip install --user --upgrade "Pillow>=10.3.0"
"!R_PY!" -c "!R_PIL!" >nul 2>nul
if not errorlevel 1 goto pillow_ok
echo.
echo Could not install Pillow automatically. Run this command yourself, then run
echo this file again:
echo     "!R_PY!" -m pip install --upgrade "Pillow>=10.3.0"
pause
goto cleanup_fail
:pillow_ok

REM ----------------------------------------------------------------------------
REM  3. EMBEDDED 3D PANE PACKAGES  (optional, Windows 8.1+)
REM  pywebview is pinned to 4.4.1 because tkwebview2 3.5.0 uses its internals.
REM ----------------------------------------------------------------------------
REM "ver" prints e.g. "Microsoft Windows [Version 10.0.22631.4602]".
set "R_WMAJ=10"
set "R_WMIN=0"
for /f "tokens=4,5 delims=. " %%a in ('ver') do (
    set "R_WMAJ=%%a"
    set "R_WMIN=%%b"
)
if !R_WMAJ! LSS 6 goto embed_unsupported
if !R_WMAJ! EQU 6 if !R_WMIN! LSS 3 goto embed_unsupported

"!R_PY!" -c "import tkwebview2" >nul 2>nul
if not errorlevel 1 goto embed_ok
echo.
echo Installing the embedded 3D pane packages ^(pythonnet, pywebview, tkwebview2^)...
echo This is optional: if it fails, models open in your default browser instead.
echo.
"!R_PY!" -m pip install pythonnet "pywebview==4.4.1" tkwebview2
"!R_PY!" -c "import tkwebview2" >nul 2>nul
if not errorlevel 1 goto embed_ok
echo.
echo The embedded pane packages could not be installed; models will open in your
echo default browser instead.
goto launch

:embed_unsupported
echo The embedded 3D pane needs Windows 8.1 or newer; models will open in your
echo default browser instead.
goto launch

REM ----------------------------------------------------------------------------
REM  4. WEBVIEW2 RUNTIME  (reported only)
REM  Installed if a "pv" version other than 0.0.0.0 exists under any of these keys
REM  (Microsoft's documented check). WebGL needs nothing extra: it comes with the
REM  runtime or browser, and the viewer falls back to its 2D renderer without it.
REM ----------------------------------------------------------------------------
:embed_ok
set "R_WV2="
for %%K in ("HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "HKCU\Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}") do (
    for /f "tokens=3" %%v in ('reg query %%K /v pv 2^>nul ^| find "REG_SZ"') do (
        if not "%%v"=="0.0.0.0" set "R_WV2=%%v"
    )
)
if defined R_WV2 goto launch
echo.
echo Note: the Microsoft Edge WebView2 Runtime isn't installed, so models will open
echo in your default browser. To use the embedded pane, install it from
echo https://developer.microsoft.com/microsoft-edge/webview2/
echo.
timeout /t 3 >nul

REM ----------------------------------------------------------------------------
REM  START THE LAUNCHER
REM  pythonw.exe next to the chosen python.exe runs it without a console window and
REM  with the same packages; this window then closes.
REM ----------------------------------------------------------------------------
:launch
call :pythonw_for "!R_PY!"
if defined FIRST (
    start "" "!R_PYW!" "!BIN!\mohaa_launcher.py" "!FIRST!"
) else (
    start "" "!R_PYW!" "!BIN!\mohaa_launcher.py"
)
del "%R_OUT%" >nul 2>&1
exit /b 0

:cleanup_fail
del "%R_OUT%" >nul 2>&1
exit /b 1

REM pythonw.exe beside the given python.exe, or python.exe itself if there is none.
:pythonw_for
set "R_PYW=%~dp1pythonw.exe"
if not exist "%R_PYW%" set "R_PYW=%~1"
goto :eof

REM ============================================================================
REM  :consider "<path to python.exe>"
REM  Keeps the newest candidate that is Python 3.8+ with tkinter in R_PY / R_VER.
REM  Records rejected versions in R_OLD / R_NOTK for the message above. Microsoft
REM  Store aliases under WindowsApps are skipped: they only open the Store.
REM ============================================================================
:consider
if not exist "%~1" goto :eof
echo "%~1" | find /i "\WindowsApps\" >nul
if not errorlevel 1 goto :eof
set "R_CN="
REM Prints the version as major*100+minor (3.12 is 312), then fails with exit code 1
REM if tkinter can't be imported.
"%~1" -c "import sys;print(sys.version_info[0]*100+sys.version_info[1]);import tkinter" > "%R_OUT%" 2>nul
set "R_TK=!errorlevel!"
set /p R_CN=<"%R_OUT%"
if not defined R_CN goto :eof
set /a R_CNUM=R_CN, R_CMAJ=R_CN/100, R_CMIN=R_CN%%100
set "R_CV=!R_CMAJ!.!R_CMIN!"
if !R_CNUM! LSS 308 (
    set "R_OLD=!R_CV!"
    goto :eof
)
if not "!R_TK!"=="0" (
    set "R_NOTK=!R_CV!"
    goto :eof
)
if defined R_NUM if !R_CNUM! LEQ !R_NUM! goto :eof
set "R_PY=%~1"
set "R_VER=!R_CV!"
set "R_NUM=!R_CNUM!"
goto :eof

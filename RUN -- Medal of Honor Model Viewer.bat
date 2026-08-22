@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM  RUN -- Medal of Honor Model Viewer.bat
REM  Drag one or more .skd / .tik files onto this to open the MOHAA viewer launcher.
REM  Or double-click to open the launcher and browse for a file.
REM  Keep this at the project root, with the scripts in the bin\ folder beside it
REM  (bin\mohaa_launcher.py, bin\mohaa_view.py, bin\mohaa_textures.py).
REM ============================================================================

set "LAUNCHER=%~dp0bin\mohaa_launcher.py"
set "PYSCRIPT=%~dp0bin\mohaa_view.py"

REM Prefer the py launcher, then a real python.exe. Microsoft Store execution aliases
REM under WindowsApps are stubs that just open the Store, so they are skipped rather
REM than used (and never deleted - that is not this script's job).
set "PYEXE="
where py >nul 2>nul && set "PYEXE=py"
if not defined PYEXE (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PYEXE (
            echo %%P | find /i "WindowsApps" >nul
            if errorlevel 1 set "PYEXE=%%P"
        )
    )
)
if not defined PYEXE (
    echo Python 3 not found on PATH. Install from https://www.python.org/
    pause & exit /b 1
)

REM Windowless Python for the GUI itself: pyw/pythonw keep no console open
REM behind the launcher window. Console PYEXE is still used for pip installs
REM below (so their output is visible) and as a last-resort fallback.
set "PYWEXE="
where pyw >nul 2>nul && set "PYWEXE=pyw"
if not defined PYWEXE ( where pythonw >nul 2>nul && set "PYWEXE=pythonw" )
if not defined PYWEXE set "PYWEXE=%PYEXE%"

if not exist "%LAUNCHER%" (
    echo mohaa_launcher.py not found in the bin folder next to this .bat
    pause & exit /b 1
)

REM ----------------------------------------------------------------------------
REM  Ensure Pillow (PIL) is installed for THIS Python. MOHAA textures are .tga,
REM  which only Pillow can decode - without it every model loads untextured and
REM  emitter sprites become plain blobs. Install it automatically into the same
REM  Python that will run the launcher, so it lands in the right place.
REM ----------------------------------------------------------------------------
"%PYEXE%" -c "import PIL,sys;v=tuple(int(x) for x in PIL.__version__.split('.')[:2]);sys.exit(0 if v>=(10,3) else 1)" >nul 2>nul
if not errorlevel 1 goto pillow_ok

echo.
echo Pillow (>=10.3) not found for %PYEXE% - it is required to show textures.
echo Installing Pillow now... this only happens once and may take a moment.
echo.
"%PYEXE%" -m pip install --upgrade "Pillow>=10.3.0"
"%PYEXE%" -c "import PIL,sys;v=tuple(int(x) for x in PIL.__version__.split('.')[:2]);sys.exit(0 if v>=(10,3) else 1)" >nul 2>nul
if not errorlevel 1 goto pillow_ok

echo.
echo Standard install did not work; retrying as a per-user install...
"%PYEXE%" -m pip install --user --upgrade "Pillow>=10.3.0"
"%PYEXE%" -c "import PIL,sys;v=tuple(int(x) for x in PIL.__version__.split('.')[:2]);sys.exit(0 if v>=(10,3) else 1)" >nul 2>nul
if not errorlevel 1 goto pillow_ok

echo.
echo Could not install Pillow automatically. Please run this command yourself:
echo     %PYEXE% -m pip install --upgrade "Pillow>=10.3.0"
echo then re-run this launcher.
pause
exit /b 1

:pillow_ok

REM ----------------------------------------------------------------------------
REM  Embedded 3D viewer support (optional, best-effort). tkwebview2 hosts an
REM  Edge WebView2 pane inside the launcher window so the model shows in the
REM  middle pane instead of a separate browser tab. pywebview is pinned to
REM  4.4.1 (tkwebview2 3.5.0 drives its internals directly). If this install
REM  fails the launcher still works - models just open in the browser.
REM ----------------------------------------------------------------------------
"%PYEXE%" -c "import tkwebview2" >nul 2>nul
if not errorlevel 1 goto embed_ok
echo.
echo Installing embedded 3D viewer support (pythonnet + pywebview + tkwebview2)...
echo This is optional - if it fails, models simply open in your browser.
echo.
"%PYEXE%" -m pip install pythonnet "pywebview==4.4.1" tkwebview2
"%PYEXE%" -c "import tkwebview2" >nul 2>nul
if not errorlevel 1 goto embed_ok
echo.
echo Embedded viewer support not installed - continuing with browser fallback.
echo.
:embed_ok

REM Collect the first dropped model (others ignored; load more via the launcher).
REM Walked with shift/%~1 rather than `for %%F in (%*)`: %* is expanded UNQUOTED, so a
REM dropped filename containing & or ^^ splits the command line - it either breaks the
REM loop or runs the tail as a separate command.
set "FIRST="
:argloop
if "%~1"=="" goto argdone
if not defined FIRST (
    if /i "%~x1"==".skd" set "FIRST=%~1"
    if /i "%~x1"==".tik" set "FIRST=%~1"
)
shift
goto argloop
:argdone

if defined FIRST (
    start "" "%PYWEXE%" "%LAUNCHER%" "%FIRST%"
) else (
    start "" "%PYWEXE%" "%LAUNCHER%"
)

exit /b 0

@echo off
setlocal EnableDelayedExpansion

REM ============================================================================
REM  python_installer_updater.bat  --  MOHAA Model Viewer prerequisite setup
REM
REM  Run this ONCE before RUN -- mohaa_view.bat.
REM  It finds (or installs) a suitable Python and installs the viewer's packages.
REM
REM  What changed from the previous version, and why:
REM   * The user's PATH is NEVER hand-edited any more. The old script read the
REM     user PATH with [Environment]::GetEnvironmentVariable, which EXPANDS
REM     %VAR% references, then wrote the expanded text back - permanently
REM     flattening REG_EXPAND_SZ entries like %USERPROFILE%\... to literals, with
REM     no backup. It also stripped any entry ending in \PythonNN, including
REM     unrelated toolchains. Python's own installer sets PATH correctly, so that
REM     job is handed back to it.
REM   * Every "if <cond> cmd1 & cmd2" is parenthesised. In cmd, & is a COMMAND
REM     SEPARATOR applied by the parser, so "if X endlocal & exit /b 1" ran the
REM     exit unconditionally - which made the old :compare_versions always report
REM     "older" and re-download Python on every single run.
REM   * Paths are passed to PowerShell as ARGUMENTS, not pasted into single-quoted
REM     strings. A path containing an apostrophe (C:\Users\O'Brien\...) used to
REM     terminate the string early and have its remainder parsed as code.
REM   * The download is pinned to TLS 1.2 and the installer's Authenticode
REM     signature is verified before it is executed.
REM   * The Python version is chosen for THIS Windows release. Python 3.9+
REM     refuses to install on Windows 7 and 3.12+ requires Windows 10, so the
REM     old "always fetch latest" simply failed there. The viewer itself needs
REM     only Python 3.7, so older Windows is fully supported on an older Python.
REM   * The CPU architecture is detected (x64 / ARM64 / x86) instead of assuming
REM     amd64, and Pillow is version-checked rather than merely imported.
REM   * The Microsoft Store execution aliases are no longer deleted. That was a
REM     system-wide change outside this program's remit, and the search below
REM     already skips them.
REM ============================================================================

echo =====================================
echo  MOHAA Model Viewer - Python setup
echo =====================================

REM Oldest interpreter the viewer's code actually runs on.
set MIN_MAJOR=3
set MIN_MINOR=7

REM ---------------------------------------------------------------------------
REM  DETECT WINDOWS VERSION  ->  highest Python that will install on it
REM ---------------------------------------------------------------------------
set WINMAJOR=
set WINMINOR=
for /f "tokens=1,2 delims=." %%a in ('powershell -NoProfile -Command "$v=[Environment]::OSVersion.Version; \"$($v.Major).$($v.Minor)\"" 2^>nul') do (
    set WINMAJOR=%%a
    set WINMINOR=%%b
)
if not defined WINMAJOR (
    for /f "tokens=4,5 delims=. " %%a in ('ver') do (
        set WINMAJOR=%%a
        set WINMINOR=%%b
    )
)
if not defined WINMAJOR set WINMAJOR=10
if not defined WINMINOR set WINMINOR=0

REM Windows 7 = 6.1, Windows 8 = 6.2, Windows 8.1 = 6.3, Windows 10/11 = 10.0
set TARGET_VERSION=
set WIN_LABEL=Windows !WINMAJOR!.!WINMINOR!
if !WINMAJOR! GEQ 10 (
    set TARGET_VERSION=LATEST
) else (
    if !WINMAJOR! EQU 6 (
        if !WINMINOR! GEQ 2 (
            REM Windows 8 / 8.1 - last Python line that installs here is 3.11.
            set TARGET_VERSION=3.11.9
        ) else (
            REM Windows 7 / Vista - 3.8 was the last release supporting Windows 7.
            set TARGET_VERSION=3.8.10
        )
    ) else (
        set TARGET_VERSION=3.8.10
    )
)

echo.
echo Detected: !WIN_LABEL!
if "!TARGET_VERSION!"=="LATEST" (
    echo Target Python: latest release
) else (
    echo Target Python: !TARGET_VERSION!  ^(newest that installs on this Windows^)
)

REM ---------------------------------------------------------------------------
REM  DETECT CPU ARCHITECTURE
REM ---------------------------------------------------------------------------
set ARCHSUFFIX=-amd64
set ARCH=%PROCESSOR_ARCHITECTURE%
if defined PROCESSOR_ARCHITEW6432 set ARCH=%PROCESSOR_ARCHITEW6432%
if /i "!ARCH!"=="ARM64" set ARCHSUFFIX=-arm64
if /i "!ARCH!"=="x86"   set ARCHSUFFIX=
echo Detected CPU: !ARCH!

REM ---------------------------------------------------------------------------
REM  FIND AN EXISTING, USABLE PYTHON  (Store aliases skipped, never deleted)
REM ---------------------------------------------------------------------------
echo.
echo Searching for an existing Python...
set BEST_PY=
set BEST_VER=

for /f "delims=" %%P in ('where python 2^>nul') do call :consider "%%P"
for /f "delims=" %%P in ('where python3 2^>nul') do call :consider "%%P"
if exist "%LOCALAPPDATA%\Programs\Python" (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%~D\python.exe" call :consider "%%~D\python.exe"
    )
)

if defined BEST_PY (
    echo.
    echo Best usable Python found:
    echo   !BEST_PY!   ^(version !BEST_VER!^)
    set PYTHON_EXE=!BEST_PY!
    goto INSTALL_PACKAGES
)

echo.
echo No Python ^>= !MIN_MAJOR!.!MIN_MINOR! found. Installing one...

REM ---------------------------------------------------------------------------
REM  RESOLVE THE EXACT VERSION TO FETCH
REM ---------------------------------------------------------------------------
if not "!TARGET_VERSION!"=="LATEST" goto HAVE_VERSION

echo Asking python.org for the current release...
set LATEST_VERSION=
for /f "delims=" %%V in ('powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try{$h=(Invoke-WebRequest -Uri 'https://www.python.org/downloads/' -UseBasicParsing).Content; if($h -match 'Download Python (\d+\.\d+\.\d+)'){$Matches[1]}}catch{}" 2^>nul') do set LATEST_VERSION=%%V

if not defined LATEST_VERSION (
    echo Could not reach python.org. Falling back to a known-good release.
    set TARGET_VERSION=3.12.7
) else (
    set TARGET_VERSION=!LATEST_VERSION!
)

:HAVE_VERSION
echo Will install Python !TARGET_VERSION! !ARCHSUFFIX!

set INSTALL_URL=https://www.python.org/ftp/python/!TARGET_VERSION!/python-!TARGET_VERSION!!ARCHSUFFIX!.exe
set INSTALLER=%TEMP%\python-!TARGET_VERSION!!ARCHSUFFIX!.exe
if exist "!INSTALLER!" del /f /q "!INSTALLER!" >nul 2>&1

echo Downloading...
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try{Invoke-WebRequest -Uri $args[0] -OutFile $args[1] -UseBasicParsing; exit 0}catch{Write-Host ('   ' + $_.Exception.Message); exit 1}" "!INSTALL_URL!" "!INSTALLER!"
if errorlevel 1 (
    echo.
    echo Download failed. Install Python !TARGET_VERSION! by hand from:
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
)
if not exist "!INSTALLER!" (
    echo Download produced no file. Aborting.
    pause
    exit /b 1
)

REM --- Verify the installer is genuinely signed by the Python Software Foundation.
REM     HTTPS protects the transport; this protects against a tampered or
REM     substituted file being executed silently with the user's privileges.
echo Verifying the installer's digital signature...
powershell -NoProfile -Command "$s=Get-AuthenticodeSignature -FilePath $args[0]; if($s.Status -ne 'Valid'){Write-Host ('   signature status: ' + $s.Status); exit 1}; $subj=$s.SignerCertificate.Subject; Write-Host ('   signed by: ' + $subj); if($subj -notmatch 'Python Software Foundation'){exit 1}; exit 0" "!INSTALLER!"
if errorlevel 1 (
    echo.
    echo REFUSING TO RUN: the downloaded installer is not validly signed by the
    echo Python Software Foundation. It has been deleted. Please install Python
    echo yourself from https://www.python.org/downloads/
    del /f /q "!INSTALLER!" >nul 2>&1
    pause
    exit /b 1
)

echo Running the installer ^(PrependPath is handled by Python's own installer^)...
"!INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_tcltk=1
del /f /q "!INSTALLER!" >nul 2>&1

REM Locate what was just installed. Do not guess the folder from the version
REM string alone - ask the py launcher first, then fall back to the standard path.
set PYTHON_EXE=
for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set PYTHON_EXE=%%P
if not defined PYTHON_EXE (
    for /f "tokens=1,2 delims=." %%a in ("!TARGET_VERSION!") do (
        if exist "%LOCALAPPDATA%\Programs\Python\Python%%a%%b\python.exe" (
            set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python%%a%%b\python.exe
        )
    )
)
if not defined PYTHON_EXE (
    echo.
    echo ERROR: Python was installed but could not be located afterwards.
    echo Close this window, open a NEW one, and run this script again.
    pause
    exit /b 1
)
echo Installed: !PYTHON_EXE!

REM ---------------------------------------------------------------------------
REM  PACKAGES
REM ---------------------------------------------------------------------------
:INSTALL_PACKAGES
echo.
echo Using interpreter: !PYTHON_EXE!
echo.
echo Updating pip...
"!PYTHON_EXE!" -m ensurepip --upgrade >nul 2>&1
"!PYTHON_EXE!" -m pip install --upgrade pip setuptools wheel

echo.
echo Installing Pillow ^(required: MOHAA textures are .tga, only Pillow decodes them^)...
REM A version FLOOR, not a bare "import PIL" check. Old Pillow releases have known
REM decoder vulnerabilities, and this program feeds Pillow .tga/.dds data straight
REM out of .pk3 archives the user downloaded - i.e. untrusted input.
"!PYTHON_EXE!" -m pip install --upgrade "Pillow>=10.3.0"
if errorlevel 1 (
    echo    retrying as a per-user install...
    "!PYTHON_EXE!" -m pip install --user --upgrade "Pillow>=10.3.0"
)
"!PYTHON_EXE!" -c "import PIL,sys;v=tuple(int(x) for x in PIL.__version__.split('.')[:2]);sys.exit(0 if v>=(10,3) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Pillow is missing or older than 10.3. Textures may not load, and
    echo older Pillow versions have known image-decoder vulnerabilities. Try:
    echo     "!PYTHON_EXE!" -m pip install --upgrade "Pillow>=10.3.0"
) else (
    echo    Pillow OK.
)

REM Embedded 3D pane. WebView2 is Windows 8.1+ only (the runtime dropped Windows 7
REM support at version 109), so skip it entirely on older Windows - the launcher
REM falls back to opening models in the default browser, which works everywhere.
if !WINMAJOR! GEQ 10 goto DO_WEBVIEW
if !WINMAJOR! EQU 6 if !WINMINOR! GEQ 3 goto DO_WEBVIEW
echo.
echo Skipping the embedded 3D pane: Edge WebView2 does not support !WIN_LABEL!.
echo Models will open in your default browser instead ^(fully supported^).
goto DONE

:DO_WEBVIEW
echo.
echo Installing the optional embedded 3D viewer pane...
echo ^(if this fails the launcher still works - models open in your browser^)
"!PYTHON_EXE!" -m pip install pythonnet "pywebview==4.4.1" tkwebview2
"!PYTHON_EXE!" -c "import tkwebview2" >nul 2>&1
if errorlevel 1 (
    echo    Not installed - the browser fallback will be used.
) else (
    echo    Embedded viewer OK.
)

:DONE
echo.
echo =====================================
echo  Setup complete
echo  Interpreter: !PYTHON_EXE!
echo =====================================
echo.
echo Your PATH was not modified by this script. If "python" is not recognised in
echo a new Command Prompt, either re-run Python's installer and tick
echo "Add python.exe to PATH", or just use "RUN -- mohaa_view.bat", which finds
echo the interpreter on its own.
echo.
pause
exit /b 0

REM ===========================================================================
REM  :consider "<path to python.exe>"
REM  Keeps the NEWEST interpreter that is >= MIN_MAJOR.MIN_MINOR and is not a
REM  Microsoft Store execution alias (those are 0-byte stubs that just open the
REM  Store). Every "if" body is parenthesised so nothing runs unconditionally.
REM ===========================================================================
:consider
set "CAND=%~1"
if not exist "!CAND!" goto :eof
echo !CAND! | find /i "WindowsApps" >nul
if not errorlevel 1 (
    echo   skipped ^(Microsoft Store alias^): !CAND!
    goto :eof
)
set CVER=
for /f "tokens=2" %%V in ('"!CAND!" --version 2^>^&1') do (
    if not defined CVER set CVER=%%V
)
if not defined CVER goto :eof
for /f "tokens=1,2 delims=." %%a in ("!CVER!") do (
    set CMAJ=%%a
    set CMIN=%%b
)
if not defined CMAJ goto :eof
if not defined CMIN set CMIN=0
if !CMAJ! LSS %MIN_MAJOR% (
    echo   skipped ^(too old: !CVER!^): !CAND!
    goto :eof
)
if !CMAJ! EQU %MIN_MAJOR% if !CMIN! LSS %MIN_MINOR% (
    echo   skipped ^(too old: !CVER!^): !CAND!
    goto :eof
)
"!CAND!" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo   skipped ^(no tkinter: !CVER!^): !CAND!
    goto :eof
)
echo   found !CVER!: !CAND!
if not defined BEST_VER (
    set BEST_VER=!CVER!
    set BEST_PY=!CAND!
    goto :eof
)
for /f "tokens=1,2 delims=." %%a in ("!BEST_VER!") do (
    set BMAJ=%%a
    set BMIN=%%b
)
if not defined BMIN set BMIN=0
if !CMAJ! GTR !BMAJ! (
    set BEST_VER=!CVER!
    set BEST_PY=!CAND!
    goto :eof
)
if !CMAJ! EQU !BMAJ! if !CMIN! GTR !BMIN! (
    set BEST_VER=!CVER!
    set BEST_PY=!CAND!
)
goto :eof

@echo off
setlocal EnableDelayedExpansion

REM ============================================================================
REM  python_installer_updater.bat  --  prerequisite setup for the MOHAA Model Viewer
REM                                      and the MOHAA Map Viewer
REM
REM  Finds the newest usable Python, or downloads one that supports this Windows
REM  version and CPU, then installs the packages both viewers use (they need the
REM  same ones). "RUN -- Medal of Honor Model Viewer.bat" and "RUN -- Medal of Honor
REM  Map Viewer.bat" offer to run this when they can't find a suitable Python,
REM  passing /fromrun so it returns without the closing pause; it can also be run
REM  on its own to update Python's packages.
REM
REM  Notes for maintainers:
REM   * PATH is never edited here; Python's installer handles it via PrependPath=1.
REM   * Python is installed per-user, launcher included, so it normally needs no admin
REM     rights (an old Windows 7 / 8.1 missing the C runtime update still asks).
REM   * Paths are passed to PowerShell as arguments, never pasted into quoted
REM     strings, so an apostrophe in a user path cannot break the command.
REM   * Every multi-command "if" body is parenthesised. In cmd, & separates
REM     commands, so "if X cmd1 & cmd2" would run cmd2 unconditionally.
REM   * The download is pinned to TLS 1.2 and the installer's Authenticode
REM     signature is verified before it runs.
REM   * Microsoft Store execution aliases are skipped, never deleted.
REM ============================================================================

set "FROMRUN="
if /i "%~1"=="/fromrun" set "FROMRUN=1"

echo ==============================================
echo  MOHAA Model Viewer / Map Viewer - Python setup
echo ==============================================

REM Oldest Python the viewers support (Pillow 10.3 requires 3.8).
set MIN_MAJOR=3
set MIN_MINOR=8

REM Scratch file for reading one line of Python output (see :consider).
set "U_OUT=%TEMP%\mohaa_setup_check.txt"

REM ---------------------------------------------------------------------------
REM  DETECT WINDOWS VERSION  ->  highest Python that will install on it
REM ---------------------------------------------------------------------------
set WINMAJOR=
set WINMINOR=
REM Keep every parenthesis in a FOR /F command inside double quotes. cmd has no escape
REM for a quote inside quotes, and an unquoted closing parenthesis ends the command
REM list, which aborts the whole script with a syntax error.
for /f "tokens=1,2 delims=." %%a in ('powershell -NoProfile -Command "[Environment]::OSVersion.Version.ToString()" 2^>nul') do (
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
REM  FIND AN EXISTING, USABLE PYTHON
REM ---------------------------------------------------------------------------
echo.
echo Searching for an existing Python...
call :search
if defined BEST_PY (
    echo.
    echo Best usable Python found:
    echo   !BEST_PY!   ^(version !BEST_VER!^)
    set "PYTHON_EXE=!BEST_PY!"
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

REM Only run the installer if it carries a valid Python Software Foundation signature.
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

REM A per-user install needs no admin rights, but the py launcher defaults to an
REM all-users install, which does; InstallLauncherAllUsers=0 keeps it per-user too.
echo Running the installer ^(PrependPath is handled by Python's own installer^)...
"!INSTALLER!" /quiet InstallAllUsers=0 InstallLauncherAllUsers=0 PrependPath=1 Include_pip=1 Include_tcltk=1
set "INST_ERR=!errorlevel!"
del /f /q "!INSTALLER!" >nul 2>&1
if not "!INST_ERR!"=="0" echo    The installer exited with code !INST_ERR!.

REM Find the new interpreter with the same search. It isn't on this window's PATH
REM yet, but the per-user install folders (Python3*) are searched directly.
echo.
echo Looking for the new Python...
call :search
if not defined BEST_PY (
    echo.
    echo ERROR: Python was installed but could not be located afterwards.
    echo Close this window, open a NEW one, and run this script again.
    pause
    exit /b 1
)
set "PYTHON_EXE=!BEST_PY!"
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
REM Enforce a minimum version, not just "import PIL": older Pillow releases have
REM known decoder vulnerabilities, and the viewer decodes images from untrusted .pk3s.
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

REM Optional embedded 3D pane, offered on Windows 8.1 and newer like the RUN .bat
REM files; older systems skip it and use the browser fallback.
if !WINMAJOR! GEQ 10 goto DO_WEBVIEW
if !WINMAJOR! EQU 6 if !WINMINOR! GEQ 3 goto DO_WEBVIEW
echo.
echo Skipping the embedded 3D pane: it needs Windows 8.1 or newer.
echo Models and maps will open in your default browser instead ^(fully supported^).
goto DONE

:DO_WEBVIEW
echo.
echo Installing the optional embedded 3D viewer pane...
echo ^(if this fails the launchers still work - models and maps open in your browser^)
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
if defined FROMRUN exit /b 0
echo.
echo Your PATH was not modified by this script. If "python" is not recognised in
echo a new Command Prompt, either re-run Python's installer and tick
echo "Add python.exe to PATH", or just use "RUN -- Medal of Honor Model Viewer.bat"
echo or "RUN -- Medal of Honor Map Viewer.bat", which find the interpreter on their own.
echo.
pause
exit /b 0

REM ===========================================================================
REM  :search
REM  Looks where the RUN .bat files look: the py launcher's default interpreter,
REM  python.exe / python3.exe on PATH, and the default per-user and all-users
REM  install folders. The best candidate ends up in BEST_PY / BEST_VER.
REM ===========================================================================
:search
set "BEST_PY="
set "BEST_VER="
set "PYCAND="
del "%U_OUT%" >nul 2>&1
where py >nul 2>nul
if not errorlevel 1 py -3 -c "import sys;print(sys.executable)" > "%U_OUT%" 2>nul
if exist "%U_OUT%" set /p PYCAND=<"%U_OUT%"
if defined PYCAND call :consider "!PYCAND!"
for /f "delims=" %%P in ('where python 2^>nul') do call :consider "%%P"
for /f "delims=" %%P in ('where python3 2^>nul') do call :consider "%%P"
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%~D\python.exe" call :consider "%%~D\python.exe"
)
for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%~D\python.exe" call :consider "%%~D\python.exe"
)
del "%U_OUT%" >nul 2>&1
goto :eof

REM ===========================================================================
REM  :consider "<path to python.exe>"
REM  Records the candidate in BEST_PY/BEST_VER if it is newer than the current
REM  best, at least MIN_MAJOR.MIN_MINOR, has tkinter, and is not a Microsoft
REM  Store alias.
REM ===========================================================================
:consider
set "CAND=%~1"
if not exist "!CAND!" goto :eof
REM The same interpreter is often found twice (py launcher, PATH, install folder).
if /i "!CAND!"=="!BEST_PY!" goto :eof
REM %~1 is expanded before the pipe starts; !CAND! would reach find unexpanded,
REM since each side of a pipe runs in a new cmd without delayed expansion.
echo "%~1" | find /i "\WindowsApps\" >nul
if not errorlevel 1 (
    echo   skipped ^(Microsoft Store alias^): !CAND!
    goto :eof
)
REM Python is run directly and its output read back with set /p: for /f would run
REM it through cmd /c, which mangles a quoted path containing ( ) or ^&.
set "CVER="
set "CMAJ="
set "CMIN="
"!CAND!" -c "import sys;v=sys.version_info;print(str(v[0])+'.'+str(v[1]))" > "%U_OUT%" 2>nul
if exist "%U_OUT%" set /p CVER=<"%U_OUT%"
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

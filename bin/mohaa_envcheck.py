#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
#  mohaa_envcheck.py  --  dependency checks and installs for the RUN launchers.
#
#  The .bat / .sh launchers only orchestrate (find Python, call this, start the
#  program, pause). Everything with real logic lives here: version comparison,
#  installing into the vendored libs folder, verifying the install in a fresh
#  process, the Windows checks for the optional embedded 3D pane.
#
#  Usage:
#    python mohaa_envcheck.py deps <libs folder> [--embed] [--upgrade]
#        Make sure every package is in <libs folder> at its minimum version, installing
#        or upgrading with "python -m pip install --target" when needed.
#        --embed    also the optional embedded-pane packages (Windows 8.1+ only)
#        --upgrade  refresh every package even if it is already current
#        --log NAME also save everything this prints (pip's output too) in
#                   output/logs/run_NAME.log, which the program then shows at the
#                   top of its Output pane (the RUN window closes once it starts)
#        Exit 0 = required packages OK (optional ones may have failed, with a
#        warning); 1 = a required package is missing and couldn't be installed.
#
#    python mohaa_envcheck.py start NAME <launcher.py> [file]
#        Start the program without a console (pythonw), wait until its window is
#        open (it writes the file named by MOHAA_READY_FILE), and exit 0 so the RUN
#        window can close. If it stops before that, print what it printed and exit
#        with its code (the RUN window then stays open). Appends to run_NAME.log.
#
#    python mohaa_envcheck.py menu
#        The RUN launcher's opening menu: which program to start. Up / Down and Enter,
#        or 1 / 2 at once; Q, Esc or Ctrl+C quits. Exit 11 = Map Viewer, 12 = Model
#        Viewer, 10 = quit (codes clear of Python's own 1 and 2 for an error).
#
#  Runs on Python 3.8+. Standard library only.
# ==============================================================================
import sys
import os
_LIBS_NAME = "libs" if sys.platform.startswith("win") else ("libs-mac" if sys.platform == "darwin" else "libs-linux")
_libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), _LIBS_NAME)
if os.path.isdir(_libs_dir) and _libs_dir not in sys.path:
    sys.path.insert(0, _libs_dir)

import re
import subprocess
import time
import tempfile
_bin_dir = os.path.dirname(os.path.abspath(__file__))
if _bin_dir not in sys.path:
    sys.path.insert(0, _bin_dir)
try:
    import mohaa_common as MC                   # logs_dir(); standard library only
except Exception:                               # a damaged install: no log file, still works
    MC = None

# ==============================================================================
#  Constants
# ==============================================================================
VERSION = "1.0.001"
# (pip requirement, distribution name, minimum version, import check run in a NEW process)
# Pillow's floor is a SECURITY floor (see docs/SECURITY.md); importing PIL._imaging catches
# a compiled extension built for a different Python (the libs folder outlived a Python update).
REQUIRED = [
    ("Pillow>=10.3.0", "pillow", (10, 3, 0), "import PIL, PIL._imaging", {}),
]
# Embedded 3D pane (Windows 8.1+). pywebview is PINNED: tkwebview2 3.5.0 drives pywebview
# 4.4.1's internals directly (EdgeChrome.web_view; pywebview 5 renamed it .webview, and the
# pane then fails with "'EdgeChrome' object has no attribute 'web_view'"). So:
#  * the pin is exact ("==" in the requirement): any other installed version is replaced;
#  * the check reads the installed code itself, not just the version in its metadata (a
#    folder can hold an old pywebview-*.dist-info beside newer code);
#  * tkwebview2 is installed with --no-deps: it lists "pywebview" unpinned, and pip would
#    otherwise put the newest pywebview over the pinned one in the same folder.
PYWEBVIEW_CHECK = ("import os, webview; "
                   "p = os.path.join(os.path.dirname(webview.__file__), 'platforms', 'edgechromium.py'); "
                   "src = open(p, encoding='utf-8').read(); "
                   "assert 'self.web_view = WebView2()' in src, "
                   "'this pywebview is not 4.4.1 (its EdgeChrome has no .web_view, which tkwebview2 needs)'")
OPTIONAL_EMBED = [
    ("pythonnet", "pythonnet", (3, 0, 0), "import clr", {}),
    ("pywebview==4.4.1", "pywebview", (4, 4, 1), PYWEBVIEW_CHECK, {}),
    ("tkwebview2", "tkwebview2", (0, 0, 0), "import tkwebview2", {"no_deps": True}),
]
EMBED_MIN_WINDOWS = (6, 3)                  # Windows 8.1
WEBVIEW2_CLIENT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
PIP_TIMEOUT = 600                           # seconds per pip run
READY_TIMEOUT = 180                         # seconds to wait for the program's window
READY_POLL = 0.2                            # seconds between checks for it
FAIL_TAIL = 40                              # lines of a failed start's output to show
RUN_LOG_ENV = "MOHAA_RUN_LOG"               # the program reads the RUN window's text here
READY_ENV = "MOHAA_READY_FILE"              # ... and writes this once its window is open

_RUN_LOG = None                             # open run_NAME.log (say / warn copy into it)


def _to_log(msg):
    """Copy one line into the run log, if one is open. Never raises."""
    if _RUN_LOG is not None:
        try:
            _RUN_LOG.write(msg + "\n")
        except (OSError, ValueError):
            pass


def say(msg):
    """Normal status line (stdout, and the run log)."""
    print(msg, flush=True)
    _to_log(msg)


def warn(msg):
    """Warning / error line (stderr, and the run log)."""
    print(msg, file=sys.stderr, flush=True)
    _to_log(msg)


def run_log_path(name):
    """output/logs/run_<name>.log for program `name` ("map" / "model"), or None."""
    name = re.sub(r"[^A-Za-z0-9_-]", "", str(name or "").strip())
    if not name or MC is None:
        return None
    return os.path.join(MC.logs_dir(), "run_%s.log" % name)


def open_run_log(name, fresh):
    """Open the run log for writing (fresh: start it again, keeping the last one as
    run_<name>.prev.log; else append). Returns its path, or None (no log, carry on)."""
    global _RUN_LOG
    path = run_log_path(name)
    if not path:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if fresh and os.path.isfile(path):
            os.replace(path, path[:-4] + ".prev.log")
        _RUN_LOG = open(path, "w" if fresh else "a", encoding="utf-8", buffering=1)
    except OSError as e:
        print("[WARN] can't write %s (%s); this window's text won't be saved" % (path, e), file=sys.stderr, flush=True)
        _RUN_LOG = None
        return None
    return path


def version_tuple(text):
    """'10.3.0' -> (10, 3, 0); stops at the first non-numeric part ('4.4.1rc1' -> (4, 4, 1))."""
    out = []
    for part in str(text).split("."):
        m = re.match(r"\d+", part)
        if not m:
            break
        out.append(int(m.group(0)))
    return tuple(out)


def _norm(name):
    """A distribution name as pip compares them: lowercase, runs of - _ . as one -."""
    return re.sub(r"[-_.]+", "-", str(name)).lower()


def dist_infos(libs):
    """{normalized name: [(mtime, version, path), ...] newest first} for every .dist-info
    folder in `libs`. pip --target replaces a package's code on an upgrade but leaves the
    older version's .dist-info beside the new one, so a name can have several."""
    out = {}
    try:
        names = os.listdir(libs)
    except OSError:
        return out
    for n in names:
        m = re.match(r"(.+?)-([^-]+)\.dist-info$", n)
        if not m:
            continue
        path = os.path.join(libs, n)
        try:
            mt = os.path.getmtime(path)
        except OSError:
            mt = 0.0
        out.setdefault(_norm(m.group(1)), []).append((mt, m.group(2), path))
    for v in out.values():
        v.sort(reverse=True)
    return out


def stale_dist_infos(libs, dist, keep=None):
    """The `dist` .dist-info folders in `libs` that don't describe the code installed:
    every version but `keep` when it is given, else all but the newest. Returns paths."""
    entries = dist_infos(libs).get(_norm(dist), [])
    if keep is not None:
        return [p for _mt, v, p in entries if v != keep]
    return [p for _mt, _v, p in entries[1:]]


def prune_dist_infos(libs):
    """After a pip run: for every package with more than one .dist-info, keep the one pip
    just wrote (the newest) and delete the rest, saying which. Covers the dependencies pip
    installed along the way (pythonnet, cffi...), not only the package asked for. Never
    raises."""
    import shutil
    for name, entries in sorted(dist_infos(libs).items()):
        for _mt, _v, path in entries[1:]:
            try:
                shutil.rmtree(path)
                say("         removed stale %s" % os.path.basename(path))
            except OSError as e:
                warn("[WARN] could not remove stale %s: %s" % (os.path.basename(path), e))


def installed_version(libs, dist):
    """Version string of distribution `dist` installed in folder `libs`, or None."""
    if not os.path.isdir(libs):
        return None
    try:
        from importlib import metadata
    except ImportError:            # Python 3.7 and older: treat as not installed
        return None
    # several .dist-info folders for one name: the newest is the one pip wrote last
    entries = dist_infos(libs).get(_norm(dist))
    if entries:
        return entries[0][1]
    for d in metadata.distributions(path=[libs]):
        if _norm(d.metadata.get("Name") or "") == _norm(dist):
            return d.version
    return None


def import_ok(libs, check):
    """Run `check` (an import statement) in a FRESH interpreter with `libs` first on
    sys.path. A fresh process because a package installed by this one can't be reliably
    imported by it (compiled modules, stale import caches). Returns (ok, error text)."""
    code = "import sys; sys.path.insert(0, %r); %s" % (libs, check)
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if r.returncode == 0:
        return True, ""
    lines = (r.stderr or "").strip().splitlines()
    return False, lines[-1] if lines else "exit code %d" % r.returncode


def pip_available():
    """True if "python -m pip" works for this interpreter; tries ensurepip once."""
    for attempt in (1, 2):
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, timeout=60)
            if r.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
        if attempt == 1:
            say("[INFO] pip is missing; trying to add it with ensurepip ...")
            try:
                subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], capture_output=True, timeout=300)
            except (OSError, subprocess.TimeoutExpired):
                pass
    return False


def pip_install(libs, req, force=False, no_deps=False):
    """python -m pip install <req> --target <libs> --upgrade --no-user (and --no-deps when
    asked: the package's own dependencies are installed by their own entries). Returns True
    on success."""
    cmd = [sys.executable, "-m", "pip", "install", req, "--target", libs, "--upgrade", "--no-user",
           "--disable-pip-version-check"]
    if force:
        cmd.append("--force-reinstall")
    if no_deps:
        cmd.append("--no-deps")
    say("         python -m pip install %s --target \"%s\"%s%s" % (req, libs, " --force-reinstall" if force else "",
                                                               " --no-deps" if no_deps else ""))
    # pip's own lines are shown as they come and copied into the run log
    start = time.time()
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             text=True, encoding="utf-8", errors="replace", bufsize=1)
    except OSError as e:
        warn("[ERROR] pip could not run: %s" % e)
        return False
    try:
        for line in p.stdout:
            say(line.rstrip("\r\n"))
            if time.time() - start > PIP_TIMEOUT:
                p.kill()
                warn("[ERROR] pip took longer than %d s and was stopped" % PIP_TIMEOUT)
                return False
        code = p.wait(timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        try:
            p.kill()
        except OSError:
            pass
        warn("[ERROR] pip could not finish: %s" % e)
        return False
    if code == 0:
        say("         wrote %s into %s" % (req.split("=")[0].split(">")[0], libs))
    return code == 0


def ensure(libs, req, dist, minimum, check, upgrade=False, opts=None):
    """Make one package present and importable in `libs`. A requirement with "==" is an
    exact pin: any other version (or a stale second .dist-info) is replaced. `opts`:
    {"no_deps": True} installs without its dependencies. Returns True when it is."""
    opts = opts or {}
    exact = "==" in req
    pin = req.split("==", 1)[1].strip() if exact else None
    have = installed_version(libs, dist)
    need = any(minimum)
    # more than one .dist-info for it: which one matches the code can't be told, so
    # install it again and keep only the record pip writes
    stale = bool(stale_dist_infos(libs, dist, pin))
    if have and (stale or (exact and version_tuple(have) != minimum)):
        if stale:
            say("[UPDATE] %s: records of more than one version are in the folder; reinstalling%s"
                % (dist, " exactly " + pin if pin else ""))
        else:
            say("[UPDATE] %s %s is installed; this program needs exactly %s" % (dist, have, pin))
        force = True
    elif have and not upgrade and (not need or version_tuple(have) >= minimum):
        ok, err = import_ok(libs, check)
        if ok:
            say("[OK] %s %s" % (dist, have))
            return True
        warn("[WARN] %s %s is installed but won't import (%s); reinstalling" % (dist, have, err))
        force = True
    else:
        if have and not upgrade:
            say("[UPDATE] %s %s is older than %s" % (dist, have, ".".join(map(str, minimum))))
        elif have:
            say("[UPDATE] refreshing %s %s" % (dist, have))
        else:
            say("[INSTALL] %s is not installed" % dist)
        force = False
    if not pip_available():
        warn("[ERROR] pip is not available for %s" % sys.executable)
        if sys.platform.startswith("linux"):
            warn("        Install it with:  sudo apt install python3-pip   (Debian/Ubuntu/Kubuntu)")
        return False
    if not pip_install(libs, req, force=force, no_deps=bool(opts.get("no_deps"))):
        warn("[ERROR] installing %s failed" % req)
        return False
    prune_dist_infos(libs)
    ok, err = import_ok(libs, check)
    if not ok:
        warn("[ERROR] %s was installed but still won't import: %s" % (dist, err))
        return False
    say("[OK] %s %s" % (dist, installed_version(libs, dist) or "?"))
    return True


def windows_version():
    """(major, minor) of Windows, or None elsewhere."""
    if not sys.platform.startswith("win"):
        return None
    v = sys.getwindowsversion()
    return (v.major, v.minor)


def webview2_runtime():
    """Installed Microsoft Edge WebView2 Runtime version, or None (Microsoft's documented
    check: a "pv" value other than 0.0.0.0 under one of three EdgeUpdate client keys)."""
    try:
        import winreg
    except ImportError:
        return None
    keys = ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients" + "\\" + WEBVIEW2_CLIENT),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients" + "\\" + WEBVIEW2_CLIENT),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\EdgeUpdate\Clients" + "\\" + WEBVIEW2_CLIENT))
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as k:
                pv, _t = winreg.QueryValueEx(k, "pv")
                if pv and pv != "0.0.0.0":
                    return pv
        except OSError:
            continue
    return None


def cmd_deps(argv):
    """The "deps" command (see the module header). Returns the exit code."""
    if not argv:
        warn("usage: mohaa_envcheck.py deps <libs folder> [--embed] [--upgrade]")
        return 2
    libs = os.path.abspath(argv[0].strip().strip('"'))
    flags = set(argv[1:])
    if not libs:
        warn("[ERROR] empty libs folder")
        return 2
    try:
        os.makedirs(libs, exist_ok=True)
    except OSError as e:
        warn("[ERROR] can't create %s: %s" % (libs, e))
        return 1
    upgrade = "--upgrade" in flags
    log_path = None
    if "--log" in argv:
        i = argv.index("--log")
        if i + 1 < len(argv):
            log_path = open_run_log(argv[i + 1], fresh=True)
            # what the RUN window printed before this (it isn't in the log otherwise)
            _to_log("MOHAA %s launch checks, %s" % (argv[i + 1], time.strftime("%Y-%m-%d %H:%M:%S")))
            _to_log("[OK] Python %d.%d: %s" % (sys.version_info[0], sys.version_info[1], sys.executable))
            _to_log("")
    say("Checking packages in %s" % libs)
    for req, dist, minimum, check, opts in REQUIRED:
        if not ensure(libs, req, dist, minimum, check, upgrade, opts):
            warn("[ERROR] %s is required (it decodes the game's textures). The program can't start without it." % dist)
            return 1
    if "--embed" in flags:
        wv = windows_version()
        if wv is None:
            say("[INFO] The embedded 3D pane is Windows-only; pages open in your default browser.")
        elif wv < EMBED_MIN_WINDOWS:
            say("[INFO] The embedded 3D pane needs Windows 8.1 or newer; pages open in your default browser.")
        else:
            ok_all = True
            for req, dist, minimum, check, opts in OPTIONAL_EMBED:
                if not ensure(libs, req, dist, minimum, check, upgrade, opts):
                    ok_all = False
                    break
            if not ok_all:
                warn("[WARN] The embedded pane packages could not be installed; pages open in your default browser.")
            rt = webview2_runtime()
            if rt:
                say("[OK] Microsoft Edge WebView2 Runtime %s" % rt)
            else:
                warn("[WARN] The Microsoft Edge WebView2 Runtime isn't installed, so pages open in your default")
                warn("       browser. To use the embedded pane: https://developer.microsoft.com/microsoft-edge/webview2/")
    if log_path:
        say("[OK] This window's text is saved in %s" % log_path)
    return 0


def _tail(path, n):
    """The last n lines of a text file, or [] if it can't be read."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()[-n:]
    except OSError:
        return []


def cmd_start(argv):
    """The "start" command (see the module header). Returns the exit code."""
    if len(argv) < 2:
        warn("usage: mohaa_envcheck.py start NAME <launcher.py> [file]")
        return 2
    name, script = argv[0].strip(), os.path.abspath(argv[1].strip().strip('"'))
    extra = [a for a in argv[2:] if a.strip()]
    if not os.path.isfile(script):
        warn("[ERROR] %s was not found" % script)
        return 1
    log_path = open_run_log(name, fresh=False)
    # pythonw: no console of its own, so this window can close once the program is up
    exe = sys.executable
    flags = 0
    if sys.platform.startswith("win"):
        w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.isfile(w):
            exe = w
        flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    fd, ready = tempfile.mkstemp(prefix="mohaa_ready_", suffix=".txt")
    os.close(fd)
    os.remove(ready)                             # the program creates it when its window is open
    out_path = os.path.join(os.path.dirname(log_path), "run_%s_program.log" % name) if log_path else os.devnull
    env = dict(os.environ)
    env[READY_ENV] = ready
    if log_path:
        env[RUN_LOG_ENV] = log_path
    env.setdefault("PYTHONIOENCODING", "utf-8")
    say("Starting %s ..." % os.path.basename(script))
    try:
        out = open(out_path, "w", encoding="utf-8")
    except OSError:
        out = subprocess.DEVNULL
    try:
        kw = {"creationflags": flags} if flags else {"start_new_session": True}
        p = subprocess.Popen([exe, script] + extra, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                             env=env, cwd=os.path.dirname(script), close_fds=True, **kw)
    except OSError as e:
        warn("[ERROR] could not start %s: %s" % (script, e))
        return 1
    finally:
        if out is not subprocess.DEVNULL:
            out.close()
    if out_path != os.devnull:
        say("         its own output goes to %s" % out_path)
    t0 = time.time()
    try:
        while time.time() - t0 < READY_TIMEOUT:
            if os.path.exists(ready):
                say("[OK] The window is open. This window closes now; its text is in the program's Output pane.")
                return 0
            code = p.poll()
            if code is not None:
                warn("[ERROR] The program stopped before its window opened (exit code %s). What it printed:" % code)
                for line in _tail(out_path, FAIL_TAIL):
                    warn("  " + line)
                return code or 1
            time.sleep(READY_POLL)
        say("[INFO] The program is still starting after %d s; this window closes now. If no window" % READY_TIMEOUT)
        say("       appears, see %s" % out_path)
        return 0
    finally:
        try:
            os.remove(ready)
        except OSError:
            pass


# ==============================================================================
#  menu: the RUN launcher's choice of program
# ==============================================================================
MENU_QUIT, MENU_MAP, MENU_MODEL = 10, 11, 12
# (key, exit code, name, what it opens, one line on it); the first is selected at start
MENU_ITEMS = [
    ("1", MENU_MAP, "Map Viewer", ".bsp / .map / .bak",
     "Fly through a level: brushes, textures, entities, AI paths, leaks."),
    ("2", MENU_MODEL, "Model Viewer", ".skd / .tik",
     "Models with their animations, skins, tags and bones, and effects."),
]
MENU_HEAD = [
    "=" * 68,
    " Medal of Honor: Allied Assault -- Map and Model Viewer   v" + VERSION,
    "=" * 68,
    " Look at MOHAA maps and models in 3D: open them from the game's .pk3",
    " files or from disk, move around, and see what they are made of.",
    "",
]
MENU_HINT = " Up / Down and Enter, or press 1 or 2.  Q or Esc quits."


def _vt_on():
    """Whether the console understands ANSI escapes (cursor moves, reverse video). On
    Windows 10+ this switches them on (ENABLE_VIRTUAL_TERMINAL_PROCESSING); older
    Windows consoles can't, and the menu then redraws a single line instead."""
    if not sys.stdout.isatty() or os.environ.get("TERM") == "dumb":
        return False
    if not sys.platform.startswith("win"):
        return True
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)                       # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        return bool(k.SetConsoleMode(h, mode.value | 0x0004))
    except Exception:
        return False


def _menu_key_reader():
    """A function returning the next key as "up", "down", "enter", "quit", a digit or
    None (anything else), and a function that puts the terminal back as it was."""
    if sys.platform.startswith("win"):
        import msvcrt

        def read_win():
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):                 # arrows and the other special keys
                ch2 = msvcrt.getwch()
                return {"H": "up", "P": "down"}.get(ch2)
            if ch in ("\r", "\n"):
                return "enter"
            if ch in ("\x1b", "\x03") or ch.lower() == "q":
                return "quit"
            return ch if ch.isdigit() else None
        return read_win, lambda: None
    import termios
    import tty
    import select
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)                                 # keys at once, no echo; Ctrl+C still interrupts

    def read_posix():
        ch = os.read(fd, 1)
        if ch == b"\x1b":
            # an arrow is ESC [ A or ESC O A (some terminals); a lone Esc is quit
            if not select.select([fd], [], [], 0.05)[0]:
                return "quit"
            seq = os.read(fd, 2)
            return {b"[A": "up", b"OA": "up", b"[B": "down", b"OB": "down"}.get(seq)
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch in (b"q", b"Q", b"\x03", b""):
            return "quit"
        c = ch.decode("ascii", "replace")
        return c if c.isdigit() else None
    return read_posix, lambda: termios.tcsetattr(fd, termios.TCSADRAIN, old)


def cmd_menu(argv):
    """Show the menu; return MENU_MAP / MENU_MODEL / MENU_QUIT as the exit code."""
    out = sys.stdout
    for line in MENU_HEAD:
        out.write(line + "\n")
    keys = {it[0]: i for i, it in enumerate(MENU_ITEMS)}
    if not sys.stdin.isatty():
        # no keyboard to read keys from (input piped in): a plain numbered prompt
        for key, _code, name, exts, about in MENU_ITEMS:
            out.write("  %s  %-13s (%s)\n       %s\n\n" % (key, name, exts, about))
        out.write("  Q  Quit\n\n")
        out.flush()
        try:
            ans = input(" Select [1,2,Q] (Enter = 1): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return MENU_QUIT
        if ans in ("", "1", "2"):
            return MENU_ITEMS[keys.get(ans or "1", 0)][1]
        return MENU_QUIT
    vt = _vt_on()
    sel = 0

    def item_lines(i):
        key, _code, name, exts, about = MENU_ITEMS[i]
        mark = ">" if i == sel else " "
        top = " %s %s  %-13s (%s)" % (mark, key, name, exts)
        if vt and i == sel:
            top = "\x1b[7m" + top + " \x1b[0m"           # reverse video on the selected one
        return [top, "        " + about, ""]       # a blank line after each option

    def block():
        lines = []
        for i in range(len(MENU_ITEMS)):
            lines += item_lines(i)
        return lines + ["   Q  Quit", "", MENU_HINT]

    def draw(first):
        if vt:
            lines = block()
            if not first:
                out.write("\x1b[%dF" % len(lines))       # back to the block's first line
            for line in lines:
                out.write("\x1b[2K" + line + "\n")
        else:
            # no cursor moves: the list once, then one line naming the selection
            if first:
                for line in block():
                    out.write(line.replace(">", " ") + "\n")
            key, _code, name, _exts, _about = MENU_ITEMS[sel]
            out.write("\r Selected: %s  %-13s" % (key, name))
        out.flush()

    try:
        read, restore = _menu_key_reader()
    except Exception:                                  # no console after all
        return MENU_ITEMS[0][1]
    choice = None
    try:
        draw(True)
        while choice is None:
            try:
                k = read()
            except KeyboardInterrupt:
                k = "quit"
            if k == "up":
                sel = (sel - 1) % len(MENU_ITEMS)
            elif k == "down":
                sel = (sel + 1) % len(MENU_ITEMS)
            elif k == "enter":
                choice = MENU_ITEMS[sel][1]
            elif k == "quit":
                choice = MENU_QUIT
            elif k in keys:
                sel = keys[k]
                choice = MENU_ITEMS[sel][1]
            else:
                continue
            draw(False)
    finally:
        restore()
    out.write("\n" if not vt else "")
    out.write((" Quit.\n" if choice == MENU_QUIT else " -> %s\n" % MENU_ITEMS[sel][2]) + "\n")
    out.flush()
    return choice


def main(argv):
    """Dispatch the command line. Returns the exit code."""
    if len(argv) < 2 or argv[1] not in ("deps", "start", "menu"):
        warn(__doc__ or "usage: mohaa_envcheck.py deps <libs folder> [--embed] [--upgrade] [--log NAME]\n"
                        "       mohaa_envcheck.py start NAME <launcher.py> [file]\n"
                        "       mohaa_envcheck.py menu")
        return 2
    if argv[1] == "menu":
        return cmd_menu(argv[2:])
    if argv[1] == "start":
        return cmd_start(argv[2:])
    return cmd_deps(argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
#  mohaa_common.py  --  shared hardening helpers for the MOHAA Model Viewer and
#  the MOHAA Map Viewer.
#
#  Every other script in bin/ imports this module. It holds the pieces that must
#  behave the same everywhere:
#
#    * where the programs write (the "output" folder beside bin/)
#    * logging: one rotating log file per program in output/logs/, plus
#      swallowed() for logging an exception that is deliberately handled
#    * crash hooks (sys.excepthook / threading.excepthook)
#    * atomic file writes (temp file -> fsync -> read-back verify -> os.replace,
#      with an optional .bak of the previous version)
#    * settings files (JSON) that survive damage and hand-typed Windows paths
#    * Pillow import with the project's security floor and an image-size limit
#    * HTTP GET with timeouts, retries and exponential backoff
#    * the environment for child Python processes
#
#  Standard library only: this module must import on a bare Python.
# ==============================================================================
import sys
import os

# --- Vendored dependencies ----------------------------------------------------
# Third-party packages live in a per-OS folder beside the scripts (bin/libs on
# Windows, bin/libs-linux on Linux, bin/libs-mac on macOS), so one folder can be
# used from a dual-boot machine without mixing compiled wheels.
_LIBS_NAME = "libs" if sys.platform.startswith("win") else ("libs-mac" if sys.platform == "darwin" else "libs-linux")
_libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), _LIBS_NAME)
if os.path.isdir(_libs_dir) and _libs_dir not in sys.path:
    sys.path.insert(0, _libs_dir)

import errno
import hashlib
import json
import logging
import logging.handlers
import re
import shutil
import tempfile
import threading
import time

# ==============================================================================
#  Constants
# ==============================================================================
HERE = os.path.dirname(os.path.abspath(__file__))
LIBS_DIR = _libs_dir
LIBS_NAME = _LIBS_NAME

LOGGER_ROOT = "mohaa"
LOG_SUBDIR = "logs"
LOG_MAX_BYTES = 2 * 1024 * 1024          # per log file before it rotates
LOG_BACKUPS = 5                          # rotated copies kept (name.log.1 .. .5)
SWALLOW_LOG_LIMIT = 5                    # tracebacks logged per call site, then a count only

# Pillow: the oldest release accepted. This is a SECURITY floor, not a feature floor:
# textures come straight out of .pk3 files the user downloaded, and older Pillow
# releases carry known image-decoder vulnerabilities (see docs/SECURITY.md).
PILLOW_MIN = (10, 3)
PILLOW_MIN_TEXT = "10.3.0"
# Largest image (in pixels) decoded. MOHAA textures are at most 2048 x 2048; the
# limit leaves room for odd mod assets while stopping a "decompression bomb" TGA.
IMAGE_MAX_PIXELS = 8192 * 8192

# Atomic writes: how much free space to demand beyond the data itself, and how often
# to retry os.replace when Windows reports the target as briefly locked (antivirus,
# indexer).
WRITE_SPACE_MARGIN = 1024 * 1024
REPLACE_RETRIES = 5
REPLACE_RETRY_DELAY = 0.2

# HTTP
HTTP_ATTEMPTS = 3
HTTP_BACKOFF_BASE = 1.0                  # seconds; doubles after each failed attempt
HTTP_RETRYABLE_STATUS = (408, 425, 429, 500, 502, 503, 504)

_log = logging.getLogger(LOGGER_ROOT + ".common")


# ==============================================================================
#  Where the programs write
# ==============================================================================
def install_root():
    """Return the project folder: the parent of bin/ in the shipped layout, else HERE.

    Expects nothing. Returns an absolute path. Pure (creates nothing)."""
    if os.path.basename(HERE).lower() == "bin":
        return os.path.dirname(HERE)
    return HERE


def data_dir():
    """Return the folder the programs write to, without creating it.

    In the shipped layout (scripts in bin/) this is the sibling "output" folder, unless
    its parent can't be written, in which case HERE is used (portable / flat install).
    Returns an absolute path. Pure: call ensure_dir() before writing into it."""
    if os.path.basename(HERE).lower() == "bin":
        out = os.path.join(os.path.dirname(HERE), "output")
        if os.path.isdir(out) or os.access(os.path.dirname(out), os.W_OK):
            return out
    return HERE


def ensure_dir(path):
    """Create `path` (and parents) if needed. Returns the absolute path.

    Raises OSError if it can't be created or isn't a directory."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("ensure_dir: empty path")
    path = os.path.abspath(path)
    os.makedirs(path, exist_ok=True)
    if not os.path.isdir(path):
        raise OSError(errno.ENOTDIR, "not a directory", path)
    return path


def logs_dir():
    """Return output/logs (absolute; not created)."""
    return os.path.join(data_dir(), LOG_SUBDIR)


# ==============================================================================
#  Logging
# ==============================================================================
class _TolerantRotatingHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler that keeps logging when a rollover is impossible.

    Several child processes (model / map builds) can write the same log at once; on
    Windows the rename during rollover then fails because another process holds the
    file. Instead of printing "--- Logging error ---" into the console (which the
    launcher would show in red), the handler keeps appending to the current file and
    tries the rollover again on a later record."""

    def doRollover(self):
        """Rotate the file; on OSError reopen the current one and carry on."""
        try:
            super().doRollover()
        except OSError:
            if self.stream is None:
                try:
                    self.stream = self._open()
                except OSError:
                    self.stream = None


class _OneLineFormatter(logging.Formatter):
    """Console format: one line per record. Tracebacks stay in the log file only."""

    def format(self, record):
        """Return "[LEVEL] message" with any traceback replaced by a pointer to the log."""
        line = "[%s] %s" % (record.levelname, record.getMessage())
        if record.exc_info:
            line += "  (traceback in %s)" % logs_dir()
        return line


_logging_ready = {}


def setup_logging(app_name, console_level=logging.WARNING, file_level=logging.DEBUG):
    """Configure the "mohaa" logger for this process. Safe to call more than once.

    app_name:      file name stem for the log, e.g. "mohaa_launcher" -> output/logs/mohaa_launcher.log
    console_level: records at or above this go to stderr (when the process has one).
                   None disables the console handler (child builds whose stderr the
                   launcher shows in red).
    file_level:    records at or above this go to the log file.
    Returns the absolute log file path, or None if the log folder can't be created (the
    reason is then printed to stderr when there is one)."""
    if not isinstance(app_name, str) or not app_name.strip():
        raise ValueError("setup_logging: app_name is empty")
    app_name = app_name.strip()
    if app_name in _logging_ready:
        return _logging_ready[app_name]
    root = logging.getLogger(LOGGER_ROOT)
    root.setLevel(logging.DEBUG)
    root.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s [%(process)d %(threadName)s] "
                            "%(name)s %(funcName)s:%(lineno)d  %(message)s")
    path = None
    try:
        d = ensure_dir(logs_dir())
        path = os.path.join(d, app_name + ".log")
        fh = _TolerantRotatingHandler(path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS,
                                      encoding="utf-8", delay=True)
        fh.setLevel(file_level)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as e:
        path = None
        if sys.stderr is not None:
            sys.stderr.write("[WARN] log file unavailable (%s); logging to the console only\n" % e)
    if console_level is not None and sys.stderr is not None:
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(console_level)
        ch.setFormatter(_OneLineFormatter())
        root.addHandler(ch)
    _logging_ready[app_name] = path
    return path


def get_logger(name):
    """Return the logger "mohaa.<name>" (name: the module, e.g. "launcher")."""
    return logging.getLogger(LOGGER_ROOT + "." + str(name or "app"))


_swallow_counts = {}
_swallow_lock = threading.Lock()


def swallowed(note=None):
    """Log the exception being handled right now, then return so the caller's own
    recovery path runs. Call it as the first statement of an `except` block whose
    exception is deliberately not re-raised.

    Each call site (file:line) logs its first SWALLOW_LOG_LIMIT occurrences with a full
    traceback at DEBUG level, then one notice that further ones are only counted, so a
    handler inside a hot loop can't flood the log. Never raises."""
    try:
        exc = sys.exc_info()
        if exc[0] is None:
            return
        f = sys._getframe(1)      # the caller's frame: where the exception was handled
        site = "%s:%d" % (os.path.basename(f.f_code.co_filename), f.f_lineno)
        with _swallow_lock:
            n = _swallow_counts.get(site, 0) + 1
            _swallow_counts[site] = n
        lg = logging.getLogger(LOGGER_ROOT + ".handled")
        if not lg.isEnabledFor(logging.DEBUG):
            return
        where = "%s in %s()" % (site, f.f_code.co_name)
        msg = "handled %s: %s at %s" % (exc[0].__name__, exc[1], where)
        if note:
            msg += " (" + str(note) + ")"
        if n <= SWALLOW_LOG_LIMIT:
            lg.debug(msg, exc_info=exc)
        elif n == SWALLOW_LOG_LIMIT + 1:
            lg.debug("%s -- further exceptions handled at %s are counted, not logged", msg, site)
    except Exception:              # the one place an exception is dropped: logging itself failed
        return


def swallow_counts():
    """Return a copy of {call site: times an exception was handled there}."""
    with _swallow_lock:
        return dict(_swallow_counts)


def install_crash_hooks(app_name, on_crash=None):
    """Route uncaught exceptions (main thread and worker threads) into the log.

    app_name: shown in the one-line console summary.
    on_crash: optional callable(summary_text) for a GUI notice; its own errors are logged.
    Returns nothing."""
    lg = get_logger("crash")

    def _report(exc_type, exc, tb, where):
        """Log one uncaught exception, print a one-line summary, call on_crash."""
        lg.critical("uncaught %s in %s: %s", exc_type.__name__, where, exc, exc_info=(exc_type, exc, tb))
        summary = "%s: %s crashed in %s: %s: %s" % (app_name, "FATAL", where, exc_type.__name__, exc)
        if sys.stderr is not None:
            try:
                sys.stderr.write(summary + "\n")
            except Exception:
                swallowed()
        if on_crash is not None:
            try:
                on_crash(summary)
            except Exception:
                lg.exception("crash notice failed")

    def _excepthook(exc_type, exc, tb):
        """sys.excepthook: report everything except Ctrl-C (left to Python's default)."""
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        _report(exc_type, exc, tb, "main thread")

    def _thread_hook(args):
        """threading.excepthook: report a worker thread's uncaught exception."""
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread is not None else "a thread"
        _report(args.exc_type, args.exc_value, args.exc_traceback, name)

    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook


# ==============================================================================
#  Atomic writes
# ==============================================================================
def _check_space(directory, need):
    """Raise OSError(ENOSPC) if `directory` has less than need + WRITE_SPACE_MARGIN free."""
    try:
        free = shutil.disk_usage(directory).free
    except OSError:
        swallowed("free space unknown; writing anyway")
        return
    if free < need + WRITE_SPACE_MARGIN:
        raise OSError(errno.ENOSPC, "not enough free space (%d bytes free, %d needed)"
                      % (free, need + WRITE_SPACE_MARGIN), directory)


def _replace_with_retry(src, dst):
    """os.replace(src, dst), retrying briefly when Windows says the target is in use."""
    for attempt in range(REPLACE_RETRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == REPLACE_RETRIES - 1:
                raise
            time.sleep(REPLACE_RETRY_DELAY * (attempt + 1))


# One function the program can set to hear about every file the atomic writers finish
# (the launchers print "saved <path>" in their Output pane). Called after the file is in
# place, with its absolute path; its own errors are logged and ignored.
_WRITE_HOOK = None


def set_write_hook(fn):
    """Call fn(path) after each successful atomic_write_bytes / _stream / _text / _json
    (None turns it off). Returns the previous hook."""
    global _WRITE_HOOK
    old, _WRITE_HOOK = _WRITE_HOOK, (fn if callable(fn) else None)
    return old


def _notify_write(path):
    """Tell the write hook, if any, that `path` was written. Never raises."""
    if _WRITE_HOOK is None:
        return
    try:
        _WRITE_HOOK(path)
    except Exception:
        swallowed("write hook failed")


def make_backup(path):
    """Copy `path` to `path`.bak (atomically) if it exists. Returns the .bak path or None.

    Raises OSError if the copy fails: callers decide whether a missing backup is fatal."""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return None
    bak = path + ".bak"
    tmp = bak + ".tmp"
    shutil.copy2(path, tmp)
    if os.path.getsize(tmp) != os.path.getsize(path):
        os.remove(tmp)
        raise OSError(errno.EIO, "backup copy is short", bak)
    _replace_with_retry(tmp, bak)
    return bak


def atomic_write_bytes(path, data, backup=False):
    """Write `data` to `path` without ever leaving a partial file at `path`.

    Writes a temp file in the same folder, flushes and fsyncs it, reads it back and
    compares length + SHA-256, then moves it over `path` with os.replace. With
    backup=True the previous version is first copied to `path`.bak.
    path:   destination file (made absolute; its folder is created if missing).
    data:   bytes / bytearray / memoryview.
    Returns the absolute destination path. Raises OSError / ValueError on failure; the
    temp file is removed and `path` is left as it was."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("atomic_write_bytes: empty path")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("atomic_write_bytes: data must be bytes, not %s" % type(data).__name__)
    data = bytes(data)
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    _check_space(directory, len(data))
    if backup:
        try:
            make_backup(path)
        except OSError:
            _log.warning("could not back up %s before overwriting it", path, exc_info=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix="." + os.path.basename(path)[:60] + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, "rb") as f:
            back = f.read()
        if len(back) != len(data) or hashlib.sha256(back).digest() != hashlib.sha256(data).digest():
            raise OSError(errno.EIO, "read-back verification failed", tmp)
        _replace_with_retry(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            swallowed("temp file already gone")
        raise
    _notify_write(path)
    return path


def atomic_write_stream(path, src, expected_size=None, chunk=1 << 20):
    """Stream a readable binary file object into `path` atomically.

    For large pak entries that shouldn't be held in memory. Same guarantees as
    atomic_write_bytes: temp file in the destination folder, fsync, size check, then
    os.replace, so an interrupted copy never leaves a short file at `path`.
    expected_size: when given, the copied byte count must match it exactly.
    Returns the number of bytes written. Raises OSError on a short / failed copy."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("atomic_write_stream: empty path")
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    if expected_size is not None:
        _check_space(directory, int(expected_size))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix="." + os.path.basename(path)[:60] + ".", suffix=".tmp")
    got = 0
    try:
        with os.fdopen(fd, "wb") as f:
            while True:
                b = src.read(chunk)
                if not b:
                    break
                f.write(b)
                got += len(b)
            f.flush()
            os.fsync(f.fileno())
        if expected_size is not None and got != int(expected_size):
            raise OSError(errno.EIO, "short copy: %d of %d bytes" % (got, int(expected_size)), path)
        if os.path.getsize(tmp) != got:
            raise OSError(errno.EIO, "read-back size mismatch", tmp)
        _replace_with_retry(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            swallowed("temp file already gone")
        raise
    _notify_write(path)
    return got


def atomic_write_text(path, text, encoding="utf-8", errors="strict", newline=None, backup=False):
    """Atomically write a text file (see atomic_write_bytes).

    newline: None   -> "\\n" becomes os.linesep, exactly like open(path, "w");
             "\\n"  -> written as-is.
    Returns the absolute destination path."""
    if not isinstance(text, str):
        raise TypeError("atomic_write_text: text must be str, not %s" % type(text).__name__)
    if newline is None and os.linesep != "\n":
        text = text.replace("\r\n", "\n").replace("\n", os.linesep)
    elif newline not in (None, "\n", ""):
        text = text.replace("\n", newline)
    return atomic_write_bytes(path, text.encode(encoding, errors), backup=backup)


_WIN_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def _forward_slash_paths(obj):
    """Return a copy of obj with Windows-looking path strings using forward slashes."""
    if isinstance(obj, str):
        return obj.replace("\\", "/") if _WIN_PATH.match(obj) else obj
    if isinstance(obj, list):
        return [_forward_slash_paths(v) for v in obj]
    if isinstance(obj, tuple):
        return [_forward_slash_paths(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _forward_slash_paths(v) for k, v in obj.items()}
    return obj


def atomic_write_json(path, obj, backup=True, slash_paths=True, **dump_kwargs):
    """Atomically write `obj` as UTF-8 JSON (keeping a .bak of the previous file).

    slash_paths: write Windows paths ("E:\\x\\y") as "E:/x/y" so the file stays safe to
                 hand-edit (Windows APIs accept forward slashes).
    Returns the absolute destination path."""
    if slash_paths:
        obj = _forward_slash_paths(obj)
    dump_kwargs.setdefault("indent", 2)
    dump_kwargs.setdefault("ensure_ascii", False)
    return atomic_write_text(path, json.dumps(obj, **dump_kwargs) + "\n", newline="\n", backup=backup)


# ==============================================================================
#  Settings files
# ==============================================================================
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]|[\n\t\r]")


def _has_control_chars(obj):
    """True if any string in obj holds a control character (a hand-typed "C:\\new")."""
    if isinstance(obj, str):
        return bool(_CTRL.search(obj))
    if isinstance(obj, list):
        return any(_has_control_chars(v) for v in obj)
    if isinstance(obj, dict):
        return any(_has_control_chars(v) for v in obj.values())
    return False


def _repair_backslashes(raw):
    """Rewrite single backslashes (hand-typed Windows paths) as forward slashes.

    Escaped quotes (\\") and \\uXXXX escapes are kept; "\\\\" (a correctly escaped
    backslash) also becomes "/"."""
    raw = raw.replace("\\\\", "/")
    return re.sub(r'\\(?!["u])', "/", raw)


def _read_text_utf8_or_latin1(path):
    """Read a text file as UTF-8, falling back to latin-1 (never fails) with a warning."""
    with open(path, "rb") as f:
        b = f.read()
    try:
        return b.decode("utf-8-sig")
    except UnicodeDecodeError:
        _log.warning("%s is not UTF-8; reading it as latin-1", path)
        return b.decode("latin-1")


def load_settings(path):
    """Load a JSON settings file, surviving damage. Returns (dict, notice).

    notice is None when the file loaded cleanly (or doesn't exist yet), otherwise a
    one-line description of what was repaired or lost, for the Output pane.
    Recovery order:
      1. hand-typed Windows backslashes (parse error, or control characters inside a
         value) are rewritten as forward slashes and the file is saved again;
      2. otherwise the .bak copy is restored;
      3. otherwise the damaged file is kept as <name>.corrupt-<date> and {} is returned.
    Never raises for a damaged file; raises ValueError for an empty path."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("load_settings: empty path")
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return {}, None
    try:
        raw = _read_text_utf8_or_latin1(path)
    except OSError as e:
        _log.error("can't read settings %s: %s", path, e)
        return {}, "Settings file %s could not be read (%s); using defaults this session" % (os.path.basename(path), e)
    data = None
    try:
        data = json.loads(raw)
    except ValueError:
        swallowed("settings file does not parse; trying repairs")
    if isinstance(data, dict) and not _has_control_chars(data):
        return data, None
    # 1. backslash repair
    try:
        fixed = json.loads(_repair_backslashes(raw))
    except ValueError:
        swallowed("backslash repair did not help")
        fixed = None
    if isinstance(fixed, dict) and not _has_control_chars(fixed):
        try:
            atomic_write_json(path, fixed, backup=True)
        except OSError:
            _log.warning("repaired settings could not be saved back to %s", path, exc_info=True)
        msg = "Settings %s: Windows paths typed with backslashes were repaired (old copy kept as .bak)" % os.path.basename(path)
        _log.warning(msg)
        return fixed, msg
    if isinstance(data, dict):
        # Parsed, but holds control characters the repair couldn't explain: keep as is.
        _log.warning("settings %s hold control characters in a value; left unchanged", path)
        return data, None
    # 2. the backup
    bak = path + ".bak"
    if os.path.isfile(bak):
        try:
            with open(bak, "r", encoding="utf-8") as f:
                old = json.load(f)
            if isinstance(old, dict):
                _keep_corrupt(path)
                atomic_write_json(path, old, backup=False)
                msg = "Settings %s were damaged; restored the previous copy (.bak)" % os.path.basename(path)
                _log.error(msg)
                return old, msg
        except (OSError, ValueError):
            swallowed("backup settings unusable")
    # 3. start fresh, keeping the damaged file for inspection
    kept = _keep_corrupt(path)
    msg = ("Settings %s were damaged and no usable backup exists; starting with defaults "
           "(damaged file kept as %s)" % (os.path.basename(path), os.path.basename(kept) if kept else "?"))
    _log.error(msg)
    return {}, msg


def _keep_corrupt(path):
    """Move a damaged file aside as <path>.corrupt-YYYYmmdd-HHMMSS. Returns the new path or None."""
    dst = path + time.strftime(".corrupt-%Y%m%d-%H%M%S")
    try:
        os.replace(path, dst)
        return dst
    except OSError:
        _log.error("could not move damaged %s aside", path, exc_info=True)
        return None


def same_path(a, b):
    """True if two path strings name the same file (case / slash / dot-dot insensitive)."""
    if not a or not b:
        return False
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except (TypeError, ValueError):
        swallowed()
        return False


# ==============================================================================
#  Pillow
# ==============================================================================
_pil_state = {}


def _version_tuple(text):
    """'10.3.0' -> (10, 3, 0); non-numeric parts end the tuple."""
    out = []
    for part in str(text).split("."):
        m = re.match(r"\d+", part)
        if not m:
            break
        out.append(int(m.group(0)))
    return tuple(out)


def pil_image():
    """Return PIL.Image configured for untrusted input, or raise ImportError.

    Raises ImportError when Pillow is missing OR older than PILLOW_MIN (the security
    floor), with a message that says which and how to fix it. On success the decoder's
    pixel limit is set to IMAGE_MAX_PIXELS and oversized images raise an error instead
    of a warning, so a hostile texture is skipped rather than decoded."""
    if "image" in _pil_state:
        return _pil_state["image"]
    if "error" in _pil_state:
        raise ImportError(_pil_state["error"])
    try:
        import PIL
        from PIL import Image
    except ImportError as e:
        _pil_state["error"] = "Pillow is not installed (%s)" % e
        raise ImportError(_pil_state["error"])
    ver = getattr(PIL, "__version__", "0")
    if _version_tuple(ver) < PILLOW_MIN:
        _pil_state["error"] = ("Pillow %s is older than the required %s (older releases have known "
                               "image-decoder vulnerabilities); textures are disabled until it is updated"
                               % (ver, PILLOW_MIN_TEXT))
        get_logger("pil").error(_pil_state["error"])
        raise ImportError(_pil_state["error"])
    import warnings
    Image.MAX_IMAGE_PIXELS = IMAGE_MAX_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    _pil_state["image"] = Image
    return Image


def pil_status():
    """Return (ok, text): whether textures can be decoded, and a one-line reason."""
    try:
        Image = pil_image()
    except ImportError as e:
        return False, str(e)
    import PIL
    return True, "Pillow %s" % getattr(PIL, "__version__", "?")


# ==============================================================================
#  Network
# ==============================================================================
def http_get(url, user_agent, timeout=(10, 30), dest=None, max_bytes=None, attempts=HTTP_ATTEMPTS):
    """GET `url` with retries. Returns the body as bytes, or `dest` when dest is given.

    timeout:   (connect, read) seconds. urllib has one socket timeout, so the larger is
               used per operation and the connect value bounds the first byte.
    dest:      file path: the body is streamed to dest + ".part", then moved into place.
    max_bytes: refuse a body larger than this (ValueError).
    attempts:  tries before giving up; waits HTTP_BACKOFF_BASE * 2**n between them.
    4xx answers other than HTTP_RETRYABLE_STATUS fail at once (urllib.error.HTTPError).
    Raises the last error after the final attempt."""
    import urllib.request
    import urllib.error
    if not isinstance(url, str) or not url.lower().startswith("https://"):
        raise ValueError("http_get: only https:// URLs are fetched (%r)" % (url,))
    t = max(timeout) if isinstance(timeout, (tuple, list)) else float(timeout)
    lg = get_logger("net")
    last = None
    for n in range(max(1, int(attempts))):
        if n:
            delay = HTTP_BACKOFF_BASE * (2 ** (n - 1))
            lg.info("retrying %s in %.0f s (attempt %d of %d)", url, delay, n + 1, attempts)
            time.sleep(delay)
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=t) as r:
                if dest is None:
                    body = r.read(max_bytes + 1 if max_bytes else -1)
                    if max_bytes and len(body) > max_bytes:
                        raise ValueError("%s: response larger than %d bytes" % (url, max_bytes))
                    return body
                part = os.path.abspath(dest) + ".part"
                got = 0
                with open(part, "wb") as f:
                    while True:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        got += len(chunk)
                        if max_bytes and got > max_bytes:
                            raise ValueError("%s: response larger than %d bytes" % (url, max_bytes))
                        f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno())
                declared = r.headers.get("Content-Length")
                if declared and declared.isdigit() and int(declared) != got:
                    raise OSError(errno.EIO, "download truncated (%d of %s bytes)" % (got, declared), url)
                _replace_with_retry(part, dest)
                return dest
        except urllib.error.HTTPError as e:
            last = e
            lg.warning("%s: HTTP %s", url, e.code)
            if e.code not in HTTP_RETRYABLE_STATUS:
                raise
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = e
            lg.warning("%s: %s", url, e)
            if isinstance(e, ValueError):
                raise
    raise last


# ==============================================================================
#  Child processes
# ==============================================================================
def child_env(extra=None):
    """Environment for a child Python run of one of these scripts.

    UTF-8 stdout/stderr (so a non-ASCII file name can't crash a build on a Windows
    code page), and the vendored libs folder on PYTHONPATH (a child interpreter does
    not inherit this process's sys.path). extra: optional dict merged last."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if os.path.isdir(LIBS_DIR):
        old = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = LIBS_DIR + (os.pathsep + old if old else "")
    if extra:
        env.update(extra)
    return env

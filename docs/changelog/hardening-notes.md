# Hardening notes

How the code is protected against crashes, damaged files, bad input and broken
environments, why it is done this way, and what is still open. Read this before changing
logging, file writes, settings, the updater or the RUN files. The history of the pass that
introduced all of it is in [CHANGELOG.md](CHANGELOG.md) under *1.0.001 hardening pass*.

The rules follow publicly hardened, standard, unified coding practices: the core rules
apply to every script, the remembered-configuration and self-updating rules apply here
because both programs keep settings and update themselves, and the field-proven rules
(`python -m pip`, batch-file discipline, two-process bootstrap, subprocess vendoring)
apply always.

## The shared module: `bin/mohaa_common.py`

Every script imports it as `MC` right after its vendored-libs block. Standard library only,
so it imports on a bare Python.

| Need | Use | Notes |
|---|---|---|
| Where to write | `MC.data_dir()`, `MC.ensure_dir()`, `MC.logs_dir()` | `data_dir()` is pure (creates nothing): `output/` beside `bin/`, or the scripts' folder in a flat install or when `output/`'s parent isn't writable. |
| Logging | `MC.setup_logging(name, console_level=...)`, `MC.get_logger(name)` | One rotating file per program part in `output/logs/` (2 MB x 5). Console gets one line per record, never a traceback. Child builds pass `console_level=None`: their stderr is shown in red by the launcher. |
| An exception you handle on purpose | `MC.swallowed()` as the first line of the `except` block | Logs the traceback at DEBUG; first 5 per call site, then a count. Never raises. A handler that re-raises doesn't need it. |
| Uncaught exceptions | `MC.install_crash_hooks(name)` | `sys.excepthook` and `threading.excepthook`. The Tk side is `App.report_callback_exception`. |
| Writing a file | `MC.atomic_write_bytes / _text / _json / _stream` | Temp file in the same folder, fsync, read-back check (SHA-256, or size for streams), `os.replace` (retried when Windows reports the target busy). `backup=True` keeps `<file>.bak`. `_text(newline=None)` writes `\n` as `os.linesep`, exactly like `open(path, "w")`. |
| Settings | `MC.load_settings(path)` -> `(dict, notice)` | Repairs hand-typed backslash paths, else restores `.bak`, else keeps the file as `.corrupt-<date>` and returns `{}`. `notice` goes to the Output pane. `atomic_write_json` writes Windows paths with forward slashes so the file stays hand-editable. |
| Pillow | `Image = MC.pil_image()` instead of `from PIL import Image` | Raises `ImportError` if Pillow is missing **or older than 10.3** (security floor), sets the 8192 x 8192 pixel limit and turns the decompression-bomb warning into an error. `MC.pil_status()` for a yes/no plus reason. |
| Network | `MC.http_get(url, ua, timeout, dest=, max_bytes=)` | HTTPS only, 3 attempts with 1 s / 2 s backoff, 4xx (other than 408/425/429) fails at once, streamed downloads go to `.part` and are length-checked. |
| A child Python process | `env=MC.child_env()` with `encoding="utf-8"` | UTF-8 stdout/stderr and the vendored libs on `PYTHONPATH`. |

## Decisions and why

- **Logs live in `output/logs/`, not next to the scripts.** The coding rules say
  `<script>.log` beside the script, but this project keeps every runtime file in `output/`
  so `bin/` can be read-only and an update never touches user data. The Output-pane mirror
  (`output_console.log`, previous launch kept as `.prev`) is kept as it was, for users.
- **Vendored packages per OS, in `bin/`.** `bin/libs` (Windows), `bin/libs-linux`,
  `bin/libs-mac`: one copy of the program can sit on a drive shared by a dual-boot PC without
  mixing compiled wheels. The folder sits next to the scripts (the coding rule), not
  next to the RUN files. The updater never writes into these folders (`UPDATE_SKIP_DIRS`).
- **`pip install --target` instead of `--user` / system installs.** It never needs admin
  rights, never changes other programs' packages, and is exempt from PEP 668, so it works
  on Ubuntu / Kubuntu 23.04+ where plain `pip install` is refused. Ubuntu 24.04's packaged
  `python3-pil` is 10.2.0, below the floor, so the system package isn't an option anyway.
- **pywebview is pinned exactly, and checked by its code.** tkwebview2 3.5.0 uses pywebview
  4.4.1's `EdgeChrome.web_view` (renamed `.webview` in pywebview 5). An "==" requirement is an
  exact pin: any other installed version, or a second version's `.dist-info` left beside the
  code (pip `--target` replaces code but not other versions' metadata), is replaced. The
  pywebview check reads `webview/platforms/edgechromium.py` for `self.web_view`, so newer
  code under old metadata is caught. tkwebview2 goes in with `--no-deps`, since it lists
  `pywebview` unpinned and pip would install the newest over the pinned one.
- **One `.dist-info` per package.** pip `--target` never removes an older version's
  `.dist-info`, so any upgrade (Pillow 13.0 to 13.1, or a dependency pip re-resolves along
  the way, like pythonnet) leaves two. The version reader takes the newest folder; a package
  with more than one is installed again; and after every pip run every package's extra
  records are deleted, keeping the one pip just wrote. A second launch after a repair is
  plain `[OK]` lines.
- **Installs are verified in a fresh process.** `mohaa_envcheck.py` imports each package
  (`PIL._imaging` for Pillow) in a new interpreter after installing it: a process can't
  reliably import what it just installed (the two-process rule), and the import also
  catches a libs folder built for a different Python version, which is then reinstalled.
- **The RUN `.bat` waits until the program's window is open, then closes.** `mohaa_envcheck.py
  start` runs the launcher with `pythonw.exe` (detached, its own output in
  `output/logs/run_<name>_program.log`) and waits for it to create the file named by
  `MOHAA_READY_FILE`, which the launcher does once its window is up. If the program stops
  first, the window shows the last lines it printed and pauses once (the launcher rule), so
  start-up failures stay visible. Before the hardening pass it started `pythonw.exe` and
  closed at once (failures invisible); during it, it waited for the program to close (a
  console window open beside it the whole time).
- **The RUN window's text isn't lost.** `mohaa_envcheck.py deps --log <name>` copies every
  line it prints, pip's output included, into `output/logs/run_<name>.log` (the last one kept
  as `.prev.log`); the launcher reads `MOHAA_RUN_LOG` and puts that text at the top of its
  Output pane, so it is in `output_console*.log` too.
- **Saved files are announced.** `MC.set_write_hook()` gets every path the atomic writers
  finish; the launchers print "saved <path>" in the Output pane, except scratch files (the
  temp folder, caches, logs) and the same file again within 3 s.
- **Windows-version detection stays in batch** in `python_installer_updater.bat`, because
  it runs before any Python exists. Everything after a Python is found is done in Python.
- **The updater's backups follow the owner's previous-versions convention:** one numbered
  folder per update in `output/previous-versions/`, with `changelog.txt` at its root holding
  lines like `3 - version 1.0.001 (replaced by 1.0.002 on 2026-12-01, 14 files)`.
- **A branch download is accepted only if it is the advertised version.** The tag zip is
  preferred; the `main` zip is the fallback only when its `docs/version.txt` equals the
  version the check reported, so an untagged release can't install unreleased code.
- **The locked-file swap is Python, not a generated `.bat`.** A `.bat` written as UTF-8 and
  run by cmd in the OEM code page lost non-ASCII paths, and only worked on Windows.
- **Every broad handler logs, nothing else changed.** `MC.swallowed()` was inserted by an
  AST-guided pass into every `except Exception` / bare `except` that doesn't re-raise, and
  every trivial `except OSError` (381 handlers). Narrow parse fallbacks
  (`except ValueError: continue` and the like) and the level script's control-flow
  exceptions were left alone: they are explicit recovery paths, not errors.
- **`mohaa_view.py` keeps its failure lines on stdout.** The launcher reads lines starting
  with `!` from the build's stdout to tell the page why an animation or attachment failed;
  moving them to stderr would break that.
- **Pillow older than 10.3 disables textures** rather than just warning, matching the
  security floor the project already declared.

## Things that must stay in step

See the table in [development-workflow.md](development-workflow.md). The ones the
hardening added: `MapApp.__init__` repeats `App.__init__` (checked by
`tests/check_init_attrs.py`); the privacy text in three places (checked by
`tests/check_privacy_sync.py`); the two RUN files, one per system (generated by `tools/make_launchers.py`,
checked by `tests/check_batch_files.py`); package floors in `mohaa_envcheck.py`,
`mohaa_common.PILLOW_MIN` and `docs/requirements.txt`.

## How it was tested

- `tests/test_hardening.py`, 27 tests. Real: file writes, zips, settings files, `.bsp`
  saves, the end-to-end map build in a child process with the launcher's environment.
  Simulated (each test says so): a crash mid-write, a file that can't be written during an
  update, the network for the updater (a local zip stands in for GitHub), and a Windows
  console (the child's output forced to cp1252, which reproduces the old crash and shows the
  fix).
- `tests/fuzz_parsers.py`: about 9,000 corrupted inputs across every file parser, before
  and after the pass; no undeclared exceptions, no hangs.
- Both launchers started under Xvfb with an injected callback error (logged, shown, clean
  exit) and an injected start-up failure (message box, exit code 1).
- The Linux `.sh` launcher run end to end on Ubuntu 24.04 (the Kubuntu base): a `python3`
  without tkinter was skipped, Pillow vendored into `bin/libs-linux`, the Map Viewer started
  and built a dropped `.bsp`. A broken install (compiled module deleted) was detected and
  reinstalled.
- Built model and map pages loaded in headless Chromium with no console errors.
- **Not run:** the `.bat` files (no Windows available; they are byte-checked only), the
  embedded WebView2 pane, the registry check for the WebView2 Runtime, and the locked-file
  swap after an update. Check those on Windows before a release.

## Still open

- About 365 functions (mostly in `mohaa_launcher.py` and `mohaa_view.py`) have no
  docstring, `mohaa_view.main()` is 841 lines, and much of the code packs several statements
  per line. The coding rules ask for docstrings and plain, readable code; doing that across
  ~34,000 lines is a rewrite, not a hardening pass, so it was left for its own reviewed
  change.
- Some pak loops open a `ZipFile` without `with`, so an exception in the loop leaves the
  handle for the garbage collector.
- The update zip has no signature of its own; its integrity rests on HTTPS and GitHub.
- Atomic writes fsync the file, not its folder, so on Linux a power cut right after a
  rename could in theory lose the rename (never a partial file).
- Saving a modified `.bsp` over an earlier Save-as copy keeps it as `<name>.bsp.bak`; the
  Map Viewer would open that as a MOHRadiant `.bak` if you pointed it at it.
- A `.tik` is rewritten with its `$include`s expanded after extraction, so its size no
  longer matches the pak entry and it is extracted again on the next build (same result,
  slightly slower).

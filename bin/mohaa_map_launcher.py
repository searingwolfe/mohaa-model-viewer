#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
#  mohaa_map_launcher.py  --  desktop launcher for the MOHAA Map Viewer
#
#  Load MOHAA .pk3 paks and browse their maps/ tree, or open a loose .bsp / .map.
#  Each map is built into a viewer page by mohaa_map_view.py (a .bsp is turned back
#  into .map source on the way, saved in the output folder) and shown in the
#  embedded WebView2 pane, or the default browser.
#
#  The window is the Model Viewer's own (mohaa_launcher.py): same layout, menus,
#  themes, dialogs, pak handling and embedded pane. This file changes what is
#  different for maps: the tree, how a file is opened and built, the map details
#  panel, the menus' map options and where settings and pages are kept.
# ==============================================================================
# --- Vendored dependencies (bin/libs on Windows, bin/libs-linux on Linux, bin/libs-mac on macOS)
import sys
import os
_LIBS_NAME = "libs" if sys.platform.startswith("win") else ("libs-mac" if sys.platform == "darwin" else "libs-linux")
_libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), _LIBS_NAME)
if os.path.isdir(_libs_dir) and _libs_dir not in sys.path:
    sys.path.insert(0, _libs_dir)
_bin_dir = os.path.dirname(os.path.abspath(__file__))
if _bin_dir not in sys.path:
    sys.path.insert(0, _bin_dir)
import mohaa_common as MC                       # logging, atomic writes, settings, Pillow guard
import os, sys, re, json, shutil, subprocess, threading, tempfile, zipfile, glob

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mohaa_launcher as ML                    # the shared launcher window
from mohaa_launcher import tk, ttk, filedialog, _mi, _MSEP

LOG = MC.get_logger("map_launcher")
try:
    import mohaa_textures as MTX                # pak file system
except Exception:
    LOG.error("mohaa_textures could not be imported", exc_info=True)
    MTX = None
try:
    import mohaa_bsp as MB                      # tells its own decompiled .map files apart
except Exception:
    LOG.error("mohaa_bsp could not be imported", exc_info=True)
    MB = None

APP_NAME = "MOHAA Map Viewer"
MAP_BUILDER = os.path.join(HERE, "mohaa_map_view.py")
# The map viewer keeps its own settings and console log next to the Model Viewer's,
# so both programs can be open at once.
MAP_CONFIG = os.path.join(ML.DATADIR, "mohaa_map_viewer_config.json")
MAP_LOG = os.path.join(ML.DATADIR, "output_console_map.log")
# Prefix of this program's scratch folders in the system temp folder.
TEMP_PREFIX = "mohaamap_"
# Oldest page format a cached map page may have; keep equal to MAP_VIEWER_REV in
# mohaa_map_view.py. Older pages are rebuilt so new viewer features show up.
MAP_VIEWER_REV_REQUIRED = 105
# Files the map tree lists, and what each kind is.
MAP_KINDS = {".bsp": "bsp", ".map": "map", ".bak": "map", ".scr": "scr", ".txt": "scr", ".pth": "bin",
             ".min": "bin", ".dcl": "bin", ".vis": "bin", ".lin": "bin", ".cfg": "scr"}
# Files that open in the viewer: a .bak is MOHRadiant's previous save of a .map (or a
# backed-up .bsp), opened as what it holds; its page and decompile have "_bak" in the name.
MAP_EXTS = (".bsp", ".map", ".bak")
TEXT_KINDS = ("scr",)

# The launcher's own shortcuts: the "Launcher" tab of the F1 window (its "3D viewer" tab
# shows MAP_VIEWER_KEYS from mohaa_map_view.py). The Model Viewer's KEYS_LAUNCHER with the
# map launcher's differences; same format (VIEWER_KEYS in mohaa_view.py).
MAP_KEYS_LAUNCHER = {
    "title": "Launcher keyboard shortcuts",
    "cols": [
        {"title": "Launcher", "rows": [
            ML._kx_sub("Anywhere in the launcher", "app"),
            ML._kx("Ctrl+O", "add .pk3 pak(s)", ("Ctrl+O", "add paks")),
            ML._kx("Ctrl+Shift+O", "open a loose .bsp / .map / .bak file", ("Ctrl+Shift+O", "open file")),
            ML._kx("Ctrl+F", "focus the search box", ("Ctrl+F", "search")),
            ML._kx("Esc", "clear the search / close a menu / cancel loading", ("Esc", "cancel")),
            ML._kx("F5", "reload all loaded paks", ("F5", "reload")),
            ML._kx("Ctrl+T", "dark / light theme", ("Ctrl+T", "theme")),
            ML._kx("Ctrl+Shift+T", "old (OS-default) popup windows on / off", ("Ctrl+Shift+T", "old pop")),
            ML._kx("F1", "this window", ("F1", "keys", "the keyboard shortcuts (this window)")),
            ML._kx("F2", "the legend: colours, markers and editor surfaces", ("F2", "legend")),
            ML._kx("right-click", "on the Output console or the details panel: copy menu",
                   ("RClick", "copy", "copy menu (Output console, details panel)")),
        ]},
        {"title": "Pak tree", "rows": [
            ML._kx_sub("In the pak tree", "tree"),
            ML._kx("Enter", "open the file / go into the folder", ("Enter", "open")),
            ML._kx("Backspace", "go up one folder", ("Backspace", "up")),
            ML._kx("Right|Left", "expand / collapse the folder", ("Right", "expand", "expand the folder"),
                   ("Left", "collapse", "collapse the folder")),
            ML._kx("Up|Down", "move the selection", ("Up", "up", "select the row above"),
                   ("Down", "down", "select the row below")),
            ML._kx("double-click", ".bsp / .map opens in the viewer, .scr in your text editor", ("DblClick", "open")),
            ML._kx("Ctrl+click|Shift+click", "select several maps (Enter or right-click builds them all)",
                   ("Ctrl+Click", "select +", "add a map to the selection"), ("Shift+Click", "range", "select a range of maps")),
            ML._kx("right-click", "file / folder / pak menu (decompile only, text editor ...)",
                   ("RClick", "menu", "file / folder / pak menu")),
            ML._kx("drag", "a file off the window: open it in its own browser window",
                   ("Drag", "drag out", "drag a file off the window: open it in its own browser window")),
        ]},
    ]}


# The Model Viewer's privacy notice (PRIVACY_TEXT in mohaa_launcher.py), reworded for this
# program: same project, same promises; only the files it writes and what its pages hold
# differ. Each left-hand text must match PRIVACY_TEXT exactly, so check these after
# editing the notice.
_PRIVACY_SWAPS = (
    ("MOHAA Model Viewer", APP_NAME),
    ("mohaa_viewer_config.json", "mohaa_map_viewer_config.json"),
    ("output_console.log", "output_console_map.log"),
    ("theme, window layout, view angles,", "theme, window layout, map options,"),
    ("(mohaaview_*), and\n"
     "        the generated .html viewers in your chosen output folder. Both are\n"
     "        removable from File --> Clear built models / Clear %temp% files. On\n"
     "        Windows, the embedded 3D pane (Microsoft Edge WebView2) also keeps its\n"
     "        browser files in a \"webview2\" folder beside (a).",
     "(mohaamap_*), and\n"
     "        the generated .html viewers and decompiled .map files in your chosen\n"
     "        output folder. Both are removable from File --> Clear built maps /\n"
     "        Clear %temp% files. On Windows, the embedded 3D pane (Microsoft Edge\n"
     "        WebView2) also keeps its browser files in a \"webview2\" folder beside (a)."),
    ("(theme, backdrop colour,\n"
     "        renderer, placement angles, game cvars) in the browser's local storage.\n"
     "        The embedded pane runs in private mode and forgets them when the program\n"
     "        closes; in your own browser they stay with that browser's data for local\n"
     "        files.",
     "(theme, backdrop colour,\n"
     "        panel options, the grid's size and colour, game cvars, where the Edit\n"
     "        parameters box was left, and Simulate's model) in the browser's local\n"
     "        storage. The embedded pane runs in private mode and forgets them when the\n"
     "        program closes; in your own browser they stay with that browser's data for\n"
     "        local files."),
    ("(textures are embedded as data: URIs)", "(its textures are embedded in it)"),
    ("workspace, model headers\n"
     "   are bounds-checked, and generated pages escape game-file text), but no\n"
     "   software is perfect. Please report suspected vulnerabilities as described in\n"
     "   SECURITY.md",
     "workspace, model\n"
     "   and .bsp headers are bounds-checked, and generated pages escape game-file\n"
     "   text), but no software is perfect. Please report suspected vulnerabilities\n"
     "   as described in SECURITY.md"),
    ("If you open a model in", "If you open a map in"),
)


def _privacy_text():
    """The privacy notice as this program shows it (see _PRIVACY_SWAPS)."""
    t = ML.PRIVACY_TEXT
    for a, b in _PRIVACY_SWAPS:
        t = t.replace(a, b)
    return t


class MapApp(ML.App):
    """The Model Viewer's launcher window, set up for maps."""

    # The only kinds of pak file ever extracted to the workspace: maps to build and text
    # files to open in the text editor.
    _EXTRACT_OK = {".bsp", ".map", ".bak", ".scr", ".txt", ".shader", ".tik", ".cfg"}

    def __init__(self, initial_file=None):
        # Same start-up as the Model Viewer's window (mohaa_launcher.App.__init__), with
        # this program's own title, settings file, console log and folders. NOTE: this
        # repeats App.__init__ rather than calling it; an attribute added there must be
        # added here too (tests/check_init_attrs.py compares the two).
        ML.init_runtime("mohaa_map_launcher")
        tk.Tk.__init__(self)
        ML.init_fonts()
        self.title(APP_NAME)
        self.geometry("1380x820"); self.minsize(1000, 600)
        self._config_path = MAP_CONFIG
        self._cfg = self._load_config(); self._pyexe = ML.find_python()
        self._attach_busy = set(); self._attach_parts = []
        self._attach_lock = threading.Lock()
        self._theme = self._cfg.get("theme", "dark")
        if self._theme not in ML.THEMES: self._theme = "dark"
        ML.apply_theme(self, self._theme)
        self.configure(bg=ML.BG)
        import queue
        self._log_q = queue.Queue(); self._drop_paths = []
        self._status_base = "Ready"; self._pak_suffix = ""
        self._upd_state = None; self._upd_dl_btn = None
        self._logfile = ML.open_console_mirror(MAP_LOG)
        self._startup_extras()       # the RUN window's text, "saved <file>" lines, window-open signal
        self._pk3_paths = []; self._tmp = None; self._animroot = None
        self._vfs = None; self._SH = None; self._TI = None; self._GS = None; self._PROPS = None; self._ED = None
        self._tex_ready = False; self._tex_gen = 0
        self._tree_entry = {}
        self._tree_kind = {}
        self._all_files = []
        self._filter_after = None
        self._tips = []
        self._auto_open = tk.BooleanVar(value=bool(self._cfg.get("auto_open", True)))
        self._remember = tk.BooleanVar(value=bool(self._cfg.get("remember_paks", True)))
        self._renderer_var = tk.StringVar(value="gl")
        self._outdir_on = tk.BooleanVar(value=bool(self._cfg.get("outdir_enabled", True)))
        self._outdir = self._cfg.get("outdir") or os.path.join(ML.DATADIR, "maps")
        self._run_opts = {}
        self._last_build = None; self._last_info = None; self._last_subdir = None
        self._reuse_html = tk.BooleanVar(value=bool(self._cfg.get("reuse_html", True)))
        self._no_recent = tk.BooleanVar(value=bool(self._cfg.get("no_recent", False)))
        self._embed_on = tk.BooleanVar(value=bool(self._cfg.get("embed_viewer", True)))
        # Map options: texture size in the page, and whether placed models are built.
        self._texsize = tk.StringVar(value=str(self._cfg.get("texsize", 256)))
        self._models_on = tk.BooleanVar(value=bool(self._cfg.get("models", True)))
        self._anim_preload = tk.StringVar(value="0")      # unused here; kept for shared code
        self._animcat = None; self._animcat_file = None; self._animcat_for = None
        self._anim_outdir = None; self._anim_busy = set()
        self._webview = None; self._embed_url = None
        self._vpath_for = {}           # extracted temp file -> its path inside the paks
        self._index_cache = None       # folder where the builder keeps its shader / texture caches
        self._stale_noted = set()      # (page, mtime) already reported as out of date
        _te = (self._cfg.get("text_editor") or "").strip()
        if (not _te) or (os.path.basename(_te) == _te and not os.path.isfile(_te)):
            self._cfg["text_editor"] = (self._default_program_path("text_editor") or _te or
                                        ("notepad.exe" if sys.platform.startswith("win")
                                         else ("open" if sys.platform == "darwin" else "xdg-open")))
        self._menus = []; self._menubtns = []
        self._treetip = None; self._treetip_row = None
        self._treetip_after = None; self._treetip_armed = None
        self._old_popups = tk.BooleanVar(value=bool(self._cfg.get("old_popups", False)))
        ML.OLD_POPUPS = bool(self._old_popups.get())
        self._open_popup = None; self._popup_owner = None; self._popup_serial = None
        self._batch = []; self._batch_total = 0; self._batch_waiting = False
        self._proc = None; self._building_name = None; self._build_gen = 0
        self._opening_view = False
        self._pending_open = None
        self.bind_all("<ButtonPress-1>", self._popup_dismiss_check, add="+")
        self.bind_all("<ButtonPress-3>", self._popup_dismiss_check, add="+")
        self.bind_all("<ButtonPress-1>", self._reclaim_focus, add="+")
        self.bind_all("<ButtonPress-3>", self._reclaim_focus, add="+")
        self._watch_camera_stop()      # clicks and keys in the launcher stop the map's camera
        self._page_requests = []       # from the page's messages, run on the Tk thread (_poll_log)
        self.bind("<Configure>", self._dismiss_transients, add="+")
        self.bind("<Unmap>", self._dismiss_transients, add="+")
        self.bind("<FocusOut>", self._popup_focus_out, add="+")
        ML._win_dark_menus(self._theme == "dark")
        self._build_menu(); self._build_ui(); self._bind_hotkeys(); self._poll_log()
        self._show_startup_notices()
        self.after(150, self._enable_win_drop)
        self.after(250, self._apply_titlebar)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # the paks both programs share (mohaa_launcher.PAKS_SHARED), else this one's own
        saved = ML.read_shared_paks()
        if saved is None: saved = self._cfg.get("pk3s") or []
        saved = [p for p in saved if os.path.exists(p)]
        if saved and self._remember.get(): self.after(200, lambda: self._add_pk3s(saved))
        self._paks_watch()
        if initial_file: self.after(350, lambda: self._load(initial_file))

    # ------------------------------------------------------------- config ---
    def _load_config(self, path=None):
        """This program's own settings (MAP_CONFIG), or {} on first run (damage handled
        as in the Model Viewer: see mohaa_launcher.App._load_config)."""
        return ML.App._load_config(self, path or MAP_CONFIG)

    def _save_config(self, path=None):
        """Save MAP_CONFIG atomically with a .bak (see mohaa_launcher.App._save_config)."""
        return ML.App._save_config(self, path or MAP_CONFIG)

    def _save_opts(self):
        """Copy the Options menu's choices into the config and save it."""
        self._cfg["reuse_html"] = bool(self._reuse_html.get())
        self._cfg["no_recent"] = bool(self._no_recent.get())
        self._cfg["outdir_enabled"] = bool(self._outdir_on.get())
        self._cfg["outdir"] = self._outdir
        self._cfg["auto_open"] = bool(self._auto_open.get())
        self._cfg["embed_viewer"] = bool(self._embed_on.get())
        try: self._cfg["texsize"] = int(self._texsize.get())
        except (TypeError, ValueError): self._cfg["texsize"] = 256
        self._cfg["models"] = bool(self._models_on.get())
        self._cfg["remember_paks"] = bool(self._remember.get())
        self._cfg["pk3s"] = self._pk3_paths if self._remember.get() else []
        self._save_config()

    # ------------------------------------------------------------ menubar ---
    def _menu_items_file(self):
        bempty = not self._built_any()
        tempty = not self._temp_dirs()
        vopen = self._webview is not None
        return [_mi("Add .pk3 pak(s)...", self._choose_pk3, "Ctrl+O"),
                _mi("Open File...", self._browse_and_run, "Ctrl+Shift+O"),
                {"type": "cascade", "label": "Recent files", "items": self._menu_items_recent},
                _MSEP,
                _mi("Close file", self._close_viewer, "Esc", "normal" if vopen else "disabled"),
                _MSEP,
                _mi("Reload paks", self._reload_all_cmd, "F5"),
                _mi("Clear all paks", self._clear_pk3s),
                _MSEP,
                _mi("Clear built maps", self._clear_built_models,
                    "(empty)" if bempty else None, "disabled" if bempty else "normal"),
                _mi("Clear %temp% files", self._clear_temp_files,
                    "(empty)" if tempty else None, "disabled" if tempty else "normal"),
                _MSEP,
                _mi("Exit", self._on_close)]

    def _menu_items_options(self):
        return [{"type": "check", "label": "Remember loaded paks between sessions", "variable": self._remember, "command": self._save_opts},
                {"type": "check", "label": "Auto-open viewer after build", "variable": self._auto_open, "command": self._save_opts},
                {"type": "check", "label": "Embed 3D viewer in this window (needs tkwebview2)", "variable": self._embed_on, "command": self._toggle_embed},
                {"type": "check", "label": "Don't save recent files (empty all)", "variable": self._no_recent, "command": self._toggle_no_recent},
                _MSEP,
                {"type": "check", "label": "Draw placed models (static props, script models, turrets)",
                 "variable": self._models_on, "command": self._save_opts},
                {"type": "cascade", "label": "Texture size in the page", "items": lambda: [
                    {"type": "radio", "label": "128  (smallest pages)", "variable": self._texsize, "value": "128", "command": self._save_opts},
                    {"type": "radio", "label": "256  (default)", "variable": self._texsize, "value": "256", "command": self._save_opts},
                    {"type": "radio", "label": "512  (sharpest, larger pages)", "variable": self._texsize, "value": "512", "command": self._save_opts}]},
                _MSEP,
                {"type": "check", "label": "Save viewer HTML to output folder", "variable": self._outdir_on, "command": self._save_opts},
                {"type": "check", "label": "Load already-built HTML from output folder (skip rebuild)", "variable": self._reuse_html, "command": self._save_opts},
                _mi("Change output folder...", self._change_outdir),
                _mi("Open output folder", self._open_outdir),
                _MSEP,
                _mi("Change Text Editor...", lambda: self._change_program("text_editor", "Text Editor")),
                _mi("Open Text Editor folder", lambda: self._open_program_folder("text_editor", "Text Editor")),
                _MSEP,
                _mi("Open log folder", self._open_log_folder),
                _mi("Reset settings...", self._reset_settings)]

    def _menu_items_view(self):
        return [_mi("Expand all folders", lambda: self._expand_all(True)),
                _mi("Collapse all folders", lambda: self._expand_all(False)),
                _MSEP,
                _mi("Toggle Dark / Light", self._toggle_theme, "Ctrl+T"),
                {"type": "check", "label": "Use old popup windows", "variable": self._old_popups,
                 "command": self._toggle_old_popups, "accel": "Ctrl+Shift+T"}]

    def _menu_items_help(self):
        """The Model Viewer's Help menu, with the legend below Keyboard shortcuts."""
        items = list(super()._menu_items_help())
        items.insert(1, _mi("Legend", self._show_legend, "F2"))
        return items

    def _bind_hotkeys(self):
        """The Model Viewer's shortcuts plus F2 for the legend."""
        super()._bind_hotkeys()
        self.bind_all("<F2>", lambda e: (self._show_legend(), "break"))

    def _menu_items_pak(self):
        """Right-click menu on the pak label or empty tree space."""
        items = []
        if self._pk3_paths:
            items.append({"type": "cascade", "label": "Remove a pak", "items": lambda: [
                _mi(os.path.basename(p), (lambda pp=p: self._remove_pak(pp))) for p in self._pk3_paths]})
        items.append(_mi("Add a pak...", self._choose_pk3, "Ctrl+O"))
        if self._pk3_paths:
            items.append(_mi("Reload paks", self._reload_all_cmd, "F5"))
            items.append(_mi("Clear all paks", self._clear_pk3s))
        return items

    # ----------------------------------------------------------------- UI ---
    def _build_ui(self):
        # Same layout as the Model Viewer: title and path bar on top, the pak tree on the
        # left, the 3D pane in the middle, the Output console and the details panel below.
        top = ttk.Frame(self); top.pack(fill="x", padx=10, pady=(8, 6))
        ttk.Label(top, text=APP_NAME, style="Title.TLabel").pack(side="left")
        self._theme_btn = self._mkbtn(top, text="◐ Theme", style="Tool.TButton", command=self._toggle_theme,
                                      tip="Toggle Dark / Light theme.\n(Ctrl+T)")
        self._theme_btn.pack(side="right")
        self._help_btn = self._mkbtn(top, text="? Shortcuts", style="Tool.TButton", command=self._show_hotkeys,
                                     tip="Show all keyboard shortcuts.\n(F1)")
        self._help_btn.pack(side="right", padx=(0, 6))
        self._path_var = tk.StringVar()
        self._path_entry = tk.Entry(top, textvariable=self._path_var, bg=ML.PANEL, fg=ML.TXT, insertbackground=ML.TXT,
                                    highlightbackground=ML.LINE, highlightcolor=ML.ACCENT, highlightthickness=1,
                                    relief="flat", font=ML.FONT_MONO)
        self._path_entry.pack(side="left", fill="x", expand=True, padx=(10, 4), pady=2, ipady=3)
        self._tip(self._path_entry, "Selected map.\nPaste a full path here, pick from the tree,\nor drag a .bsp/.map/.bak onto this window.")
        self._mkbtn(top, text="Browse...", command=self._browse_and_run,
                    tip="Pick a loose .bsp, .map or .bak from disk and open it.\n(Ctrl+Shift+O)").pack(side="left", padx=(0, 4))
        self._mkbtn(top, text="▶ Open Viewer", style="Accent.TButton", command=self._run,
                    tip="Build the viewer for the selected map and show it in the middle pane\n(also runs on double-click / Enter in the tree)").pack(side="left", padx=(0, 14))
        self._lines = [tk.Frame(self, bg=ML.LINE, height=1)]; self._lines[0].pack(fill="x", padx=8)
        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=10, pady=8)
        _pw = dict(bg=ML.LINE, bd=0, sashwidth=6, sashpad=0, sashrelief="flat", showhandle=False, opaqueresize=True)
        outer = tk.PanedWindow(body, orient="horizontal", **_pw); outer.pack(fill="both", expand=True)
        rightside = tk.PanedWindow(outer, orient="vertical", **_pw)
        bottomrow = tk.PanedWindow(rightside, orient="horizontal", **_pw)
        self._panes = [outer, rightside, bottomrow]

        left = ttk.Frame(outer, style="Panel.TFrame", width=300)
        lh = ttk.Frame(left, style="Panel.TFrame"); lh.pack(fill="x", padx=8, pady=(8, 2))
        self._pk3_label = ttk.Label(lh, text="No .pk3 loaded", style="PanelDim.TLabel", cursor="hand2")
        self._pk3_label.pack(side="left")
        self._pk3_label.bind("<Button-3>", self._show_pak_menu)
        self._tip(self._pk3_label, "Right-click to list / manage every loaded Pak")
        sr = ttk.Frame(left, style="Panel.TFrame"); sr.pack(fill="x", padx=8, pady=(2, 4))
        self._mkbtn(sr, text="Add .pk3(s)...", command=self._choose_pk3,
                    tip="Add the paks that hold the maps you want to see, plus the game's own\n(Pak0.pk3 ... Pak5.pk3) for their textures and models.\nLater paks override earlier ones.\n(Ctrl+O)").pack(side="right")
        self._search_var = tk.StringVar()
        self._search_hint = ttk.Label(sr, text="⌕", style="PanelDim.TLabel"); self._search_hint.pack(side="right", padx=(6, 10))
        self._search = ttk.Entry(sr, textvariable=self._search_var)
        self._search.pack(side="left", fill="x", expand=True)
        self._tip(self._search, "Filter the tree by name (e.g. 'mohdm', 'obj', '.bsp').\nCtrl+F focuses.\nEsc clears (only while the search bar is focused).")
        self._search.bind("<KeyRelease>", self._on_search)
        self._search.bind("<Escape>", lambda e: (self._search_var.set(""), self._rebuild_tree(), self._tree.focus_set()))
        treewrap = ttk.Frame(left, style="Panel.TFrame"); treewrap.pack(fill="both", expand=True, padx=6, pady=(0, 8))
        self._tree = ttk.Treeview(treewrap, show="tree", selectmode="extended")
        tsb = ttk.Scrollbar(treewrap, command=self._tree.yview); self._tree.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y"); self._tree.pack(side="left", fill="both", expand=True)
        self._retheme_tree_tags()
        self._tree.bind("<Double-1>", self._on_tree_activate)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Return>", self._on_tree_enter)
        self._tree.bind("<BackSpace>", self._on_tree_backspace)
        self._tree.bind("<Button-3>", self._show_pak_menu)
        self._tree.bind("<Button-1>", self._on_tree_click, add="+")
        self._tree.bind("<Motion>", self._on_tree_motion, add="+")
        self._tree.bind("<Leave>", lambda e: self._hide_treetip(), add="+")
        self._dragout = None; self._dragout_live = False; self._dragout_xy = (0, 0)
        self._tree.bind("<ButtonPress-1>", self._dragout_press, add="+")
        self._tree.bind("<B1-Motion>", self._dragout_motion, add="+")
        self._tree.bind("<ButtonRelease-1>", self._dragout_release, add="+")

        upper = ttk.Frame(rightside, style="Panel.TFrame")
        self._viewpane = ttk.Frame(upper, style="Panel.TFrame")
        self._viewpane.pack(fill="both", expand=True)
        _ph = ("3D map viewer\n\nadd your .pk3 paks, then pick a map in the tree\n(maps / dm, obj ...),"
               "\nor drag a .bsp / .map / .bak onto this window,\nthen Open Viewer")
        if ML.WEBVIEW2 is None:
            _ph += ("\n\nembedded view unavailable - maps open in your browser."
                    + (("\n(" + ML._WEBVIEW_ERR[:80] + ")") if ML._WEBVIEW_ERR else "")
                    + "\nto enable:  pip install pythonnet pywebview==4.4.1 tkwebview2")
        self._view_placeholder = ttk.Label(self._viewpane, text=_ph, style="PanelDim.TLabel",
                                           justify="center", anchor="center")
        self._view_placeholder.pack(fill="both", expand=True)

        lf = ttk.Frame(bottomrow, style="Panel.TFrame")
        self._outlab = ttk.Label(lf, text="Output", style="PanelDim.TLabel"); self._outlab.pack(anchor="w", padx=8, pady=(6, 0))
        logwrap = ttk.Frame(lf, style="Panel.TFrame"); logwrap.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        self._log = tk.Text(logwrap, bg=ML.PANEL, fg=ML.TXT, insertbackground=ML.TXT, font=ML.FONT_SMALL, relief="flat",
                            height=8, state="disabled", wrap="word", highlightbackground=ML.LINE, highlightthickness=1)
        sb = ttk.Scrollbar(logwrap, command=self._log.yview); self._log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); self._log.pack(side="left", fill="both", expand=True)
        self._log.tag_config("ok", foreground=ML.ACCENT); self._log.tag_config("err", foreground=ML.ERR_C)
        self._log.tag_config("dim", foreground=ML.DIM); self._log.tag_config("note", foreground=ML.WARN_C)
        self._log.bind("<Button-3>", self._show_log_menu)
        self._log.bind("<Button-1>", lambda e: self._log.focus_set(), add="+")
        self._log.bind("<Escape>", self._cancel_build)
        self._tip(self._log, "Build / decompile log.\nRight-click to copy or clear.\nEscape to cancel loading / building.")

        # Map details: name, counts, then the entity breakdown (as MOHRadiant's Map Info).
        # one scrollable column: title, stats, Rebuild / Browser / .map, then the list (a small
        # pane scrolls as a whole, so the buttons and the scrollbar never get squeezed out)
        info = ML.make_info_pane(self, bottomrow, "No map loaded",
                                 "Entity breakdown of the last-built map (like MOHRadiant's Map Info).\nSelect + copy freely.\nRight-click for Copy all / Select all / Open in Text Editor.")
        self._retheme_tag_text()

        outer.add(left, minsize=180, width=300, stretch="never")
        outer.add(rightside, minsize=340, stretch="always")
        rightside.add(upper, minsize=160, stretch="always")
        rightside.add(bottomrow, minsize=ML.BOTTOM_ROW_MIN, height=ML.BOTTOM_ROW_HEIGHT, stretch="never")
        bottomrow.add(lf, minsize=220, stretch="always")
        bottomrow.add(info, minsize=200, width=ML.INFO_PANE_WIDTH, stretch="never")
        self.after(160, self._restore_panes); self.after(480, self._restore_panes)

        stat = ttk.Frame(self, style="Panel.TFrame"); stat.pack(fill="x", side="bottom")
        self._lines.append(tk.Frame(self, bg=ML.LINE, height=1)); self._lines[-1].pack(fill="x", side="bottom")
        self._status_l = ttk.Label(stat, text="Ready", style="Status.TLabel"); self._status_l.pack(side="left")
        self._status_r = ttk.Label(stat, text=ML.VERSION_LABEL, style="Status.TLabel"); self._status_r.pack(side="right")

    def _retheme_tree_tags(self):
        """Tree colours by file kind, for the current theme."""
        self._tree.tag_configure("folder", foreground=ML.TXT)
        self._tree.tag_configure("bsp", foreground=ML.ACCENT)       # compiled maps
        self._tree.tag_configure("map", foreground=ML.ORIGIN)       # map sources
        self._tree.tag_configure("scr", foreground=ML.TXT)          # scripts
        self._tree.tag_configure("bin", foreground=ML.DIM)          # other map data

    def _retheme_tag_text(self):
        """Map-details panel colours for the current theme."""
        t = self._tag_text
        t.configure(bg=ML.PANEL, fg=ML.TXT, insertbackground=ML.TXT, selectbackground=ML.SEL_BG, selectforeground=ML.TXT)
        cv = getattr(self, "_info_canvas", None)
        if cv is not None: cv.configure(bg=ML.PANEL)
        for tg, cl in (("thead", ML.DIM), ("tname", ML.TXT), ("tcount", ML.ACCENT), ("tdim", ML.DIM),
                       ("terr", ML.ERR_C), ("ttl", ML.ACCENT)):
            t.tag_config(tg, foreground=cl)

    def _treetip_text(self, row):
        """Tooltip for a tree row: what double-click does with it."""
        if row in self._tree_entry:
            kind = self._tree_kind.get(row)
            if kind in ("bsp", "map"):
                return "Double-click / Enter opens the map in the viewer (a .bsp is decompiled to .map first)"
            if kind in TEXT_KINDS:
                return "Double-click / Enter opens it in your Text Editor"
            if os.path.splitext(self._tree_entry[row].lower())[1] in (".pth", ".dcl", ".lin"):
                return "Map data the viewer shows with its map (AI paths, decals, leak trail): open the .bsp"
            return "Compiled map data the viewer doesn't show yet"
        return "Backspace goes up a folder - Enter opens selected folder"

    def _tag_open_editor(self):
        """Map-details panel > Open in Text Editor: saves the text to the workspace first."""
        txt = self._tag_text.get("1.0", "end-1c").strip()
        if not txt:
            self._log_line("No map details to open yet - build a map first.", "dim"); return
        try:
            base = os.path.join(self._tmp or tempfile.gettempdir(), "map_info.txt")
            MC.atomic_write_text(base, txt + "\n")
        except Exception as e:
            MC.swallowed()
            self._log_line(f"Could not write the map details: {e}", "err"); return
        self._launch_with("text_editor", "text editor", "Text Editor", base)

    # ------------------------------------------------- output folders ---
    def _viewer_html_name(self, map_path):
        """mohdm6.bsp -> mohdm6_bsp_view.html (mohaa_map_view.page_name)."""
        stem, ext = os.path.splitext(os.path.basename(map_path))
        return f"{stem}_{(ext[1:] or 'map').lower()}_view.html"

    def _entry_subdir(self, entry):
        """maps/dm/mohdm1.bsp -> dm (the output folder IS the maps folder). Folder names
        are lower-cased so maps/DM and maps/dm land together."""
        if not entry: return ""
        parts = [p.lower() for p in os.path.dirname(entry).replace("\\", "/").split("/") if p]
        if parts and parts[0] == "maps": parts = parts[1:]
        return os.path.join(*parts) if parts else ""

    def _standalone_dir(self):
        """Pages for files opened from disk: a 'maps_standalone' folder next to the maps
        output folder (the Model Viewer's 'standalone' folder stays its own)."""
        return os.path.join(os.path.dirname(os.path.abspath(self._outdir)), "maps_standalone")

    def _unsafe_to_wipe(self, d):
        """Why folder d must not be cleared (a drive root, the home folder, or not one of
        this program's 'maps' folders), or None when it is safe."""
        try: d = os.path.abspath(d)
        except Exception: MC.swallowed(); return "unresolvable path"
        leaf = os.path.basename(d.rstrip(os.sep))
        if not leaf or os.path.dirname(d.rstrip(os.sep)) == d.rstrip(os.sep): return "a drive/filesystem root"
        home = os.path.abspath(os.path.expanduser("~"))
        if os.path.normcase(d) == os.path.normcase(home): return "your home folder"
        if os.path.normcase(leaf) not in ("maps", "maps_standalone"):
            return "not a 'maps' or 'maps_standalone' folder built by this program"
        return None

    @staticmethod
    def _is_built_file(path):
        """Only files this program wrote: <stem>_bsp_view.html / <stem>_map_view.html pages
        and .map files that start with the decompiler's own first line. A 'maps' folder is
        a common name in a game install, so anything else in it is never touched."""
        fl = os.path.basename(path).lower()
        if fl.endswith(("_bsp_view.html", "_map_view.html", "_bak_view.html")): return True
        return fl.endswith(".map") and MB is not None and MB.is_decompiled_map(path)

    def _built_scan(self):
        """(built files, [], total bytes) under the output folders, for Clear built maps.
        The folder list is empty: folders are only removed once emptied."""
        files = []; dirs = []; nb = 0
        for root in self._built_roots():
            for dp, dn, fn in os.walk(root):
                for f in fn:
                    fp = os.path.join(dp, f)
                    if self._is_built_file(fp):
                        files.append(fp)
                        try: nb += os.path.getsize(fp)
                        except OSError: MC.swallowed()
        return files, dirs, nb

    def _built_any(self):
        """Is there anything for Clear built maps to delete? (greys the menu item)"""
        for root in self._built_roots():
            for dp, _dn, fn in os.walk(root):
                if any(self._is_built_file(os.path.join(dp, f)) for f in fn): return True
        return False

    def _clear_built_models(self):
        """Delete the pages and decompiled .map files this program built, then any folders
        left empty. Nothing else in the output folders is touched (unlike the Model Viewer,
        which wipes its own 'models' folder whole)."""
        files, _dirs, nb = self._built_scan()
        roots = self._built_roots()
        if not roots or not files:
            self._log_line("Clear built maps: nothing to clear.", "dim"); return
        lines = [("Clear built maps", "title"),
                 ("Delete every map page and decompiled .map this program built", "body"),
                 ("in the folder(s) below? Other files there are left alone.", "body"),
                 ("", "dim")]
        for r in roots: lines.append(("    " + r, "dim"))
        lines += [("", "dim"),
                  ("%d built viewer page(s) and decompiled .map file(s) - %s total."
                   % (len(files), self._fmt_bytes(nb)), "dim"),
                  ("", "dim"),
                  ("The 3D viewer will close and return to the start page.", "dim")]
        if not self._confirm_dialog("Clear built maps", lines, ok_text="Delete"): return
        self._close_viewer()
        self._last_build = None
        try: self._path_var.set("")
        except Exception: MC.swallowed()
        n = 0; failed = 0
        for root in roots:
            why = self._unsafe_to_wipe(root)
            if why:
                self._log_line("  refused to clear %s - %s" % (root, why), "err"); continue
            for fp in files:
                if os.path.normcase(os.path.abspath(fp)).startswith(os.path.normcase(root) + os.sep):
                    try: os.remove(fp); n += 1
                    except OSError: failed += 1
            # folders left empty (deepest first), the output folder itself included
            for dp, _dn, _fn in sorted(os.walk(root), key=lambda w: -len(w[0])):
                try: os.rmdir(dp)
                except OSError: MC.swallowed()
        if failed: self._log_line("  %d file(s) could not be deleted (open in another program?)" % failed, "err")
        self._log_line("Cleared built maps: %d file(s) deleted, %s freed." % (n, self._fmt_bytes(nb)), "ok")

    def _temp_dirs(self):
        """This program's workspace folders in the system temp folder."""
        try: base = tempfile.gettempdir()
        except Exception: MC.swallowed(); return []
        try:
            return [d for d in sorted(glob.glob(os.path.join(glob.escape(base), TEMP_PREFIX + "*"))) if os.path.isdir(d)]
        except Exception:
            MC.swallowed()
            return []

    def _own_pycache(self):
        """bin/__pycache__ if it holds this project's compiled scripts, else None."""
        pc = os.path.join(HERE, "__pycache__")
        if not os.path.isdir(pc): return None
        try: names = os.listdir(pc)
        except OSError: MC.swallowed(); return None
        ours = ("mohaa_map_view", "mohaa_map_page", "mohaa_bsp", "mohaa_entdefs", "mohaa_map_launcher",
                "mohaa_view", "mohaa_textures", "mohaa_launcher")
        return pc if any(any(nm.startswith(o + ".") for o in ours) for nm in names) else None

    def _clear_temp_files(self):
        """File > Clear %temp% files: delete the workspaces (the current one is recreated
        and the paks re-indexed) and the compiled .pyc files."""
        dirs = self._temp_dirs()
        pyc = self._own_pycache()
        if not dirs and not pyc:
            self._log_line("Clear %temp% files: nothing to clear.", "dim"); return
        nb = sum(self._dir_size(d) for d in dirs) + (self._dir_size(pyc) if pyc else 0)
        live = os.path.abspath(self._tmp) if self._tmp else None
        has_live = bool(live) and any(os.path.abspath(d) == live for d in dirs)
        lines = [("Clear %temp% files", "title"),
                 ("Delete %d workspace folder(s)  (%s)  from:" % (len(dirs), self._fmt_bytes(nb)), "body"),
                 ("", "dim"), ("    " + tempfile.gettempdir(), "dim"), ("", "dim"),
                 ("These are the %s* folders holding extracted maps and the" % TEMP_PREFIX, "dim"),
                 ("shader / texture caches that make later builds faster.", "dim")]
        if pyc:
            lines += [("", "dim"), ("Also clears this program's __pycache__ (compiled .pyc), for a", "dim"),
                      ("clean reinstall state - Python rebuilds it on next launch.", "dim")]
        if has_live:
            lines += [("", "dim"), ("One is the CURRENT session's workspace: clearing it re-indexes", "dim"),
                      ("the loaded paks.", "dim")]
        if not self._confirm_dialog("Clear %temp% files", lines, ok_text="Delete"): return
        n = 0
        for d in dirs:
            if live and os.path.abspath(d) == live: continue
            shutil.rmtree(d, ignore_errors=True)
            if not os.path.isdir(d): n += 1
        if has_live:
            if self._pk3_paths: self._reload_all()
            else:
                shutil.rmtree(live, ignore_errors=True)
                try: self._tmp = tempfile.mkdtemp(prefix=TEMP_PREFIX)
                except Exception: MC.swallowed(); self._tmp = None
            n += 1
        pn = 0
        if pyc:
            shutil.rmtree(pyc, ignore_errors=True)
            if not os.path.isdir(pyc): pn = 1
        self._log_line("Cleared %%temp%% files: %d workspace folder(s)%s, %s freed."
                       % (n, (" + __pycache__" if pn else ""), self._fmt_bytes(nb)), "ok")

    # ------------------------------------------------------------- paks ---
    def _pak_label(self):
        """'Pak0.pk3  +6 more  /  maps' above the tree."""
        n = len(self._pk3_paths)
        head = os.path.basename(self._pk3_paths[0]) if n else ""
        return (head + (f"  +{n-1} more" if n > 1 else "") + "  /  maps") if n else "No .pk3 loaded"

    def _add_pk3s(self, paths):
        """Add paks (each checked to open as a zip), save the list and reload the tree."""
        added = 0
        for path in paths:
            if not os.path.exists(path): continue
            try: zipfile.ZipFile(path).close()
            except Exception as e: MC.swallowed(); self._log_line(f"Could not open {os.path.basename(path)}: {e}", "err"); continue
            if path not in self._pk3_paths: self._pk3_paths.append(path); added += 1
        if not added and paths: return
        self._cfg["pk3s"] = self._pk3_paths if self._remember.get() else []
        self._save_config(); self._paks_changed()
        self._pk3_label.configure(text=self._pak_label())
        self._reload_all()
        self._log_line(f"Loaded {len(self._pk3_paths)} pak(s): " + ", ".join(os.path.basename(p) for p in self._pk3_paths), "ok")
        self._set_status("Paks loaded", f"{len(self._pk3_paths)} pak(s)")

    def _remove_pak(self, path):
        """Pak menu > Remove a pak."""
        if path in self._pk3_paths:
            self._pk3_paths.remove(path)
            self._cfg["pk3s"] = self._pk3_paths if self._remember.get() else []
            self._save_config(); self._paks_changed()
            self._pk3_label.configure(text=self._pak_label())
            self._log_line(f"Removed {os.path.basename(path)}", "dim")
            if self._pk3_paths: self._reload_all()
            else: self._clear_pk3s()

    def _reload_all(self):
        """Rebuild the maps tree from every loaded pak, start a fresh temp workspace, and
        index the shaders and entity definitions in the background."""
        self._populate_tree(self._pk3_paths)
        if self._tmp and os.path.isdir(self._tmp): shutil.rmtree(self._tmp, ignore_errors=True)
        self._tmp = tempfile.mkdtemp(prefix=TEMP_PREFIX)
        self._index_cache = os.path.join(self._tmp, "cache")
        self._tex_ready = False; self._tex_gen += 1
        self._set_status("Indexing shaders and entities...")
        threading.Thread(target=self._prepare_indexes, args=(self._tex_gen, list(self._pk3_paths)), daemon=True).start()

    def _prepare_indexes(self, gen, paks):
        """Index the paks once (shaders, entity definitions), cached in the workspace so each
        map build starts straight away. The builder reads the same cache."""
        if MTX is None:
            self._log_q.put(("dim", "(mohaa_textures.py not found - maps will draw without textures)")); return
        try:
            import mohaa_map_view as MMV
            vfs = MTX.Vfs(paks)
            shaders, ed = MMV.build_indexes(vfs, paks, self._index_cache, say=lambda m: None)
            if gen != self._tex_gen: return
            old = self._vfs
            self._vfs = vfs; self._SH = shaders; self._ED = ed; self._tex_ready = True
            if old is not None and hasattr(old, "close"):
                try: old.close()
                except Exception: MC.swallowed()
            nmaps = sum(1 for _k, kind in self._all_files if kind in ("bsp", "map"))
            self._log_q.put(("ok", f"Ready: {len(shaders)} shaders, {len(ed.defs)} entity classes indexed; {nmaps} map(s) in the tree."))
            self._log_q.put(("status", "Ready"))
        except Exception as e:
            MC.swallowed()
            self._log_q.put(("err", f"Indexing failed: {e}"))

    def _populate_tree(self, paks):
        """Every file under maps/ in the loaded paks (later paks override earlier ones)."""
        files = {}
        for p in paks:
            try: names = zipfile.ZipFile(p).namelist()
            except Exception: MC.swallowed(); continue
            for n in names:
                nl = n.lower()
                if not nl.startswith("maps/") or n.endswith("/"): continue
                kind = MAP_KINDS.get(os.path.splitext(nl)[1])
                if kind: files[nl] = (n, kind)
        self._all_files = [(real, kind) for _k, (real, kind) in files.items()]
        self._rebuild_tree()
        nb = sum(1 for _r, k in self._all_files if k == "bsp")
        nm = sum(1 for _r, k in self._all_files if k == "map")
        self._log_line(f"{nb} .bsp and {nm} .map file(s) under maps/ (combined from {len(paks)} pak(s)).", "dim")

    def _rebuild_tree(self):
        """The maps tree, filtered by the search box. Folders are matched without regard
        to case (paks mix maps/DM and maps/dm)."""
        self._tree.delete(*self._tree.get_children()); self._tree_entry.clear(); self._tree_kind.clear()
        q = (self._search_var.get() or "").strip().lower() if hasattr(self, "_search_var") else ""
        files = [(k, kind) for (k, kind) in self._all_files if (not q or q in k.lower())]
        node = {"maps": self._tree.insert("", "end", text="maps", open=True, tags=("folder",))}
        open_all = bool(q)

        def folder(path_l):
            if path_l in node: return node[path_l]
            parent = folder(path_l.rsplit("/", 1)[0]) if "/" in path_l else node["maps"]
            node[path_l] = self._tree.insert(parent, "end", text=path_l.rsplit("/", 1)[-1], open=open_all, tags=("folder",))
            return node[path_l]
        order = {"bsp": 0, "map": 1, "scr": 2, "bin": 3}
        # folders first (sorted), then files by kind and name, as the Model Viewer does
        for d in sorted({k.lower().rsplit("/", 1)[0] for k, _ in files if "/" in k}):
            folder(d)
        for k, kind in sorted(files, key=lambda kv: (order.get(kv[1], 9), kv[0].lower())):
            parent = folder(k.lower().rsplit("/", 1)[0]) if "/" in k else node["maps"]
            iid = self._tree.insert(parent, "end", text=k.rsplit("/", 1)[-1], tags=(kind,))
            self._tree_entry[iid] = k; self._tree_kind[iid] = kind
        if q: self._set_status(f"Filter: '{q}' - {len(files)} match(es)")
        elif self._all_files: self._set_status("Ready")

    def _show_pak_menu(self, e):
        """Right-click menu for the tree: a map, a script, a folder, several maps at once,
        or the paks."""
        iid = ""
        try:
            if e.widget is self._tree: iid = self._tree.identify_row(e.y)
        except Exception: MC.swallowed(); iid = ""
        sel = self._tree.selection()
        if iid:
            if not (iid in sel and len(sel) > 1):
                self._tree.selection_set(iid); sel = (iid,)
            self._tree.focus(iid)
        if iid and len(sel) > 1:
            ents = self._collect_entries(sel); n = len(ents)
            items = [_mi(f"Build {n} maps in selection (don't open anything)",
                         lambda ss=tuple(sel): self._build_selected(ss), state=("normal" if n else "disabled")),
                     _mi(f"Open {n} maps in browser tab windows (HTML)",
                         lambda ss=tuple(sel): self._open_selected(ss), state=("normal" if n else "disabled")),
                     _MSEP,
                     _mi("Expand selected folders", lambda ss=tuple(sel): self._expand_selected(ss, True)),
                     _mi("Collapse selected folders", lambda ss=tuple(sel): self._expand_selected(ss, False))]
            self._post_menu(items, e.x_root, e.y_root, event=e); return
        entry = self._tree_entry.get(iid) if iid else None
        if entry:
            base = os.path.basename(entry); kind = self._tree_kind.get(iid)
            if kind in ("bsp", "map"):
                items = [_mi(f"Open {base} in viewer", lambda: self._ctx_open(entry)),
                         _mi("Open HTML in browser tab window", lambda: self._open_external(entry)),
                         _mi("Build only (don't open anything)", lambda: self._ctx_open(entry, no_open=True)),
                         _mi("Rebuild in viewer (ignore saved HTML)", lambda: self._ctx_open(entry, force=True)),
                         _MSEP]
                if kind == "bsp":
                    items.append(_mi("Decompile to .map only", lambda: self._decompile_only(entry)))
                    items.append(_mi("Decompile and open the .map in Text Editor", lambda: self._decompile_only(entry, edit=True)))
                else:
                    items.append(_mi("Open in Text Editor", lambda: self._open_entry_with(entry, "text_editor", "text editor", "Text Editor")))
            elif kind in TEXT_KINDS:
                items = [_mi(f"Open {base} in Text Editor", lambda: self._open_entry_with(entry, "text_editor", "text editor", "Text Editor"))]
            else:
                items = [_mi("(compiled map data - nothing to show yet)", state="disabled")]
        elif iid:
            items = [_mi("Expand this folder", lambda: self._expand_subtree(iid, True)),
                     _mi("Collapse this folder", lambda: self._expand_subtree(iid, False)),
                     _MSEP,
                     _mi("Build all maps in this folder (don't open anything)", lambda: self._build_all_in_folder(iid))]
        else:
            items = self._menu_items_pak()
        self._post_menu(items, e.x_root, e.y_root, event=e)

    def _entries_under(self, iid):
        """Every .bsp / .map under a tree item (batch builds skip scripts and data files)."""
        out = []

        def rec(item):
            if item in self._tree_entry and self._tree_kind.get(item) in ("bsp", "map"):
                out.append(self._tree_entry[item])
            for ch in self._tree.get_children(item): rec(ch)
        rec(iid)
        return out

    # ----------------------------------------------------------- opening ---
    def _kind_of(self, path):
        """'bsp', 'map', 'scr', 'bin' or None, from the file extension."""
        return MAP_KINDS.get(os.path.splitext(path.lower())[1])

    def _open_pk3_model(self, entry, loose_path=None):
        """Open a tree entry: maps go to the viewer, scripts to the text editor."""
        kind = self._kind_of(entry)
        if kind in TEXT_KINDS and loose_path is None:
            self._open_entry_with(entry, "text_editor", "text editor", "Text Editor"); self._batch_signal(); return
        if kind not in ("bsp", "map"):
            self._log_line(f"{os.path.basename(entry)}: compiled map data the viewer doesn't show yet - open the .bsp instead.", "dim")
            self._batch_signal(); return
        if self._viewer_open_busy(): return
        subdir = ML.STANDALONE_SUBDIR if loose_path else self._entry_subdir(entry)
        if loose_path is None and self._reuse_ok():
            hp = os.path.join(self._outdir, subdir or "", self._viewer_html_name(entry))
            if os.path.exists(hp) and self._html_current(hp):
                self._last_subdir = subdir; self._open_cached(hp, entry, subdir); return
        if not self._pk3_paths or not self._tmp:
            self._log_line("Load a .pk3 first.", "err"); return
        if MTX is not None and (self._vfs is None or not self._tex_ready):
            self._queue_open_until_indexed(entry); return
        self._log_line(f"Extracting {entry} ...", "dim"); self._set_status(f"Extracting {os.path.basename(entry)}...")
        self._building_name = os.path.basename(entry)
        if self._auto_open.get() and not self._run_opts.get("no_open") and not self._run_opts.get("external"):
            self._opening_view = True
        bgen = self._build_gen

        def work():
            try:
                target = None
                for p in self._pk3_paths:                       # later paks override earlier
                    if bgen != self._build_gen: return
                    try: zf = zipfile.ZipFile(p)
                    except Exception: MC.swallowed(); continue
                    for n in zf.namelist():
                        if n.lower() == entry.lower() and not n.endswith("/"):
                            target = self._extract_one(zf, n, force=True)
                    zf.close()
                if not target:
                    self._log_q.put(("err", "Could not find that map inside the loaded paks")); return
                if bgen != self._build_gen: return
                self._vpath_for[target] = entry
                self._log_q.put(("load", (target, None, None, None, subdir)))
            except Exception as e:
                MC.swallowed()
                self._log_q.put(("err", f"Extract failed: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def _decompile_only(self, entry, edit=False):
        """Right-click > Decompile: write the .map into the output folder without building
        a page (and optionally open it in the text editor)."""
        if not self._pk3_paths or not self._tmp:
            self._log_line("Load a .pk3 first.", "err"); return
        subdir = self._entry_subdir(entry)

        def work():
            try:
                target = None
                for p in self._pk3_paths:
                    try: zf = zipfile.ZipFile(p)
                    except Exception: MC.swallowed(); continue
                    for n in zf.namelist():
                        if n.lower() == entry.lower() and not n.endswith("/"):
                            target = self._extract_one(zf, n, force=True)
                    zf.close()
                if not target:
                    self._log_q.put(("err", "Could not find that map inside the loaded paks")); return
                outdir = os.path.join(self._outdir, subdir) if self._outdir_on.get() else os.path.dirname(target)
                cmd = self._builder_cmd(target, entry, outdir) + ["--decompile-only"]
                self._log_q.put(("dim", f"Decompiling {os.path.basename(entry)} ..."))
                env = MC.child_env()
                p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=600, env=env, **ML.NOWIN)
                mp = None
                for ln in (p.stdout or "").splitlines():
                    self._log_q.put(("err" if ln.lstrip().startswith("!") else "dim", ln))
                    s = ln.strip()
                    if s.startswith("wrote ") and s.lower().endswith(".map"): mp = s[6:]
                if p.returncode != 0 or not mp:
                    self._log_q.put(("err", (p.stderr or "").strip()[-400:] or f"Exited with code {p.returncode}")); return
                self._log_q.put(("ok", f"Decompiled to {mp}"))
                if edit and os.path.exists(mp): self._launch_with("text_editor", "text editor", "Text Editor", mp)
            except Exception as e:
                MC.swallowed()
                self._log_q.put(("err", f"Decompile failed: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def _browse(self):
        """Pick a loose .bsp / .map / .bak; returns it ("" on Cancel). Browse... opens it at
        once (_browse_and_run)."""
        p = filedialog.askopenfilename(title="Select a MOHAA map (.bsp, .map or .bak)",
                                       filetypes=[("MOHAA map", "*.bsp *.map *.bak"), ("Compiled map", "*.bsp"),
                                                  ("Map source", "*.map"), ("MOHRadiant backup", "*.bak"),
                                                  ("All files", "*.*")])
        if p: self._path_var.set(p)
        return p or ""

    def _run(self):
        """Open Viewer: build what the path bar names (a pak map or a file on disk)."""
        path = self._path_var.get().strip().strip('"')
        if path.startswith("pk3://"): self._open_pk3_model(path[len("pk3://"):]); return
        if path.startswith("pk3 map:") and self._last_build:
            self._load(*self._last_build); return
        if not path: self._log_line("No file selected.", "err"); return
        if not path.lower().endswith(MAP_EXTS):
            self._log_line("File must be a .bsp, .map or .bak", "err"); return
        if not os.path.exists(path): self._log_line(f"Not found: {path}", "err"); return
        if not self._pyexe: self._log_line("Python not found on PATH.", "err"); return
        if not os.path.exists(MAP_BUILDER): self._log_line("mohaa_map_view.py not found next to the launcher.", "err"); return
        self._load(path)

    def _load(self, path, animroot=None, manifest=None, emittex=None, subdir=None, _cont=False):
        """Build (or reuse) the page for a map file on disk. Pak entries arrive here once
        extracted (_cont=True); loose files from Browse, drag-drop or Recent come straight in."""
        if not _cont and self._viewer_open_busy(): return
        if not path.lower().endswith(MAP_EXTS):
            self._log_line(f"{os.path.basename(path)}: only .bsp, .map and .bak files open in the map viewer.", "err"); return
        if (not _cont and subdir is None and os.path.isfile(path)
                and not (self._tmp and path.startswith(self._tmp))):
            subdir = ML.STANDALONE_SUBDIR
        self._last_build = (path, None, None, None, subdir)
        self._last_subdir = subdir
        disp = ("pk3 map: " + os.path.basename(path)) if (self._tmp and path.startswith(self._tmp)) else path
        self._path_var.set(disp)
        self._push_recent(path)
        if self._reuse_ok():
            hp = self._html_out_path(path, subdir)
            if os.path.exists(hp) and self._html_current(hp):
                self._opening_view = False
                self._open_cached(hp, path, subdir); return
        self._log_line(f"Building {os.path.basename(path)} ...", "dim")
        self._set_status(f"Building viewer for {os.path.basename(path)}...")
        self._building_name = os.path.basename(path)
        if self._auto_open.get() and not self._run_opts.get("no_open") and not self._run_opts.get("external"):
            self._opening_view = True
        threading.Thread(target=self._worker, args=(path, subdir, self._build_gen), daemon=True).start()

    def _builder_cmd(self, path, vpath, outdir):
        """The mohaa_map_view.py command line for one map. The pak list goes in a file
        in the workspace, so a long list can't overflow the command line."""
        cmd = [self._pyexe, MAP_BUILDER, path]
        if self._pk3_paths and self._tmp:
            lst = os.path.join(self._tmp, "paks.txt")
            try:
                MC.atomic_write_text(lst, "\n".join(self._pk3_paths) + "\n")
                cmd.append("--paks=" + lst)
            except OSError:
                for p in self._pk3_paths: cmd.append("--pak=" + p)
        if vpath: cmd.append("--vfs=" + vpath)
        if outdir: cmd.append("--outdir=" + outdir)
        if self._index_cache: cmd.append("--cache=" + self._index_cache)
        try: cmd.append("--texsize=%d" % int(self._texsize.get()))
        except (TypeError, ValueError): pass
        if not self._models_on.get(): cmd.append("--no-models")
        return cmd

    def _worker(self, path, subdir=None, bgen=None):
        """Run mohaa_map_view.py and stream its progress lines into the Output pane."""
        try:
            opts = self._run_opts; self._run_opts = {}
            if bgen is not None and bgen != self._build_gen: return
            vpath = self._vpath_for.get(path) or os.path.basename(path)
            if self._outdir_on.get():
                outdir = self._standalone_dir() if subdir == ML.STANDALONE_SUBDIR else (
                    os.path.join(self._outdir, subdir) if subdir else self._outdir)
            else:
                outdir = os.path.dirname(os.path.abspath(path))
            cmd = self._builder_cmd(path, vpath, outdir)
            if opts.get("theme") in ("light", "dark"): cmd.append("--theme=" + opts["theme"])
            cmd.append("--no-open")
            ext = bool(opts.get("external"))
            will_open = ext or (self._auto_open.get() and not opts.get("no_open"))
            env = MC.child_env()
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 encoding="utf-8", errors="replace", bufsize=1, env=env, **ML.NOWIN)
            self._proc = p
            out_lines = []
            try:
                for line in p.stdout:
                    line = line.rstrip("\n")
                    out_lines.append(line)
                    if bgen is not None and bgen != self._build_gen: break
                    # "!" lines in red, as warnings: the build carries on ("err" would end it)
                    self._log_q.put(("warn" if line.lstrip().startswith("!") else "dim", "  " + line))
                err = p.stderr.read()
                p.wait(timeout=900)
            finally:
                self._proc = None
            if bgen is not None and bgen != self._build_gen: return
            if (err or "").strip():
                tail = err.strip().splitlines()[-12:]
                self._log_q.put(("err", "\n".join(tail)))
            if p.returncode == 0:
                self._log_q.put(("ok", "Done - viewer opened." if will_open else "Done - viewer page written (not opened)."))
                self._log_q.put(("parse", (path, "\n".join(out_lines))))
                if will_open: self._log_q.put(("openext" if ext else "openhtml", (path, subdir)))
                self._log_q.put(("status", "Done"))
            else:
                self._log_q.put(("err", f"Exited with code {p.returncode}"))
        except Exception as e:
            MC.swallowed()
            self._log_q.put(("err", str(e)))
        finally:
            self._log_q.put(("done", None))
            self._log_q.put(("batchnext", None))

    def _html_current(self, hp):
        """Reuse a built page only if it is newer than every script that builds it and its
        baked page revision is current."""
        try:
            srcs = [os.path.abspath(__file__), MAP_BUILDER] + [os.path.join(HERE, n) for n in
                    ("mohaa_map_page.py", "mohaa_bsp.py", "mohaa_entdefs.py", "mohaa_textures.py", "mohaa_view.py")]
            newest = max((os.path.getmtime(s) for s in srcs if os.path.exists(s)), default=0)
            if os.path.getmtime(hp) < newest:
                key = (hp, os.path.getmtime(hp))   # a pak map is checked twice per open: say it once
                if key not in self._stale_noted:
                    self._stale_noted.add(key)
                    self._log_line(f"({os.path.basename(hp)} is older than the current scripts - rebuilding)", "dim")
                return False
            with open(hp, "r", encoding="utf-8", errors="ignore") as f: head = f.read(400)
            m = re.search(r"mohaa-map-viewer-rev:(\d+)", head)
            if m and int(m.group(1)) >= MAP_VIEWER_REV_REQUIRED:
                # the loose files it was built from (the map opened from disk, its .scr,
                # .dcl, .lin, .pth): one that changed, appeared or went means a rebuild
                for dp, mt in self._read_page_info(hp).get("deps") or ():
                    now = round(os.path.getmtime(dp), 3) if os.path.isfile(dp) else 0
                    if abs(now - (mt or 0)) > 0.002:
                        self._log_line(f"({os.path.basename(dp)} {'changed' if now and mt else 'appeared' if now else 'is gone'}"
                                       f" since {os.path.basename(hp)} was built - rebuilding)", "dim")
                        return False
                return True
            self._log_line(f"({os.path.basename(hp)} is from an older viewer build - rebuilding)", "dim")
            return False
        except Exception:
            MC.swallowed()
            return False

    def _open_file(self, path):
        """Show a built page in the embedded pane (with #embed&theme=... so it starts in the
        launcher's layout and theme), else in the default browser."""
        import pathlib
        base = pathlib.Path(os.path.abspath(path)).as_uri()
        if self._ensure_webview():
            try:
                url = base + "#embed&theme=" + ("light" if self._theme == "light" else "dark")
                self._webview.load_url(url); self._embed_url = url
                self._set_status(f"Viewing {os.path.basename(path)}")
                self.after(700, self._embed_merge_ui); self.after(2200, self._embed_merge_ui)
                return
            except Exception as e:
                MC.swallowed()
                self._log_line(f"(embed failed: {e}; opening in browser)", "dim")
        self._open_in_browser(path)

    # -------------------------------------------------- map details panel ---
    def _clear_info(self):
        """Empty the map-details panel."""
        self._last_info = None
        try: self._info_title.configure(text="No map loaded", foreground=ML.DIM)
        except Exception: MC.swallowed()
        try: self._info_stats.configure(text="")
        except Exception: MC.swallowed()
        try:
            t = self._tag_text
            t.configure(state="normal"); t.delete("1.0", "end"); t.configure(state="disabled")
        except Exception: MC.swallowed()
        try:
            for w in self._reopen_bar.winfo_children(): w.destroy()
        except Exception: MC.swallowed()
        self._info_refit()

    @staticmethod
    def _read_page_info(html_path):
        """The summary the builder puts at the top of every page (counts, entity classes,
        missing textures)."""
        try:
            with open(html_path, encoding="utf-8", errors="ignore") as f:
                head = f.read(400000)
            m = re.search(r'<script type="application/json" id="mohaa-map-info">(.*?)</script>', head, re.S)
            return json.loads(m.group(1)) if m else {}
        except Exception:
            MC.swallowed()
            return {}

    def _update_info(self, path, stdout, html_path=None):
        """Fill the map-details panel from the page's summary block: counts, the entity
        breakdown, missing textures, and Rebuild / Browser / .map buttons."""
        if html_path is None: html_path = self._html_out_path(path)
        self._last_info = (path, stdout, html_path)
        info = self._read_page_info(html_path)
        for w in self._reopen_bar.winfo_children(): w.destroy()
        name = info.get("name") or os.path.splitext(os.path.basename(path))[0]
        self._info_title.configure(text=name, foreground=ML.ACCENT)
        stats = []
        if info:
            stats.append(f"{info.get('brushes', 0)} brushes · {info.get('entities', 0)} entities")
            extra = []
            if info.get("patches"): extra.append(f"{info['patches']} patches")
            if info.get("terrain"): extra.append(f"{info['terrain']} terrain")
            if extra: stats.append(" · ".join(extra))
            if info.get("models"): stats.append(f"{info['models']} placed models")
            if info.get("message"): stats.append('"' + info["message"] + '"')
        self._info_stats.configure(text="\n".join(stats))
        t = self._tag_text; self._retheme_tag_text()
        t.configure(state="normal"); t.delete("1.0", "end")
        if info:
            t.insert("end", "Total brushes    %d\n" % info.get("brushes", 0), "tname")
            t.insert("end", "Total entities   %d\n" % info.get("entities", 0), "tname")
            if "real" in info:
                # real: an entity number in game (1024 slots); simple: path nodes, player
                # starts, lights...; static props: drawn without an entity
                t.insert("end", "  real           %d\n" % info.get("real", 0), "terr" if info.get("real", 0) > 1024 else "tdim")
                t.insert("end", "  simple         %d\n" % info.get("simple", 0), "tdim")
                t.insert("end", "  static props   %d\n" % info.get("static", 0), "tdim")
            t.insert("end", "Net brush count  %d\n" % info.get("netBrushes", 0), "tname")
            t.insert("end", "  (brushes not in an entity)\n", "tdim")
            t.insert("end", "\nEntity breakdown\n", "thead")
            for cls, n in info.get("classes", []):
                t.insert("end", "%5d  " % n, "tcount"); t.insert("end", cls + "\n", "tname")
            miss = info.get("missing") or []
            if miss:
                t.insert("end", "\nTextures not in the loaded paks (%d)\n" % len(miss), "terr")
                for m in miss: t.insert("end", "  " + m.replace("textures/", "", 1) + "\n", "tdim")
        t.configure(state="disabled")
        if os.path.exists(html_path):
            ML.info_button(self, "rebuild", "Rebuild", self._rebuild_shown,
                           "Build this map's viewer again from its files\n(ignores the saved HTML)").pack(side="left")
            ML.info_button(self, "browser", "Browser", lambda p=html_path: self._open_in_browser(p),
                           "Open the viewer page in your external browser").pack(side="left", padx=(4, 0))
            mp = info.get("mapFile")
            if not mp and path.lower().endswith(".map"): mp = path
            if mp and os.path.exists(mp):
                ML.info_button(self, "file", ".map", lambda p=mp: self._launch_with("text_editor", "text editor", "Text Editor", p),
                               "Open the map's .map source in your Text Editor\n" + mp).pack(side="left", padx=(4, 0))
        self._info_refit()

    # ------------------------------------------------ embedded pane hooks ---
    def _poll_log(self):
        """The base class's log poll, after running what the page asked for (its messages
        arrive on the WebView2 thread; these must run on the Tk thread)."""
        reqs = getattr(self, "_page_requests", None)
        while reqs:
            fn = reqs.pop(0)
            try: fn()
            except Exception as e: MC.swallowed(); self._log_line(f"(viewer request: {e})", "err")
        super()._poll_log()

    # ------------------------------------------------ MODIFY: Save as .bsp / .map ---
    def _page_js(self, js):
        """Run a line of script in the viewer's page (on the Tk thread)."""
        try:
            if self._webview is not None and getattr(self._webview, "core", None) is not None:
                self._webview.core.ExecuteScriptAsync(js)
        except Exception: MC.swallowed()

    def _modify_source(self, req, want_bsp):
        """The bytes / text the new file starts from: the file the page was built from, else
        the map's entry in the loaded paks."""
        src = req.get("src") or ""
        if want_bsp:
            if src.lower().endswith(".bsp") and os.path.isfile(src):
                with open(src, "rb") as f: return f.read(), src
            vp = (req.get("vpath") or "").replace("\\", "/").lstrip("/")
            if vp.lower().endswith(".bsp"):
                for pk in reversed(self._pk3_paths):
                    try:
                        with zipfile.ZipFile(pk) as z:
                            for n in z.namelist():
                                if n.lower() == vp.lower(): return z.read(n), f"{os.path.basename(pk)}/{n}"
                    except Exception: MC.swallowed(); continue
            return None, None
        mp = req.get("mapFile") or (src if src.lower().endswith((".map", ".bak")) else "")
        if mp and os.path.isfile(mp):
            with open(mp, "r", encoding="latin-1", errors="replace") as f: return f.read(), mp
        return None, None

    def _modify_save(self, req):
        """The page's Save as .bsp / .map: ask where, never over the map it came from (nor
        over a file this didn't write), and write the copy with the new entities."""
        kind = "bsp" if req.get("kind") == "bsp" else "map"
        added = req.get("ents") or ""
        name = os.path.splitext(os.path.basename(req.get("vpath") or req.get("src") or "map"))[0] or "map"

        def tell(ok, msg):
            self._log_line(("  " if ok else "! ") + msg, "ok" if ok else "err")
            self._page_js("try{modSaved(%s,%s)}catch(e){}" % ("true" if ok else "false", json.dumps(msg)))
        if kind == "bsp" and not req.get("isBsp"):
            tell(False, "Save as .bsp needs a map opened from its .bsp (this one is a .map: save as .map and compile it)"); return
        data, where = self._modify_source(req, kind == "bsp")
        if data is None:
            tell(False, "the map's " + (".bsp" if kind == "bsp" else ".map") + " wasn't found to copy from (rebuild the map and try again)"); return
        src = req.get("src") or ""
        loose = os.path.isfile(src) and not (self._tmp and os.path.abspath(src).startswith(os.path.abspath(self._tmp)))
        init_dir = self._cfg.get("modify_dir") or (os.path.dirname(src) if loose else os.path.expanduser("~"))
        out = filedialog.asksaveasfilename(
            title="Save the map with the new entities as" + (" a .bsp" if kind == "bsp" else " a .map"),
            initialdir=init_dir if os.path.isdir(init_dir) else None, initialfile=name + "_mod." + kind,
            defaultextension="." + kind, filetypes=[("MOHAA " + ("compiled map" if kind == "bsp" else "map source"), "*." + kind)])
        if not out:
            self._page_js("try{modSaveCancelled()}catch(e){}"); return
        out = os.path.abspath(out)
        made = set(self._cfg.get("modify_written") or [])
        same = lambda a, b: bool(a) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(out)
        if same(src, out) or same(req.get("mapFile"), out) or same(where, out):
            tell(False, "not saved: that is the map it was opened from - pick another name"); return
        if os.path.exists(out) and os.path.normcase(out) not in made:
            tell(False, "not saved: " + os.path.basename(out) + " is already there and wasn't written by Save as - pick a new name"); return
        try:
            if kind == "bsp":
                import mohaa_bsp as MB
                sets = req.get("set") or []
                old, new, n0, n1, ne = MB.write_bsp_entities(data, added, out, src if loose else None, replace=sets)
                msg = (f"saved {os.path.basename(out)}: {ne} entities ({len(sets)} changed), info_pathnode {n0} -> {n1}; "
                       f"map_time {old!r} -> {new!r}, so the game rebuilds the AI paths")
            else:
                # the page sends the whole .map when it has it (changed entities written again)
                text = req.get("mapText") or (data.rstrip() + "\n// added in MOHAA Map Viewer's MODIFY\n" + added.strip("\n") + "\n")
                # atomic; overwriting an earlier Save-as copy keeps that copy as .bak
                MC.atomic_write_text(out, text, encoding="latin-1", errors="replace", newline="\n",
                                     backup=os.path.exists(out))
                msg = f"saved {os.path.basename(out)} with {added.count('{')} new and {len(req.get('set') or [])} changed entities"
        except Exception as e:
            MC.swallowed()
            tell(False, f"not saved: {e}"); return
        made.add(os.path.normcase(out))
        self._cfg["modify_written"] = sorted(made)[-200:]
        self._cfg["modify_dir"] = os.path.dirname(out)
        self._save_config()
        tell(True, msg)
        if kind == "bsp":
            stem = os.path.splitext(os.path.basename(out))[0]
            if stem.lower() != name.lower():
                self._log_line(f"  (a new name is a new map: the game runs maps/{stem}.scr with it, not maps/{name}.scr - "
                               f"copy or rename the script, or keep the name {name}.bsp in another folder)", "dim")

    # ------------------------------------------------ MODIFY: unsaved changes on close ---
    def _close_ask(self, info):
        """The viewer is closing (Esc past its last layer) with MODIFY's new or changed
        entities not saved: Save as .bsp / Save as .map (the viewer closes once the file is
        written), Discard changes (close now), or Cancel (stay; Esc and the window's X too)."""
        def num(k):
            try: return max(0, int(info.get(k) or 0))
            except (TypeError, ValueError): return 0
        nw, ch, is_bsp = num("new"), num("changed"), bool(info.get("isBsp"))
        parts = []
        if nw: parts.append(f"{nw} new entit{'y' if nw == 1 else 'ies'}")
        if ch: parts.append(f"{ch} changed entit{'y' if ch == 1 else 'ies'}")
        what = " and ".join(parts) or "changes"
        name = str(info.get("name") or "this map")[:80]
        choice = self._unsaved_dialog(
            "Unsaved changes",
            f"MODIFY has {what} in {name} that {'is' if (nw + ch) == 1 else 'are'} not saved.",
            "Save them before closing the viewer?" + ("" if is_bsp else
            "\n(this map was opened from a .map: Save as .bsp needs its .bsp)"),
            [("bsp", "Save as .bsp", is_bsp), ("map", "Save as .map", True),
             ("discard", "Discard changes", True), ("cancel", "Cancel", True)])
        if choice in ("bsp", "map"):
            self._page_js("try{modSaveThenClose(%s)}catch(e){}" % json.dumps(choice))
        elif choice == "discard":
            self._log_line("  (MODIFY's unsaved changes discarded)", "dim")
            self._close_viewer()

    def _unsaved_dialog(self, title, head, body, buttons):
        """A modal choice in the launcher's look (dark / light), or the system's own look
        with "Use old popup windows" on. buttons: (key, text, enabled); returns the key
        picked, "cancel" for Esc or the window's X. Cancel has the focus, so Enter or Space
        straight away doesn't throw anything away."""
        old = ML.OLD_POPUPS
        w = tk.Toplevel(self); w.title(title)
        w.transient(self); w.resizable(False, False)
        res = {"k": "cancel"}

        def pick(k):
            res["k"] = k; w.destroy()
        if old:
            frm = tk.Frame(w); frm.pack(fill="both", expand=True, padx=14, pady=(12, 6))
            tk.Label(frm, text=head, justify="left", anchor="w").pack(anchor="w", pady=(0, 4))
            tk.Label(frm, text=body, justify="left", anchor="w").pack(anchor="w")
            row = tk.Frame(w); row.pack(padx=10, pady=(6, 12))
            mk = lambda t, c: tk.Button(row, text=t, command=c, width=max(10, len(t) + 2))
        else:
            w.configure(bg=ML.BG)
            frm = ttk.Frame(w, style="Panel.TFrame"); frm.pack(fill="both", expand=True, padx=10, pady=(10, 0))
            ttk.Label(frm, text=head, style="Panel.TLabel", foreground=ML.ACCENT, justify="left"
                      ).pack(anchor="w", padx=10, pady=(8, 4))
            ttk.Label(frm, text=body, style="Panel.TLabel", justify="left").pack(anchor="w", padx=10, pady=(0, 8))
            row = ttk.Frame(w, style="Panel.TFrame"); row.pack(fill="x", padx=10, pady=(0, 10), ipady=4)
            mk = lambda t, c: ttk.Button(row, text=t, command=c, cursor="hand2")
        cancel = None
        for k, text, ok in buttons:
            b = mk(text, lambda k=k: pick(k)); b.pack(side="left", padx=5)
            if not ok: b.configure(state="disabled")
            if k == "cancel": cancel = b
        w.protocol("WM_DELETE_WINDOW", lambda: pick("cancel"))
        w.bind("<Escape>", lambda e: pick("cancel"))
        # Enter presses the button that has the focus (ttk's own buttons don't by themselves)
        w.bind("<Return>", lambda e: (e.widget.invoke() if hasattr(e.widget, "invoke") else None))
        try:
            w.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() - w.winfo_width()) // 2
            y = self.winfo_rooty() + (self.winfo_height() - w.winfo_height()) // 2
            x0, y0, _x1, _y1 = ML._virtual_screen(w)
            w.geometry(f"+{max(x0, x)}+{max(y0, y)}")
        except Exception: MC.swallowed()
        if not old: self._apply_titlebar(w)
        try: w.grab_set()
        except Exception: MC.swallowed()
        if cancel is not None: cancel.focus_set()
        self.wait_window(w)
        return res["k"]

    # Text editors that open a file at a line, and how: {program name: args(file, line)}.
    _EDITOR_LINE = {
        "notepad++": lambda f, n: ["-n%d" % n, f],
        "code": lambda f, n: ["-g", "%s:%d" % (f, n)],
        "code - insiders": lambda f, n: ["-g", "%s:%d" % (f, n)],
        "codium": lambda f, n: ["-g", "%s:%d" % (f, n)],
        "sublime_text": lambda f, n: ["%s:%d" % (f, n)],
        "subl": lambda f, n: ["%s:%d" % (f, n)],
        "notepad2": lambda f, n: ["/g", str(n), f],
        "notepad3": lambda f, n: ["/g", str(n), f],
        "emeditor": lambda f, n: ["/l", str(n), f],
        "gedit": lambda f, n: ["+%d" % n, f],
        "kate": lambda f, n: ["-l", str(n), f],
        "gvim": lambda f, n: ["+%d" % n, f],
    }

    def _open_map_at(self, line, page_map=""):
        """An info card's Open (the page's "mohaa-open-map" message): the viewed map's .map in
        the Text Editor, at the line of that entity or brush when the editor takes a line
        (Notepad++, VS Code, Sublime Text, Notepad2/3, EmEditor...; Notepad opens it at the
        top). The .map is the one the page was built from (a .bsp's decompiled .map), else
        the last map shown here."""
        mp = page_map if (page_map and page_map.lower().endswith(".map") and os.path.isfile(page_map)) else None
        if mp is None and self._last_info:
            path, _out, html_path = self._last_info
            info = self._read_page_info(html_path)
            mp = info.get("mapFile") or (path if path.lower().endswith(".map") else None)
        if not mp or not os.path.isfile(mp):
            self._log_line("(the .map for this page wasn't found - rebuild the map to write it again)", "err"); return
        prog = (self._cfg.get("text_editor") or "").strip()
        name = os.path.splitext(os.path.basename(prog))[0].lower()
        args = self._EDITOR_LINE.get(name)
        if not args or line <= 0 or not (os.path.isabs(prog) and os.path.isfile(prog)):
            # no line to go to, or the editor needs the usual checks: open the file as the .map button does
            self._launch_with("text_editor", "text editor", "Text Editor", mp); return
        try:
            subprocess.Popen([prog] + args(mp, line))
            self._log_line(f"opened with {os.path.basename(prog)}: {os.path.basename(mp)} at line {line}", "dim")
        except Exception:
            MC.swallowed()
            self._launch_with("text_editor", "text editor", "Text Editor", mp)

    # ------------------------------------------------ SIMULATE: a model for the page ---
    def _sim_models(self):
        """The page's model picker asked for the paks' models: every models/**.tik."""
        if self._vfs is None or not self._tex_ready:
            self._page_js("try{MOHAA_SIM_MODELS(null,%s)}catch(e){}"
                          % json.dumps("The paks are still loading: close this and choose again in a moment"))
            return
        try:
            names = sorted(k for k in self._vfs.names() if k.startswith("models/") and k.endswith(".tik"))
        except Exception as e:
            MC.swallowed()
            self._page_js("try{MOHAA_SIM_MODELS(null,%s)}catch(e){}" % json.dumps("No model list: %s" % e))
            return
        self._page_js("try{MOHAA_SIM_MODELS(%s)}catch(e){}" % json.dumps(names, separators=(",", ":")))

    def _sim_build(self, vpath):
        """Build one model (a .tik in the loaded paks) for the page's SIMULATE, as the map
        build builds the models a map places, and hand it to the page (MOHAA_SIMMODEL).
        The path comes from the page, so it must name a .tik under models/ in the paks."""
        vp = (vpath or "").strip().replace("\\", "/").lower()
        fail = lambda why: self._page_js("try{MOHAA_SIMMODEL_FAIL(%s,%s)}catch(e){}" % (json.dumps(vp), json.dumps(why)))
        if (not vp.startswith("models/") or not vp.endswith(".tik") or ".." in vp or len(vp) > 260
                or any(ord(c) < 32 for c in vp)):
            fail("not a model in the paks"); return
        vfs, shaders = self._vfs, self._SH
        if vfs is None or not self._tex_ready:
            fail("the paks are still loading"); return
        if not vfs.exists(vp):
            fail("not found in the loaded paks"); return
        try: texsize = int(self._texsize.get())
        except (TypeError, ValueError): texsize = 256
        cache = self._index_cache
        if not hasattr(self, "_sim_lock"): self._sim_lock = threading.Lock()
        self._log_line(f"(Simulate: building {vp} ...)", "dim")
        threading.Thread(target=self._sim_build_work, args=(vp, vfs, shaders, texsize, cache), daemon=True).start()

    def _sim_build_work(self, vp, vfs, shaders, texsize, cache):
        """Worker thread: one model's mesh and pictures, packed as the page's own data."""
        with self._sim_lock:
            try:
                import mohaa_map_view as MMV
                blobs = MMV.Blobs()
                tcache = MMV.TextureCache(os.path.join(cache, "tex")) if cache else None
                texs = MMV.TextureTable(vfs, shaders, blobs, max(32, min(1024, texsize)), tcache)
                mb = MMV.ModelBuilder(vfs, texs, blobs, say=lambda *a: None)
                if mb.get(vp) < 0:
                    raise ValueError(mb.failed.get(vp) or "it can't be drawn")
                b64, _raw, gz = MMV.pack_payload({"tex": texs.entries, "models": mb.models}, blobs)
                js = "try{MOHAA_SIMMODEL(%s,%s)}catch(e){}" % (json.dumps(vp), json.dumps(b64))
                self._log_q.put(("dim", f"  (Simulate: {vp} built, {gz // 1024} KB)"))
            except Exception as e:
                MC.swallowed()
                js = "try{MOHAA_SIMMODEL_FAIL(%s,%s)}catch(e){}" % (json.dumps(vp), json.dumps(str(e)[:200]))
                self._log_q.put(("warn", f"  (Simulate: {vp} can't be drawn: {str(e)[:200]})"))
            self._page_requests.append(lambda j=js: self._page_js(j))

    def _open_scr(self, vpath, where):
        """The level-script card's Open .scr / Open: the script in the Text Editor. `where`
        is the file it was read from (a path on disk) or "<path> (<pak>)" for one read from a
        pak, which is extracted first."""
        vpath = (vpath or "").strip(); where = (where or "").strip()
        if where and os.path.isfile(where):
            self._launch_with("text_editor", "text editor", "Text Editor", where); return
        if not vpath:
            self._log_line("(no script to open)", "err"); return
        self._open_entry_with(vpath.replace("\\", "/"), "text_editor", "text editor", "Text Editor")

    def _hook_embed_drop(self, _tries=0):
        """As the Model Viewer's (refuse file drops on the pane, catch them ourselves, and
        listen for the page's messages), for .bsp / .map files."""
        wv = self._webview
        if wv is None or getattr(self, "_embed_drop_hooked", False): return
        if getattr(wv, "core", None) is None:
            if _tries < 150: self.after(200, lambda: self._hook_embed_drop(_tries + 1))
            return
        self._embed_drop_hooked = True
        try: wv.web.AllowExternalDrop = False
        except Exception: MC.swallowed()
        try:
            from System.Windows.Forms import DataFormats, DragDropEffects

            def _enter(s, a):
                try:
                    if a.Data.GetDataPresent(DataFormats.FileDrop): a.Effect = DragDropEffects.Copy
                except Exception: MC.swallowed()

            def _drop(s, a):
                try:
                    for p in a.Data.GetData(DataFormats.FileDrop):
                        if str(p).lower().endswith(MAP_EXTS): self._drop_paths.append(str(p))
                except Exception: MC.swallowed()
            self._wv_drag_cbs = (_enter, _drop)
            for c in (getattr(wv, "web", None), getattr(wv, "control", None)):
                if c is None: continue
                try: c.AllowDrop = True; c.DragEnter += _enter; c.DragDrop += _drop
                except Exception: MC.swallowed()
        except Exception: MC.swallowed()
        js = ("(function(){if(window.__mohaaDropGuard)return;window.__mohaaDropGuard=1;"
              "function s(e){e.preventDefault();e.stopPropagation();"
              "if(e.dataTransfer)e.dataTransfer.dropEffect='none';}"
              "window.addEventListener('dragover',s,true);"
              "window.addEventListener('dragenter',s,true);"
              "window.addEventListener('drop',function(e){s(e);"
              "try{if(window.chrome&&chrome.webview)chrome.webview.postMessage('mohaa-drop-blocked');}catch(_){}"
              "},true);})();")
        try: wv.core.AddScriptToExecuteOnDocumentCreatedAsync(js)
        except Exception: MC.swallowed()
        try: wv.core.ExecuteScriptAsync(js)
        except Exception: MC.swallowed()
        try:
            def _msg(s, a):
                try: m = a.TryGetWebMessageAsString()
                except Exception: MC.swallowed(); return
                try:
                    if m == "mohaa-drop-blocked":
                        self._log_q.put(("dim", "(the 3D pane can't take drops here - drop onto the file tree or console instead)"))
                    elif m == "mohaa-close":
                        # runs on the WebView2 thread: hand it to the Tk main thread
                        self._log_q.put(("closeview", None))
                    elif m.startswith("mohaa-close-ask\n"):
                        # closing with MODIFY's changes unsaved: "mohaa-close-ask\n{json}"
                        try: info = json.loads(m.split("\n", 1)[1])
                        except Exception: MC.swallowed(); info = None
                        if not isinstance(info, dict): info = {}
                        self._page_requests.append(lambda i=info: self._close_ask(i))
                    elif m.startswith("mohaa-open-map\n"):
                        # an info card's Open: the .map at a line (and the .map the page was built from)
                        parts = (m.split("\n") + ["", ""])[1:3]
                        try: line = int(parts[0])
                        except Exception: MC.swallowed(); line = 0
                        self._page_requests.append(lambda l=line, f=parts[1]: self._open_map_at(l, f))
                    elif m.startswith("mohaa-open-scr\n"):
                        # the level-script card's Open .scr: "mohaa-open-scr\n<path in the paks>\n<where>"
                        parts = (m.split("\n") + ["", ""])[1:3]
                        self._page_requests.append(lambda v=parts[0], w=parts[1]: self._open_scr(v, w))
                    elif m == "mohaa-sim-models":
                        # SIMULATE's model picker: every model in the loaded paks
                        self._page_requests.append(self._sim_models)
                    elif m.startswith("mohaa-sim-build\n"):
                        # SIMULATE's model: "mohaa-sim-build\n<path of a .tik in the paks>"
                        vp = m.split("\n", 1)[1][:300]
                        self._page_requests.append(lambda v=vp: self._sim_build(v))
                    elif m.startswith("mohaa-modify-save\n"):
                        # MODIFY's Save as .bsp / .map: the new entities, and the map they go in
                        try: req = json.loads(m.split("\n", 1)[1])
                        except Exception: MC.swallowed(); req = None
                        if isinstance(req, dict):
                            self._page_requests.append(lambda r=req: self._modify_save(r))
                    elif m.startswith("mohaa-log\n"):
                        # a line from the page for the Output pane: "mohaa-log\n<tag>\n<text>"
                        parts = (m.split("\n", 2) + ["", ""])[1:3]
                        tag = parts[0] if parts[0] in ("dim", "ok", "warn", "err") else "dim"
                        self._log_q.put((tag, "  " + parts[1][:400]))
                    elif m.startswith("mohaa-map-errors\n"):
                        # blocks of the .map the page's reader skipped: title, count, then
                        # one line each (entity, primitive, line in the .map, why); in red
                        # (a warning: the rest of the map is shown)
                        rows = m.split("\n")[1:]
                        title = rows[0] if rows else "?"
                        try: total = int(rows[1])
                        except Exception: MC.swallowed(); total = 0
                        rows = [r for r in rows[2:] if r]
                        total = max(total, len(rows))
                        self._log_q.put(("warn", f"  {title}: the viewer skipped {total} unreadable block{'' if total == 1 else 's'} of the .map:"))
                        for r in rows:
                            self._log_q.put(("warn", "    " + r))
                        if total > len(rows):
                            self._log_q.put(("warn", f"    ... and {total - len(rows)} more (the red line in the viewer's panel opens the list)"))
                except Exception as e:
                    MC.swallowed()
                    self._log_q.put(("dim", f"(viewer message: {e})"))
            wv.core.WebMessageReceived += _msg
            self._wv_msg_cb = _msg
        except Exception: MC.swallowed()

    def _enable_win_drop(self):
        """Windows drag-and-drop of .bsp / .map files onto the window (same mechanism as
        the Model Viewer's)."""
        if not sys.platform.startswith("win"): return
        try:
            import ctypes
            is64 = ctypes.sizeof(ctypes.c_void_p) == 8
            LONG_PTR = ctypes.c_int64 if is64 else ctypes.c_int32
            ULONG_PTR = ctypes.c_uint64 if is64 else ctypes.c_uint32
            LRESULT = LONG_PTR; WPARAM = ULONG_PTR; LPARAM = LONG_PTR
            HWND = ctypes.c_void_p; HANDLE = ctypes.c_void_p; UINT = ctypes.c_uint
            user32 = ctypes.windll.user32; shell32 = ctypes.windll.shell32
            hwnd = self.winfo_id(); WM_DROPFILES = 0x0233; GWLP_WNDPROC = -4
            WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)
            SetWL = user32.SetWindowLongPtrW if (is64 and hasattr(user32, "SetWindowLongPtrW")) else user32.SetWindowLongW
            CallWP = user32.CallWindowProcW
            SetWL.argtypes = [HWND, ctypes.c_int, WNDPROC]; SetWL.restype = LONG_PTR
            CallWP.argtypes = [LONG_PTR, HWND, UINT, WPARAM, LPARAM]; CallWP.restype = LRESULT
            shell32.DragQueryFileW.argtypes = [HANDLE, UINT, ctypes.c_wchar_p, UINT]; shell32.DragQueryFileW.restype = UINT
            shell32.DragFinish.argtypes = [HANDLE]; shell32.DragAcceptFiles.argtypes = [HWND, ctypes.c_int]
            self._old_wndproc = 0

            def py_wndproc(h, msg, wp, lp):
                if msg == WM_DROPFILES:
                    try:
                        n = shell32.DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
                        for i in range(n):
                            need = shell32.DragQueryFileW(wp, i, None, 0)
                            buf = ctypes.create_unicode_buffer(need + 1)
                            shell32.DragQueryFileW(wp, i, buf, need + 1)
                            if buf.value.lower().endswith(MAP_EXTS): self._drop_paths.append(buf.value)
                        shell32.DragFinish(wp)
                    except Exception: MC.swallowed()
                    return 0
                try: return CallWP(self._old_wndproc, h, msg, wp, lp)
                except Exception: MC.swallowed(); return 0
            self._wndproc_cb = WNDPROC(py_wndproc)
            old = SetWL(hwnd, GWLP_WNDPROC, self._wndproc_cb)
            if not old: self._wndproc_cb = None; self._log_line("(drag-drop unavailable; use Browse)", "dim"); return
            self._old_wndproc = old; shell32.DragAcceptFiles(hwnd, True)

            def _restore(*_):
                try: SetWL.argtypes = [HWND, ctypes.c_int, LONG_PTR]; SetWL(hwnd, GWLP_WNDPROC, self._old_wndproc)
                except Exception: MC.swallowed()
            self._restore_drop = _restore
            self.bind("<Destroy>", lambda e: _restore() if e.widget is self else None)
            self._log_line("Drag-and-drop ready - drop a .bsp/.map/.bak onto this window.", "dim")
        except Exception as e:
            MC.swallowed()
            self._log_line(f"(drag-drop unavailable: {e}; use Browse)", "dim")

    # ------------------------------------------------------------ dialogs ---
    def _keymap_tabs(self):
        """The F1 window's tabs (the window itself is the Model Viewer's KeyMapWindow)."""
        import mohaa_map_view as MMV
        return [("3D viewer", MMV.MAP_VIEWER_KEYS, self.KEYMAP_VIEWER_HINT), ("Launcher", MAP_KEYS_LAUNCHER)]

    def _show_legend(self):
        """Help > Legend (F2): what the viewer's colours, markers and editor surfaces mean.
        The same table as the viewer's own legend (L), LEGEND in mohaa_map_view.py: one
        column per section (path nodes, entities, brushes and editor surfaces), each
        scrolling on its own. The editor textures show their picture from the loaded paks."""
        w0 = getattr(self, "_legend_win", None)
        try:
            if w0 is not None and w0.winfo_exists():
                w0.deiconify(); w0.lift(); w0.focus_set(); return
        except Exception:
            MC.swallowed()
        try:
            import mohaa_map_view as MMV
        except Exception as e:
            MC.swallowed()
            self._log_line(f"(the legend needs mohaa_map_view.py: {e})", "err"); return
        import base64
        old = ML.OLD_POPUPS
        w = tk.Toplevel(self); w.title("Legend")
        w.transient(self)
        self._legend_win = w
        if not old: w.configure(bg=ML.BG)
        body = tk.Frame(w, bg=ML.PANEL) if not old else tk.Frame(w)
        bg = ML.PANEL if not old else body.cget("bg")
        # the editor pictures, when the paks are loaded (24 px, from the builder's 48 px ones)
        thumbs = {}
        if self._tex_ready and self._vfs is not None:
            try:
                cache = MMV.TextureCache(os.path.join(self._index_cache, "tex")) if self._index_cache else None
                for name, val in MMV.legend_thumbs(self._vfs, self._SH, cache).items():
                    try:
                        thumbs[name] = tk.PhotoImage(master=w, data=base64.b64encode(val[1]).decode("ascii")).subsample(2, 2)
                    except Exception:
                        MC.swallowed()
            except Exception:
                MC.swallowed()
                thumbs = {}
        w._thumbs = thumbs                     # Tk drops images nothing in Python refers to
        # text wraps at about 44 characters, narrower on a small screen so the three
        # columns still fit across it
        try:
            import tkinter.font as _tkfont
            wrap = (_tkfont.nametofont("TkDefaultFont") if old else _tkfont.Font(font=ML.FONT_SMALL)).measure("x" * 44)
        except Exception:
            MC.swallowed()
            wrap = 320
        wrap = max(200, min(wrap, (self.winfo_screenwidth() - 160) // 3 - 60))

        def label(parent, text, kind, **grid):
            wl = wrap if kind != "title" else 0
            if old:
                lb = tk.Label(parent, text=text, justify="left", anchor="w", font="TkDefaultFont", wraplength=wl)
            else:
                st = "PanelDim.TLabel" if kind in ("desc", "note", "sub") else "Panel.TLabel"
                lb = ttk.Label(parent, text=text, style=st, justify="left", wraplength=wl)
                if kind in ("title", "name"): lb.configure(foreground=ML.ACCENT)
            lb.grid(sticky="w", **grid)
            return lb

        # One column per section, each its own canvas under its title, so each scrolls on
        # its own; a column's scroll bar shows only while it has more than fits.
        cols = []
        for ci, sec in enumerate(MMV.LEGEND):
            colf = tk.Frame(body, bg=ML.PANEL) if not old else tk.Frame(body)
            colf.grid(row=0, column=ci, sticky="nsew", padx=(0 if ci == 0 else 14, 0))
            body.grid_columnconfigure(ci, weight=1)
            label(colf, sec["title"].upper(), "title", row=0, column=0, columnspan=2, pady=(0, 4))
            cv = tk.Canvas(colf, highlightthickness=0, bd=0, yscrollincrement=24, **({"bg": ML.PANEL} if not old else {}))
            sb = ttk.Scrollbar(colf, orient="vertical", command=cv.yview) if not old else tk.Scrollbar(colf, command=cv.yview)
            cv.configure(yscrollcommand=sb.set)
            cv.grid(row=1, column=0, sticky="nsew"); sb.grid(row=1, column=1, sticky="ns", padx=(4, 0))
            colf.grid_rowconfigure(1, weight=1); colf.grid_columnconfigure(0, weight=1)
            inner = ttk.Frame(cv, style="Panel.TFrame") if not old else tk.Frame(cv)
            cv.create_window((0, 0), window=inner, anchor="nw")
            r = 0
            if sec.get("note"):
                label(inner, sec["note"], "note", row=r, column=0, columnspan=2, pady=(0, 4)); r += 1
            for row in sec["rows"]:
                if row.get("sub"):
                    label(inner, row["sub"], "sub", row=r, column=0, columnspan=2, pady=(6, 2)); r += 1
                    continue
                self._legend_swatch(inner, row, thumbs, bg).grid(row=r, column=0, sticky="nw", padx=(0, 9), pady=(3, 3))
                tf = ttk.Frame(inner, style="Panel.TFrame") if not old else tk.Frame(inner)
                tf.grid(row=r, column=1, sticky="w", pady=(1, 3))
                label(tf, row["name"] + (f"   [{row['key']}]" if row.get("key") else ""), "name", row=0, column=0)
                label(tf, row.get("desc", ""), "desc", row=1, column=0)
                r += 1
            cols.append((cv, sb, inner, colf))
        body.grid_rowconfigure(0, weight=1)
        btn = tk.Button(w, text="Close", command=w.destroy) if old else ttk.Button(w, text="Close", command=w.destroy, cursor="hand2")
        btn.pack(side="bottom", pady=(0, 10))
        body.pack(side="top", fill="both", expand=True, padx=12, pady=(10, 8))
        w.update_idletasks()
        # About as tall as the viewer's own legend (640 px with the title and Close button),
        # never taller than the launcher window, the screen or the longest column.
        needs = []
        for cv, sb, inner, colf in cols:
            nw, nh = inner.winfo_reqwidth(), inner.winfo_reqheight()
            cv.configure(width=nw, scrollregion=(0, 0, nw, nh))
            colf.grid_columnconfigure(1, minsize=sb.winfo_reqwidth() + 4)   # room kept for the bar
            needs.append(nh)
        try:
            lh = self.winfo_height() if self.winfo_height() > 200 else 820
        except Exception:
            MC.swallowed()
            lh = 820
        extra = w.winfo_reqheight() - max(c[0].winfo_reqheight() for c in cols)
        cap = max(240, min(lh, self.winfo_screenheight() - 80, 640) - extra)
        h = min(cap, max(needs) if needs else cap)
        for cv, sb, inner, colf in cols:
            cv.configure(height=h)

            def _fit(e=None, cv=cv, sb=sb, inner=inner):
                if cv.winfo_height() + 1 >= inner.winfo_reqheight():
                    sb.grid_remove(); cv.yview_moveto(0)
                else:
                    sb.grid()
            cv.bind("<Configure>", _fit)

        def _wheel(e):
            # the column under the mouse pointer scrolls, whichever widget has the focus
            try:
                wdg = w.winfo_containing(e.x_root, e.y_root)
            except Exception:
                MC.swallowed()
                wdg = None
            while wdg is not None and not any(wdg is c[3] for c in cols):
                wdg = getattr(wdg, "master", None)
            for cv, sb, inner, colf in cols:
                if wdg is colf and cv.winfo_height() < inner.winfo_reqheight():
                    up = getattr(e, "delta", 0) > 0 or getattr(e, "num", 0) == 4
                    cv.yview_scroll(-3 if up else 3, "units")
                    return "break"
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            w.bind(seq, _wheel)
        w.bind("<Escape>", lambda e: w.destroy()); w.bind("<F2>", lambda e: (w.destroy(), "break"))
        self._center(w)
        if not old: self._apply_titlebar(w)
        btn.focus_set()

    def _legend_swatch(self, parent, row, thumbs, bg):
        """A legend row's 26 px swatch, drawn as the viewer draws that thing."""
        def hexc(c):
            return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v * 255)))) for v in (list(c or (0.5, 0.5, 0.5)) + [0, 0, 0])[:3])
        S = 26
        cv = tk.Canvas(parent, width=S, height=S, highlightthickness=0, bd=0, bg=bg)
        sw, fill = row.get("sw"), hexc(row.get("fill"))
        if sw == "tex" and thumbs.get(row.get("tex")):
            cv.create_image(S // 2, S // 2, image=thumbs[row["tex"]])
            cv.create_rectangle(0, 0, S - 1, S - 1, outline="#000000")
        elif sw == "node":
            cv.create_rectangle(0, 0, S - 1, S - 1, fill=fill, outline="#000000")
            if row.get("line"):
                cv.create_rectangle(3, 3, S - 4, S - 4, outline=hexc(row["line"]), width=3)
        elif sw == "diamond":
            cv.create_polygon(S // 2, 1, S - 2, S // 2, S // 2, S - 2, 1, S // 2, fill=fill, outline="#000000")
        elif sw == "wire":                     # a setsize box: a wire cube
            cv.create_rectangle(0, 0, S - 1, S - 1, fill="#2b333d", outline="")
            for x0, y0, x1, y1 in ((4, 9, 17, 9), (17, 9, 17, 22), (17, 22, 4, 22), (4, 22, 4, 9),
                                   (9, 4, 22, 4), (22, 4, 22, 17), (22, 17, 9, 17), (9, 17, 9, 4),
                                   (4, 9, 9, 4), (17, 9, 22, 4), (17, 22, 22, 17), (4, 22, 9, 17)):
                cv.create_line(x0, y0, x1, y1, fill=fill, width=1)
        elif sw == "arrow":
            cv.create_rectangle(0, 0, S - 1, S - 1, fill="#2b333d", outline="")
            for x0, y0, x1, y1 in ((4, 13, 21, 13), (21, 13, 16, 8), (21, 13, 16, 18)):
                cv.create_line(x0, y0, x1, y1, fill="#ffffff", width=3)
        elif sw == "link":
            cv.create_rectangle(0, 0, S - 1, S - 1, fill="#2b333d", outline="")
            cv.create_line(4, 21, 21, 5, fill=fill, width=2, arrow="last", arrowshape=(7, 8, 3))
        elif sw == "lines":                    # the game cvars' rows: coloured lines on 24 x 24
            cv.create_rectangle(0, 0, S - 1, S - 1, fill="#2b333d", outline="")
            for x0, y0, x1, y1, c in row.get("lines") or ():
                cv.create_line(x0 + 1, y0 + 1, x1 + 1, y1 + 1, fill=hexc(c), width=1)
        elif sw == "label":
            cv.create_rectangle(0, 0, S - 1, S - 1, fill=ML.BG or "#0e1116", outline=ML.LINE or "#2b333d")
            cv.create_text(S // 2, S // 2, text="Aa", fill=ML.ACCENT or "#7ee787", font=ML.FONT_SMALL)
        elif sw == "sel":
            cv.create_rectangle(0, 0, S - 1, S - 1, fill="#b5606a", outline="#000000")
        elif sw == "hover":
            cv.create_rectangle(0, 0, S - 1, S - 1, fill="#6b7480", outline="")
            cv.create_rectangle(3, 3, S - 4, S - 4, outline=ML.ACCENT or "#7ee787", width=1)
        else:                                  # a plain box, or a texture the paks don't have
            cv.create_rectangle(0, 0, S - 1, S - 1, fill=fill, outline="#000000")
        return cv

    def _center(self, w):
        """Centre a dialog over the window, kept on screen."""
        try:
            w.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() - w.winfo_width()) // 2
            y = self.winfo_rooty() + (self.winfo_height() - w.winfo_height()) // 2
            x0, y0, _x1, _y1 = ML._virtual_screen(w)
            w.geometry(f"+{max(x0, x)}+{max(y0, y)}")
        except Exception: MC.swallowed()

    def _show_privacy(self):
        """Help > Privacy & Legal."""
        self._text_dialog("Privacy & Legal", _privacy_text(), width=88, height=26)

    def _show_about(self):
        """Help > About."""
        old = ML.OLD_POPUPS
        w = tk.Toplevel(self); w.title("About")
        w.transient(self); w.resizable(False, False)
        if not old: w.configure(bg=ML.BG)
        frm = tk.Frame(w) if old else ttk.Frame(w, style="Panel.TFrame")
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        rows = [(APP_NAME + " launcher", "title"), ("made by: Searingwolfe", "body"), (ML.VERSION_LABEL, "dim"),
                ("Browses MOHAA .pk3 paks and opens .bsp / .map maps in a\n"
                 "self-contained browser-based 3D viewer. A .bsp is decompiled\n"
                 "back to .map source by its own built-in decompiler.", "dim"),
                ("Engine reference: OpenMOHAA (github.com/openmoh/openmohaa)", "dim"),
                ("Decompiling approach: wfowler1's BSP Decompiler (LibBSP)", "dim"),
                (ML.PRIVACY_SUMMARY, "dim")]
        for text, kind in rows:
            if old:
                tk.Label(frm, text=text, justify="left", font="TkDefaultFont").pack(anchor="w", padx=10, pady=(4, 2))
            else:
                st = "Panel.TLabel" if kind in ("title", "body") else "PanelDim.TLabel"
                lb = ttk.Label(frm, text=text, style=st, justify="left")
                if kind == "title": lb.configure(foreground=ML.ACCENT)
                lb.pack(anchor="w", padx=10, pady=(6 if kind == "title" else 0, 6))
        (tk.Button(frm, text="Privacy & Legal...", command=self._show_privacy) if old else
         ttk.Button(frm, text="Privacy & Legal...", command=self._show_privacy, cursor="hand2")).pack(anchor="w", padx=10, pady=(0, 6))
        btn = tk.Button(w, text="Close", command=w.destroy) if old else ttk.Button(w, text="Close", command=w.destroy, cursor="hand2")
        btn.pack(pady=(0, 10))
        w.bind("<Escape>", lambda e: w.destroy())
        self._center(w)
        if not old: self._apply_titlebar(w)
        w.grab_set(); btn.focus_set()

    def _launcher_path(self):
        """After an update, start this launcher again (not the Model Viewer's); the restart
        itself, staged files included, is mohaa_launcher.App._restart_program."""
        return os.path.abspath(__file__)


if __name__ == "__main__":
    init = None
    for a in sys.argv[1:]:
        if a.lower().endswith(MAP_EXTS) and os.path.exists(a): init = a; break
    _code = ML.run_gui(lambda: MapApp(initial_file=init), "mohaa_map_launcher")
    if ML.WEBVIEW2 is not None:
        os._exit(_code)       # pythonnet + WebView2 crash in normal interpreter shutdown
    sys.exit(_code)

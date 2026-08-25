#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
#  mohaa_launcher.py  --  Launcher for mohaa_view.py
#  - Browse / drag-drop a loose .skd or .tik, OR
#  - Open MOHAA .pk3 pak(s) and navigate the models/ tree to any .skd/.tik.
#  Loaded paks + preferences are remembered between sessions.
#  Keep this file next to mohaa_view.py (and mohaa_textures.py for skins).
#
#  UI features:
#   - File / Options / View / Help menu bar (with accelerators)
#   - Dark & Light themes (Options > Theme, or Ctrl+T / header button)
#   - Tooltips on every control
#   - Search box filtering the pak tree (Ctrl+F, Esc clears)
#   - Explorer-style tree keys: Enter opens/descends, Backspace goes up,
#     Right/Left expand/collapse, F5 reloads paks
#   - Right-click the tree / pak header for a context menu listing every
#     loaded pak (with per-pak remove) + quick actions
#   - Recent-files list, status bar, log context menu (copy / clear)
# ==============================================================================
import sys, os, re, subprocess, threading, queue, glob, json, zipfile, tempfile, shutil, hashlib
# Tk is stdlib but NOT always installed: Debian/Ubuntu/Fedora ship it as a separate
# python3-tk / python3-tkinter package, and a bare ImportError traceback tells a Linux
# user nothing. Fail with instructions instead.
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError as _tkerr:
    _hint={"linux":"    sudo apt install python3-tk        (Debian/Ubuntu/Mint)\n"
                   "    sudo dnf install python3-tkinter   (Fedora/RHEL)\n"
                   "    sudo pacman -S tk                  (Arch)",
           "darwin":"    brew install python-tk\n"
                    "    (or use the python.org installer, which bundles Tk)"}.get(
        "linux" if sys.platform.startswith("linux") else sys.platform,
        "    Reinstall Python from python.org with the tcl/tk option enabled.")
    sys.stderr.write("\nMOHAA viewer: Python's Tk GUI toolkit is missing (%s).\n"
                     "Install it with one of:\n%s\n\n"%(_tkerr,_hint))
    raise SystemExit(2)
try:
    import mohaa_textures as MTX           # texture resolution over the loaded paks
except Exception:
    MTX=None

# Optional embedded 3D viewer: Edge WebView2 inside the tk window (Windows only).
# Needs `pip install pythonnet pywebview==4.4.1 tkwebview2` plus the WebView2
# runtime (ships with Win10/11; Edge). If anything is missing WEBVIEW2 stays None
# and every open falls back to the external browser - exactly the old behaviour.
# pywebview is pinned to 4.4.1: tkwebview2 3.5.0 constructs pywebview's Window/
# EdgeChrome internals directly and 4.4.1 is signature-verified against that call.
WEBVIEW2=None; _WV_HAVE_RT=None; _WEBVIEW_ERR=""
if sys.platform.startswith("win"):
    try:
        from tkwebview2.tkwebview2 import WebView2 as WEBVIEW2, have_runtime as _WV_HAVE_RT
    except Exception as _e:
        _WEBVIEW_ERR=str(_e)

# Suppress console-window flashes from child console processes (python probes,
# viewer builds) - vital when the launcher itself runs under pythonw (no console),
# where every plain Popen of a console exe would otherwise pop a black window.
NOWIN=dict(creationflags=0x08000000) if sys.platform.startswith("win") else {}   # CREATE_NO_WINDOW

# ------------------------------------------------------------------ themes ---
THEMES={
 "dark":dict(BG="#0e1116",PANEL="#161b22",LINE="#2b333d",TXT="#d6dde6",DIM="#8b97a6",
             ACCENT="#7ee787",TAG_C="#f2f5f8",ORIGIN="#c084fc",BONE_C="#566778",
             BTN_BG="#21272f",BTN_HOV="#2d3a2d",ERR_C="#f47067",SEL_BG="#243042",
             TIP_BG="#1c232c",TIP_TXT="#d6dde6",ENTRY_BG="#10151c"),
 "light":dict(BG="#f5f7fa",PANEL="#ffffff",LINE="#d0d7de",TXT="#1f2328",DIM="#57606a",
             ACCENT="#0969da",TAG_C="#7c6408",ORIGIN="#8250df",BONE_C="#57606a",
             BTN_BG="#eef1f4",BTN_HOV="#ddebff",ERR_C="#cf222e",SEL_BG="#ddf4ff",
             TIP_BG="#ffffff",TIP_TXT="#1f2328",ENTRY_BG="#ffffff"),
}
# module-level colour names (kept for compatibility with all existing code
# paths); apply_theme() re-points them at the active palette.
BG=PANEL=LINE=TXT=DIM=ACCENT=TAG_C=ORIGIN=BONE_C=BTN_BG=BTN_HOV=ERR_C=SEL_BG=TIP_BG=TIP_TXT=ENTRY_BG=""
globals().update(THEMES["dark"])

def _mono_family():
    """First monospace family actually present. Consolas is Windows-only; asking Tk for
    it on macOS/Linux silently falls back to a PROPORTIONAL default, which breaks every
    column-aligned thing in the UI (the file tree and the Output console). Tk always
    resolves the logical name "TkFixedFont", so that is the last-resort answer."""
    try:
        import tkinter.font as _tkf
        have={f.lower() for f in _tkf.families()}
    except Exception:
        return "TkFixedFont"
    for f in ("Consolas","SF Mono","Menlo","DejaVu Sans Mono","Liberation Mono",
              "Ubuntu Mono","Noto Sans Mono","Courier New","Monaco"):
        if f.lower() in have: return f
    return "TkFixedFont"

_MONO=None      # resolved lazily: tkinter.font.families() needs a live Tk root
def init_fonts():
    global FONT_MONO,FONT_SMALL,FONT_TITLE,_MONO
    if _MONO is not None: return
    _MONO=_mono_family()
    FONT_MONO=(_MONO,10); FONT_SMALL=(_MONO,9); FONT_TITLE=(_MONO,13,"bold")

FONT_MONO=("Consolas",10); FONT_SMALL=("Consolas",9); FONT_TITLE=("Consolas",13,"bold")

# ---------------------------------------------------------------- privacy ---
# Shown in Help --> Privacy & Legal and summarised in About. Kept here, in the
# program, rather than only in PRIVACY.md, because a user who downloads a zip and
# never visits the repository still has to be able to read it. Keep this text and
# PRIVACY.md in step when either changes.
PRIVACY_SUMMARY=("This program collects nothing and sends nothing, and has no\n"
                 "telemetry. It uses the network only when you check for updates.")

PRIVACY_TEXT = """PRIVACY NOTICE  --  MOHAA Model Viewer
Last updated: 22 August 2026

1. THE SHORT VERSION
   This program does not collect, transmit, sell, share or profile anything.
   It contains no telemetry, no analytics, no crash reporting, no advertising
   and no tracking identifiers, and it never checks for updates on its own. The
   only time it uses the network is when YOU open Help --> Check for updates;
   everything else it does happens entirely on your computer.

2. WHAT IS STORED, AND WHERE
   The program writes three things, all on your own machine, all readable and
   deletable by you at any time:

     a) Settings file  --  mohaa_viewer_config.json
        Written to the program's "output" folder (the one beside the "bin" folder
        that holds the scripts). In a flat / portable install - all files in one
        folder - it sits in that folder instead. Same on Windows, macOS and Linux.
        Contains: the .pk3 paths you loaded, your chosen output folder, theme,
        window layout, view angles, and the paths of any external programs you
        configured. It contains file paths, which on most systems include your
        user name.

     b) Console log  --  output_console.log, in the same folder as (a).
        A copy of the Output pane. Overwritten on each launch. It contains the
        file paths the program touched, so it too may include your user name.

     c) Working files
        A temporary workspace under your system temp folder (mohaaview_*), and
        the generated .html viewers in your chosen output folder. Both are
        removable from Options --> Clear %temp% files / Clear built models.

   None of this is transmitted anywhere. If you want it gone, delete the folders
   above; the program will simply start fresh.

3. NETWORK ACCESS
   The viewer itself makes no network requests. The generated .html page is
   self-contained (textures are embedded as data: URIs) and is served with a
   Content-Security-Policy that blocks outbound connections even if a malformed
   game file were to inject script into it.

   The program reaches the network in only two places, both of which you start
   yourself and neither of which runs in the background:

     - Help --> Check for updates reads a small version file from this project's
       GitHub repository, and, if you choose to install an update, downloads the
       new files from GitHub. This reveals your IP address to GitHub under its
       privacy policy, not this one. It happens only when you open that window and
       click to install; nothing is ever checked automatically.

     - The optional setup script, python_installer_updater.bat, downloads Python
       from python.org and packages from pypi.org when you choose to run it, under
       those sites' own privacy policies.

   The viewer itself makes no other network requests.

   If you open a model in an external web browser rather than the built-in pane,
   that browser is governed by its own privacy policy.

4. YOUR DATA AND THE DEVELOPER
   Because nothing leaves your computer, the developer of this program never
   receives, sees or holds any of your data. There is no account, no sign-in and
   no server. Under the EU/UK GDPR this means the developer is not acting as a
   controller or processor of your personal data through this software, and
   there is correspondingly no data to access, rectify, export or erase from any
   service. You retain full control of the local files listed in section 2.

   For the same reason there is no "sale" or "sharing" of personal information
   within the meaning of the California Consumer Privacy Act, and no personal
   information is collected from anyone, including children (COPPA).

5. CHILDREN
   The program is not directed at children and collects no information from
   anyone of any age.

6. SECURITY
   The program reads .pk3 archives, which are ordinary zip files that you supply.
   Treat downloaded paks as untrusted content. The program is hardened against
   hostile archives (archive paths are confined to the workspace, model headers
   are bounds-checked, and generated pages escape game-file text), but no
   software is perfect. Please report suspected vulnerabilities as described in
   SECURITY.md rather than in a public issue.

7. TRADEMARKS AND GAME CONTENT
   Medal of Honor and Medal of Honor: Allied Assault are trademarks of their
   respective owners. This is an unofficial, non-commercial fan tool. It is not
   affiliated with, authorised, sponsored or endorsed by Electronic Arts Inc. or
   any other rights holder. Trademarks are used only to identify the game whose
   files this tool reads.

   No game assets are included with this program. You must supply your own
   legally obtained copy of the game. Do not redistribute extracted game assets.

8. CHANGES
   Any change to this notice will be reflected here and in PRIVACY.md, with the
   date above updated. Changes reach you when you download or update to a newer
   version.

9. CONTACT
   Questions about this notice: open an issue on the project's repository, or
   use the contact address given in the repository README.
"""

HERE=os.path.dirname(os.path.abspath(__file__))

def _write_base_dir():
    """Base folder the program WRITES into - the config json, the console log and the
    default 'models'/'standalone' output folders all live directly under here.

    Layout-aware, so the same code works before and after the release reorg with no
    setting to flip:
      * scripts in a folder named 'bin'  ->  a sibling 'output' folder (bin/../output),
        created if missing. This is the shipped layout:  bin/ (the .py files),
        docs/ (documentation), output/ (config + log + the built models/ tree).
      * anything else - all files flat in one folder, or portable use  ->  that same
        folder (HERE), so the config and log sit right beside the .py files.
    Falls back to HERE if the target can't be created (e.g. a read-only location)."""
    try:
        if os.path.basename(HERE).lower()=="bin":
            d=os.path.join(os.path.dirname(HERE),"output")
            os.makedirs(d,exist_ok=True)
            return d
    except Exception:
        pass
    return HERE
DATADIR=_write_base_dir()
VIEWER=os.path.join(HERE,"mohaa_view.py")
# Minimum mohaa-viewer-rev a saved HTML must carry to be served from the output-
# folder cache. Older pages (or pre-rev pages with no marker) are rebuilt, so new
# viewer features actually show up instead of a stale page. Keep in step with
# VIEWER_REV in mohaa_view.py. rev 3: dead-GL-canvas backdrop fix.
# rev 4: embed-hash boot (in-launcher layout + theme applied before first paint).
# rev 35: Display-panel placement-angle dial (pitch/yaw/roll) replaces the smoke-light
# slider; the page must be able to read the #ang= boot hash, so pre-35 caches are stale.
# rev 36: drawn tick marks on that dial + a ( pitch yaw roll ) readout.
# Raised to the live VIEWER_REV rather than +1: the source-mtime gate below is the usual
# rebuild trigger, but mtimes come back scrambled when the scripts are round-tripped
# through a zip, and then the baked rev is the only thing left that can catch it.
# rev 37: pages built before the inline-<script> escaping + CSP hardening must be
# rebuilt, so the cache floor moves with VIEWER_REV.
# rev 58: load-time `surface <n> +nodraw` from the tik's init{server{}} / setup{} blocks,
# and the surfaces <select> replaced by a popup that stays open across toggles - pre-58
# pages have neither, and their cached DATA has no tikNodraw key at all.
# rev 59: sidecar animations now carry their own `fx.surf` (the frame commands the
# catalogue always had but the sidecar builder discarded). Every sidecar cached before
# this has no fx at all, so the stamp has to move or they never get rebuilt.
# rev 60: the attach-to-bone <select> is now a searchable popup, so pre-60 pages carry
# markup the new script no longer wires up.
VIEWER_REV_REQUIRED=61
# Sentinel subdir marking an individual-file (Browse / drag-drop / Recent / path-bar)
# build. It rides through the normal subdir plumbing but redirects the output HTML to a
# "standalone" folder sibling to "models", instead of into the pak-mirroring models tree.
# The null byte guarantees it can never collide with a real pak folder name.
STANDALONE_SUBDIR="\x00standalone"
# Migrated from HERE on first run so existing installs keep their settings.
CONFIG=os.path.join(DATADIR,"mohaa_viewer_config.json")
if not os.path.exists(CONFIG):
    try:
        _old=os.path.join(HERE,"mohaa_viewer_config.json")
        if os.path.isfile(_old): shutil.copyfile(_old,CONFIG)
    except Exception: pass

# ============================================================================
#  Version + update channel
#  VERSION is baked into this build and shown in the status bar, the About box
#  and the Help --> Check for updates window. The updater reads version.txt on
#  the repo's main branch; if it names a newer version, the branch zip is pulled
#  and bin/, the RUN .bat and docs/ are refreshed in place.
#  ON EACH RELEASE: bump VERSION here AND write the same number into version.txt
#  at the repo root, then commit both.
# ============================================================================
VERSION="1.0.000"
VERSION_LABEL="version "+VERSION
# GitHub coordinates the update check points at. The repo is private / not yet
# created for now; until it is public these URLs 404 and the check simply reports
# that it could not reach GitHub and changes nothing on disk.
GITHUB_OWNER="searingwolfe"
GITHUB_REPO="mohaa-model-viewer"
GITHUB_BRANCH="main"
UPDATE_UA="MOHAA-Model-Viewer/"+VERSION
# raw version marker + the branch zipball (codeload is what github.com/.../archive
# redirects to anyway) + the human page the update window links to.
UPDATE_VERSION_URL=f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/docs/version.txt"
UPDATE_ZIP_URL=f"https://codeload.github.com/{GITHUB_OWNER}/{GITHUB_REPO}/zip/refs/heads/{GITHUB_BRANCH}"
UPDATE_PAGE_URL=f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"

def _install_root():
    """Folder the updater refreshes: the RUN .bat's directory (the parent of the
    bin/ that holds these scripts) in the shipped layout, else HERE for a flat /
    portable install. The downloaded repo tree (bin/, docs/, RUN .bat) is copied
    over it."""
    return os.path.dirname(HERE) if os.path.basename(HERE).lower()=="bin" else HERE

def find_python():
    """The interpreter used for child mohaa_view.py builds - sys.executable FIRST.

    Two reasons it must not be a PATH lookup. Correctness: this launcher is already
    running under a Python that imported mohaa_textures and (usually) Pillow, so probing
    for "py"/"python" can hand the build to a DIFFERENT interpreter that silently lacks
    Pillow - every model then renders untextured with no obvious cause. Security: on
    Windows a bare program name is resolved by CreateProcess, which searches the CURRENT
    DIRECTORY before PATH, so a py.exe planted in the extracted release folder would be
    executed instead. Under pythonw.exe sys.executable is pythonw.exe, which runs the
    capture_output=True child fine (no console is needed for a redirected build)."""
    exe=sys.executable
    if exe and os.path.isfile(exe): return exe
    for name in ("py","python","python3"):        # frozen/embedded host with no sys.executable
        p=shutil.which(name)
        if not p: continue
        try:
            if subprocess.run([p,"--version"],capture_output=True,**NOWIN).returncode==0: return p
        except OSError: pass
    return None

def _virtual_screen(w):
    """(x0,y0,x1,y1) of the FULL desktop across all monitors. Tk's
    winfo_screenwidth/height report only the primary monitor on Windows, so
    clamping popups against them shoves every menu back onto monitor 1 when the
    app sits on a second monitor. Windows: SM_X/Y/CX/CYVIRTUALSCREEN (76-79)."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            u=ctypes.windll.user32
            x0=u.GetSystemMetrics(76); y0=u.GetSystemMetrics(77)
            return (x0,y0,x0+u.GetSystemMetrics(78),y0+u.GetSystemMetrics(79))
        except Exception: pass
    return (0,0,w.winfo_screenwidth(),w.winfo_screenheight())

def _win_dark_menus(dark):
    """Best-effort dark chrome for NATIVE popup menus (the white border Tk can't
    touch). Undocumented uxtheme ordinals: 135 SetPreferredAppMode (2=ForceDark,
    3=ForceLight), 104 RefreshImmersiveColorPolicyState, 136 FlushMenuThemes.
    Only reliably takes if called BEFORE the first menu is realised. Win10 1903+."""
    if not sys.platform.startswith("win"): return
    try:
        import ctypes
        ux=ctypes.WinDLL("uxtheme.dll")
        ux[135](2 if dark else 3)
        try: ux[104]()
        except Exception: pass
        ux[136]()
    except Exception: pass

def apply_theme(root, name):
    """(Re)apply the named palette to every ttk style. tk widgets that hold raw
    colours are refreshed by App._retheme_widgets() afterwards."""
    globals().update(THEMES.get(name,THEMES["dark"]))
    root.configure(bg=BG); st=ttk.Style(root)
    try: st.theme_use("clam")
    except Exception: pass
    st.configure(".",background=BG,foreground=TXT,fieldbackground=PANEL,troughcolor=PANEL,
                 selectbackground=SEL_BG,selectforeground=TXT,font=FONT_MONO,borderwidth=0)
    st.configure("TFrame",background=BG); st.configure("Panel.TFrame",background=PANEL)
    st.configure("TLabel",background=BG,foreground=TXT,font=FONT_MONO)
    st.configure("Dim.TLabel",background=BG,foreground=DIM,font=FONT_SMALL)
    st.configure("Title.TLabel",background=BG,foreground=ACCENT,font=FONT_TITLE)
    st.configure("Panel.TLabel",background=PANEL,foreground=TXT,font=FONT_MONO)
    st.configure("PanelDim.TLabel",background=PANEL,foreground=DIM,font=FONT_SMALL)
    st.configure("Status.TLabel",background=PANEL,foreground=DIM,font=FONT_SMALL,padding=(8,3))
    # buttons: visible border + hover/pressed states so they read as clickable
    st.configure("TButton",background=BTN_BG,foreground=TXT,bordercolor=LINE,
                 darkcolor=BTN_BG,lightcolor=BTN_BG,relief="raised",padding=(9,5),font=FONT_MONO)
    st.map("TButton",background=[("active",BTN_HOV),("pressed",SEL_BG)],
                     bordercolor=[("active",ACCENT),("focus",ACCENT)],
                     relief=[("pressed","sunken")])
    st.configure("Accent.TButton",foreground=ACCENT,bordercolor=ACCENT)
    st.map("Accent.TButton",background=[("active",BTN_HOV),("pressed",SEL_BG)])
    st.configure("Tool.TButton",padding=(6,2),font=FONT_SMALL)
    st.configure("TScrollbar",background=PANEL,troughcolor=BG,arrowcolor=DIM,bordercolor=BG)
    st.configure("Treeview",background=PANEL,fieldbackground=PANEL,foreground=TXT,
                 borderwidth=0,rowheight=20,font=FONT_SMALL)
    st.map("Treeview",background=[("selected",SEL_BG)],foreground=[("selected",ACCENT)])
    st.layout("Treeview",[("Treeview.treearea",{"sticky":"nswe"})])
    st.configure("TEntry",fieldbackground=ENTRY_BG,foreground=TXT,insertcolor=TXT,
                 bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,padding=(6,3))
    st.map("TEntry",bordercolor=[("focus",ACCENT)])
    st.configure("TCheckbutton",background=BG,foreground=TXT,font=FONT_SMALL)
    st.map("TCheckbutton",background=[("active",BG)])

# When True, every popup (tooltips, drop-down menus, right-click menus) uses the
# OS-default look: white, system font, native tk.Menu. When False (default) they
# use the custom themed windows below, which follow dark/light mode - including
# the border, which native Windows menus always draw white.
OLD_POPUPS=False

def _add_popup_shadow(win):
    """Soft drop shadow behind a borderless popup (menus/tooltips), like native
    Windows menus have: a second Toplevel offset +3+3 at 30% black, kept just
    below the popup and auto-destroyed with it. Best-effort - silently skipped
    where per-window alpha isn't available."""
    sh=None
    try:
        win.update_idletasks()
        sh=tk.Toplevel(win); sh.wm_overrideredirect(True)
        sh.configure(bg="#000000")
        sh.attributes("-alpha",0.30)
        try: sh.attributes("-topmost",True)
        except Exception: pass
        sh.wm_geometry(f"{win.winfo_width()}x{win.winfo_height()}"
                       f"+{win.winfo_rootx()+3}+{win.winfo_rooty()+3}")
        win.lift(sh)                     # popup above its own shadow
        win._shadow=sh
        def _cleanup(e,s=sh,w=win):
            if e.widget is w:
                try: s.destroy()
                except Exception: pass
        win.bind("<Destroy>",_cleanup,add="+")
    except Exception:
        try:
            if sh is not None: sh.destroy()
        except Exception: pass

def _tip_window(master,text,x,y,wrap=360):
    """One shared look for every floating popup: a borderless Toplevel with a 1px
    LINE-coloured border and the theme's tip colours - or the OS-default white +
    system font when 'Use old popup windows' is on."""
    tip=tk.Toplevel(master); tip.wm_overrideredirect(True); tip.wm_geometry(f"+{x}+{y}")
    try: tip.attributes("-topmost",True)
    except Exception: pass
    if OLD_POPUPS:
        tk.Label(tip,text=text,justify="left",bg="#ffffff",fg="#000000",relief="solid",
                 borderwidth=1,font="TkDefaultFont",padx=6,pady=3,wraplength=wrap).pack()
    else:
        outer=tk.Frame(tip,bg=LINE); outer.pack(fill="both",expand=True)
        tk.Label(outer,text=text,justify="left",bg=TIP_BG,fg=TIP_TXT,bd=0,
                 font=FONT_SMALL,padx=7,pady=4,wraplength=wrap).pack(padx=1,pady=1)
        _add_popup_shadow(tip)
    return tip

def _mi(label,command=None,accel=None,state="normal"):
    return {"type":"command","label":label,"command":command,"accel":accel,"state":state}
_MSEP={"type":"separator"}

class PopupMenu:
    """Custom themed popup menu built from Toplevels (like the tooltips), because
    native Windows menus draw a white border Tk cannot recolour. Items are dicts:
    command / separator / check / radio / cascade (cascade "items" may be a list or
    a provider callable, resolved fresh at open). Dismissal is handled by the App's
    persistent Button/Escape bindings via app._open_popup."""
    def __init__(self, app, items, parent=None):
        self.app=app; self.items=items; self.parent=parent
        self.top=None; self.child=None
    def post(self,x,y):
        t=tk.Toplevel(self.app); self.top=t
        t.wm_overrideredirect(True)
        try: t.attributes("-topmost",True)
        except Exception: pass
        outer=tk.Frame(t,bg=LINE); outer.pack(fill="both",expand=True)
        inner=tk.Frame(outer,bg=PANEL); inner.pack(fill="both",expand=True,padx=1,pady=1)
        for it in self.items: self._row(inner,it)
        t.wm_geometry(f"+{x}+{y}"); t.update_idletasks()
        x0,y0,x1,y1=_virtual_screen(t)
        nx=max(x0,min(x,x1-t.winfo_width()-4)); ny=max(y0,min(y,y1-t.winfo_height()-4))
        t.wm_geometry(f"+{nx}+{ny}")
        _add_popup_shadow(t)             # after the final clamped position
        t.bind("<Escape>",lambda e:self.root().unpost())
    def root(self):
        n=self
        while n.parent: n=n.parent
        return n
    def _row(self,parent,it):
        typ=it.get("type","command")
        if typ=="separator":
            tk.Frame(parent,bg=LINE,height=1).pack(fill="x",padx=6,pady=3); return
        state=it.get("state","normal")
        fgc=DIM if state=="disabled" else TXT
        row=tk.Frame(parent,bg=PANEL); row.pack(fill="x")
        pre=""
        if typ=="check": pre=("\u2713 " if it["variable"].get() else "   ")
        if typ=="radio": pre=("\u25cf " if str(it["variable"].get())==str(it.get("value")) else "  ")
        lab=tk.Label(row,text=pre+it["label"],bg=PANEL,fg=fgc,font=FONT_SMALL,anchor="w",padx=10,pady=3)
        lab.pack(side="left",fill="x",expand=True)
        rt=it.get("accel") or ("\u25b8" if typ=="cascade" else "")
        rl=tk.Label(row,text=rt,bg=PANEL,fg=DIM,font=FONT_SMALL,anchor="e",padx=10)
        rl.pack(side="right")
        if state=="disabled": return
        parts=(row,lab,rl)
        def on_enter(_e):
            for w in parts: w.configure(bg=SEL_BG)
            if typ=="cascade": self._open_cascade(row,it)
            else: self.unpost_child()
        def on_leave(_e):
            try:
                w=row.winfo_containing(row.winfo_pointerx(),row.winfo_pointery())
                if w in parts: return          # moved between the row's own labels
            except Exception: pass
            for w in parts: w.configure(bg=PANEL)
        for w in parts:
            w.bind("<Enter>",on_enter); w.bind("<Leave>",on_leave)
            if typ=="cascade": w.bind("<Button-1>",lambda e:self._open_cascade(row,it))
            else: w.bind("<Button-1>",lambda e:self._invoke(it))
    def _invoke(self,it):
        typ=it.get("type","command")
        if typ=="check": it["variable"].set(not it["variable"].get())
        if typ=="radio": it["variable"].set(it.get("value"))
        self.root().unpost()
        cb=it.get("command")
        if cb:
            try: cb()
            except Exception: pass
    def _open_cascade(self,row,it):
        self.unpost_child()
        items=it.get("items")
        if callable(items): items=items()
        sub=PopupMenu(self.app,items,parent=self); self.child=sub
        sub.post(row.winfo_rootx()+row.winfo_width()-4, row.winfo_rooty()-4)
    def contains(self,rx,ry):
        """Is the screen point inside this popup or any open descendant?"""
        n=self
        while n:
            t=n.top
            if t:
                try:
                    x0,y0=t.winfo_rootx(),t.winfo_rooty()
                    if x0<=rx<x0+t.winfo_width() and y0<=ry<y0+t.winfo_height(): return True
                except Exception: pass
            n=n.child
        return False
    def unpost_child(self):
        if self.child:
            self.child.unpost(); self.child=None
    def unpost(self):
        self.unpost_child()
        if self.top:
            try: self.top.destroy()
            except Exception: pass
            self.top=None
        if self.parent is None and getattr(self.app,"_open_popup",None) is self:
            self.app._open_popup=None; self.app._popup_owner=None

def dot_canvas(parent,color,size=8,bg=None):
    c=tk.Canvas(parent,width=size,height=size,bg=bg or PANEL,highlightthickness=0)
    c.create_oval(1,1,size-1,size-1,fill=color,outline=""); return c

# ---------------------------------------------------------------- tooltips ---
class Tooltip:
    """Hover tooltip: shows `text` in a small borderless window after a short
    delay; follows the active theme. Attach with Tooltip(widget, 'text')."""
    DELAY=550
    def __init__(self, widget, text):
        self.w=widget; self.text=text; self.tip=None; self._id=None
        widget.bind("<Enter>",self._schedule,add="+")
        widget.bind("<Leave>",self._hide,add="+")
        widget.bind("<ButtonPress>",self._hide,add="+")
    def set_text(self,text): self.text=text
    def _schedule(self,_e=None):
        self._cancel(); self._id=self.w.after(self.DELAY,self._show)
    def _cancel(self):
        if self._id:
            try: self.w.after_cancel(self._id)
            except Exception: pass
            self._id=None
    def _show(self):
        if self.tip or not self.text: return
        try:
            x=self.w.winfo_rootx()+12; y=self.w.winfo_rooty()+self.w.winfo_height()+6
            self.tip=_tip_window(self.w,self.text,x,y,wrap=340)
        except Exception:
            self.tip=None
    def _hide(self,_e=None):
        self._cancel()
        if self.tip:
            try: self.tip.destroy()
            except Exception: pass
            self.tip=None

# The "All Keyboard shortcuts" window (F1 / the top-right "? Shortcuts" button) is laid out
# in TWO columns: the launcher's own keys on the left, the 3D viewer's on the right. The
# right column is deliberately a mirror of the viewer's own "Viewer Keyboard shortcuts"
# overlay (mohaa_view.py, #helpCard): SAME groups, SAME order, SAME key column, row for row,
# so the two lists read as one document and neither can quietly drift from the other. Only
# the descriptions differ, and only where context forces it - this window is read from
# OUTSIDE the viewer, so it says "the viewer's control panel" / "close the model" where the
# in-viewer overlay can just say "the control panel" / "close the viewer window". Anything
# added to one MUST be added to the other, in the same place.
HOTKEYS_LAUNCHER=[
 ("","--- Launcher ---"),
 ("Ctrl+O","Add .pk3 pak(s)"),
 ("Ctrl+Shift+O","Open a loose .skd / .tik file"),
 ("Ctrl+F","Focus the search box"),
 ("Esc","Clear search / close a menu / cancel loading"),
 ("F5","Reload all loaded paks"),
 ("Ctrl+T","Toggle Dark / Light theme"),
 ("Ctrl+Shift+T","Use old (OS-default) popup windows on/off"),
 ("F1","Show this shortcut list"),
 ("","--- Pak tree ---"),
 ("Enter","Open file / descend into folder"),
 ("Backspace","Go up one folder"),
 ("Right / Left","Expand / collapse folder"),
 ("Up / Down","Move selection"),
 ("Double-click",".skd / .tik opens in the viewer"),
 ("Ctrl+Click / Shift+Click","Select multiple files / folders (Enter or right-click batch-builds them)"),
 ("Right-click","Pak context menu (view / remove loaded paks)"),
 ("Drag a file off the window","Open it in its own standalone viewer window"),
]
HOTKEYS_VIEWER=[
 ("","--- 3D viewer - camera (click inside the model pane first) ---"),
 ("drag / wheel","Look around / zoom"),
 ("W / S","Move forward / back"),
 ("A / D","Strafe left / right"),
 ("Q / E","Tilt (roll) left / right"),
 ("Space / C","Move up / down"),
 ("Up / Down","Move forward / back"),
 ("Left / Right","Turn (yaw) left / right"),
 ("R","Reset camera"),
 ("V","Toggle Free-look / Tag-lock camera"),
 ("","--- 3D viewer - playback ---"),
 ("P","Play / pause the model & animation"),
 ("F","Freeze / resume everything (same as Play / Pause)"),
 ("[ / ]","Step one frame back / forward"),
 ("Backspace","Reset model & effects to time 0"),
 ("","--- 3D viewer - display toggles ---"),
 ("1 - 7","Texture, Mesh, Wire, Setsizes, Nodes, Labels, Face Anims"),
 ("L","Viewer Light / Dark theme"),
 ("\\","Collapse / expand the viewer's control panel"),
 ("","--- 3D viewer - pop-up lists (animations / surfaces / attach) ---"),
 ("type","Filter the list"),
 ("Up / Down","Move the highlight"),
 ("Enter","Open the highlighted row (or take the top match)"),
 ("Right","Open the highlighted category"),
 ("Left / Backspace","Go back one level"),
 ("Home / End","Jump to the first / last row"),
 ("Esc","Close the list"),
 ("","--- 3D viewer - window ---"),
 ("H or ?","Show / hide the viewer's shortcut overlay"),
 ("Esc","Close the model (back to the start page)"),
]

class App(tk.Tk):
    def __init__(self, initial_file=None):
        super().__init__()
        init_fonts()          # families() needs a live root; picks a real mono per-OS
        self.title("MOHAA Model Viewer")
        self.geometry("1380x820"); self.minsize(1000,600)
        self._cfg=self._load_config(); self._pyexe=find_python()
        self._attach_busy=set()      # attachment keys currently building (see _build_attach)
        self._theme=self._cfg.get("theme","dark")
        if self._theme not in THEMES: self._theme="dark"
        apply_theme(self,self._theme)
        self.configure(bg=BG)
        self._log_q=queue.Queue(); self._drop_paths=[]
        self._status_base="Ready"; self._pak_suffix=""    # status-bar left cell = "<state>  --  N pak(s)"
        self._upd_state=None; self._upd_dl_btn=None        # Check-for-updates window state
        # Output-console mirror: every line shown in the Output pane is also appended to
        # output_console.log in the program's write folder (DATADIR - the 'output' folder
        # in the shipped layout, else beside the .py files). Opened in "w" so it starts
        # fresh each launch; line-buffered so a crash still leaves the log on disk.
        # Best-effort - a read-only folder just disables the mirror.
        self._logfile=None
        try:
            self._logfile=open(os.path.join(DATADIR,"output_console.log"),"w",
                               encoding="utf-8",buffering=1)
        except Exception:
            self._logfile=None
        self._pk3_paths=[]; self._tmp=None; self._animroot=None
        self._vfs=None; self._SH=None; self._TI=None; self._GS=None; self._PROPS=None; self._tex_ready=False; self._tex_gen=0
        self._tree_entry={}
        self._all_files=[]           # (relpath, kind) kind in {"skd","tik"} from the last pak scan
        self._filter_after=None
        self._tips=[]                # Tooltip instances (retext not needed; colours read at show time)
        self._auto_open=tk.BooleanVar(value=bool(self._cfg.get("auto_open",True)))
        self._remember=tk.BooleanVar(value=bool(self._cfg.get("remember_paks",True)))
        self._theme_var=tk.StringVar(value=self._theme)
        self._outdir_on=tk.BooleanVar(value=bool(self._cfg.get("outdir_enabled",True)))
        self._outdir=self._cfg.get("outdir") or os.path.join(DATADIR,"models")
        self._run_opts={}          # one-shot per-build viewer options (right-click open)
        self._last_build=None      # (path,animroot,manifest,emittex,subdir) of the last build
        self._last_info=None       # (path,stdout,html_path) of the last info render, re-run on theme toggle
        self._last_subdir=None     # pak-relative output subfolder of the last build
        self._reuse_html=tk.BooleanVar(value=bool(self._cfg.get("reuse_html",True)))
        self._no_recent=tk.BooleanVar(value=bool(self._cfg.get("no_recent",False)))
        # embedded 3D viewer pane (WebView2). Created lazily on first open so a
        # broken install can never block startup - failures fall back to browser.
        self._embed_on=tk.BooleanVar(value=bool(self._cfg.get("embed_viewer",True)))
        # Animation catalogue: the model's whole animation reach, resolved through its
        # $include / $path / includes{} structure. Only models at or under this count
        # get every animation baked into the page; above it the page ships the menu and
        # each animation is built on first click into the cache folder beside the HTML.
        self._anim_preload=tk.StringVar(value=str(self._cfg.get("anim_preload",150)))
        self._animcat=None          # the catalogue dict for the model now on screen
        self._animcat_file=None     # ...written out as JSON for mohaa_view.py
        self._animcat_for=None      # ...and the model path it belongs to
        self._anim_outdir=None      # <html stem>/ - where built animations are cached
        self._anim_busy=set()       # ids currently building, so a double-click is one build
        self._webview=None; self._embed_url=None
        # external programs: text editor (platform default) + legacy model viewer (unset)
        if not self._cfg.get("text_editor"):
            self._cfg["text_editor"]=("notepad.exe" if sys.platform.startswith("win")
                                      else ("open" if sys.platform=="darwin" else "xdg-open"))
        self._menus=[]; self._menubtns=[]      # themed menubar parts, recoloured on toggle
        self._treetip=None; self._treetip_row=None       # armed-hover tree tooltip
        self._treetip_after=None; self._treetip_armed=None
        global OLD_POPUPS
        self._old_popups=tk.BooleanVar(value=bool(self._cfg.get("old_popups",False)))
        OLD_POPUPS=bool(self._old_popups.get())
        self._open_popup=None; self._popup_owner=None; self._popup_serial=None
        self._batch=[]; self._batch_total=0; self._batch_waiting=False   # sequential folder builds
        # Escape-to-cancel state: the running viewer subprocess, the model name
        # currently being built, and a build generation counter - extraction/build
        # threads capture the counter and bail out when it changes (cancel).
        self._proc=None; self._building_name=None; self._build_gen=0
        # open-in-viewer serialization latch: True while a build that WILL open
        # the viewer is in flight. New open requests are rejected until it clears
        # (stops spam-clicking a file from stacking tabs/builds). Build-only work
        # (right-click "Build only", batch builds) neither sets nor checks this.
        self._opening_view=False
        # a pk3 open requested before the texture/VFS index finished: latched here
        # and fired automatically by _poll_log the moment the index is ready. Stored
        # as (entry, build_gen) so an Escape-cancel (which bumps build_gen) drops it.
        self._pending_open=None
        # persistent dismiss checks: clicking outside an open custom popup closes it
        self.bind_all("<ButtonPress-1>",self._popup_dismiss_check,add="+")
        self.bind_all("<ButtonPress-3>",self._popup_dismiss_check,add="+")
        # keyboard reclaim: clicking any launcher widget while the embedded
        # WebView2 pane holds the Win32 keyboard takes typing + launcher hotkeys
        # back (see _reclaim_focus). Clicks on the viewer pane never reach Tk, so
        # Chromium keeps the keyboard there and viewer hotkeys stay active.
        self.bind_all("<ButtonPress-1>",self._reclaim_focus,add="+")
        self.bind_all("<ButtonPress-3>",self._reclaim_focus,add="+")
        # move / minimize dismissal: a moved or minimized window leaves hover tooltips
        # and right-click / menubar popups stranded at stale screen coordinates. <Configure>
        # on the toplevel fires on move+resize, <Unmap> on minimize - both close every
        # transient overlay (see _dismiss_transients).
        self.bind("<Configure>",self._dismiss_transients,add="+")
        self.bind("<Unmap>",self._dismiss_transients,add="+")
        # focus-loss dismissal: a PopupMenu is an overrideredirect + -topmost Toplevel,
        # so switching to another desktop app (Notepad, a browser) left the drop-down
        # painted on top of it. <FocusOut> on the toplevel catches that switch.
        self.bind("<FocusOut>",self._popup_focus_out,add="+")
        _win_dark_menus(self._theme=="dark")
        self._build_menu(); self._build_ui(); self._bind_hotkeys(); self._poll_log()
        self.after(150,self._enable_win_drop)
        self.after(250,self._apply_titlebar)
        self.protocol("WM_DELETE_WINDOW",self._on_close)
        # migrate old single-pk3 config to the multi-pk3 list
        saved=self._cfg.get("pk3s")
        if not saved and self._cfg.get("pk3"): saved=[self._cfg["pk3"]]
        saved=[p for p in (saved or []) if os.path.exists(p)]
        if saved and self._remember.get(): self.after(200,lambda:self._add_pk3s(saved))
        if initial_file: self.after(350,lambda:self._load(initial_file))

    # ------------------------------------------------------------- config ---
    def _load_config(self):
        try: return json.load(open(CONFIG,encoding="utf-8"))
        except Exception: return {}
    def _set_view_angles(self,raw):
        """Remember the viewer's Pitch/Yaw/Roll placement dial in mohaa_viewer_config.json.

        The viewer posts "mohaa-ang <pitch>,<yaw>,<roll>" (degrees) whenever the slider
        moves; _open_file hands the saved triple back on the page's #ang= boot hash so the
        next model opens already rotated. Values are normalised to the four quarter turns
        the dial offers, and an unchanged triple is dropped so dragging the slider does not
        rewrite the config file on every detent."""
        try: v=[int(round(float(x))) for x in str(raw).split(",")[:3]]
        except Exception: return
        if len(v)!=3: return
        # floor(x/90) on the +45 bias, NOT round(): Python's round() is banker's rounding
        # (round(0.5)==0) while the viewer's JS quantiser is Math.round (half up), so the two
        # would disagree on exact half-detents. Floor division agrees with JS on both signs.
        v=[(((x+45)//90*90)%360+360)%360 for x in v]
        if self._cfg.get("view_angles")==v: return
        self._cfg["view_angles"]=v; self._save_config()

    def view_angles(self):
        """The saved (pitch,yaw,roll) triple, or None when the model sits unrotated."""
        v=self._cfg.get("view_angles")
        if not (isinstance(v,(list,tuple)) and len(v)==3): return None
        try: v=[int(x)%360 for x in v]
        except Exception: return None
        return v if any(v) else None

    def _save_config(self):
        try: json.dump(self._cfg,open(CONFIG,"w",encoding="utf-8"),indent=2)
        except Exception: pass

    # ------------------------------------------------------------ menubar ---
    def _mkmenu(self, parent=None, persistent=True):
        """A tk.Menu coloured for the active theme. Persistent menus (menubar, recent,
        theme cascade) are tracked and recoloured on toggle; one-shot context menus
        are built fresh each popup so they pick the current palette here."""
        m=tk.Menu(parent or self,tearoff=0,bg=PANEL,fg=TXT,activebackground=SEL_BG,
                  activeforeground=ACCENT,disabledforeground=DIM,bd=0,relief="flat",font=FONT_SMALL)
        if persistent: self._menus.append(m)
        return m

    def _build_menu(self):
        # custom themed menubar: Windows' native menu bar can't be recoloured by Tk,
        # so File/Options/View/Help are Menubuttons on a themed frame. Their drop-downs
        # (and every context menu) are custom PopupMenus so even the BORDER follows the
        # theme - unless "Use old popup windows" is checked, which posts native tk.Menus.
        bar=tk.Frame(self,bg=PANEL); bar.pack(fill="x",side="top"); self._menubar=bar
        self._menubar_line=tk.Frame(self,bg=LINE,height=1); self._menubar_line.pack(fill="x",side="top")
        def addbtn(label,provider,ul=0):
            b=tk.Menubutton(bar,text=label,underline=ul,bg=PANEL,fg=TXT,
                            activebackground=SEL_BG,activeforeground=ACCENT,bd=0,relief="flat",
                            padx=10,pady=3,highlightthickness=0,font=FONT_MONO,cursor="hand2")
            def _post(e,pv=provider,bb=b,name=label):
                self._post_menu(pv(),bb.winfo_rootx(),bb.winfo_rooty()+bb.winfo_height(),
                                owner=name,event=e)
                return "break"
            b.bind("<Button-1>",_post)
            def _hover(e,pv=provider,bb=b,name=label):
                # once a menubar menu is open, sliding along the bar switches menus
                if self._open_popup is not None and self._popup_owner and self._popup_owner!=name:
                    self._post_menu(pv(),bb.winfo_rootx(),bb.winfo_rooty()+bb.winfo_height(),
                                    owner=name,event=None)
            b.bind("<Enter>",_hover)
            b.pack(side="left"); self._menubtns.append(b); return b
        addbtn("File",self._menu_items_file)
        addbtn("Options",self._menu_items_options)
        addbtn("View",self._menu_items_view)
        addbtn("Help",self._menu_items_help)

    # ---- menu definitions (built fresh at every open, so Recent etc. stay live) ----
    def _menu_items_file(self):
        # housekeeping rows: "(empty)" rides the dim right-hand accelerator column and
        # the row is disabled when there is genuinely nothing to delete.
        bempty = not self._built_any()
        tempty = not self._temp_dirs()
        # "Close file" is the menu twin of the viewer's Esc: both call _close_viewer(), which
        # reverts the middle pane to the start page while KEEPING _last_build, so the top
        # "Open Viewer" button can reopen the same model instantly. Only meaningful for the
        # embedded pane - a model sent to the external browser is that browser's tab to close -
        # so the row is disabled unless a WebView2 is actually up.
        vopen = self._webview is not None
        return [_mi("Add .pk3 pak(s)...",self._choose_pk3,"Ctrl+O"),
                _mi("Open File...",self._browse_and_run,"Ctrl+Shift+O"),
                {"type":"cascade","label":"Recent files","items":self._menu_items_recent},
                _MSEP,
                _mi("Close file",self._close_viewer,"Esc","normal" if vopen else "disabled"),
                _MSEP,
                _mi("Reload paks",self._reload_all_cmd,"F5"),
                _mi("Clear all paks",self._clear_pk3s),
                _MSEP,
                _mi("Clear built models",self._clear_built_models,
                    "(empty)" if bempty else None, "disabled" if bempty else "normal"),
                _mi("Clear %temp% files",self._clear_temp_files,
                    "(empty)" if tempty else None, "disabled" if tempty else "normal"),
                _MSEP,
                _mi("Exit",self._on_close)]

    def _menu_items_recent(self):
        rec=[p for p in self._cfg.get("recent",[]) if os.path.exists(p)]
        if not rec: return [_mi("(empty)",state="disabled")]
        items=[_mi(os.path.basename(p)+"   "+os.path.dirname(p),(lambda pp=p:self._load(pp)))
               for p in rec[:10]]
        return items+[_MSEP,_mi("Clear recent",self._clear_recent)]

    def _menu_items_options(self):
        return [{"type":"cascade","label":"Theme","items":lambda:[
                    {"type":"radio","label":"Dark","variable":self._theme_var,"value":"dark",
                     "command":lambda:self._set_theme("dark")},
                    {"type":"radio","label":"Light","variable":self._theme_var,"value":"light",
                     "command":lambda:self._set_theme("light")}]},
                _MSEP,
                {"type":"check","label":"Remember loaded paks between sessions","variable":self._remember,"command":self._save_opts},
                {"type":"check","label":"Auto-open viewer after build","variable":self._auto_open,"command":self._save_opts},
                {"type":"check","label":"Embed 3D viewer in this window (needs tkwebview2)","variable":self._embed_on,"command":self._toggle_embed},
                {"type":"check","label":"Don't save recent files (empty all)","variable":self._no_recent,"command":self._toggle_no_recent},
                _MSEP,
                {"type":"cascade","label":"Bake at most N of a .tik's own animations into the page","items":lambda:[
                    {"type":"radio","label":"0  (always build on click)","variable":self._anim_preload,"value":"0","command":self._save_opts},
                    {"type":"radio","label":"24","variable":self._anim_preload,"value":"24","command":self._save_opts},
                    {"type":"radio","label":"60","variable":self._anim_preload,"value":"60","command":self._save_opts},
                    {"type":"radio","label":"150  (default)","variable":self._anim_preload,"value":"150","command":self._save_opts},
                    {"type":"radio","label":"400","variable":self._anim_preload,"value":"400","command":self._save_opts}]},
                _MSEP,
                {"type":"check","label":"Save viewer HTML to output folder","variable":self._outdir_on,"command":self._save_opts},
                {"type":"check","label":"Load already-built HTML from output folder (skip rebuild)","variable":self._reuse_html,"command":self._save_opts},
                _mi("Change output folder...",self._change_outdir),
                _mi("Open output folder",self._open_outdir),
                _MSEP,
                _mi("Change Text Editor...",lambda:self._change_program("text_editor","Text Editor")),
                _mi("Open Text Editor folder",lambda:self._open_program_folder("text_editor","Text Editor")),
                _MSEP,
                _mi("Change Legacy Model Viewer...",lambda:self._change_program("legacy_viewer","Legacy Model Viewer")),
                _mi("Open Legacy Model Viewer folder",lambda:self._open_program_folder("legacy_viewer","Legacy Model Viewer"))]

    def _menu_items_view(self):
        return [_mi("Expand all folders",lambda:self._expand_all(True)),
                _mi("Collapse all folders",lambda:self._expand_all(False)),
                _MSEP,
                _mi("Toggle Dark / Light",self._toggle_theme,"Ctrl+T"),
                {"type":"check","label":"Use old popup windows","variable":self._old_popups,
                 "command":self._toggle_old_popups,"accel":"Ctrl+Shift+T"}]

    def _menu_items_help(self):
        return [_mi("Keyboard shortcuts",self._show_hotkeys,"F1"),
                _MSEP,
                _mi("Check for updates...",self._check_for_updates),
                _MSEP,
                _mi("Privacy & Legal",self._show_privacy),
                _mi("About",self._show_about)]

    def _menu_items_pak(self):
        """Pak management: on the pak header label and empty tree space."""
        items=[]
        if self._pk3_paths:
            items.append({"type":"cascade","label":"Remove a pak","items":lambda:[
                _mi(os.path.basename(p),(lambda pp=p:self._remove_pak(pp))) for p in self._pk3_paths]})
        items.append(_mi("Add a pak...",self._choose_pk3,"Ctrl+O"))
        if self._pk3_paths:
            items.append(_mi("Reload paks",self._reload_all_cmd,"F5"))
            items.append(_mi("Clear all paks",self._clear_pk3s))
        return items

    # ---- posting + dismissal ---------------------------------------------------
    def _post_menu(self, items, x, y, owner=None, event=None):
        """Show a menu: custom themed PopupMenu normally, native tk.Menu (OS default
        colours/font) when 'Use old popup windows' is on. Clicking the owning menubar
        button again toggles the menu closed."""
        self._hide_treetip()
        if OLD_POPUPS:
            m=tk.Menu(self,tearoff=0)
            self._fill_native(m,items)
            try: m.tk_popup(x,y)
            finally: m.grab_release()
            return
        if self._open_popup is not None:
            same=(owner is not None and self._popup_owner==owner)
            self._open_popup.unpost()
            if same: return                      # toggle-close on the same button
        pm=PopupMenu(self,items)
        self._open_popup=pm; self._popup_owner=owner
        self._popup_serial=getattr(event,"serial",None) if event is not None else None
        pm.post(x,y)

    def _fill_native(self,m,items):
        for it in items:
            t=it.get("type","command")
            if t=="separator": m.add_separator()
            elif t=="check": m.add_checkbutton(label=it["label"],variable=it["variable"],command=it.get("command"))
            elif t=="radio": m.add_radiobutton(label=it["label"],variable=it["variable"],value=it.get("value"),command=it.get("command"))
            elif t=="cascade":
                sub=tk.Menu(m,tearoff=0)
                sit=it.get("items"); sit=sit() if callable(sit) else sit
                self._fill_native(sub,sit)
                m.add_cascade(label=it["label"],menu=sub)
            else: m.add_command(label=it["label"],command=it.get("command"),
                                accelerator=it.get("accel"),state=it.get("state","normal"))

    def _popup_dismiss_check(self,e):
        pm=self._open_popup
        if pm is None: return
        if self._popup_serial is not None and getattr(e,"serial",None)==self._popup_serial:
            return                               # the click that opened this menu
        if pm.contains(e.x_root,e.y_root): return
        pm.unpost()

    def _popup_escape(self,_e=None):
        if self._open_popup is not None: self._open_popup.unpost()

    def _dismiss_transients(self,e=None):
        """Close every transient overlay - open right-click / menubar popup, the armed
        tree tooltip, and any live hover tooltip - when the window is moved or minimized.
        Bound to <Configure> (move/resize) and <Unmap> (minimize). Only reacts to events
        on the toplevel itself (child <Configure> events from sash drags etc. have a
        different widget and are ignored) so it never fights normal in-window resizing."""
        if e is not None and getattr(e,"widget",None) not in (self,None): return
        try:
            if self._open_popup is not None: self._open_popup.unpost()
        except Exception: pass
        try: self._hide_treetip()
        except Exception: pass
        for t in getattr(self,"_tips",()):
            try: t._hide()
            except Exception: pass

    def _popup_focus_out(self,_e=None):
        """Close menus/tooltips when the LAUNCHER loses focus to another desktop window.

        <FocusOut> also fires for focus moves *inside* the app (child widgets, the
        embedded WebView2 pane, a popup's own Toplevel), so the decision is deferred
        one tick and then asks Tk who owns the focus now: focus_displayof() returns
        None only when no window of this application holds it."""
        if self._open_popup is None and not getattr(self,"_tips",None): return
        def _check():
            try:
                if self.focus_displayof() is not None: return   # still inside the launcher
            except Exception: return                            # unknown -> leave it alone
            self._dismiss_transients()
        try: self.after(60,_check)
        except Exception: pass

    # ---- housekeeping: built output + %TEMP% workspaces -----------------------
    @staticmethod
    def _dir_size(path):
        n=0
        for dp,_dn,fn in os.walk(path):
            for f in fn:
                try: n+=os.path.getsize(os.path.join(dp,f))
                except OSError: pass
        return n

    @staticmethod
    def _fmt_bytes(n):
        f=float(n)
        for u in ("B","KB","MB"):
            if f<1024.0: return ("%d %s"%(int(f),u)) if u=="B" else ("%.1f %s"%(f,u))
            f/=1024.0
        return "%.2f GB"%f

    # Folders a "Clear built models" must never rmtree, however the output folder got
    # pointed at them. The dialog does say it deletes the whole folder, but one mis-set
    # Options --> output folder plus one confirmation click should not be able to take
    # out Documents or a home directory - the delete is recursive and unrecoverable.
    def _unsafe_to_wipe(self, d):
        try: d=os.path.abspath(d)
        except Exception: return "unresolvable path"
        parent,leaf=os.path.split(d.rstrip(os.sep))
        if not leaf: return "a drive/filesystem root"
        if os.path.dirname(d.rstrip(os.sep))==d.rstrip(os.sep): return "a drive/filesystem root"
        home=os.path.abspath(os.path.expanduser("~"))
        if os.path.normcase(d)==os.path.normcase(home): return "your home folder"
        for name in ("desktop","documents","downloads","pictures","music","videos",
                     "onedrive","dropbox","program files","program files (x86)","windows",
                     "system32","users","applications","library","etc","usr","bin","var"):
            if os.path.normcase(leaf)==os.path.normcase(name): return "a system/user folder (%s)"%leaf
        # Only ever created BY us, so requiring the name is a cheap, exact guard.
        if os.path.normcase(leaf) not in ("models","standalone"):
            return "not a 'models' or 'standalone' folder built by this program"
        return None

    def _built_roots(self):
        """The two folders built viewers are written to: the models output folder
        (_html_out_path) and its sibling 'standalone' folder (_standalone_dir, used
        for STANDALONE_SUBDIR builds)."""
        roots=[]
        for d in (self._outdir, self._standalone_dir()):
            try:
                d=os.path.abspath(d)
                if os.path.isdir(d) and d not in roots: roots.append(d)
            except Exception: pass
        return roots

    def _built_scan(self):
        """Everything this launcher BUILDS, and nothing else. Only two artefact shapes
        are ever written into the output folder: '<stem>_skd_view.html' /
        '<stem>_tik_view.html' (_viewer_html_name) and the matching '<stem>_..._view/'
        folder that caches on-demand animations (_anim_outdir = the html path minus its
        extension, a*.js inside). Anything else there is the user's own file and is
        deliberately left alone. Returns (files, dirs, total_bytes)."""
        files=[]; dirs=[]; nb=0
        for root in self._built_roots():
            for dp,dn,fn in os.walk(root):
                for f in fn:
                    if f.lower().endswith("_view.html"):
                        fp=os.path.join(dp,f); files.append(fp)
                        try: nb+=os.path.getsize(fp)
                        except OSError: pass
                for d in list(dn):
                    if d.lower().endswith("_view"):
                        dpp=os.path.join(dp,d); dirs.append(dpp); nb+=self._dir_size(dpp)
                        dn.remove(d)                 # never descend into a folder we delete whole
        return files,dirs,nb

    def _built_any(self):
        """Cheap 'is there anything to clear?' probe for the File-menu label: stops at
        the first artefact instead of sizing the whole output tree on every menu open."""
        for root in self._built_roots():
            for _dp,dn,fn in os.walk(root):
                if any(f.lower().endswith("_view.html") for f in fn): return True
                if any(d.lower().endswith("_view") for d in dn): return True
        return False

    def _temp_dirs(self):
        """Every workspace this tool has ever created: %TEMP%/mohaaview_* - the
        tempfile.mkdtemp(prefix='mohaaview_') made in _reload_all. Includes leftovers
        from previous or crashed sessions, which is usually most of them."""
        try: base=tempfile.gettempdir()
        except Exception: return []
        out=[]
        try:
            for d in sorted(glob.glob(os.path.join(glob.escape(base),"mohaaview_*"))):
                if os.path.isdir(d): out.append(d)
        except Exception: pass
        return out

    def _clear_built_models(self):
        files,dirs,nb=self._built_scan()
        roots=self._built_roots()
        if not roots or (not files and not dirs):
            self._log_line("Clear built models: nothing to clear.","dim"); return
        lines=[("Clear built models","title"),
               ("Delete the entire output folder(s) below,","body"),
               ("including the 'models' and 'standalone' folders themselves?","body"),
               ("","dim")]
        for r in roots: lines.append(("    "+r,"dim"))
        lines.append(("","dim"))
        lines.append(("%d built viewer file(s) + %d animation-cache folder(s) - %s total."
                      % (len(files),len(dirs),self._fmt_bytes(nb)),"dim"))
        lines.append(("","dim"))
        lines.append(("The 3D viewer will close and return to the start page.","dim"))
        if not self._confirm_dialog("Clear built models",lines,ok_text="Delete"): return
        self._close_viewer()          # can't leave a page open whose files are being deleted
        # the builds are gone, so there is nothing for Open Viewer to reopen: drop the
        # remembered build and reset the path bar (otherwise it would show a stale
        # "pk3 model: <n>" whose HTML no longer exists).
        self._last_build=None
        try: self._path_var.set("")
        except Exception: pass
        n=0
        for root in roots:
            why=self._unsafe_to_wipe(root)
            if why:
                self._log_line("  refused to delete %s - %s"%(root,why),"err"); continue
            shutil.rmtree(root,ignore_errors=True)
            if not os.path.isdir(root): n+=1
            else: self._log_line("  could not delete %s"%root,"err")
        self._log_line("Cleared built models: %d folder(s) removed, %s freed."
                       % (n,self._fmt_bytes(nb)),"ok")

    def _own_pycache(self):
        """This program's OWN __pycache__ next to the .py files (HERE), and only that.
        The launcher does `import mohaa_textures / mohaa_view`, so CPython writes
        __pycache__/mohaa_*.cpython-XX.pyc beside the scripts. It is an install artefact,
        not a built-model or %TEMP% file, and Python regenerates it on next run - but a
        user wanting a clean 'reinstall' state expects it gone, so a temp-clear removes
        it. Guarded to fire ONLY when the folder actually holds one of our modules, so an
        unrelated __pycache__ is never touched."""
        pc=os.path.join(HERE,"__pycache__")
        if not os.path.isdir(pc): return None
        try: names=os.listdir(pc)
        except OSError: return None
        ours=("mohaa_view","mohaa_textures","mohaa_launcher")
        if any(any(nm.startswith(o+".") for o in ours) for nm in names): return pc
        return None

    def _clear_temp_files(self):
        dirs=self._temp_dirs()
        pyc=self._own_pycache()
        if not dirs and not pyc:
            self._log_line("Clear %temp% files: nothing to clear.","dim"); return
        nb=sum(self._dir_size(d) for d in dirs)+(self._dir_size(pyc) if pyc else 0)
        live=os.path.abspath(self._tmp) if self._tmp else None
        has_live=bool(live) and any(os.path.abspath(d)==live for d in dirs)
        lines=[("Clear %temp% files","title"),
               ("Delete %d workspace folder(s)  (%s)  from:" % (len(dirs),self._fmt_bytes(nb)),"body"),
               ("","dim"),
               ("    "+tempfile.gettempdir(),"dim"),
               ("","dim"),
               ("These are the mohaaview_* folders created for extracted models,","dim"),
               ("animations and texture manifests.","dim")]
        if pyc:
            lines.append(("","dim"))
            lines.append(("Also clears this program's __pycache__ (compiled .pyc), for a","dim"))
            lines.append(("clean reinstall state - Python rebuilds it on next launch.","dim"))
        if has_live:
            lines.append(("","dim"))
            lines.append(("One is the CURRENT session's workspace: clearing it re-extracts","dim"))
            lines.append(("the loaded paks, so the tree will re-index.","dim"))
        if not self._confirm_dialog("Clear %temp% files",lines,ok_text="Delete"): return
        n=0
        for d in dirs:
            if live and os.path.abspath(d)==live: continue
            shutil.rmtree(d,ignore_errors=True)
            if not os.path.isdir(d): n+=1
        if has_live:
            if self._pk3_paths:
                self._reload_all()                  # rmtree + fresh mkdtemp + re-index
            else:
                shutil.rmtree(live,ignore_errors=True)
                try:
                    self._tmp=tempfile.mkdtemp(prefix="mohaaview_")
                    self._animroot=os.path.join(self._tmp,"models")
                except Exception:
                    self._tmp=None; self._animroot=None
            n+=1
        pn=0
        if pyc:
            shutil.rmtree(pyc,ignore_errors=True)
            if not os.path.isdir(pyc): pn=1
        self._log_line("Cleared %%temp%% files: %d workspace folder(s)%s, %s freed."
                       % (n,(" + __pycache__" if pn else ""),self._fmt_bytes(nb)),"ok")

    def _save_panes(self):
        """Persist the three sash positions so the layout is restored next launch.
        Horizontal panes (outer, bottomrow) store the sash X; the vertical pane
        (rightside) stores the sash Y. Called from _on_close before teardown."""
        try:
            outer,rightside,bottomrow=self._panes
            self._cfg["panes"]={"tree":int(outer.sash_coord(0)[0]),
                                "bottom":int(rightside.sash_coord(0)[1]),
                                "console":int(bottomrow.sash_coord(0)[0])}
            self._save_config()
        except Exception: pass

    def _restore_panes(self):
        """Re-place the sashes at the saved positions. The panes are nested (bottomrow
        lives inside rightside, which lives inside outer), so a sash must only be placed
        after its container's geometry has settled - otherwise it is laid out against a
        stale width/height and drifts. Placement therefore goes outermost-first with an
        update between each. sash_place clamps to each pane's minsize, so a value that no
        longer fits the current window size lands at the nearest legal spot. Idempotent."""
        p=self._cfg.get("panes")
        if not p: return
        try: outer,rightside,bottomrow=self._panes
        except Exception: return
        self.update_idletasks()
        if "tree" in p:
            try: outer.sash_place(0,int(p["tree"]),0); self.update_idletasks()
            except Exception: pass
        if "bottom" in p:
            try: rightside.sash_place(0,0,int(p["bottom"])); self.update_idletasks()
            except Exception: pass
        if "console" in p:
            try: bottomrow.sash_place(0,int(p["console"]),0); self.update_idletasks()
            except Exception: pass

    def _toggle_old_popups(self):
        global OLD_POPUPS
        OLD_POPUPS=bool(self._old_popups.get())
        self._cfg["old_popups"]=OLD_POPUPS; self._save_config()
        if self._open_popup is not None: self._open_popup.unpost()

    def _toggle_old_popups_hotkey(self,_e=None):
        self._old_popups.set(not self._old_popups.get()); self._toggle_old_popups()
        self._log_line("Old popup windows: "+("ON" if OLD_POPUPS else "OFF"),"dim")

    def _toggle_no_recent(self):
        if self._no_recent.get():
            self._cfg["recent"]=[]          # empty all, and stop recording while checked
        self._save_opts()

    def _save_opts(self):
        self._cfg["reuse_html"]=bool(self._reuse_html.get())
        self._cfg["no_recent"]=bool(self._no_recent.get())
        self._cfg["outdir_enabled"]=bool(self._outdir_on.get())
        self._cfg["outdir"]=self._outdir
        self._cfg["auto_open"]=bool(self._auto_open.get())
        self._cfg["embed_viewer"]=bool(self._embed_on.get())
        try: self._cfg["anim_preload"]=int(self._anim_preload.get())
        except (TypeError,ValueError): self._cfg["anim_preload"]=150
        self._cfg["remember_paks"]=bool(self._remember.get())
        if not self._remember.get(): self._cfg["pk3s"]=[]
        else: self._cfg["pk3s"]=self._pk3_paths
        self._save_config()

    def _clear_recent(self):
        self._cfg["recent"]=[]; self._save_config()

    def _push_recent(self,path):
        if self._no_recent.get(): return                       # user opted out of recent files
        if self._tmp and path.startswith(self._tmp): return    # pak-extracted temp files aren't reopenable
        rec=self._cfg.get("recent",[])
        rec=[p for p in rec if os.path.normcase(p)!=os.path.normcase(path)]
        rec.insert(0,path); self._cfg["recent"]=rec[:10]; self._save_config()

    # ----------------------------------------------------------------- UI ---
    def _tip(self,widget,text):
        t=Tooltip(widget,text); self._tips.append(t); return t

    def _mkbtn(self,parent,**kw):
        tiptext=kw.pop("tip",None)
        b=ttk.Button(parent,cursor="hand2",**kw)
        if tiptext: self._tip(b,tiptext)
        return b

    def _build_ui(self):
        # ---- top bar (diagram row 1): title . model path . Browse . Open Viewer
        #      . tool buttons (Add-pak + search live in the left panel) -----------
        top=ttk.Frame(self); top.pack(fill="x",padx=10,pady=(8,6))
        ttk.Label(top,text="MOHAA Model Viewer",style="Title.TLabel").pack(side="left")
        self._theme_btn=self._mkbtn(top,text="\u25d0 Theme",style="Tool.TButton",command=self._toggle_theme,
                                    tip="Toggle Dark / Light theme.\n(Ctrl+T)")
        self._theme_btn.pack(side="right")
        self._help_btn=self._mkbtn(top,text="? Shortcuts",style="Tool.TButton",command=self._show_hotkeys,
                                   tip="Show all keyboard shortcuts.\n(F1)")
        self._help_btn.pack(side="right",padx=(0,6))
        # selected model path + open controls
        self._path_var=tk.StringVar()
        self._path_entry=tk.Entry(top,textvariable=self._path_var,bg=PANEL,fg=TXT,insertbackground=TXT,
                                  highlightbackground=LINE,highlightcolor=ACCENT,highlightthickness=1,
                                  relief="flat",font=FONT_MONO)
        self._path_entry.pack(side="left",fill="x",expand=True,padx=(10,4),pady=2,ipady=3)
        self._tip(self._path_entry,"Selected model / effect.\nPaste a full path here, pick from the tree,\nor drag a .skd/.tik onto this window.")
        self._mkbtn(top,text="Browse...",command=self._browse,
                    tip="Pick a loose .skd model or .tik effect from disk.\n(Ctrl+Shift+O)").pack(side="left",padx=(0,4))
        self._mkbtn(top,text="\u25b6 Open Viewer",style="Accent.TButton",command=self._run,
                    tip="Build the HTML viewer for the selected file and show it in the middle pane\n(also runs on double-click / Enter in the tree)").pack(side="left",padx=(0,14))
        self._lines=[tk.Frame(self,bg=LINE,height=1)]; self._lines[0].pack(fill="x",padx=8)
        body=ttk.Frame(self); body.pack(fill="both",expand=True,padx=10,pady=8)

        # Resizable layout (see diagram): three draggable dividers built from nested
        # tk.PanedWindows -
        #   outer     (horizontal): [ file tree | rightside ]
        #   rightside (vertical)  : [ 3D viewer (top) / bottom row ]
        #   bottomrow (horizontal): [ output console | model-info panel ]
        # The output console and the model-info panel share ONE top edge - the rightside
        # vertical sash - because both live inside the single 'bottomrow' pane. Dragging
        # that sash moves both their ceilings together, so no empty gap can open between
        # the viewer and them ("upper ceilings stay connected"). tk (not ttk) panes so the
        # sash colour follows the theme and shows a grabbable handle; refs in self._panes
        # are recoloured on theme toggle. minsize on every pane stops a divider being
        # dragged far enough to swallow a neighbour.
        _pw=dict(bg=LINE,bd=0,sashwidth=6,sashpad=0,sashrelief="flat",
                 showhandle=False,opaqueresize=True)
        outer=tk.PanedWindow(body,orient="horizontal",**_pw); outer.pack(fill="both",expand=True)
        rightside=tk.PanedWindow(outer,orient="vertical",**_pw)
        bottomrow=tk.PanedWindow(rightside,orient="horizontal",**_pw)
        self._panes=[outer,rightside,bottomrow]

        # ---- left panel (diagram col 1): full-height pak file tree ----------
        left=ttk.Frame(outer,style="Panel.TFrame",width=300)
        # row 1: the pak summary label gets the whole row, so it never runs into a button
        lh=ttk.Frame(left,style="Panel.TFrame"); lh.pack(fill="x",padx=8,pady=(8,2))
        self._pk3_label=ttk.Label(lh,text="No .pk3 loaded",style="PanelDim.TLabel",cursor="hand2")
        self._pk3_label.pack(side="left")
        self._pk3_label.bind("<Button-3>",self._show_pak_menu)
        self._tip(self._pk3_label,"Right-click to list / manage every loaded Pak")
        # row 2: search box filtering the pak tree + the Add-pak button. Button is
        # packed FIRST so it always keeps its full size; the entry expands into
        # whatever is left.
        sr=ttk.Frame(left,style="Panel.TFrame"); sr.pack(fill="x",padx=8,pady=(2,4))
        self._mkbtn(sr,text="Add .pk3(s)...",command=self._choose_pk3,
                    tip="Add one or more MOHAA pak files (Pak0.pk3, Pak2.pk3, expansions...).\nLater paks override earlier ones.\n(Ctrl+O)").pack(side="right")
        self._search_var=tk.StringVar()
        self._search_hint=ttk.Label(sr,text="\u2315",style="PanelDim.TLabel"); self._search_hint.pack(side="right",padx=(6,10))
        self._search=ttk.Entry(sr,textvariable=self._search_var)
        self._search.pack(side="left",fill="x",expand=True)
        self._tip(self._search,"Filter the tree by name (e.g. 'panzer', 'fire', '.tik').\nCtrl+F focuses.\nEsc clears (only while the search bar is focused).")
        self._search.bind("<KeyRelease>",self._on_search)
        self._search.bind("<Escape>",lambda e:(self._search_var.set(""),self._rebuild_tree(),self._tree.focus_set()))
        treewrap=ttk.Frame(left,style="Panel.TFrame"); treewrap.pack(fill="both",expand=True,padx=6,pady=(0,8))
        self._tree=ttk.Treeview(treewrap,show="tree",selectmode="extended")   # Ctrl/Shift multi-select
        tsb=ttk.Scrollbar(treewrap,command=self._tree.yview); self._tree.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right",fill="y"); self._tree.pack(side="left",fill="both",expand=True)
        self._retheme_tree_tags()
        self._tree.bind("<Double-1>",self._on_tree_activate)
        self._tree.bind("<<TreeviewSelect>>",self._on_tree_select)
        self._tree.bind("<Return>",self._on_tree_enter)
        self._tree.bind("<BackSpace>",self._on_tree_backspace)
        self._tree.bind("<Button-3>",self._show_pak_menu)
        # click-again tooltips: shown only when single-clicking a row that is ALREADY
        # selected (and only while still hovering that row) - no hover-spam.
        self._tree.bind("<Button-1>",self._on_tree_click,add="+")
        self._tree.bind("<Motion>",self._on_tree_motion,add="+")
        self._tree.bind("<Leave>",lambda e:self._hide_treetip(),add="+")
        # drag-out: press a file row, drag OUTSIDE the launcher window, release ->
        # the model opens in its own standalone browser viewer window, so several
        # models can be viewed side by side.
        self._dragout=None; self._dragout_live=False; self._dragout_xy=(0,0)
        self._tree.bind("<ButtonPress-1>",self._dragout_press,add="+")
        self._tree.bind("<B1-Motion>",self._dragout_motion,add="+")
        self._tree.bind("<ButtonRelease-1>",self._dragout_release,add="+")

        # ---- 3D viewer (diagram top): now spans the FULL width above the bottom row
        # (the model-info panel moved down beside the console). Hosts an embedded WebView2
        # (created lazily by _ensure_webview) or a placeholder when embedding is off/missing.
        upper=ttk.Frame(rightside,style="Panel.TFrame")
        self._viewpane=ttk.Frame(upper,style="Panel.TFrame")
        self._viewpane.pack(fill="both",expand=True)
        _ph=("3D model viewer\n\nselect a .skd / .tik in the tree\n(or drag one onto this window),\nthen Open Viewer")
        if WEBVIEW2 is None:
            _ph+=("\n\nembedded view unavailable - models open in your browser."
                  +(("\n("+_WEBVIEW_ERR[:80]+")") if _WEBVIEW_ERR else "")
                  +"\nto enable:  pip install pythonnet pywebview==4.4.1 tkwebview2")
        self._view_placeholder=ttk.Label(self._viewpane,text=_ph,style="PanelDim.TLabel",
                                         justify="center",anchor="center")
        self._view_placeholder.pack(fill="both",expand=True)

        # ---- bottom-left (diagram): output console --------------------------
        lf=ttk.Frame(bottomrow,style="Panel.TFrame")
        self._outlab=ttk.Label(lf,text="Output",style="PanelDim.TLabel"); self._outlab.pack(anchor="w",padx=8,pady=(6,0))
        logwrap=ttk.Frame(lf,style="Panel.TFrame"); logwrap.pack(fill="both",expand=True,padx=6,pady=(2,6))
        self._log=tk.Text(logwrap,bg=PANEL,fg=TXT,insertbackground=TXT,font=FONT_SMALL,relief="flat",
                          height=8,state="disabled",wrap="word",highlightbackground=LINE,highlightthickness=1)
        sb=ttk.Scrollbar(logwrap,command=self._log.yview); self._log.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y"); self._log.pack(side="left",fill="both",expand=True)
        self._log.tag_config("ok",foreground=ACCENT); self._log.tag_config("err",foreground=ERR_C)
        self._log.tag_config("dim",foreground=DIM)
        self._log.bind("<Button-3>",self._show_log_menu)
        # Escape-to-cancel is scoped to the Output window: clicking it focuses it
        # (a disabled Text doesn't always take focus by itself), and only a focused
        # Output window receives the Escape binding below.
        self._log.bind("<Button-1>",lambda e:self._log.focus_set(),add="+")
        self._log.bind("<Escape>",self._cancel_build)
        self._tip(self._log,"Build / extraction log.\nRight-click to copy or clear.\nEscape to cancel loading / building.")

        # ---- bottom-right (diagram): title / surfaces / anims / tags / bones list
        info=ttk.Frame(bottomrow,style="Panel.TFrame",width=270); info.pack_propagate(False)
        self._info_title=ttk.Label(info,text="No model loaded",style="Panel.TLabel",foreground=DIM)
        self._info_title.pack(anchor="w",padx=10,pady=(8,2))
        self._info_stats=ttk.Label(info,text="",style="PanelDim.TLabel",wraplength=245,justify="left")
        self._info_stats.pack(anchor="w",padx=10,pady=(0,4))
        # surfaces / anims / tags / bones as a read-only Text widget: text can be
        # selected and copied like the Output window, coloured per tag/origin/bone,
        # wheel-scrolls natively, right-clicks for Copy all / Select all / editor.
        tagwrap=ttk.Frame(info,style="Panel.TFrame"); tagwrap.pack(fill="both",expand=True,padx=6,pady=(0,4))
        self._tag_text=tk.Text(tagwrap,bg=PANEL,fg=TXT,insertbackground=TXT,font=FONT_SMALL,
                               relief="flat",height=8,wrap="none",state="disabled",
                               highlightthickness=0,cursor="arrow")
        _sb=ttk.Scrollbar(tagwrap,orient="vertical",command=self._tag_text.yview)
        self._tag_text.configure(yscrollcommand=_sb.set)
        _sb.pack(side="right",fill="y"); self._tag_text.pack(side="left",fill="both",expand=True)
        self._retheme_tag_text()
        self._tag_text.bind("<Button-3>",self._show_tag_menu)
        self._tip(self._tag_text,"Surfaces / anims / tags / bones of the last-built model.\nSelect + copy freely.\nRight-click for Copy all / Select all / Open in Text Editor.")
        # Re-open buttons live outside the list so they are always reachable
        self._reopen_bar=ttk.Frame(info,style="Panel.TFrame"); self._reopen_bar.pack(fill="x",padx=10,pady=(2,8))

        # ---- assemble the panes (add() order = left->right / top->bottom) ----
        # stretch='always' panes soak up extra space when the window grows; 'never'
        # panes keep their set size. Initial sizes: tree 300w, info 270w, bottom row
        # ~210h. minsize keeps every pane grabbable and non-collapsing.
        outer.add(left,minsize=180,width=300,stretch="never")
        outer.add(rightside,minsize=340,stretch="always")
        rightside.add(upper,minsize=160,stretch="always")
        rightside.add(bottomrow,minsize=130,height=210,stretch="never")
        bottomrow.add(lf,minsize=220,stretch="always")
        bottomrow.add(info,minsize=200,width=270,stretch="never")
        # restore the saved sash positions once the panes have a real on-screen size
        # (two staggered attempts: the first catches the usual case, the second covers a
        # slow first map). See _restore_panes / _save_panes.
        self.after(160,self._restore_panes); self.after(480,self._restore_panes)

        # ---- status bar ----------------------------------------------------
        stat=ttk.Frame(self,style="Panel.TFrame"); stat.pack(fill="x",side="bottom")
        self._lines.append(tk.Frame(self,bg=LINE,height=1)); self._lines[-1].pack(fill="x",side="bottom")
        self._status_l=ttk.Label(stat,text="Ready",style="Status.TLabel"); self._status_l.pack(side="left")
        self._status_r=ttk.Label(stat,text=VERSION_LABEL,style="Status.TLabel"); self._status_r.pack(side="right")

    def _compose_left(self):
        base=getattr(self,"_status_base","Ready")
        suf=getattr(self,"_pak_suffix","")
        return f"{base}  --  {suf}" if suf else base

    def _set_status(self,left=None,right=None):
        # The left cell shows "<state>  --  N pak(s)"; the right cell is reserved for
        # the program version. Callers still pass the pak count as `right` (e.g.
        # "9 pak(s)" / "0 paks") - it now rides on the LEFT as the suffix, not the
        # right cell, so both pieces of info sit together and the version stays put.
        try:
            if left is not None: self._status_base=left
            if right is not None:
                self._pak_suffix="" if str(right).strip() in ("","0 paks","0 pak(s)") else right
            self._status_l.configure(text=self._compose_left())
            self._status_r.configure(text=VERSION_LABEL)
        except Exception: pass

    # ------------------------------------------------------------ theming ---
    def _retheme_tree_tags(self):
        self._tree.tag_configure("skd",foreground=ACCENT); self._tree.tag_configure("folder",foreground=TXT)
        self._tree.tag_configure("tik",foreground=ORIGIN)   # .tik effects/emitters stand out

    def _set_theme(self,name):
        if name not in THEMES: return
        self._theme=name; self._theme_var.set(name)
        self._cfg["theme"]=name; self._save_config()
        apply_theme(self,name); self._retheme_widgets(); self._apply_titlebar()
        # keep the embedded 3D viewer's theme in lockstep (merged Theme button)
        self._embed_js(f"try{{if(typeof setTheme==='function')setTheme({'true' if name=='light' else 'false'})}}catch(e){{}}")

    def _toggle_theme(self,_e=None):
        self._set_theme("light" if self._theme=="dark" else "dark")

    def _retheme_tag_text(self):
        t=self._tag_text
        t.configure(bg=PANEL,fg=TXT,insertbackground=TXT,selectbackground=SEL_BG,selectforeground=TXT)
        for tg,cl in (("thead",DIM),("torigin",ORIGIN),("ttag",TAG_C),("tbone",BONE_C),("tdim",DIM),("ttl",ACCENT)):
            t.tag_config(tg,foreground=cl)

    def _show_tag_menu(self,e):
        self._post_menu([_mi("Copy all",self._tag_copy_all),
                         _mi("Select all",self._tag_select_all),
                         _MSEP,
                         _mi("Open in Text Editor",self._tag_open_editor)],e.x_root,e.y_root,event=e)

    def _tag_copy_all(self):
        try:
            self.clipboard_clear(); self.clipboard_append(self._tag_text.get("1.0","end-1c"))
            self._set_status("Tag/bone list copied to clipboard")
        except Exception: pass

    def _tag_select_all(self):
        t=self._tag_text
        t.tag_remove("sel","1.0","end"); t.tag_add("sel","1.0","end-1c"); t.focus_set()

    def _tag_open_editor(self):
        txt=self._tag_text.get("1.0","end-1c").strip()
        if not txt:
            self._log_line("No tag/bone list to open yet - build a model first.","dim"); return
        try:
            base=os.path.join(self._tmp or tempfile.gettempdir(),"tags_bones.txt")
            open(base,"w",encoding="utf-8").write(txt+"\n")
        except Exception as e:
            self._log_line(f"Could not write tag list: {e}","err"); return
        self._launch_with("text_editor","text editor","Text Editor",base)

    # ---- click-again tree tooltips -------------------------------------------
    def _on_tree_click(self,e):
        """A second single-click on an ALREADY-selected row doesn't show anything by
        itself - it merely ARMS the normal hover tooltip for that row: the standard
        hover delay starts, and the tip appears only if the pointer is still on the
        row when it elapses. Clicking any other row disarms."""
        self._hide_treetip()
        row=self._tree.identify_row(e.y)
        if not row: self._treetip_armed=None; return
        cur=self._tree.selection()               # widget binding fires BEFORE the class
        if cur and cur[0]==row:                  # binding changes selection: 2nd click
            self._treetip_armed=row
            self._schedule_treetip(row)
        else:
            self._treetip_armed=None

    def _treetip_text(self,row):
        return ("Double-click / Enter opens file in model viewer + anims + effects + tags/bones"
                if row in self._tree_entry else
                "Backspace goes up a folder - Enter opens selected folder")

    def _schedule_treetip(self,row):
        self._cancel_treetip_timer()
        self._treetip_after=self.after(Tooltip.DELAY,lambda:self._maybe_show_treetip(row))

    def _maybe_show_treetip(self,row):
        self._treetip_after=None
        try:                                      # only if the pointer is still on the row
            wx=self._tree.winfo_pointerx()-self._tree.winfo_rootx()
            wy=self._tree.winfo_pointery()-self._tree.winfo_rooty()
            if not (0<=wx<self._tree.winfo_width()): return
            if self._tree.identify_row(wy)!=row: return
        except Exception: return
        self._show_treetip(self._treetip_text(row),
                           self._tree.winfo_pointerx()+14,self._tree.winfo_pointery()+14,row)

    def _show_treetip(self,text,x,y,row):
        self._hide_treetip()
        try: self._treetip=_tip_window(self,text,x,y,wrap=380)
        except Exception: self._treetip=None; return
        self._treetip_row=row
        self.after(6000,lambda t=self._treetip:(self._hide_treetip() if self._treetip is t else None))

    def _on_tree_motion(self,e):
        row=self._tree.identify_row(e.y)
        if self._treetip and row!=self._treetip_row:
            self._hide_treetip()
        if self._treetip_armed:
            if row==self._treetip_armed:
                # re-hovering the armed row restarts the hover delay
                if not self._treetip and not self._treetip_after:
                    self._schedule_treetip(row)
            else:
                self._cancel_treetip_timer()

    def _cancel_treetip_timer(self):
        if self._treetip_after:
            try: self.after_cancel(self._treetip_after)
            except Exception: pass
            self._treetip_after=None

    def _hide_treetip(self):
        self._cancel_treetip_timer()
        if self._treetip:
            try: self._treetip.destroy()
            except Exception: pass
            self._treetip=None; self._treetip_row=None

    # ---- output paths mirror the pak's models/ subfolders ----------------------
    def _viewer_html_name(self, model_path):
        """The viewer names its HTML by source type: jeep_tik_view.html / jeep_skd_view.html."""
        stem=os.path.splitext(os.path.basename(model_path))[0]
        kind="tik" if model_path.lower().endswith(".tik") else "skd"
        return f"{stem}_{kind}_view.html"

    def _entry_subdir(self, entry):
        """Pak-relative output subfolder for a models/ entry, with the leading 'models'
        segment dropped (the output folder IS the models folder):
        models/vehicles/jeep.tik -> vehicles. Empty for loose files."""
        if not entry: return ""
        d=os.path.dirname(entry).replace("\\","/")
        parts=[p for p in d.split("/") if p]
        if parts and parts[0].lower()=="models": parts=parts[1:]
        return os.path.join(*parts) if parts else ""

    def _standalone_dir(self):
        """Output folder for individual-file builds: a 'standalone' folder sitting next
        to the models output folder (i.e. sibling of self._outdir)."""
        return os.path.join(os.path.dirname(os.path.abspath(self._outdir)), "standalone")

    def _html_out_path(self, model_path, subdir=None):
        if subdir is None: subdir=self._last_subdir
        if self._outdir_on.get():
            if subdir==STANDALONE_SUBDIR:
                return os.path.join(self._standalone_dir(), self._viewer_html_name(model_path))
            return os.path.join(self._outdir, subdir or "", self._viewer_html_name(model_path))
        return os.path.join(os.path.dirname(os.path.abspath(model_path)), self._viewer_html_name(model_path))

    def _anim_preload_n(self):
        """How many catalogued animations may be baked straight into the page."""
        try: return max(0,int(self._anim_preload.get()))
        except (TypeError,ValueError): return 150

    def _vfs_read_skc(self,vpath):
        """Read one animation out of the paks. The catalogue resolves the exact
        path the engine would use (currentScript->path + token, tiki_parse.cpp:
        470-472); a basename match is only the fallback for the handful of retail
        entries whose $path is stale."""
        if self._vfs is None or not vpath: return None
        d=self._vfs.read(vpath)
        if d is not None: return d
        bn="/"+os.path.basename(vpath.replace("\\","/")).lower()
        k=next((kk for kk in self._vfs.names() if kk.endswith(bn)),None)
        return self._vfs.read(k) if k else None

    def _stamp_anim_cache(self):
        """Drop cached a<id>.js sidecars when the builder that wrote them is out of date.

        VIEWER_REV gates the cached HTML, but the per-animation sidecars beside it were
        never invalidated by anything - so a sidecar written by an older build kept being
        served forever. That bit hard when body animations gained their facial "mw" layer:
        a smoking05 sidecar cached before that change has no face and would never get one,
        because the file already existed. A one-line rev stamp in the folder means a format
        change clears the cache exactly once, and normal use keeps every built animation."""
        d=self._anim_outdir
        if not d: return
        try:
            stamp=os.path.join(d,".rev")
            have=None
            if os.path.isfile(stamp):
                with open(stamp,encoding="utf-8") as f: have=f.read().strip()
            if have==str(VIEWER_REV_REQUIRED): return
            if os.path.isdir(d):
                n=0
                for fn in os.listdir(d):
                    if fn.startswith("a") and fn.endswith(".js"):
                        try: os.remove(os.path.join(d,fn)); n+=1
                        except OSError: pass
                if n: self._log_q.put(("dim","(animation cache rebuilt for viewer rev %s - %d cached file(s) cleared)"%(VIEWER_REV_REQUIRED,n)))
            os.makedirs(d,exist_ok=True)
            with open(stamp,"w",encoding="utf-8") as f: f.write(str(VIEWER_REV_REQUIRED))
        except Exception:
            pass

    def _reuse_ok(self):
        """May this open serve the already-built HTML from the output folder? Not when
        the option is off, when a one-shot theme was requested (the theme is baked at
        build time), or when a Rebuild was requested."""
        o=self._run_opts
        return (self._reuse_html.get() and self._outdir_on.get()
                and not o.get("force") and o.get("theme") not in ("light","dark"))

    def _html_current(self,hp):
        """A cached viewer HTML is only served when it is at least as new as all three
        source scripts AND its baked mohaa-viewer-rev is new enough; anything older (a
        stale build, or a pre-marker page) is rebuilt so script fixes and viewer features
        actually take effect. The source-mtime gate also clears untextured HTMLs left over
        from a pre-fix build the moment any script is updated."""
        try:
            srcs=[os.path.abspath(__file__), VIEWER, os.path.join(HERE,"mohaa_textures.py")]
            newest_src=max((os.path.getmtime(s) for s in srcs if os.path.exists(s)), default=0)
            if os.path.getmtime(hp) < newest_src:
                self._log_line(f"({os.path.basename(hp)} is older than the current scripts - rebuilding)","dim")
                return False
            with open(hp,"r",encoding="utf-8",errors="ignore") as f: head=f.read(400)
            m=re.search(r"mohaa-viewer-rev:(\d+)",head)
            if m and int(m.group(1))>=VIEWER_REV_REQUIRED: return True
            self._log_line(f"({os.path.basename(hp)} is from an older viewer build - rebuilding)","dim")
            return False
        except Exception:
            return False                     # unreadable cache: rebuild instead

    def _open_cached(self, hp, model_path=None, subdir=None):
        opts=self._run_opts; self._run_opts={}
        if subdir is not None: self._last_subdir=subdir
        self._log_line(f"Loaded existing {os.path.basename(hp)} from the output folder "
                       f"(right-click > Rebuild to regenerate).","ok")
        self._set_status("Loaded existing HTML")
        if opts.get("external"): self._open_standalone(hp)
        elif self._auto_open.get() and not opts.get("no_open"): self._open_file(hp)
        # Refresh the model-details panel. A fresh build fills it via the builder's
        # 'parse' stdout; a cache hit never runs the builder, so the panel used to keep
        # the PREVIOUS model's details. Read the tags/surfs/anims straight from the HTML
        # we just opened (empty stdout -> stats reconstructed from DATA). This only reads
        # the already-built file, so it doesn't add a build step or slow the open.
        if model_path is not None:
            try: self._update_info(model_path,"",html_path=hp)
            except Exception: pass
        self._batch_signal()                             # cache hit counts as a finished step

    # ---- external programs (text editor / legacy model viewer) -----------------
    def _change_program(self, key, menu_label):
        ft=[("Program","*.exe"),("All files","*.*")] if sys.platform.startswith("win") else [("All files","*.*")]
        cur=self._cfg.get(key) or ""
        initdir=os.path.dirname(cur) if cur and os.path.isdir(os.path.dirname(cur)) else ""
        if not initdir: initdir=self._program_folder_default(key)[0] or HERE
        p=filedialog.askopenfilename(title=f"Choose the {menu_label} program",initialdir=initdir,filetypes=ft)
        if p:
            self._cfg[key]=p; self._save_config()
            self._log_line(f"{menu_label}: {p}","dim")

    def _program_folder_default(self, key):
        """Fallback (folder, item-to-highlight) for "Open ... folder" when the program
        has never been configured, or is a bare command name ("notepad.exe", "open",
        "xdg-open") that has no folder of its own.

        Text Editor
          Windows  %SystemRoot% (C:\\Windows) scrolled to notepad.exe. The notepad that
                   actually resolves on PATH sits in System32 (noise) or WindowsApps
                   (ACL-locked), so C:\\Windows is the useful landing spot.
          macOS    TextEdit.app - /System/Applications on 10.15+, /Applications before.
          Linux    whichever of nano / vim / vi is installed, shown in its bin folder.
        Legacy Model Viewer - LightRay3D and Milkshape 3D are Windows programs, so the
        "it could be installed anywhere under here" root is:
          Windows  the system-drive root (C:\\), covering both Program Files trees.
          mac/Lin  a Wine prefix's drive_c when one exists (the literal C:\\ equivalent
                   for running either tool), else the usual third-party install root.
        Anything that doesn't resolve returns "" and the caller keeps its Options message."""
        home=os.path.expanduser("~")
        def _pick(cands):
            for c in cands:
                if c and os.path.isdir(c): return c
            return ""
        if sys.platform.startswith("win"):
            win=os.environ.get("SystemRoot") or os.environ.get("WINDIR") or "C:\\Windows"
            if key=="text_editor":
                # notepad.exe has moved across Windows releases, so probe rather than
                # assume: the Windows-root copy covers 9x/NT/2000/XP/Vista/7/8/10 and
                # most Win11 builds, System32 covers every NT release (incl. XP/7 where
                # the root copy has been removed by hand), SysWOW64 covers 64-bit, and
                # recent Win11 builds that dropped the legacy copies leave only the
                # WindowsApps execution alias. First hit wins, so C:\Windows stays the
                # landing folder wherever it still has one.
                cands=[os.path.join(win,"notepad.exe"),
                       os.path.join(win,"System32","notepad.exe"),
                       os.path.join(win,"SysWOW64","notepad.exe")]
                lad=(os.environ.get("LOCALAPPDATA") or "").strip()
                wapps=os.path.join(lad,"Microsoft","WindowsApps") if lad else ""
                if wapps: cands.append(os.path.join(wapps,"notepad.exe"))
                w=shutil.which("notepad.exe")
                if w: cands.append(w)
                soft=""
                for c in cands:
                    try:
                        if os.path.isfile(c) and os.path.isdir(os.path.dirname(c)):
                            return (os.path.dirname(c),c)
                    except OSError:
                        soft=soft or os.path.dirname(c)   # AppExecLink stat can raise:
                                                          # can't verify it, but it's a lead
                # No verified copy. Land on evidence first, then the alias folder, and only
                # then the Windows root - by this point we know the root has no notepad, so
                # opening it would just be the old dead end with extra steps.
                return (_pick([soft,wapps,win]),None)
            if key=="legacy_viewer":
                return (_pick([(os.path.splitdrive(win)[0] or "C:")+os.sep]),None)
            return ("",None)
        wine=[]
        wp=(os.environ.get("WINEPREFIX") or "").strip()
        if wp: wine.append(os.path.join(wp,"drive_c"))
        wine.append(os.path.join(home,".wine","drive_c"))
        if sys.platform=="darwin":
            if key=="text_editor":
                for d in ("/System/Applications","/Applications"):
                    app=os.path.join(d,"TextEdit.app")
                    if os.path.exists(app): return (d,app)     # .app is a bundle DIR
                return (_pick(["/Applications"]),None)
            if key=="legacy_viewer":
                return (_pick(wine+[os.path.join(home,"Library","Application Support",
                                                 "CrossOver","Bottles"),
                                    "/Applications","/"]),None)
            return ("",None)
        if key=="text_editor":                                  # Linux / other POSIX
            for name in ("nano","vim","vi"):
                w=shutil.which(name)
                if not w: continue
                w=os.path.realpath(w)                           # /bin/nano -> /usr/bin/nano
                if os.path.isdir(os.path.dirname(w)): return (os.path.dirname(w),w)
            return (_pick(["/usr/bin","/bin"]),None)
        if key=="legacy_viewer":
            return (_pick(wine+["/opt","/usr/local/bin","/"]),None)
        return ("",None)

    def _open_program_folder(self, key, menu_label):
        prog=(self._cfg.get(key) or "").strip()
        d=os.path.dirname(prog) if prog else ""
        sel=prog if (d and os.path.exists(prog)) else None
        if not d or not os.path.isdir(d): d,sel=self._program_folder_default(key)
        if not d or not os.path.isdir(d):
            self._log_line(f"Error. No {menu_label.lower()} folder to open. "
                           f"Please go to Options --> Change {menu_label}...","err"); return
        try:
            if sys.platform.startswith("win"):
                if sel:
                    # explorer /select, opens the folder scrolled to the item with it
                    # highlighted. Handed over as ONE raw command string: Popen's Windows
                    # list-quoting wraps the whole "/select,<path>" argument in quotes when
                    # the path has spaces, which explorer then fails to parse.
                    # Absolute path, never the bare name: CreateProcess resolves a bare
                    # "explorer" through the CURRENT DIRECTORY before PATH, so an
                    # explorer.exe sitting in the extracted release folder would run.
                    _expl=os.path.join(os.environ.get("SystemRoot",r"C:\Windows"),"explorer.exe")
                    subprocess.Popen('"%s" /select,"%s"'%(_expl,os.path.normpath(sel)))
                else: os.startfile(d)
            elif sys.platform=="darwin":
                subprocess.Popen(["open","-R",sel] if sel else ["open",d])
            else:
                # freedesktop.org's FileManager1.ShowItems is the only portable "open the
                # folder with this item selected" on Linux - Nautilus / Dolphin / Nemo /
                # Thunar / PCManFM all implement it, while xdg-open can only open a
                # directory. Bounded reply timeout so a cold file manager can't hang the
                # UI for long, then fall back to plain xdg-open on any failure.
                shown=False
                if sel and shutil.which("dbus-send"):
                    from urllib.parse import quote as _urlq
                    try:
                        shown=subprocess.call(
                            ["dbus-send","--session","--print-reply","--reply-timeout=2000",
                             "--dest=org.freedesktop.FileManager1","--type=method_call",
                             "/org/freedesktop/FileManager1",
                             "org.freedesktop.FileManager1.ShowItems",
                             "array:string:file://"+_urlq(sel),"string:"],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)==0
                    except Exception: shown=False
                if not shown: subprocess.Popen(["xdg-open",d])
            self._log_line(f"{menu_label} folder: {d}","dim")
        except Exception as e:
            self._log_line(f"Could not open folder: {e}","err")

    def _launch_with(self, key, label, menu_label, filepath):
        """Launch the configured external program on filepath, with the exact error
        messages requested: missing program -> point at Options; broken program ->
        ask for a valid one. Thread-safe (logs via the queue)."""
        prog=(self._cfg.get(key) or "").strip()
        if not prog:
            self._log_q.put(("err",f"Error. No {label} program was found. "
                                   f"Please go to Options --> Change {menu_label}..."))
            return
        # The config is data, not a command line: only ever launch an existing FILE at an
        # absolute path. Without this a mohaa_viewer_config.json shipped inside a
        # downloaded bundle could name any program (or a bare "powershell") and this
        # menu item would run it. shutil.which is deliberately NOT used - resolving a
        # bare name through PATH (and, on Windows, the current directory) is the exact
        # behaviour being closed off.
        if not (os.path.isabs(prog) and os.path.isfile(prog)):
            self._log_q.put(("err",f"Error. The saved {label} program is not a valid file "
                                   f"({prog[:120]}). Please go to Options --> Change {menu_label}..."))
            return
        try:
            subprocess.Popen([prog,filepath])
            self._log_q.put(("dim",f"opened with {os.path.basename(prog)}: {os.path.basename(filepath)}"))
        except Exception:
            self._log_q.put(("err",f"Error. Please select a valid program for {label} "
                                   f"in Options --> Change {menu_label}..."))

    def _change_outdir(self):
        d=filedialog.askdirectory(title="Choose the viewer HTML output folder",
                                  initialdir=self._outdir if os.path.isdir(self._outdir) else HERE)
        if d:
            self._outdir=d; self._save_opts()
            self._log_line(f"Output folder: {d}","dim")

    def _open_outdir(self):
        try:
            os.makedirs(self._outdir,exist_ok=True)
            if sys.platform.startswith("win"): os.startfile(self._outdir)
            elif sys.platform=="darwin": subprocess.Popen(["open",self._outdir])
            else: subprocess.Popen(["xdg-open",self._outdir])
        except Exception as e:
            self._log_line(f"Could not open output folder: {e}","err")

    def _apply_titlebar(self, win=None):
        """Windows: colour the native title bar to match the theme via immersive dark
        mode (DwmSetWindowAttribute, attribute 20; 19 on older Win10 builds), then a
        SetWindowPos frame-changed nudge so it repaints immediately. No-op elsewhere."""
        if not sys.platform.startswith("win"): return
        try:
            import ctypes
            w=win or self
            w.update_idletasks()
            hwnd=ctypes.windll.user32.GetParent(w.winfo_id())
            v=ctypes.c_int(1 if self._theme=="dark" else 0)
            for attr in (20,19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,attr,ctypes.byref(v),ctypes.sizeof(v))==0:
                    break
            SWP=0x0001|0x0002|0x0004|0x0020   # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
            ctypes.windll.user32.SetWindowPos(hwnd,None,0,0,0,0,SWP)
            # the white frame around drop-down / right-click menus is NATIVE popup-menu
            # chrome (Windows draws it, Tk can't recolour it). Flip Windows' own menu
            # theme per-process: uxtheme ordinal 135 = SetPreferredAppMode
            # (2=ForceDark, 3=ForceLight), ordinal 136 = FlushMenuThemes. Undocumented
            # but the standard dark-mode approach; needs Win10 1903+, harmless otherwise.
            try:
                ux=ctypes.WinDLL("uxtheme.dll")
                ux[135](2 if self._theme=="dark" else 3)
                ux[136]()
            except Exception: pass
        except Exception: pass

    def _retheme_widgets(self):
        """Refresh raw-tk widgets that hold palette colours directly."""
        try:
            self.configure(bg=BG)
            for ln in self._lines:
                try: ln.configure(bg=LINE)
                except Exception: pass
            for pw in getattr(self,"_panes",()):
                try: pw.configure(bg=LINE)
                except Exception: pass
            self._path_entry.configure(bg=PANEL,fg=TXT,insertbackground=TXT,
                                       highlightbackground=LINE,highlightcolor=ACCENT)
            self._log.configure(bg=PANEL,fg=TXT,insertbackground=TXT,highlightbackground=LINE)
            self._log.tag_config("ok",foreground=ACCENT); self._log.tag_config("err",foreground=ERR_C)
            self._log.tag_config("dim",foreground=DIM)
            self._retheme_tree_tags()
            self._retheme_tag_text()
            self._menubar.configure(bg=PANEL); self._menubar_line.configure(bg=LINE)
            for b in self._menubtns:
                b.configure(bg=PANEL,fg=TXT,activebackground=SEL_BG,activeforeground=ACCENT)
            for mm in self._menus:
                try: mm.configure(bg=PANEL,fg=TXT,activebackground=SEL_BG,
                                  activeforeground=ACCENT,disabledforeground=DIM)
                except Exception: pass
            # the info panel's title/tag/bone labels + dots hold theme colours from
            # render time; re-render from the last build so light mode gets the HTML
            # light palette (dark tag text, blue accent) instead of stale dark colours
            if self._last_info:
                self._update_info(*self._last_info)
        except Exception: pass

    # ------------------------------------------------------------ hotkeys ---
    def _bind_hotkeys(self):
        self.bind_all("<Control-o>",lambda e:(self._choose_pk3(),"break"))
        self.bind_all("<Control-O>",lambda e:(self._browse_and_run(),"break"))       # Ctrl+Shift+O
        self.bind_all("<Control-Shift-o>",lambda e:(self._browse_and_run(),"break"))
        self.bind_all("<Control-f>",lambda e:(self._search.focus_set(),self._search.select_range(0,"end"),"break"))
        self.bind_all("<Control-t>",lambda e:(self._toggle_theme(),"break"))
        self.bind_all("<Control-T>",lambda e:(self._toggle_old_popups_hotkey(),"break"))       # Ctrl+Shift+T
        self.bind_all("<Control-Shift-t>",lambda e:(self._toggle_old_popups_hotkey(),"break"))
        self.bind_all("<F5>",lambda e:(self._reload_all_cmd(),"break"))
        self.bind_all("<F1>",lambda e:(self._show_hotkeys(),"break"))
        self.bind_all("<Escape>",self._popup_escape,add="+")

    def _reload_all_cmd(self):
        if not self._pk3_paths:
            self._log_line("No paks to reload.","dim"); return
        self._log_line("Reloading paks...","dim"); self._reload_all()

    def _expand_all(self,open_):
        def rec(item):
            for ch in self._tree.get_children(item):
                self._tree.item(ch,open=open_); rec(ch)
        for r in self._tree.get_children(""): self._tree.item(r,open=open_); rec(r)

    # tree: Enter = open file / descend into folder
    def _on_tree_enter(self,_e=None):
        self._hide_treetip()
        sel=self._tree.selection()
        if not sel: return "break"
        if len(sel)>1:
            self._build_selected(sel); return "break"      # multi-select: batch build
        it=sel[0]
        if it in self._tree_entry:
            self._open_pk3_model(self._tree_entry[it]); return "break"
        kids=self._tree.get_children(it)
        if kids:
            self._tree.item(it,open=True)
            self._tree.selection_set(kids[0]); self._tree.focus(kids[0]); self._tree.see(kids[0])
        return "break"

    # tree: Backspace = go up one folder (collapse the folder being left)
    def _on_tree_backspace(self,_e=None):
        sel=self._tree.selection()
        if not sel: return "break"
        it=sel[0]
        if it not in self._tree_entry and self._tree.get_children(it) and self._tree.item(it,"open"):
            self._tree.item(it,open=False); return "break"     # open folder: close it first
        par=self._tree.parent(it)
        if par:
            self._tree.selection_set(par); self._tree.focus(par); self._tree.see(par)
        return "break"

    # ----------------------------------------- drag-out: standalone viewer ---
    # Dragging a .skd/.tik row OUT of the launcher window and releasing opens it
    # in its own self-contained browser viewer (always external, never the
    # embedded pane), so multiple models can be open at once. Builds triggered
    # this way skip the open-in-viewer latch: they never touch the embedded pane,
    # so they can't race it.
    def _outside_win(self,xr,yr):
        try:
            x,y=self.winfo_rootx(),self.winfo_rooty()
            return not (x<=xr<=x+self.winfo_width() and y<=yr<=y+self.winfo_height())
        except Exception: return False

    def _dragout_press(self,e):
        iid=self._tree.identify_row(e.y)
        self._dragout=self._tree_entry.get(iid) if iid else None
        self._dragout_xy=(e.x_root,e.y_root); self._dragout_live=False

    def _dragout_motion(self,e):
        if not self._dragout: return
        if not self._dragout_live:
            x0,y0=self._dragout_xy
            if abs(e.x_root-x0)<12 and abs(e.y_root-y0)<12: return
            self._dragout_live=True
            self._set_status("Release outside this window to open a standalone viewer")
        out=self._outside_win(e.x_root,e.y_root)
        try: self._tree.configure(cursor="plus" if out else "")
        except Exception: pass
        if out: return "break"        # stop the Treeview auto-scrolling while outside

    def _dragout_release(self,e):
        entry,live=self._dragout,self._dragout_live
        self._dragout=None; self._dragout_live=False
        try: self._tree.configure(cursor="")
        except Exception: pass
        if not (entry and live): return
        self._set_status("Ready")
        if not self._outside_win(e.x_root,e.y_root): return
        self._open_external(entry)

    def _open_external(self,entry):
        """Build (or reuse) a tree entry's HTML and open it in a new browser tab
        window - the browser-version page (with its own Theme / Shortcuts buttons),
        never the embedded in-launcher pane. Also used by the drag-off-window gesture."""
        self._log_line(f"Opening {os.path.basename(entry)} in a browser tab...","dim")
        self._run_opts={"external":True}
        self._open_pk3_model(entry)

    # ----------------------------------------------------- context menus ---
    def _show_pak_menu(self,e):
        # what was right-clicked? a file row, a folder row, or the pak header / empty space
        iid=""
        try:
            if e.widget is self._tree: iid=self._tree.identify_row(e.y)
        except Exception: iid=""
        sel=self._tree.selection()
        if iid:
            if not (iid in sel and len(sel)>1):      # right-click inside a multi-selection keeps it
                self._tree.selection_set(iid); sel=(iid,)
            self._tree.focus(iid)
        if iid and len(sel)>1:                        # Ctrl/Shift multi-selection menu
            ents=self._collect_entries(sel); n=len(ents)
            files_only=all(s in self._tree_entry for s in sel)   # no folder rows in the selection
            items=[_mi(f"Build {n} files in selection (don't open anything)",
                       lambda ss=tuple(sel):self._build_selected(ss),
                       state=("normal" if n else "disabled"))]
            if files_only and n:                      # file-only selection: fully-open options
                items+=[_mi(f"Open {n} files in browser tab windows (HTML)",
                            lambda ss=tuple(sel):self._open_selected(ss)),
                        _mi(f"Open {n} files in Text Editor",
                            lambda ee=tuple(ents):self._open_entries_with(ee,"text_editor","text editor","Text Editor"))]
            items+=[_MSEP,
                    _mi("Expand selected folders",lambda ss=tuple(sel):self._expand_selected(ss,True)),
                    _mi("Collapse selected folders",lambda ss=tuple(sel):self._expand_selected(ss,False))]
            self._post_menu(items,e.x_root,e.y_root,event=e); return
        entry=self._tree_entry.get(iid) if iid else None
        if entry:                                   # a .skd / .tik file row: open options only
            base=os.path.basename(entry)
            items=[_mi(f"Open {base} in viewer",lambda:self._ctx_open(entry)),
                   _mi("Open HTML in browser tab window",lambda:self._open_external(entry)),
                   _mi("Build only (don't open anything)",lambda:self._ctx_open(entry,no_open=True)),
                   _mi("Rebuild in viewer (ignore saved HTML)",lambda:self._ctx_open(entry,force=True)),
                   _MSEP]
            if entry.lower().endswith(".tik"):
                items.append(_mi("Open in Text Editor",lambda:self._open_entry_with(entry,"text_editor","text editor","Text Editor")))
            else:
                items.append(_mi("Open in Legacy Model Viewer",lambda:self._open_entry_with(entry,"legacy_viewer","legacy model viewer","Legacy Model Viewer")))
        elif iid:                                    # a folder row: subtree-only expand/collapse
            items=[_mi("Expand this folder",lambda:self._expand_subtree(iid,True)),
                   _mi("Collapse this folder",lambda:self._expand_subtree(iid,False)),
                   _MSEP,
                   _mi("Build all in this folder (don't open anything)",lambda:self._build_all_in_folder(iid))]
        else:                                        # pak header label / empty tree space
            items=self._menu_items_pak()
        self._post_menu(items,e.x_root,e.y_root,event=e)

    def _expand_subtree(self, iid, open_):
        """Expand/collapse ONLY the right-clicked folder and everything under it."""
        def rec(item):
            for ch in self._tree.get_children(item):
                self._tree.item(ch,open=open_); rec(ch)
        self._tree.item(iid,open=open_); rec(iid)

    def _entries_under(self, iid):
        """Every .skd/.tik entry under a tree item (the item itself if it's a file)."""
        out=[]
        def rec(item):
            if item in self._tree_entry: out.append(self._tree_entry[item])
            for ch in self._tree.get_children(item): rec(ch)
        rec(iid); return out

    def _collect_entries(self, iids):
        seen=set(); out=[]
        for iid in iids:
            for en in self._entries_under(iid):
                if en not in seen: seen.add(en); out.append(en)
        return out

    def _expand_selected(self, iids, open_):
        for iid in iids:
            if iid not in self._tree_entry: self._expand_subtree(iid,open_)

    def _build_all_in_folder(self, iid):
        self._start_batch(self._entries_under(iid),
                          "folder '"+self._tree.item(iid,"text")+"'")

    def _build_selected(self, iids):
        self._start_batch(self._collect_entries(iids),"selection")

    def _open_selected(self, iids):
        """Multi-selection right-click: build every selected FILE sequentially and
        open each finished viewer HTML in its own standalone browser window (the
        embedded pane can only show one page at a time, so own-window is the only
        way to genuinely open several at once)."""
        self._start_batch(self._collect_entries(iids),"selection",open_mode="external")

    def _open_entries_with(self, entries, key, label, menu_label):
        """Multi-selection right-click: extract every selected pak file to the temp
        workspace and hand each one to the configured external program (e.g. the
        Text Editor). Same per-file behaviour as _open_entry_with, batched."""
        if not self._pk3_paths or not self._tmp:
            self._log_line("Load a .pk3 first.","err"); return
        if not (self._cfg.get(key) or "").strip():   # one error, not one per file
            self._log_line(f"Error. No {label} program was found. "
                           f"Please go to Options --> Change {menu_label}...","err"); return
        def work():
            try:
                found={en.lower():None for en in entries}
                for p in self._pk3_paths:               # later paks override earlier
                    try: zf=zipfile.ZipFile(p)
                    except Exception: continue
                    for n in zf.namelist():
                        if n.lower() in found and not n.endswith("/"):
                            found[n.lower()]=self._extract_one(zf,n)
                    zf.close()
                for en in entries:
                    t=found.get(en.lower())
                    if t: self._launch_with(key,label,menu_label,t)
                    else: self._log_q.put(("err",f"Could not find {en} inside the loaded paks"))
            except Exception as ex:
                self._log_q.put(("err",f"Could not open: {ex}"))
        threading.Thread(target=work,daemon=True).start()

    def _start_batch(self, entries, what, open_mode=None):
        """Sequential background builds of many entries. open_mode=None (default):
        never open the browser (classic batch build). open_mode='external': open
        each finished HTML in its own standalone window. Each step goes through
        the normal open pipeline (so the HTML cache, output subfolders and texture
        resolve all apply); the next step starts when the previous one finishes
        or fails."""
        if self._batch:
            self._log_line("A batch build is already running - wait for it to finish.","err"); return
        if not entries:
            self._log_line("Nothing to build there.","dim"); return
        self._batch=list(entries); self._batch_total=len(entries)
        self._batch_open=open_mode
        tail=("each opens in its own window" if open_mode=="external" else "browser stays closed")
        self._log_line(f"Batch: building {len(entries)} file(s) from {what} ({tail})...","ok")
        self._batch_step()

    def _batch_step(self):
        if not self._batch:
            self._batch_total=0
            self._log_line("Batch complete.","ok"); self._set_status("Batch complete")
            return
        entry=self._batch.pop(0)
        n=self._batch_total-len(self._batch)
        self._log_line(f"[batch {n}/{self._batch_total}] {entry}","dim")
        self._batch_waiting=True
        self._run_opts=({"external":True} if getattr(self,"_batch_open",None)=="external"
                        else {"no_open":True})
        self._open_pk3_model(entry)

    def _batch_signal(self):
        """A build step ended (built, served from cache, or failed): advance the
        batch exactly once (latched - duplicate signals are harmless)."""
        if not self._batch_waiting: return
        self._batch_waiting=False
        self.after(80,self._batch_step)

    def _ctx_open(self, entry, theme=None, no_open=False, force=False):
        """Open a tree file with one-shot viewer options: a baked initial theme
        (light/dark), build-only (write + log, don't open the browser), and/or
        force (rebuild even when a saved HTML exists in the output folder).
        Applies to exactly this build; the global settings are untouched."""
        self._run_opts={"theme":theme,"no_open":bool(no_open),"force":bool(force)}
        # A forced rebuild has to LOOK like one. _open_file navigates the existing
        # WebView2 to the same file:// URL it is already showing, and a same-URL
        # navigation differing only past the '#' is an in-page hash change, not a
        # reload - so the freshly written HTML is never fetched and the pane appears
        # to ignore the rebuild. Dropping the control here means the build runs into
        # the placeholder pane and _open_file's _ensure_webview() builds a new one:
        # a real close and reopen. Build-only deliberately opens nothing, so it is
        # left alone, and _close_viewer is already a no-op when nothing is open.
        if force and not no_open: self._close_viewer()
        self._open_pk3_model(entry)

    def _open_entry_with(self, entry, key, label, menu_label):
        """Extract the clicked pak file to the temp workspace and hand it to the
        configured external program: .tik -> Text Editor, .skd -> Legacy Model Viewer
        (e.g. LightRay3D). Missing/broken programs report the Options path to fix."""
        if not self._pk3_paths or not self._tmp:
            self._log_line("Load a .pk3 first.","err"); return
        def work():
            try:
                target=None
                for p in self._pk3_paths:               # later paks override earlier
                    try: zf=zipfile.ZipFile(p)
                    except Exception: continue
                    for n in zf.namelist():
                        if n.lower()==entry.lower() and not n.endswith("/"):
                            target=self._extract_one(zf,n)
                    zf.close()
                if not target:
                    self._log_q.put(("err","Could not find that file inside the loaded paks")); return
                self._launch_with(key,label,menu_label,target)
            except Exception as ex:
                self._log_q.put(("err",f"Could not open: {ex}"))
        threading.Thread(target=work,daemon=True).start()

    def _remove_pak(self,path):
        if path in self._pk3_paths:
            self._pk3_paths.remove(path)
            self._cfg["pk3s"]=self._pk3_paths if self._remember.get() else []
            self._save_config()
            n=len(self._pk3_paths)
            head=os.path.basename(self._pk3_paths[0]) if n else ""
            self._pk3_label.configure(text=(head+(f"  +{n-1} more" if n>1 else "")+"  /  models") if n else "No .pk3 loaded")
            self._log_line(f"Removed {os.path.basename(path)}","dim")
            if n: self._reload_all()
            else: self._clear_pk3s()

    def _show_log_menu(self,e):
        self._post_menu([_mi("Copy all",self._copy_log),
                         _mi("Clear log",self._clear_log)],e.x_root,e.y_root,event=e)
    def _copy_log(self):
        try:
            self.clipboard_clear(); self.clipboard_append(self._log.get("1.0","end-1c"))
            self._set_status("Log copied to clipboard")
        except Exception: pass
    def _clear_log(self):
        self._log.configure(state="normal"); self._log.delete("1.0","end"); self._log.configure(state="disabled")

    # ------------------------------------------------ cancel loading / build ---
    def _cancel_build(self,_e=None):
        """Escape with the Output window focused: abort the in-flight open. The
        build generation counter is bumped (extraction/build threads capture it
        and bail out when it changes), a running viewer subprocess is killed, and
        a pending batch is abandoned. Logged in red."""
        name=self._building_name
        if not name:
            self._log_line("(nothing is loading / building right now)","dim"); return "break"
        self._build_gen+=1                 # stale-gen threads stop at their next check
        self._building_name=None; self._opening_view=False
        p=self._proc
        if p is not None:
            try: p.kill()
            except Exception: pass
        if self._batch:                    # cancelling also abandons the rest of a batch
            self._log_line(f"Batch cancelled with {len(self._batch)} file(s) left unbuilt.","err")
            self._batch=[]; self._batch_total=0; self._batch_waiting=False
        self._log_line(f"Cancelled building the viewer, {name} file was not finished building","err")
        self._set_status("Cancelled")
        return "break"

    # ------------------------------------------------------------ dialogs ---
    def _confirm_dialog(self, title, lines, ok_text="Delete", cancel_text="Cancel"):
        """A themed yes/no dialog matching Help > About: same Panel.TFrame body and the
        same three-colour text scheme (ACCENT title, TXT body, DIM detail), so it follows
        Dark/Light like every other launcher window instead of the OS-white messagebox.

        `lines` is a list of (text, kind) where kind is 'title' (ACCENT), 'body' (TXT) or
        'dim' (DIM). Returns True only if the user presses the OK button / Enter.

        When "Use old popup windows" is on, this defers to the OS-default messagebox
        (white, system font) instead of the themed window - same rule the menus/tooltips
        follow via OLD_POPUPS."""
        if OLD_POPUPS:
            # drop the ACCENT title row (kind=='title'): the native box shows the title
            # in its own title bar. Everything else keeps its order and blank-line spacing.
            body="\n".join(t for t,k in lines if k!="title")
            return bool(messagebox.askokcancel(title, body, parent=self))
        w=tk.Toplevel(self); w.title(title); w.configure(bg=BG)
        w.transient(self); w.resizable(False,False)
        frm=ttk.Frame(w,style="Panel.TFrame"); frm.pack(fill="both",expand=True,padx=10,pady=10)
        first=True
        for text,kind in lines:
            if kind=="title":
                ttk.Label(frm,text=text,style="Panel.TLabel",foreground=ACCENT,justify="left"
                          ).pack(anchor="w",padx=10,pady=(8 if first else 2,4))
            elif kind=="dim":
                ttk.Label(frm,text=text,style="PanelDim.TLabel",justify="left"
                          ).pack(anchor="w",padx=10,pady=(0,4))
            else:
                ttk.Label(frm,text=text,style="Panel.TLabel",justify="left"
                          ).pack(anchor="w",padx=10,pady=(0,4))
            first=False
        res={"ok":False}
        def _do_ok(): res["ok"]=True; w.destroy()
        row=ttk.Frame(w,style="Panel.TFrame"); row.pack(pady=(4,10))
        ok=ttk.Button(row,text=ok_text,command=_do_ok,cursor="hand2"); ok.pack(side="left",padx=6)
        ca=ttk.Button(row,text=cancel_text,command=w.destroy,cursor="hand2"); ca.pack(side="left",padx=6)
        w.bind("<Escape>",lambda e:w.destroy())
        w.bind("<Return>",lambda e:_do_ok())
        try:
            w.update_idletasks()
            x=self.winfo_rootx()+(self.winfo_width()-w.winfo_width())//2
            y=self.winfo_rooty()+(self.winfo_height()-w.winfo_height())//2
            x0,y0,_x1,_y1=_virtual_screen(w)
            w.geometry(f"+{max(x0,x)}+{max(y0,y)}")
        except Exception: pass
        self._apply_titlebar(w)
        w.grab_set(); ca.focus_set()
        self.wait_window(w)
        return res["ok"]

    @staticmethod
    def _fill_hotkeys(frm,rows,col,old):
        """Grid one column-group of the shortcut list into `frm` at grid columns col / col+1.

        Two groups are placed side by side (launcher keys at 0/1, viewer keys at 2/3). The
        single-column list this replaced would now be ~47 rows tall and run off the bottom of
        a 768px-high screen; side by side it is the same height it always was, at the cost of
        width - so the description column is capped with a font-relative wraplength. Measuring
        the font (rather than counting characters) keeps the cap honest whatever mono family
        _mono_family() picked and whatever the OS-default font is under 'old popup windows',
        and it bounds the window width no matter how long a future description gets."""
        try:
            import tkinter.font as _tkfont
            _f=_tkfont.nametofont("TkDefaultFont") if old else _tkfont.Font(font=FONT_SMALL)
            wrap=_f.measure("x"*50)          # descriptions past ~50 chars fold to a 2nd line
        except Exception:
            wrap=0                           # 0 = Tk's default, i.e. no wrapping
        lpad = 6 if col==0 else 26           # gutter between the two column-groups
        r=0
        for key,desc in rows:
            if not key:                      # "--- Section ---" header spans both of its columns
                if old:
                    tk.Label(frm,text=desc.strip("- "),font="TkDefaultFont").grid(
                        row=r,column=col,columnspan=2,sticky="w",padx=(lpad,6),pady=(8,2))
                else:
                    ttk.Label(frm,text=desc.strip("- "),style="PanelDim.TLabel").grid(
                        row=r,column=col,columnspan=2,sticky="w",padx=(lpad,6),pady=(8,2))
                r+=1; continue
            if old:
                tk.Label(frm,text=key,font="TkDefaultFont").grid(row=r,column=col,sticky="w",padx=(lpad,18),pady=1)
                tk.Label(frm,text=desc,font="TkDefaultFont",justify="left",wraplength=wrap).grid(
                    row=r,column=col+1,sticky="w",padx=6,pady=1)
            else:
                ttk.Label(frm,text=key,style="Panel.TLabel",foreground=ACCENT).grid(row=r,column=col,sticky="w",padx=(lpad,18),pady=1)
                ttk.Label(frm,text=desc,style="Panel.TLabel",justify="left",wraplength=wrap).grid(
                    row=r,column=col+1,sticky="w",padx=6,pady=1)
            r+=1

    def _show_hotkeys(self):
        # OS-default (white, system font) window when "Use old popup windows" is on,
        # matching the menus/tooltips/confirm dialogs; themed window otherwise.
        # Titled "All Keyboard shortcuts" because it covers BOTH programs; the viewer's own
        # H overlay is the viewer-only subset and is titled "Viewer Keyboard shortcuts".
        if OLD_POPUPS:
            w=tk.Toplevel(self); w.title("All Keyboard shortcuts")
            w.transient(self); w.resizable(False,False)
            frm=tk.Frame(w); frm.pack(fill="both",expand=True,padx=10,pady=10)
            self._fill_hotkeys(frm,HOTKEYS_LAUNCHER,0,True)
            self._fill_hotkeys(frm,HOTKEYS_VIEWER,2,True)
            btn=tk.Button(w,text="Close",command=w.destroy); btn.pack(pady=(0,10))
            w.bind("<Escape>",lambda e:w.destroy()); w.bind("<F1>",lambda e:w.destroy())
            try:
                w.update_idletasks()
                x=self.winfo_rootx()+(self.winfo_width()-w.winfo_width())//2
                y=self.winfo_rooty()+(self.winfo_height()-w.winfo_height())//2
                x0,y0,_x1,_y1=_virtual_screen(w)
                w.geometry(f"+{max(x0,x)}+{max(y0,y)}")
            except Exception: pass
            w.grab_set(); btn.focus_set(); return
        w=tk.Toplevel(self); w.title("All Keyboard shortcuts"); w.configure(bg=BG)
        w.transient(self); w.resizable(False,False)
        frm=ttk.Frame(w,style="Panel.TFrame"); frm.pack(fill="both",expand=True,padx=10,pady=10)
        self._fill_hotkeys(frm,HOTKEYS_LAUNCHER,0,False)
        self._fill_hotkeys(frm,HOTKEYS_VIEWER,2,False)
        btn=ttk.Button(w,text="Close",command=w.destroy,cursor="hand2"); btn.pack(pady=(0,10))
        w.bind("<Escape>",lambda e:w.destroy()); w.bind("<F1>",lambda e:w.destroy())
        try:
            w.update_idletasks()
            x=self.winfo_rootx()+(self.winfo_width()-w.winfo_width())//2
            y=self.winfo_rooty()+(self.winfo_height()-w.winfo_height())//2
            x0,y0,_x1,_y1=_virtual_screen(w)
            w.geometry(f"+{max(x0,x)}+{max(y0,y)}")
        except Exception: pass
        self._apply_titlebar(w)
        w.grab_set(); btn.focus_set()

    def _show_privacy(self):
        self._text_dialog("Privacy & Legal", PRIVACY_TEXT, width=88, height=26)

    def _text_dialog(self, title, body, width=80, height=24):
        """Scrollable read-only text window, themed or OS-default like every other dialog."""
        w=tk.Toplevel(self); w.title(title)
        w.transient(self); w.resizable(True,True)
        if not OLD_POPUPS: w.configure(bg=BG)
        wrap=tk.Frame(w,bg=(PANEL if not OLD_POPUPS else None)) if not OLD_POPUPS else tk.Frame(w)
        wrap.pack(fill="both",expand=True,padx=10,pady=10)
        sb=tk.Scrollbar(wrap)
        sb.pack(side="right",fill="y")
        kw=dict(wrap="word",width=width,height=height,yscrollcommand=sb.set,
                font=FONT_SMALL,relief="flat",borderwidth=0)
        if not OLD_POPUPS:
            kw.update(bg=ENTRY_BG,fg=TXT,insertbackground=TXT,
                      selectbackground=SEL_BG,selectforeground=TXT)
        txt=tk.Text(wrap,**kw)
        txt.pack(side="left",fill="both",expand=True)
        sb.config(command=txt.yview)
        txt.insert("1.0",body)
        txt.config(state="disabled")                 # read-only, still selectable/copyable
        btn=(ttk.Button(w,text="Close",command=w.destroy,cursor="hand2")
             if not OLD_POPUPS else tk.Button(w,text="Close",command=w.destroy))
        btn.pack(pady=(0,10))
        w.bind("<Escape>",lambda e:w.destroy())
        try:
            w.update_idletasks()
            x=self.winfo_rootx()+(self.winfo_width()-w.winfo_width())//2
            y=self.winfo_rooty()+(self.winfo_height()-w.winfo_height())//2
            x0,y0,_x1,_y1=_virtual_screen(w)
            w.geometry(f"+{max(x0,x)}+{max(y0,y)}")
        except Exception: pass
        if not OLD_POPUPS: self._apply_titlebar(w)
        w.grab_set(); btn.focus_set()

    def _show_about(self):
        if OLD_POPUPS:
            w=tk.Toplevel(self); w.title("About")
            w.transient(self); w.resizable(False,False)
            frm=tk.Frame(w); frm.pack(fill="both",expand=True,padx=10,pady=10)
            tk.Label(frm,text="MOHAA Model Viewer launcher",font="TkDefaultFont"
                     ).pack(anchor="w",padx=10,pady=(8,2))
            tk.Label(frm,text="made by: Searingwolfe",font="TkDefaultFont"
                     ).pack(anchor="w",padx=10,pady=(0,2))
            tk.Label(frm,text=VERSION_LABEL,font="TkDefaultFont"
                     ).pack(anchor="w",padx=10,pady=(0,8))
            tk.Label(frm,text="Browses MOHAA .pk3 paks and opens .skd models / .tik effects\n"
                              "in a self-contained browser-based 3D viewer.",
                     justify="left",font="TkDefaultFont").pack(anchor="w",padx=10,pady=(0,6))
            tk.Label(frm,text="Engine reference: OpenMOHAA (github.com/openmoh/openmohaa)",
                     font="TkDefaultFont").pack(anchor="w",padx=10,pady=(0,8))
            tk.Label(frm,text=PRIVACY_SUMMARY,justify="left",
                     font="TkDefaultFont").pack(anchor="w",padx=10,pady=(0,8))
            tk.Button(frm,text="Privacy & Legal...",command=self._show_privacy
                      ).pack(anchor="w",padx=10,pady=(0,6))
            btn=tk.Button(w,text="Close",command=w.destroy); btn.pack(pady=(0,10))
            w.bind("<Escape>",lambda e:w.destroy())
            try:
                w.update_idletasks()
                x=self.winfo_rootx()+(self.winfo_width()-w.winfo_width())//2
                y=self.winfo_rooty()+(self.winfo_height()-w.winfo_height())//2
                x0,y0,_x1,_y1=_virtual_screen(w)
                w.geometry(f"+{max(x0,x)}+{max(y0,y)}")
            except Exception: pass
            w.grab_set(); btn.focus_set(); return
        w=tk.Toplevel(self); w.title("About"); w.configure(bg=BG)
        w.transient(self); w.resizable(False,False)
        frm=ttk.Frame(w,style="Panel.TFrame"); frm.pack(fill="both",expand=True,padx=10,pady=10)
        ttk.Label(frm,text="MOHAA Model Viewer launcher",style="Panel.TLabel",
                  foreground=ACCENT).pack(anchor="w",padx=10,pady=(8,2))
        ttk.Label(frm,text="made by: Searingwolfe",style="Panel.TLabel").pack(anchor="w",padx=10,pady=(0,2))
        ttk.Label(frm,text=VERSION_LABEL,style="PanelDim.TLabel").pack(anchor="w",padx=10,pady=(0,8))
        ttk.Label(frm,text="Browses MOHAA .pk3 paks and opens .skd models / .tik effects\n"
                           "in a self-contained browser-based 3D viewer.",
                  style="PanelDim.TLabel",justify="left").pack(anchor="w",padx=10,pady=(0,6))
        ttk.Label(frm,text="Engine reference: OpenMOHAA (github.com/openmoh/openmohaa)",
                  style="PanelDim.TLabel").pack(anchor="w",padx=10,pady=(0,8))
        ttk.Label(frm,text=PRIVACY_SUMMARY,style="PanelDim.TLabel",
                  justify="left").pack(anchor="w",padx=10,pady=(0,8))
        ttk.Button(frm,text="Privacy & Legal...",command=self._show_privacy,cursor="hand2"
                   ).pack(anchor="w",padx=10,pady=(0,6))
        btn=ttk.Button(w,text="Close",command=w.destroy,cursor="hand2"); btn.pack(pady=(0,10))
        w.bind("<Escape>",lambda e:w.destroy())
        try:
            w.update_idletasks()
            x=self.winfo_rootx()+(self.winfo_width()-w.winfo_width())//2
            y=self.winfo_rooty()+(self.winfo_height()-w.winfo_height())//2
            x0,y0,_x1,_y1=_virtual_screen(w)
            w.geometry(f"+{max(x0,x)}+{max(y0,y)}")
        except Exception: pass
        self._apply_titlebar(w)
        w.grab_set(); btn.focus_set()

    # ------------------------------------------------------------ updates ---
    @staticmethod
    def _version_tuple(s):
        """'1.0.003' -> (1,0,3). Non-numeric parts count as 0 so a stray tag can
        never crash the comparison."""
        out=[]
        for part in str(s).strip().split("."):
            m=re.match(r"\s*(\d+)",part)
            out.append(int(m.group(1)) if m else 0)
        return tuple(out) if out else (0,)

    def _open_url(self,url):
        try:
            import webbrowser; webbrowser.open(url)
        except Exception: pass

    def _check_for_updates(self):
        """Help --> Check for updates. A small Firefox-style window: the current
        version, a link to the repo, and a background check of version.txt on the
        main branch. Then either 'up to date' or an offer to download + install the
        newer files. Nothing here runs on its own - the network is touched only when
        the user opens this window (see the PRIVACY notice, section 3)."""
        old=OLD_POPUPS
        self._upd_state=None
        w=tk.Toplevel(self); w.title("Check for updates")
        w.transient(self); w.resizable(False,False)
        if not old: w.configure(bg=BG)
        frm=(ttk.Frame(w,style="Panel.TFrame") if not old else tk.Frame(w))
        frm.pack(fill="both",expand=True,padx=16,pady=14)
        if old:
            tk.Label(frm,text="MOHAA Model Viewer",font="TkDefaultFont").pack(anchor="w",pady=(2,2))
            tk.Label(frm,text="Current version:  "+VERSION,font="TkDefaultFont").pack(anchor="w",pady=(0,6))
        else:
            ttk.Label(frm,text="MOHAA Model Viewer",style="Panel.TLabel",
                      foreground=ACCENT).pack(anchor="w",pady=(2,2))
            ttk.Label(frm,text="Current version:  "+VERSION,
                      style="PanelDim.TLabel").pack(anchor="w",pady=(0,6))
        link=tk.Label(frm,text=UPDATE_PAGE_URL,cursor="hand2",font=FONT_SMALL,
                      fg=(ACCENT if not old else "blue"),bg=(PANEL if not old else None))
        link.pack(anchor="w",pady=(0,10))
        link.bind("<Button-1>",lambda e:self._open_url(UPDATE_PAGE_URL))
        status_lbl=(ttk.Label(frm,text="Checking for updates\u2026",style="Panel.TLabel",
                              justify="left") if not old
                    else tk.Label(frm,text="Checking for updates\u2026",justify="left",font="TkDefaultFont"))
        status_lbl.pack(anchor="w",pady=(0,12))
        btnrow=(ttk.Frame(frm,style="Panel.TFrame") if not old else tk.Frame(frm))
        btnrow.pack(fill="x")
        closeb=(ttk.Button(btnrow,text="Close",command=w.destroy,cursor="hand2") if not old
                else tk.Button(btnrow,text="Close",command=w.destroy))
        closeb.pack(side="right")
        w.bind("<Escape>",lambda e:w.destroy())
        try:
            w.update_idletasks()
            x=self.winfo_rootx()+(self.winfo_width()-w.winfo_width())//2
            y=self.winfo_rooty()+(self.winfo_height()-w.winfo_height())//2
            x0,y0,_x1,_y1=_virtual_screen(w)
            w.geometry(f"+{max(x0,x)}+{max(y0,y)}")
        except Exception: pass
        if not old: self._apply_titlebar(w)
        w.grab_set()
        def worker():
            try:
                import urllib.request
                req=urllib.request.Request(UPDATE_VERSION_URL,headers={"User-Agent":UPDATE_UA})
                with urllib.request.urlopen(req,timeout=15) as r:
                    raw=r.read(256).decode("utf-8","replace")
                latest=""
                for ln in raw.splitlines():
                    if ln.strip(): latest=ln.strip(); break
                res={"ok":True,"latest":latest} if latest else {"ok":False,"error":"empty version file"}
            except Exception as e:
                res={"ok":False,"error":str(e)}
            self._upd_state=("checked",res)
        threading.Thread(target=worker,daemon=True).start()
        self.after(200,lambda:self._update_poll(w,status_lbl,btnrow))

    def _upd_add_button(self,row,text,cmd):
        b=(ttk.Button(row,text=text,command=cmd,cursor="hand2") if not OLD_POPUPS
           else tk.Button(row,text=text,command=cmd))
        b.pack(side="right",padx=(0,8)); return b

    def _update_poll(self,w,status_lbl,btnrow):
        try:
            if not w.winfo_exists(): return
        except Exception: return
        st=self._upd_state
        if st is None or st[0]!="checked":
            self.after(200,lambda:self._update_poll(w,status_lbl,btnrow)); return
        res=st[1]; self._upd_state=None
        if not res.get("ok"):
            status_lbl.configure(text="Couldn't reach GitHub - no update information found.\n"
                                      "Check your internet connection and try again later.")
            return
        latest=res["latest"]
        if self._version_tuple(latest)<=self._version_tuple(VERSION):
            status_lbl.configure(text="\u2713  You're up to date.")
        else:
            status_lbl.configure(text="Update available:    "+VERSION+"    \u2192    "+latest)
            self._upd_dl_btn=self._upd_add_button(btnrow,"Download and install",
                                 lambda:self._update_install(w,status_lbl,btnrow,latest))

    def _update_install(self,w,status_lbl,btnrow,latest):
        self._upd_latest=latest
        try: self._upd_dl_btn.destroy()
        except Exception: pass
        status_lbl.configure(text="Downloading "+latest+" \u2026")
        self._upd_state=None
        def worker():
            res=self._update_download_and_apply()
            self._upd_state=("installed",res)
        threading.Thread(target=worker,daemon=True).start()
        self.after(200,lambda:self._update_poll_install(w,status_lbl,btnrow))

    def _update_poll_install(self,w,status_lbl,btnrow):
        try:
            if not w.winfo_exists(): return
        except Exception: return
        st=self._upd_state
        if st is None or st[0]!="installed":
            self.after(200,lambda:self._update_poll_install(w,status_lbl,btnrow)); return
        res=st[1]; self._upd_state=None
        if not res.get("ok"):
            status_lbl.configure(text="Update failed:\n"+str(res.get("error",""))[:220])
            self._upd_dl_btn=self._upd_add_button(btnrow,"Try again",
                                 lambda:self._update_install(w,status_lbl,btnrow,getattr(self,"_upd_latest","")))
            return
        staged=res.get("staged") or []
        if staged:
            status_lbl.configure(text="Update downloaded. The program will now close and\n"
                                      "reopen to finish installing\u2026")
            self.after(1000,lambda:self._restart_program(staged))
        else:
            status_lbl.configure(text="\u2713  Update installed.\n"
                                      "Restart the program for the changes to take effect.")
            self._upd_add_button(btnrow,"Restart now",lambda:self._restart_program())

    def _update_download_and_apply(self):
        """Background worker: download the branch zip, extract it, and copy every file
        over the install root (bin/, docs/, the RUN .bat). Files that are locked and
        can't be overwritten live are written as <file>.new and returned in 'staged'
        for the restart helper to swap in. Returns a result dict - no Tk calls here."""
        import urllib.request
        root=_install_root()
        tmp=tempfile.mkdtemp(prefix="mohaaupd_")
        try:
            zpath=os.path.join(tmp,"repo.zip")
            req=urllib.request.Request(UPDATE_ZIP_URL,headers={"User-Agent":UPDATE_UA})
            with urllib.request.urlopen(req,timeout=90) as r, open(zpath,"wb") as f:
                shutil.copyfileobj(r,f)
            exdir=os.path.join(tmp,"x")
            with zipfile.ZipFile(zpath) as z: z.extractall(exdir)
            tops=[d for d in os.listdir(exdir)
                  if os.path.isdir(os.path.join(exdir,d)) and d!="__MACOSX"]
            src=os.path.join(exdir,tops[0]) if len(tops)==1 else exdir
            replaced=[]; staged=[]
            for dp,_dn,files in os.walk(src):
                rel=os.path.relpath(dp,src)
                for fn in files:
                    s=os.path.join(dp,fn)
                    rp=fn if rel=="." else os.path.join(rel,fn)
                    d=os.path.join(root,rp)
                    try:
                        os.makedirs(os.path.dirname(d) or root,exist_ok=True)
                        try:
                            shutil.copyfile(s,d); replaced.append(rp.replace("\\","/"))
                        except PermissionError:
                            shutil.copyfile(s,d+".new"); staged.append(d)
                    except Exception:
                        pass
            if not replaced and not staged:
                return {"ok":False,"error":"nothing was written (empty download?)"}
            for pc in (os.path.join(root,"bin","__pycache__"),os.path.join(root,"__pycache__")):
                shutil.rmtree(pc,ignore_errors=True)
            return {"ok":True,"replaced":replaced,"staged":staged}
        except Exception as e:
            return {"ok":False,"error":str(e)}
        finally:
            shutil.rmtree(tmp,ignore_errors=True)

    def _restart_program(self,staged=None):
        """Relaunch a fresh launcher and close this one. When files were staged as
        *.new (locked, couldn't be replaced live), a one-shot helper .bat waits for
        THIS process to exit, swaps them in, then starts the new build - the
        'auto-close and auto-reopen' path."""
        launcher=os.path.abspath(__file__)
        exe=sys.executable or "pythonw"
        try:
            if staged:
                pid=os.getpid()
                lines=["@echo off",
                       ":wait",
                       'tasklist /FI "PID eq %d" 2>nul | find "%d" >nul && (ping 127.0.0.1 -n 2 >nul & goto wait)'%(pid,pid)]
                for d in staged:
                    lines.append('move /y "%s.new" "%s" >nul'%(d,d))
                lines.append('start "" "%s" "%s"'%(exe,launcher))
                lines.append('del "%~f0"')
                bat=os.path.join(tempfile.gettempdir(),"mohaa_update_swap.bat")
                with open(bat,"w",encoding="utf-8") as f: f.write("\r\n".join(lines))
                subprocess.Popen(["cmd","/c",bat],**NOWIN)
            else:
                subprocess.Popen([exe,launcher],**NOWIN)
        except Exception:
            pass
        try:
            if getattr(self,"_tmp",None) and os.path.isdir(self._tmp):
                shutil.rmtree(self._tmp,ignore_errors=True)
        except Exception: pass
        try: self.destroy()
        except Exception: pass
        os._exit(0)

    # ------------------------------------------------------------- search ---
    def _on_search(self,_e=None):
        if self._filter_after:
            try: self.after_cancel(self._filter_after)
            except Exception: pass
        self._filter_after=self.after(180,self._rebuild_tree)

    # --------------------------------------------------------------- paks ---
    def _choose_pk3(self):
        ps=filedialog.askopenfilenames(title="Select one or more .pk3 (Pak0, Pak2, expansions...)",
            filetypes=[("MOHAA pak","*.pk3"),("Zip","*.zip"),("All files","*.*")])
        if ps: self._add_pk3s(list(ps))

    def _clear_pk3s(self):
        self._pk3_paths=[]; self._cfg["pk3s"]=[]; self._save_config()
        self._tree.delete(*self._tree.get_children()); self._tree_entry.clear(); self._all_files=[]
        self._pk3_label.configure(text="No .pk3 loaded")
        self._vfs=None; self._SH=None; self._TI=None; self._tex_ready=False
        self._set_status("Paks cleared","0 paks")

    def _add_pk3s(self, paths):
        added=0
        for path in paths:
            if not os.path.exists(path): continue
            try: zipfile.ZipFile(path).close()
            except Exception as e: self._log_line(f"Could not open {os.path.basename(path)}: {e}","err"); continue
            if path not in self._pk3_paths: self._pk3_paths.append(path); added+=1
        if not added and paths: return
        self._cfg["pk3s"]=self._pk3_paths if self._remember.get() else []
        self._cfg.pop("pk3",None); self._save_config()
        n=len(self._pk3_paths)
        head=os.path.basename(self._pk3_paths[0]) if n else ""
        self._pk3_label.configure(text=(head+(f"  +{n-1} more" if n>1 else "")+"  /  models") if n else "No .pk3 loaded")
        self._reload_all()
        self._log_line(f"Loaded {n} pak(s): "+", ".join(os.path.basename(p) for p in self._pk3_paths),"ok")
        self._set_status("Paks loaded",f"{n} pak(s)")

    def _reload_all(self):
        """Rebuild the combined model tree from every loaded pak, reset the temp
        workspace, and (re)build texture indexes + shared anims in the background."""
        self._populate_tree(self._pk3_paths)
        if self._tmp and os.path.isdir(self._tmp): shutil.rmtree(self._tmp,ignore_errors=True)
        self._tmp=tempfile.mkdtemp(prefix="mohaaview_"); self._animroot=os.path.join(self._tmp,"models")
        self._tex_ready=False; self._tex_gen+=1
        self._set_status("Indexing textures...")
        threading.Thread(target=self._prepare_indexes,args=(self._tex_gen,list(self._pk3_paths)),daemon=True).start()

    def _prepare_indexes(self, gen, paks):
        # extract shared human animations from all paks (for posing characters)
        try:
            roots=("models/human/animation/idle/","models/human/animation/walks_runs/",
                   "models/human/animation/misc/")
            for p in paks:
                try:
                    zf=zipfile.ZipFile(p)
                    for n in zf.namelist():
                        low=n.lower()
                        if low.endswith(".skc") and any(low.startswith(r) for r in roots):
                            self._extract_one(zf,n)
                    zf.close()
                except Exception: pass
        except Exception: pass
        # build texture resolution indexes (shaders + tik skins) across all paks
        if MTX is None:
            self._log_q.put(("dim","(mohaa_textures.py not found - models will load untextured)")); return
        try:
            vfs=MTX.Vfs(paks); SH=MTX.build_shader_index(vfs); TI=MTX.build_tik_index(vfs)
            GS=MTX.build_global_surface_shaders(TI)
            PROPS=MTX.build_shader_props(vfs) if hasattr(MTX,"build_shader_props") else {}
            if gen!=self._tex_gen: return        # a newer reload superseded this one
            old=self._vfs
            self._vfs=vfs; self._SH=SH; self._TI=TI; self._GS=GS; self._PROPS=PROPS; self._tex_ready=True
            if old is not None and hasattr(old,"close"):
                try: old.close()                  # release the previous reload's pak handles
                except Exception: pass
            self._log_q.put(("ok",f"Textures ready: {len(SH)} shaders, {len(TI)} skinned models indexed."))
            self._log_q.put(("status","Textures ready"))
        except Exception as e:
            self._log_q.put(("err",f"Texture index failed: {e}"))

    # Everything the viewer actually consumes out of the workspace folder. A .pk3 is just
    # a zip and may contain anything at all; nothing outside this set is ever written to
    # disk, so a hostile pak cannot drop a .bat / .exe / .ps1 / .desktop payload even if
    # the user goes on to build the model that sits beside it.
    _EXTRACT_OK={".skd",".skb",".skc",".tik",".map",".txt",".shader",
                 ".tga",".jpg",".jpeg",".png",".dds",".tif",".tiff"}
    # Windows resolves these as DEVICES no matter what directory or extension they carry.
    _WIN_RESERVED={"con","prn","aux","nul","clock$"} | {p+str(i) for p in ("com","lpt") for i in range(1,10)}

    def _safe_target(self, name):
        """Resolve a pak entry name to a path INSIDE the workspace, or None to refuse it.

        Pak entry names are attacker-controlled - the zip central directory can say
        anything, including "models/x/../../../../../../Startup/pwn.bat". The old
        os.path.join(self._tmp,*name.split("/")) let those '..' segments escape %TEMP%
        and land the write anywhere the user could write (and on Windows a bare "C:"
        component silently re-rooted the join as well). Every component is reduced to a
        plain name here, the extension is checked against the allow-list, and the result
        is re-verified against the workspace root with realpath so a symlink or NTFS
        junction in the middle cannot slip past either."""
        root=self._tmp
        if not root: return None
        if os.path.splitext(name)[1].lower() not in self._EXTRACT_OK: return None
        parts=[]
        for seg in name.replace("\\","/").split("/"):
            seg=seg.strip().rstrip(". ")             # Win32 strips trailing dots/spaces itself
            if not seg or seg in (".",".."): return None
            if ":" in seg: return None               # "C:" drive token / NTFS alternate data stream
            if seg.split(".")[0].lower() in self._WIN_RESERVED: return None
            parts.append(seg)
        if not parts: return None
        target=os.path.join(root,*parts)
        try:
            rr=os.path.normcase(os.path.realpath(root))
            rt=os.path.normcase(os.path.realpath(target))
        except OSError: return None
        if rt!=rr and not rt.startswith(rr+os.sep): return None
        return target

    def _extract_one(self, zf, name, force=False):
        target=self._safe_target(name)
        if target is None:
            self._log_q.put(("dim","(skipped unsafe pak entry: %s)"%name[:120])); return None
        if not force and os.path.exists(target) and os.path.getsize(target)>0: return target  # cached
        os.makedirs(os.path.dirname(target),exist_ok=True)
        with zf.open(name) as src, open(target,"wb") as dst: shutil.copyfileobj(src,dst)
        return target

    def _extract_model_map(self, stem, dest_dir):
        """Extract <stem>.map (the model's world-space clip/box brushes) into dest_dir so the viewer
        can derive `setsize` from it. MOHAA keeps these under models/ but NOT always beside the .skd
        (e.g. models/static/indycrate.skd while the .map may sit elsewhere in the models/ tree), so
        the prefix/sibling passes can miss it - we match by basename across every loaded pak, prefer a
        path under models/ (over a same-named level .map), and let later paks override earlier. The
        viewer looks for <stem>.map next to the model (mohaa_view.parse_map_bounds). Returns the
        written path or None."""
        if not self._pk3_paths: return None
        want=stem.lower()+".map"; best=None   # (score, data); lower score wins
        for p in self._pk3_paths:
            try: zf=zipfile.ZipFile(p)
            except Exception: continue
            try:
                for n in zf.namelist():
                    if n.endswith("/") or os.path.basename(n).lower()!=want: continue
                    score=0 if "models/" in n.lower() else 1
                    if best is None or score<=best[0]:
                        try: best=(score,zf.read(n))
                        except Exception: continue
            finally: zf.close()
        if not best: return None
        try:
            tgt=os.path.join(dest_dir,stem+".map")
            with open(tgt,"wb") as f: f.write(best[1])
            return tgt
        except OSError: return None

    def _populate_tree(self, paks):
        """Scan every pak's models/ tree into self._all_files, then build the
        (optionally filtered) Treeview from it."""
        skds={}; tiks={}   # relpath -> display (later paks override earlier)
        for p in paks:
            try: names=zipfile.ZipFile(p).namelist()
            except Exception: continue
            for n in names:
                if not n.lower().startswith("models/"): continue
                if n.endswith("/"): continue
                nl=n.lower()
                if nl.endswith(".skd"): skds[n]=n
                elif nl.endswith(".tik"): tiks[n]=n
        self._all_files=[(k,"skd") for k in skds]+[(k,"tik") for k in tiks]
        self._rebuild_tree()
        nf=len({("/".join(k.split("/")[:-1])) for k,_ in self._all_files})
        self._log_line(f"{len(skds)} models, {len(tiks)} .tik across {nf} folders (combined from {len(paks)} pak(s)).","dim")

    def _rebuild_tree(self):
        """Build the Treeview from self._all_files, applying the search filter.
        A filter match keeps the file and all its ancestor folders; filtered
        views auto-expand so hits are visible immediately."""
        self._tree.delete(*self._tree.get_children()); self._tree_entry.clear()
        q=(self._search_var.get() or "").strip().lower() if hasattr(self,"_search_var") else ""
        files=[(k,kind) for (k,kind) in self._all_files if (not q or q in k.lower())]
        folders=set()
        for k,_ in files:
            d=k[:k.rfind("/")] if "/" in k else "models"
            parts=d.split("/")
            for i in range(1,len(parts)+1): folders.add("/".join(parts[:i]))
        open_all=bool(q)
        node={"models":self._tree.insert("","end",text="models",open=True,tags=("folder",))}
        for fp in sorted(folders):
            if fp=="models": continue
            parent="/".join(fp.split("/")[:-1])
            node[fp]=self._tree.insert(node.get(parent,node["models"]),"end",text=fp.split("/")[-1],open=open_all,tags=("folder",))
        for sp in sorted(k for k,kind in files if kind=="skd"):
            parent="/".join(sp.split("/")[:-1])
            iid=self._tree.insert(node.get(parent,node["models"]),"end",text=sp.split("/")[-1],tags=("skd",))
            self._tree_entry[iid]=sp
        for tp in sorted(k for k,kind in files if kind=="tik"):
            parent="/".join(tp.split("/")[:-1])
            iid=self._tree.insert(node.get(parent,node["models"]),"end",text=tp.split("/")[-1],tags=("tik",))
            self._tree_entry[iid]=tp
        if q: self._set_status(f"Filter: '{q}' - {len(files)} match(es)")
        elif self._all_files: self._set_status("Ready")

    def _on_tree_select(self, _):
        sel=self._tree.selection()
        if len(sel)>1:
            self._set_status(f"{len(sel)} items selected - right-click to batch build")
        if sel and sel[0] in self._tree_entry: self._path_var.set("pk3://"+self._tree_entry[sel[0]])

    def _on_tree_activate(self, _):
        self._hide_treetip()
        sel=self._tree.selection()
        if len(sel)>1: self._build_selected(sel); return
        if sel and sel[0] in self._tree_entry: self._open_pk3_model(self._tree_entry[sel[0]])

    def _viewer_open_busy(self):
        """A previous open-in-viewer request is still building: reject this one.
        Build-only requests (_run_opts['no_open'], set by right-click Build only
        and by every batch step) are exempt and never blocked here."""
        if self._run_opts.get("no_open") or self._run_opts.get("external"): return False
        if self._opening_view:
            self._log_line("Please wait until the current file(s) finish building.","err")
            return True
        return False

    def _queue_open_until_indexed(self, entry):
        """A pk3 open arrived before the texture/VFS index finished. Latch it and let
        _poll_log fire it automatically the instant the index is ready (or drop it on an
        Escape-cancel). Building an untextured HTML now would cache it and serve it
        forever, so we wait instead. While queued, any further open request hits
        _viewer_open_busy -> "Please wait until the current file(s) finish building.".
        Shared by the .skd (_open_pk3_model) and .tik (_open_pk3_tik) open paths."""
        interactive=(self._auto_open.get() and not self._run_opts.get("no_open")
                     and not self._run_opts.get("external"))
        self._log_line("Textures/VFS still indexing - viewer will open shortly...","err")
        if interactive:
            self._building_name=os.path.basename(entry)   # so Escape can cancel the queued open
            self._opening_view=True                       # block further opens until it fires
            self._pending_open=(entry,self._build_gen)
            self._set_status("Textures indexing - viewer queued...")
        else:
            self._batch_signal()                          # build-only/drag-out: never stall a batch

    def _open_pk3_model(self, entry, loose_path=None):
        if self._viewer_open_busy(): return
        if entry.lower().endswith(".tik"): return self._open_pk3_tik(entry, loose_path)
        subdir=STANDALONE_SUBDIR if loose_path else self._entry_subdir(entry)
        # already built? open the saved HTML straight from the output folder - no
        # extraction, no texture resolve, no build (right-click > Rebuild to force).
        # A loose open resolves its own cache in _load, so skip this pak-cache probe.
        if loose_path is None and self._reuse_ok():
            hp=os.path.join(self._outdir, subdir or "", self._viewer_html_name(entry))
            if os.path.exists(hp) and self._html_current(hp):
                self._last_subdir=subdir; self._open_cached(hp,entry,subdir); return
        if not self._pk3_paths or not self._tmp:
            self._log_line("Load a .pk3 first.","err"); return
        # textures not indexed yet? queue this open and fire it once the index is ready,
        # instead of building an untextured HTML that then gets cached and served forever
        # (the .skd counterpart of the .tik defer). With no texture module at all (MTX is
        # None) there is no index to wait for, so fall through and build untextured.
        if MTX is not None and (self._vfs is None or not self._tex_ready):
            self._queue_open_until_indexed(entry); return
        self._log_line(f"Extracting {entry} ...","dim"); self._set_status(f"Extracting {os.path.basename(entry)}...")
        self._building_name=os.path.basename(entry)
        if self._auto_open.get() and not self._run_opts.get("no_open") and not self._run_opts.get("external"): self._opening_view=True
        gen=self._tex_gen; bgen=self._build_gen
        def work():
            try:
                if loose_path:                                  # loose .skd from disk: use it as-is
                    skd_target=os.path.join(self._tmp, os.path.basename(loose_path))
                    try: shutil.copyfile(loose_path, skd_target)
                    except Exception as e:
                        self._log_q.put(("err",f"Could not read {os.path.basename(loose_path)}: {e}")); return
                else:
                    prefix="/".join(entry.split("/")[:-1])+"/"; skd_target=None
                    for p in self._pk3_paths:                       # later paks override earlier
                        if bgen!=self._build_gen: return            # Escape: cancelled
                        try: zf=zipfile.ZipFile(p)
                        except Exception: continue
                        for n in zf.namelist():
                            if n.startswith(prefix) and not n.endswith("/"):
                                t=self._extract_one(zf,n,force=True)
                                if n==entry: skd_target=t
                        zf.close()
                    if not skd_target:
                        self._log_q.put(("err","Could not find that .skd inside the loaded paks")); return
                # A loose .skd carries only a basename. Resolve its VFS twin so the texture
                # index (surface->shader maps keyed by full pak path) still applies, and pull
                # its sibling .skc/.tik/.map next to it so animations and skins load - the same
                # dependencies a tree open gets for free from its folder-prefix extraction.
                tex_key=entry
                if loose_path and self._vfs is not None:
                    bn="/"+os.path.basename(entry).lower()
                    vk=next((k for k in self._vfs.names() if k.endswith(bn)),None)
                    if vk:
                        tex_key=vk
                        folder="/".join(vk.split("/")[:-1])+"/"
                        for k in list(self._vfs.names()):
                            if k.startswith(folder) and not k.endswith("/") and (k.endswith(".skc") or k.endswith(".tik") or k.endswith(".map")):
                                d=self._vfs.read(k)
                                if d:
                                    with open(os.path.join(self._tmp,os.path.basename(k)),"wb") as f: f.write(d)
                # pull the model's .map (setsize source) next to the .skd, wherever it lives in the paks
                try:
                    mp=self._extract_model_map(os.path.splitext(os.path.basename(entry))[0], os.path.dirname(skd_target))
                    if mp: self._log_q.put(("dim",f"setsize .map: {os.path.basename(mp)}"))
                except Exception: pass
                # resolve textures -> manifest (if the index is ready)
                manifest=None
                if MTX is not None and self._tex_ready and self._vfs is not None and gen==self._tex_gen:
                    try:
                        import mohaa_view as MV
                        surfs=[s["name"] for s in MV.parse_skd(skd_target)["surfaces"]]
                        manifest=os.path.join(self._tmp,"_tex_"+os.path.basename(entry)+".json")
                        nt,ns=MTX.write_textures_manifest(self._vfs,tex_key,surfs,self._SH,self._TI,manifest,global_surf=self._GS,shader_props=self._PROPS)
                        self._log_q.put(("dim",f"textures: {nt}/{ns} surfaces"))
                        if nt<ns: self._report_surface_misses(manifest,surfs)
                        if nt==0: manifest=None
                    except Exception as e:
                        self._log_q.put(("dim",f"(texture resolve skipped: {e})")); manifest=None
                elif MTX is not None and not self._tex_ready:
                    self._log_q.put(("dim","(textures still indexing - opening untextured for now)"))
                if bgen!=self._build_gen: return                # Escape: cancelled
                self._animcat=None; self._animcat_file=None; self._animcat_for=None
                self._log_q.put(("load",(skd_target,self._animroot,manifest,None,subdir)))
            except Exception as e:
                self._log_q.put(("err",f"Extract failed: {e}"))
        threading.Thread(target=work,daemon=True).start()

    def _resolve_skel_vfs(self, skel, pathhead, entry=None):
        """Resolve a .tik `skelmodel` reference to a VFS key, trying the .skb<->.skd twin.
        Many retail .tik files still reference a stale <n>.skb while the pak only ships
        <n>.skd (flaregun, papers_o, wirecutters, ...). The engine dispatches skeletal
        loading by extension - TIKI_RegisterSkel .skb->TIKI_LoadSKB / .skd->TIKI_LoadSKD
        (openmoh/openmohaa code/tiki/tiki_skel.cpp:1116,1142-1150) - and its bare-skelmodel
        fallback normalises to .skd (tiki_files.cpp:243-251), so a missing .skb resolves to
        the shipped .skd. The referenced extension is tried in full first (no regression for
        correctly-referenced models); the twin is only a fallback. Returns the key or None."""
        if self._vfs is None: return None
        skel=(skel or "").replace("\\","/").strip().strip('"')
        if not skel: return None
        pathhead=(pathhead or "").replace("\\","/").strip().strip('"')
        skel_dir=os.path.dirname(skel)                        # "" when the ref is a bare name
        stem,ext=os.path.splitext(os.path.basename(skel))
        exts=[ext]                                            # referenced extension first...
        twin={".skb":".skd",".skd":".skb"}.get(ext.lower())   # ...then the .skb<->.skd twin
        if twin and twin not in [e.lower() for e in exts]: exts.append(twin)
        for e in exts:
            nm=stem+e
            cands=[]
            if skel_dir:  cands.append(skel_dir+"/"+nm)                        # ref carried its own path
            if pathhead:  cands.append(pathhead.rstrip("/")+"/"+nm)            # setup `path` + name
            if entry:     cands.append("/".join(entry.split("/")[:-1])+"/"+nm) # next to the opened .tik
            for c in cands:
                if self._vfs.exists(c): return self._vfs._k(c)
            bn="/"+nm.lower()                                                  # last resort: basename match
            for k in self._vfs.names():
                if k.endswith(bn): return k
        return None

    def _open_pk3_tik(self, entry, loose_path=None):
        """Open a .tik effect/emitter: extract the tik, resolve+extract its skelmodel
        (which usually lives in a different models/fx/* folder) next to it, pull in the
        skelmodel's .skc/.tik siblings and textures, then hand the .tik to the viewer.
        loose_path, when set, is an on-disk .tik opened from Browse/drag-drop: its own
        edited content drives the build while its dependencies resolve from the paks."""
        subdir=STANDALONE_SUBDIR if loose_path else self._entry_subdir(entry)
        # noted for on-demand animation builds: a cache hit returns below without
        # extracting anything, so the catalogue is rebuilt lazily from this entry the
        # first time the viewer asks for an animation (_ensure_anim_ctx)
        self._anim_entry=(loose_path or entry)
        if loose_path is None and self._reuse_ok():
            hp=os.path.join(self._outdir, subdir or "", self._viewer_html_name(entry))
            if os.path.exists(hp) and self._html_current(hp):
                self._animcat=None; self._animcat_file=None; self._animcat_for=None
                self._last_subdir=subdir; self._open_cached(hp,entry,subdir); return
        if not self._pk3_paths or not self._tmp:
            self._log_line("Load a .pk3 first.","err"); return
        if self._vfs is None or not self._tex_ready:
            if MTX is None:                       # no texture module -> index never completes
                self._log_line("Textures unavailable (mohaa_textures.py not found).","err"); return
            self._queue_open_until_indexed(entry); return
        self._log_line(f"Extracting effect {entry} ...","dim"); self._set_status(f"Extracting {os.path.basename(entry)}...")
        self._building_name=os.path.basename(entry)
        if self._auto_open.get() and not self._run_opts.get("no_open") and not self._run_opts.get("external"): self._opening_view=True
        gen=self._tex_gen; bgen=self._build_gen
        def work():
            try:
                import mohaa_view as MV
                # 1) get the .tik onto disk in the temp workspace (loose file: copy it in
                #    as-is so the user's edits drive the build; pak entry: extract it)
                if loose_path:
                    tik_target=os.path.join(self._tmp, os.path.basename(loose_path))
                    try: shutil.copyfile(loose_path, tik_target)
                    except Exception as e:
                        self._log_q.put(("err",f"Could not read {os.path.basename(loose_path)}: {e}")); return
                else:
                    tik_target=None
                    for p in self._pk3_paths:
                        if bgen!=self._build_gen: return            # Escape: cancelled
                        try: zf=zipfile.ZipFile(p)
                        except Exception: continue
                        for n in zf.namelist():
                            if n.lower()==entry.lower() and not n.endswith("/"):
                                tik_target=self._extract_one(zf,n,force=True)
                        zf.close()
                    if not tik_target:
                        self._log_q.put(("err","Could not find that .tik inside the loaded paks")); return
                # latin-1, explicitly: every OTHER path decodes pak bytes as latin-1
                # (expand_tik_includes, build_shader_index), while a bare open() uses the
                # LOCALE codec - cp1252 here, cp932 on a Japanese Windows, UTF-8 on Linux.
                # The same .tik then parsed differently per machine. latin-1 is also
                # byte-transparent, so it can never raise on a stray high byte.
                txt=open(tik_target,"r",encoding="latin-1",errors="replace").read()
                # ANIMATION CATALOGUE, built from the RAW tik text - before the $include
                # splice below. It has to be: mohaa_textures.build_anim_catalog walks the
                # includes itself so it can keep each file's own $path scope, which is what
                # the engine does (TikiScript::path is per-script, tiki_script.cpp:50/414-421)
                # and what a flat splice destroys. This is what turns allied_pilot.tik from
                # "8 balcony animations" into its full reach across new_generic_human.tik,
                # every `includes <map>{}` group and the dialogue tik.
                self._animcat=None; self._animcat_file=None; self._animcat_for=None
                if MTX is not None and hasattr(MTX,"build_anim_catalog"):
                    try:
                        _cat=MTX.build_anim_catalog(txt, self._vfs, entry)
                        if _cat.get("anims"):
                            _cf=os.path.join(self._tmp,"animcat_"+re.sub(r"[^A-Za-z0-9_.-]","_",
                                             os.path.basename(entry))+".json")
                            with open(_cf,"w",encoding="utf-8") as _f:
                                json.dump(_cat,_f,separators=(",",":"))
                            self._animcat=_cat; self._animcat_file=_cf; self._animcat_for=tik_target
                            self._log_q.put(("dim",f"animations: {len(_cat['anims'])} unique across "
                                                  f"{len(_cat['nodes'])} menu group(s), {_cat['files']} file(s)"))
                            if _cat.get("missing"):
                                self._log_q.put(("dim","(unresolved $include: "+", ".join(_cat["missing"][:4])
                                                +(" ..." if len(_cat["missing"])>4 else "")+")"))
                    except Exception as _e:
                        self._log_q.put(("dim",f"(animation catalogue failed: {_e})"))
                if MTX is not None: txt=MTX.expand_tik_includes(txt, self._vfs)   # splice $include'd _base.txt (grenades)
                open(tik_target,"w",encoding="utf-8",errors="replace").write(txt)  # write back so mohaa_view.py sees expanded content
                emitters=MV.parse_tik_emitters(txt)
                # anim-level client spawn blocks (tagspawn/originspawn bursts) also
                # reference sprite / sub-model targets; collect their param dicts so
                # the sprite resolver below covers them too.
                anim_prms=[]; tikanims=[]
                try:
                    tikanims=MV.parse_tik_animations(txt)
                    for ta in tikanims:
                        for c in ta.get("client",[]):
                            # any client frame command carrying a ( ... ) block is a spawn
                            # block, including wrapped forms like `entry commanddelay 0.100
                            # originspawn` (fx_bike_explosion) - collect them all so their
                            # sprites resolve
                            if c.get("prm"):
                                anim_prms.append(c["prm"])
                        # server `explosioneffect <type>` (tankshellexplosion.tik) redirects to a
                        # base explosion .tik (bazooka -> models/fx/bazookaexp_base.tik, etc -
                        # MV._EXPLOSIONEFFECT_TIK, mirroring cg_parsemsg CG_MakeExplosionEffect).
                        # It has no ( ) block, so synthesise a prm with that .tik model so the
                        # sub-tik resolver + expand_subfx below flatten its effects.
                        for c in ta.get("server",[]):
                            av=c.get("argv") or []
                            _cmd,_rest,_dl=MV._strip_cmd_prefix(av)
                            if _cmd=="explosioneffect":
                                _et=(_rest[0].strip('"').lower() if _rest else "grenade")
                                _tik=MV._EXPLOSIONEFFECT_TIK.get(_et,MV._EXPLOSIONEFFECT_TIK["grenade"])
                                anim_prms.append({"model":_tik})
                except Exception: pass
                # init{client{}} `sfx originspawn ( ... )` one-shots (grenexp_water)
                # reference sprites too - include them so their billboards resolve
                try:
                    for _s in MV.parse_tik_init_sfx(txt):
                        if _s.get("prm"): anim_prms.append(_s["prm"])
                except Exception: pass
                pathhead,skel=MV.parse_tik_setup_head(txt)
                tik_dir=os.path.dirname(tik_target)
                manifest=None
                if not skel:
                    self._log_q.put(("err","this .tik defines no skelmodel - no still frame to anchor the effect yet")); return
                skel=skel.replace("\\","/").strip().strip('"')
                pathhead=(pathhead or "").replace("\\","/").strip().strip('"')
                # 2) resolve the skelmodel over the VFS (retail .tik files often carry a stale
                #    <n>.skb while the pak only ships <n>.skd - the resolver tries the twin)
                skel_vfs=self._resolve_skel_vfs(skel, pathhead, entry)
                if not skel_vfs:
                    self._log_q.put(("err",f"skelmodel '{skel}' not found in loaded paks")); return
                data=self._vfs.read(skel_vfs)
                if not data:
                    self._log_q.put(("err","skelmodel is indexed but could not be read")); return
                skd_out=os.path.join(tik_dir,os.path.basename(skel))
                with open(skd_out,"wb") as f: f.write(data)
                self._log_q.put(("dim",f"skelmodel: {skel_vfs}"))
                # 3) pull the skelmodel's sibling .skc (animation), .tik (shaders) and .map (the
                #    world-space clip box the viewer derives setsize from) next to it
                skel_folder="/".join(skel_vfs.split("/")[:-1])+"/"
                sib=0
                for k in list(self._vfs.names()):
                    if k.startswith(skel_folder) and not k.endswith("/") and (k.endswith(".skc") or k.endswith(".tik") or k.endswith(".map")):
                        d=self._vfs.read(k)
                        if d:
                            with open(os.path.join(tik_dir,os.path.basename(k)),"wb") as f: f.write(d); 
                            sib+=1
                if sib: self._log_q.put(("dim",f"+{sib} animation/shader sibling(s)"))
                # ensure the model's .map (setsize source) is present next to the skelmodel even if it
                # doesn't sit in the skelmodel's folder (matched by basename across paks)
                try: self._extract_model_map(os.path.splitext(os.path.basename(skel))[0], tik_dir)
                except Exception: pass
                # 3c) extract every .skc the tik's animations{} references (basename match
                # across the VFS) so the viewer can play each named anim. Vehicles reference
                # sibling files (already pulled above); effect/human tiks pull anims from
                # other folders. Capped so a 600-anim player model doesn't stall the open.
                try:
                    _pre=self._anim_preload_n()
                    _own=[e for e in (self._animcat or {}).get("anims",[]) if e.get("d")][:_pre]
                    if self._animcat and _own:
                        # pull the .skc for the animations the .tik declares ITSELF (jeep,
                        # effect tiks) so the page can bake them and their per-anim fx fire at
                        # load, exactly as before. Extracted under the entry's
                        # own id, not its basename - `salute idle/salute.skc` and
                        # `american_salute misc/salute.skc` are two different animations
                        # that a basename sweep silently collapsed into one.
                        _ad=os.path.join(tik_dir,"_anims"); os.makedirs(_ad,exist_ok=True)
                        got=0; miss=0
                        for _e in _own:
                            if bgen!=self._build_gen: return    # Escape: cancelled
                            _tg=os.path.join(_ad,_e["id"]+".skc")
                            if os.path.exists(_tg): continue
                            _d=self._vfs_read_skc(_e["s"])
                            if _d is None: miss+=1; continue
                            with open(_tg,"wb") as f: f.write(_d)
                            got+=1
                        if got: self._log_q.put(("dim",f"+{got} animation .skc extracted"
                                                       +(f" ({miss} unresolved)" if miss else "")))
                    elif self._animcat:
                        self._log_q.put(("dim",f"{len(self._animcat['anims'])} animation(s), none declared "
                                              f"by the .tik itself - each builds on first click"))
                    else:
                        # no catalogue (a .tik whose animations{} the resolver could not
                        # reach): keep the original basename sweep as the fallback
                        refs={os.path.basename((ta.get("file") or "").replace("\\","/")).lower()
                              for ta in tikanims}
                        refs={r for r in refs if r.endswith(".skc")}
                        got=0
                        for r in sorted(refs):
                            if bgen!=self._build_gen: return
                            tgt=os.path.join(tik_dir,r)
                            if os.path.exists(tgt): continue
                            k=next((kk for kk in self._vfs.names() if kk.endswith("/"+r)),None)
                            if not k: continue
                            d=self._vfs.read(k)
                            if d:
                                with open(tgt,"wb") as f: f.write(d)
                                got+=1
                            if got>=300:
                                self._log_q.put(("dim","(animation extraction capped at 300 .skc)")); break
                        if got: self._log_q.put(("dim",f"+{got} referenced animation .skc extracted"))
                except Exception as _e: self._log_q.put(("dim",f"(animation extraction: {_e})"))
                # 3b) extract the OTHER skelmodels this .tik assembles (head, hands, helmet, ...)
                #     next to the tik so the viewer merges them into one static model, as in-game.
                part_disk=[skd_out]                          # body first
                try: all_parts=MV.parse_tik_skelmodels(txt)
                except Exception: all_parts=[]
                for (pp,ps) in all_parts[1:]:
                    ps=(ps or "").replace("\\","/").strip().strip('"')
                    pp=(pp or "").replace("\\","/").strip().strip('"')
                    if not ps: continue
                    pv=self._resolve_skel_vfs(ps, pp)   # twin-aware; attached parts can be stale-.skb too
                    if not pv:
                        self._log_q.put(("dim",f"(attached part not found: {ps})")); continue
                    pd=self._vfs.read(pv)
                    if not pd: continue
                    pout=os.path.join(tik_dir,os.path.basename(ps))
                    with open(pout,"wb") as f: f.write(pd)
                    part_disk.append(pout)
                    pfolder="/".join(pv.split("/")[:-1])+"/"     # pull that part's sibling .skc too
                    for k in list(self._vfs.names()):
                        if k.startswith(pfolder) and k.endswith(".skc"):
                            dd=self._vfs.read(k)
                            if dd:
                                with open(os.path.join(tik_dir,os.path.basename(k)),"wb") as f: f.write(dd)
                if len(part_disk)>1:
                    self._log_q.put(("dim",f"assembled {len(part_disk)} parts: "+", ".join(os.path.basename(p) for p in part_disk)))
                # 4) resolve textures for the skelmodel's surfaces
                if bgen!=self._build_gen: return                # Escape: cancelled
                if MTX is not None and self._tex_ready and gen==self._tex_gen:
                    try:
                        # combined surface list across all assembled parts (body + head + hands)
                        surfs=[]
                        for pdp in part_disk:
                            try: surfs+=[s["name"] for s in MV.parse_skd(pdp)["surfaces"]]
                            except Exception: pass
                        seen=set(); surfs=[s for s in surfs if not (s in seen or seen.add(s))]
                        manifest=os.path.join(self._tmp,"_tex_"+os.path.basename(entry)+".json")
                        # The opened .tik's OWN setup maps this skd's surfaces to the right shader
                        # (e.g. bangalore_pulsating vs ..._ghosting vs plain bangalore - all skin the
                        # same bangalore.skd). The global tik index keeps only one mapping per skd, so
                        # let the opened tik's mapping take precedence for correct per-variant skins.
                        local_TI=dict(self._TI)
                        allpairs=[]
                        try:
                            tik_map=MTX.parse_tik_setup(txt)
                            local_TI.update(tik_map)
                            # the assembled model skins ALL parts' surfaces under one mesh, so make
                            # every part's surface->shader visible under the body key the manifest uses
                            for v in tik_map.values(): allpairs+=v
                            local_TI[skel_vfs]=allpairs; local_TI[skel_vfs.lower()]=allpairs
                        except Exception: pass
                        nt,ns=MTX.write_textures_manifest(self._vfs,skel_vfs,surfs,self._SH,local_TI,manifest,global_surf=self._GS,shader_props=self._PROPS)
                        self._log_q.put(("dim",f"textures: {nt}/{ns} surfaces"))
                        # SILENT MISS: the .skd path already reports unresolved surfaces, but this
                        # .tik path never did - it printed "textures: 0/1 surfaces" and moved on,
                        # so muzflash_bar.tik came out untextured with NO error line at all.
                        # Pass the tik's own surface->shader pairs so the reason can name the
                        # shader that failed to resolve rather than claiming there was no mapping.
                        if nt<ns: self._report_surface_misses(manifest,surfs,dict(allpairs))
                        if nt==0: manifest=None
                    except Exception as e:
                        self._log_q.put(("dim",f"(texture resolve skipped: {e})")); manifest=None
                # 5) resolve each emitter's sprite/sub-model -> billboard texture data URL
                # (setup emitters + anim-level spawn blocks in one pass; a second pass
                # resolves sprites referenced from INSIDE flattened dummy sub-tiks,
                # e.g. snipesmoke's vsssource.spr)
                emittex=self._resolve_emitter_sprites(emitters+anim_prms)
                inner=[]
                for ent in emittex.values():
                    if isinstance(ent,dict) and ent.get("subfx"): inner+=ent["subfx"]
                if inner:
                    more=self._resolve_emitter_sprites(inner)
                    for k,v in more.items(): emittex.setdefault(k,v)
                # MISSING-ASSET DIAGNOSTIC: any `model` ref still absent from emittex
                # never produced a sprite. Say so in red rather than silently dropping
                # to an untextured blob (adam-firefill -> senn_fire1.spr / senn_fire2.spr).
                self._warn_emitter_assets(emitters+anim_prms+inner, emittex)
                emittex_file=None
                if emittex:
                    emittex_file=os.path.join(self._tmp,"_emit_"+os.path.basename(entry)+".json")
                    try:
                        with open(emittex_file,"w",encoding="utf-8") as _ef: json.dump(emittex,_ef)
                    except Exception: emittex_file=None
                    self._log_q.put(("dim",f"emitter sprites: {len(emittex)} resolved"))
                self._log_q.put(("dim",f"{len(emitters)} particle emitter(s) parsed"))
                if bgen!=self._build_gen: return                # Escape: cancelled
                self._log_q.put(("load",(tik_target,self._animroot,manifest,emittex_file,subdir)))
            except Exception as e:
                self._log_q.put(("err",f"Effect extract failed: {e}"))
        threading.Thread(target=work,daemon=True).start()

    def _submodel_basesize(self, sub_text):
        """For a .tik sub-model particle (e.g. bh_metal_fastpiece -> splinter.skd), return
        (longest_world_size, aspect) where size = the skelmodel's longest bind-pose axis
        times the sub-tik's `scale`, and aspect = longest/middle extent. Lets the viewer
        draw mesh particles as the small, thin slivers they are. Returns (0.0, 1.0) on miss."""
        if self._vfs is None: return (0.0, 1.0)
        try:
            import mohaa_view as MV
            pathhead, skel = MV.parse_tik_setup_head(sub_text)
            if not skel: return (0.0, 1.0)
            skel=skel.replace("\\","/").strip().strip('"')
            pathhead=(pathhead or "").replace("\\","/").strip().strip('"')
            m=re.search(r'\bscale\s+([-\d.]+)', sub_text, re.I)
            tscale=float(m.group(1)) if m else 1.0
            cands=[]
            if "/" in skel or skel.lower().startswith("models/"): cands.append(skel)
            if pathhead: cands.append(pathhead.rstrip("/")+"/"+os.path.basename(skel))
            skel_vfs=None
            for c in cands:
                if self._vfs.exists(c): skel_vfs=self._vfs._k(c); break
            if not skel_vfs:
                bn="/"+os.path.basename(skel).lower()
                for k in self._vfs.names():
                    if k.endswith(bn): skel_vfs=k; break
            if not skel_vfs: return (0.0, 1.0)
            data=self._vfs.read(skel_vfs)
            if not data: return (0.0, 1.0)
            tmp=os.path.join(self._tmp or ".","_submodel_"+os.path.basename(skel))
            with open(tmp,"wb") as f: f.write(data)
            try: dims=MV.skd_bind_dims(MV.parse_skd(tmp))
            finally:
                try: os.remove(tmp)
                except OSError: pass
            longest=dims[0]; middle=dims[1] if len(dims)>1 and dims[1]>0.01 else longest
            aspect=round(longest/middle, 3) if middle>0.01 else 1.0
            return (round(longest*tscale, 3), aspect)
        except Exception:
            return (0.0, 1.0)

    def _submodel_pose_channels(self, sub_text, pathhead):
        """Frame-0 channel dict of the sub-tik's `idle` animation, used to POSE its skelmodel.

        A tempmodel spawned from an RT_MODEL .tik is skinned in an ANIMATION pose, never the
        raw skeleton: SpawnTempModel sets ent.frameInfo[0].index = Anim_NumForName(tiki,"idle")
        - falling back to animation 0 on a miss - with weight 1.0 and wasframe 0
        (cg_tempmodels.cpp:1337-1347); AnimateTempModel only advances wasframe from there
        (:259-300). compute_world({}) gives every bone an IDENTITY rotation instead
        (bone_local: channels.get(name+" rot",[0,0,0,1])), which is exactly why the MAIN model
        path feeds it a real base .skc via pick_base_anim. Without this, models/fx/muzflash.tik
        baked out lying along -Y - ACROSS the barrel instead of down it - and `randomroll` then
        swept that sideways card around the barrel axis: the "muzzle flash points wherever it
        likes" / "two sprites at different angles" report (the two crossed quads share the same
        long axis, so both were wrong together).
        Returns {} on any miss, which reproduces the previous behaviour exactly.
        """
        if self._vfs is None: return {}
        try:
            import mohaa_view as MV
            anims=MV.parse_tik_animations(sub_text)
            if not anims: return {}
            pick=None
            for a in anims:
                if (a.get("name") or "").strip().lower()=="idle": pick=a; break
            if pick is None: pick=anims[0]          # Anim_NumForName miss -> index 0
            ref=(pick.get("file") or "").replace("\\","/").strip().strip('"')
            if not ref: return {}
            pathhead=(pathhead or "").replace("\\","/").strip().strip('"')
            cands=[]
            if "/" in ref or ref.lower().startswith("models/"): cands.append(ref)
            if pathhead: cands.append(pathhead.rstrip("/")+"/"+os.path.basename(ref))
            key=None
            for c in cands:
                if self._vfs.exists(c): key=self._vfs._k(c); break
            if not key:
                bn="/"+os.path.basename(ref).lower()
                for k in self._vfs.names():
                    if k.endswith(bn): key=k; break
            if not key: return {}
            data=self._vfs.read(key)
            if not data: return {}
            tmp=os.path.join(self._tmp or ".","_subanim_"+os.path.basename(ref))
            with open(tmp,"wb") as f: f.write(data)
            try: skc=MV.parse_skc(tmp)
            finally:
                try: os.remove(tmp)
                except OSError: pass
            fr=skc.get("frames") or []
            return dict(fr[0]) if fr else {}
        except Exception:
            return {}

    def _submodel_mesh(self, sub_text, max_aspect=3.0):
        """For a .tik sub-model debris particle (metal_section / ibeam_piece), return compact
        bind-pose geometry {v:[[x,y,z]...], t:[[a,b,c]...]} in MOHAA model space (Z-up), centred
        on the mesh centroid and pre-multiplied by the sub-tik `scale`, so the viewer can draw it
        as a real 3D chunk instead of a flat billboard. Returns None for thin slivers
        (aspect >= max_aspect, e.g. spark splinters that read fine as oriented streaks - keeping
        those on the signed-off billboard path) or on any miss."""
        if self._vfs is None: return None
        try:
            import mohaa_view as MV
            pathhead, skel = MV.parse_tik_setup_head(sub_text)
            if not skel: return None
            # AUTOSPRITE / animmap sub-tik shaders are camera-facing SPRITES, not solid geometry.
            # bh_wood_puff / bh_stone_puff are `surface all shader bh_wood_puff`, whose shader is
            # `deformVertexes autoSprite2` + `animmap woodpuff1..7` - in-game the spritebeam.skd
            # quad is REPLACED by a camera-facing animated sprite, never drawn as its raw mesh.
            # Rendering that quad as a 3D chunk here produced the untextured BLACK SQUARE (its
            # bind pose is a flat, near-1:1 quad, so the aspect gate below never caught it). Keep
            # these on the sprite billboard path (the animmap texture the sprite resolver ships)
            # by returning None. Real debris (bh_wood_piece: no autosprite, no animmap) still
            # meshes as a tumbling chunk.
            _shm=re.search(r'surface\s+\S+\s+shader\s+(\S+)', sub_text, re.I)
            if _shm and self._PROPS:
                _sp=(self._PROPS or {}).get(_shm.group(1).strip().lower())
                if _sp and (_sp.get("autosprite") or _sp.get("autosprite2") or _sp.get("frames")):
                    return None
            skel=skel.replace("\\","/").strip().strip('"')
            pathhead=(pathhead or "").replace("\\","/").strip().strip('"')
            m=re.search(r'\bscale\s+([-\d.]+)', sub_text, re.I)
            tscale=float(m.group(1)) if m else 1.0
            cands=[]
            if "/" in skel or skel.lower().startswith("models/"): cands.append(skel)
            if pathhead: cands.append(pathhead.rstrip("/")+"/"+os.path.basename(skel))
            skel_vfs=None
            for c in cands:
                if self._vfs.exists(c): skel_vfs=self._vfs._k(c); break
            if not skel_vfs:
                bn="/"+os.path.basename(skel).lower()
                for k in self._vfs.names():
                    if k.endswith(bn): skel_vfs=k; break
            if not skel_vfs: return None
            data=self._vfs.read(skel_vfs)
            if not data: return None
            tmp=os.path.join(self._tmp or ".","_mesh_"+os.path.basename(skel))
            with open(tmp,"wb") as f: f.write(data)
            try: skd=MV.parse_skd(tmp)
            finally:
                try: os.remove(tmp)
                except OSError: pass
            # Pose the skeleton the way the engine does - the sub-tik's `idle` animation,
            # frame 0 (cg_tempmodels.cpp:1337-1347) - not an all-identity skeleton.
            _ch=self._submodel_pose_channels(sub_text, pathhead)
            dims=MV.skd_bind_dims(skd, _ch)
            longest=dims[0]; mid=dims[1] if len(dims)>1 and dims[1]>0.01 else longest
            if mid>0.01 and (longest/mid)>=max_aspect: return None    # thin sliver -> billboard
            wR,wT=MV.compute_world(skd["bones"], _ch)
            verts=[]; tris=[]; uvs=[]; cen=[0.0,0.0,0.0]; nv=0; base=0
            for s in skd["surfaces"]:
                sv=[]
                for weights in s["verts"]:
                    P=[0.0,0.0,0.0]
                    for w in weights:
                        bi,wv,offv=w[0],w[1],w[2]
                        wp=MV.v_add(MV.mat_vec(wR[bi],offv),wT[bi])
                        P=[P[k]+wv*wp[k] for k in range(3)]
                    sv.append(P); cen=[cen[k]+P[k] for k in range(3)]; nv+=1
                # per-vertex UVs so the viewer can paint the chunk with its real skin
                # texture instead of a flat average colour ("debris missing textures").
                _suv=s.get("uvs") or []
                for k in range(len(s["verts"])):
                    if k<len(_suv): uvs.extend([round(_suv[k][0],4),round(_suv[k][1],4)])
                    else: uvs.extend([0.0,0.0])
                for tr in s["tris"]:
                    tris.append([tr[0]+base,tr[1]+base,tr[2]+base])
                verts.extend(sv); base+=len(sv)
            if nv==0 or not tris: return None
            cen=[cen[k]/nv for k in range(3)]
            # NATIVE MODEL SPACE - do NOT re-centre on the centroid. A tempmodel is a plain
            # refEntity: SpawnTempModel puts the spawn point in p->cgd.origin and the particle's
            # randomized Euler angles in p->ent.axis (cg_tempmodels.cpp:1492-1494), and the
            # model's own vertices are then rotated about the ENTITY origin. So a card authored
            # away from its model origin - bh_foliage_leaf's leaf.skd - is swung onto a shell of
            # radius |centroid|*scale by each particle's random `angles`. For fx_leaves_blowing
            # that is the ONLY source of per-leaf separation the engine has: the block sets no
            # shape flag, no radius and no offset, and `radialvelocity 0 10 110` then REPLACES
            # the forward velocity with (origin-start)*fVel, which is zero-length and leaves the
            # leaf at rest (cg_tempmodels.cpp:1511-1521, SetRadialVelocity cg_commands.cpp:
            # 2739-2754). Centring collapsed all five leaves onto one point - the falling clump.
            V=[[round(p[k]*tscale,3) for k in range(3)] for p in verts]
            out={"v":V,"t":tris}
            if any(uvs): out["uv"]=uvs
            # texture: the sub-tik's first `surface <n> shader <s>` resolved through the
            # shader index (same lookup the sprite path uses). tempmodels render the model
            # with its own skin in-game (SpawnTempModel -> RT_MODEL refEntity), so the chunk
            # carries its texture as a data-url; flat colour remains the fallback.
            try:
                m2=re.search(r'surface\s+\S+\s+shader\s+(\S+)', sub_text, re.I)
                if m2:
                    sh=m2.group(1).strip()
                    mp=self._SH.get(sh.lower()) if self._SH else None
                    t=self._vfs.find_texture(mp) if mp else self._vfs.find_texture(sh)
                    if t:
                        d=MTX.texture_to_dataurl(self._vfs,t,max_dim=512,keep_alpha=True)
                        if d: out["tex"]=d
                    # BLEND MODE of the sub-model's surface. muzflash.tik is `surface material1
                    # shader muzmodel`, and muzmodel (effects.shader) is `blendFunc GL_SRC_ALPHA
                    # GL_ONE` - the card is ADDED to the scene, so flashnode1.tga's black
                    # surround contributes nothing in-game. Without this flag the viewer drew the
                    # chunk source-over and that surround showed as an opaque BLACK RECTANGLE
                    # around the muzzle flash on mg42_gun / jeep_30cal. Ship it so the mesh path
                    # composites additively (and skips the flat shade - such a stage has no
                    # rgbGen, so it is CGEN_IDENTITY_LIGHTING, tr_shader.c:1755-1765).
                    _sp2=(self._PROPS or {}).get(sh.lower())
                    if _sp2 and _sp2.get("additive"): out["add"]=True
            except Exception:
                pass
            return out
        except Exception:
            return None

    def _avg_tex_color(self, texpath):
        """Mean RGB (0..1) of a VFS texture, for flat-shading 3D debris chunks. Metal-grey on miss."""
        default=[0.56,0.56,0.60]
        if not texpath or self._vfs is None: return default
        try:
            import io
            from PIL import Image
            data=self._vfs.read(texpath)
            if not data: return default
            with Image.open(io.BytesIO(data)) as im:
                px=list(im.convert("RGB").resize((8,8)).getdata())
            n=len(px)
            if not n: return default
            return [round(sum(p[k] for p in px)/n/255.0,3) for k in range(3)]
        except Exception:
            return default

    def _resolve_emitter_sprites(self, emitters):
        """Resolve each emitter's `model` reference to a billboard sprite.
        Returns {model_ref_lower: entry} where entry is a data-url string, or, when
        the sprite's shader animates (animMap), an object
            {"tex":url,"frames":[url,...],"fps":N,"additive":bool}
        so the viewer can cycle frames (e.g. the electric arc's 3-frame wiggle).
        .spr -> textures/sprites/<n>.tga (or a same-named shader);
        .tik -> the sub-model's first `surface ... shader ...` texture."""
        out={}
        if self._vfs is None or MTX is None: return out
        for e in emitters:
            ref=(e.get("model") or "").replace("\\","/").strip().strip('"')
            if not ref: continue
            rl=ref.lower()
            if rl in out: continue
            du=None; shname=None; basesize=0.0; baseaspect=1.0; tp=None; _mesh=None; _banim=None; _edu=None
            # MOHAA volumetric smoke (the `volumetric` keyword + `model <type>`): ALL 12
            # cg_vsstypes (default/gun/bulletimpact/bulletdirtimpact/heavy/steam/mist/
            # smokegrenade/grenade/fire/greasefire/debris) render with VSSSource.spr /
            # VSSSource2.spr (openmohaa cg_volumetricsmoke.cpp). They are NOT .spr/.tik refs,
            # so without this they resolve to nothing and the viewer draws a synthetic radial
            # blob (the "bland sphere"). Map them to the vsssource sprite (alpha smoke).
            _VSS_TYPES={"default","gun","bulletimpact","bulletdirtimpact","heavy","steam",
                        "mist","smokegrenade","grenade","fire","greasefire","debris"}
            is_vol=("volumetric" in (e.get("flags") or [])) or (rl in _VSS_TYPES)
            try:
                if is_vol:
                    base="vsssource"
                    cands=["textures/sprites/vsssource.tga","vsssource","sprites/vsssource"]
                    sh=self._SH.get(base) if self._SH else None
                    if sh: cands.insert(0,sh)
                    for c in cands:
                        t=self._vfs.find_texture(c)
                        if t: tp=t; du=MTX.texture_to_dataurl(self._vfs,tp,max_dim=512,emitter_clean=True); shname=base; break
                    # ENGINE: every VSS puff renders as VSSSource.spr / VSSSource2.spr
                    # (AddVSSSources, cg_volumetricsmoke.cpp:1167-1168; model choice by
                    # T_RANDOMROLL, :1331-1340) - i.e. through the vsssource shader, the SAME
                    # dual counter-rotating GL_MODULATE bundle as flat vsssource sprites.
                    # Without it the viewer drew each puff as a solid blob of the raw bright
                    # base texture at full base alpha: far too white and too dense vs the
                    # in-game grey wisps. Ship the animated bundle exactly like the .spr
                    # path; the generic export below then carries tex (keep_alpha), rotate,
                    # brot and halpha, and the viewer's _bundleFrame halpha product (RGB AND
                    # alpha modulate, A = A0*A1) applies to volumetric smoke too.
                    if tp is not None and self._PROPS:
                        _pp=(self._PROPS or {}).get(base)
                        if _pp and _pp.get("bundle"):
                            _bd=_pp["bundle"]
                            _bt=self._vfs.find_texture(_bd.get("map") or "")
                            if _bt and (_bd.get("scroll") or _bd.get("rotate")):
                                _banim=(_bt,_bd)
                elif rl.endswith(".spr"):
                    # SPR_RegisterSprite (openmohaa code/renderergl1/tr_sprite.c:31-56): the
                    # sprite's shader NAME is the .spr path minus extension - so
                    # `model textures/effects/bang.spr` (explosion_tank) resolves the shader
                    # "textures/effects/bang", falling back to an implicit shader from the
                    # same-path image. The old basename-only candidates missed every
                    # full-path .spr ref outside textures/sprites/.
                    base=os.path.splitext(os.path.basename(rl))[0]
                    full=os.path.splitext(rl)[0]                       # path-noext shader name
                    cands=[]
                    if self._SH:
                        for k in (full, base):
                            sh=self._SH.get(k)
                            if sh and sh not in cands: cands.append(sh)
                    for c in (full+".tga", full+".jpg",
                              "textures/sprites/"+base+".tga", base, "sprites/"+base):
                        if c not in cands: cands.append(c)
                    shname=full if (self._PROPS or {}).get(full) else base
                    # detail bundle (nextbundle GL_MODULATE): bake the tiled noise into the
                    # sprite pixels at build time (mortar_dirthit's mortar_noise 8x16 grain,
                    # mortar_dirthit2's sandplume 2x2) - the in-game "HD" speckle detail.
                    _pp=(self._PROPS or {}).get(shname)
                    _bpath=None; _bscale=(1.0,1.0)
                    if _pp and _pp.get("bundle"):
                        _bd=_pp["bundle"]
                        _bt=self._vfs.find_texture(_bd.get("map") or "")
                        if _bt:
                            if _bd.get("scroll") or _bd.get("rotate"):
                                # animated tcmods: DON'T bake - export for runtime
                                # compositing so the grain actually drifts/spins in the
                                # viewer like in-game (mortar_noise scroll, dirtnoise rotate)
                                _banim=(_bt,_bd)
                            else:
                                _bpath=_bt; _bscale=tuple(_bd.get("scale") or (1.0,1.0))
                    _edu=None
                    for c in cands:
                        t=self._vfs.find_texture(c)
                        if t: tp=t; du=MTX.texture_to_dataurl(self._vfs,tp,max_dim=512,emitter_clean=True,bundle_path=_bpath,bundle_scale=_bscale); break
                    # EROSION SOURCE for animated bundles: the viewer's alpha-test pattern
                    # is thresholded from the OLD-STYLE static PIL bake (base x noise at
                    # phase 0, the exact texture_to_dataurl bundle path that produced the
                    # in-game-verified granular dissipation) - the granular speckle in that
                    # dissolve IS the noise texture's alpha, which the base alone lacks.
                    # The unbaked `du` above stays the RGB source so the grain still
                    # drifts/spins at runtime.
                    if tp is not None and _banim is not None:
                        _abt,_abd=_banim
                        _edu=MTX.texture_to_dataurl(self._vfs,tp,max_dim=512,emitter_clean=True,
                                                    bundle_path=_abt,
                                                    bundle_scale=tuple(_abd.get("scale") or (1.0,1.0)))
                    # animmap-only shaders (e.g. air_explosion: only animMap frames, no `map`
                    # directive) have no single base texture so all cands miss -> du stays None.
                    # The animmap frame list is only applied AFTER du is set, so without this
                    # fallback the emitter is silently skipped. Use the first animmap frame as
                    # the base: it loads correctly and multi-frame animation still applies below
                    # via props["frames"]. (catches parallel_oriented animmap sprites)
                    if not du:
                        for _nm in (full, base):
                            _p=(self._PROPS or {}).get(_nm)
                            if _p and _p.get("frames"):
                                _ft=self._vfs.find_texture(_p["frames"][0])
                                if _ft:
                                    tp=_ft; shname=_nm
                                    du=MTX.texture_to_dataurl(self._vfs,tp,max_dim=512,emitter_clean=True)
                                    break
                elif rl.endswith(".tik"):
                    data=self._vfs.read(rl) if self._vfs.exists(rl) else None
                    if data is None:
                        bn="/"+os.path.basename(rl)
                        k=next((k for k in self._vfs.names() if k.endswith(bn)),None)
                        data=self._vfs.read(k) if k else None
                    if data:
                        sub=data.decode("latin-1","replace")
                        m=re.search(r'surface\s+\S+\s+shader\s+(\S+)',sub,re.I)
                        sh=m.group(1).strip() if m else None
                        if sh:
                            shname=sh
                            mp=self._SH.get(sh.lower()) if self._SH else None
                            tp=self._vfs.find_texture(mp) if mp else self._vfs.find_texture(sh)
                            # animmap-only shader (no `map`/`clampmap` base directive) - the
                            # bullet-hit puff sub-tiks (bh_wood_puff/bh_stone_puff -> surface
                            # all shader bh_wood_puff, which is `animmap 20 woodpuff1..7.tga`)
                            # have no single base texture, so _SH.get() and find_texture(sh)
                            # both miss and the sub-model resolved to nothing (reported as
                            # "no resolvable surface shader texture"). Fall back to the FIRST
                            # animmap frame as the base - it loads, and the frame list below
                            # carries the 7-frame cycle - mirroring the top-level .spr animmap
                            # fallback so wood/stone/carpet bullet holes show their puff.
                            if not tp and self._PROPS:
                                _pp=(self._PROPS or {}).get(sh.lower())
                                if _pp and _pp.get("frames"):
                                    tp=self._vfs.find_texture(_pp["frames"][0])
                        if tp: du=MTX.texture_to_dataurl(self._vfs,tp,max_dim=512,emitter_clean=True)
                        # DUMMY fx sub-tik (snipesmoke, gas_mushroom_cloud): no drawable surface
                        # of its own - the spawned tempmodel's look is its OWN idle-anim `enter
                        # originspawn` one-shots + init-client emitters. Export those inner
                        # blocks for one-level flattening in the viewer (expand_subfx).
                        if not du:
                            _sf=self._collect_subfx(sub)
                            if _sf:
                                out[rl]={"subfx":_sf}
                                continue
                        # a .tik particle is a real mesh - record true size + aspect so the
                        # viewer draws it at geometry scale as a thin sliver, not a sprite blob.
                        basesize,baseaspect=self._submodel_basesize(sub)
                        # chunky debris (metal_section, ibeam_piece) render as actual tumbling
                        # 3D geometry, not flat billboards. Thin slivers (spark splinters) stay
                        # on the billboard path. mesh=None for slivers / on miss.
                        _mesh=self._submodel_mesh(sub)
                        if _mesh is not None:
                            _mesh["color"]=self._avg_tex_color(tp)
            except Exception:
                du=None
            if not du: continue
            # original (pre-downscale) texture pixels, so the viewer can size .spr sprites
            # by true texture dimensions (a 256px arc stays wide; a 32px puff unchanged).
            texw,texh=self._orig_tex_dims(tp)
            props=(self._PROPS or {}).get((shname or "").lower())
            # GL_ONE SOURCE BLEND IGNORES ALPHA (tr_shader.c NameToSrcBlendMode):
            # `blendFunc GL_ONE GL_ONE` / `blendfunc add` add the stage's RGB whole,
            # so the texture's alpha channel must NOT gate the sprite. Canvas 'lighter'
            # is premultiplied and would mask it down (bh_metal_fastpiece sparks were
            # 2.18x under-lit -> the ~0.5x scale; corona_util 1.92x -> lost soft
            # falloff). Debris CHUNKS keep their native alpha: they draw source-over
            # through the mesh path, where an opaque skin would fill the whole facet.
            _glone=bool(props and props.get("additive")
                        and props.get("srcalpha") is False and _mesh is None)
            if _glone: du=MTX.dataurl_gl_one_additive(du)
            entry={"tex":du}
            # carry the sprite's true blend mode (from its shader's first blendfunc) so the
            # viewer alpha-blends water/smoke instead of additively stacking them to white.
            if props is not None:
                entry["additive"]=bool(props.get("additive"))
                # rgbGen vertex/entity present? Without it the emitter `color` never reaches the
                # framebuffer (corona_util's plain `blendfunc add` stage stays WHITE regardless
                # of the tik's red tint). srcalpha: does the src blend factor read alpha at all?
                # `blendfunc add` == GL_ONE GL_ONE ignores shaderRGBA[3], so alpha/fade/
                # flickeralpha are no-ops in-game for those sprites.
                if "rgbvertex" in props: entry["rgbvertex"]=bool(props.get("rgbvertex"))
                if "srcalpha"  in props: entry["srcalpha"]=bool(props.get("srcalpha"))
                # alphafunc on a blendfunc-less base stage: the sprite is ALPHA-TESTED -
                # each pixel either draws fully opaque or is a hole (tr_shader.c NameToAFunc).
                # The viewer erodes these with threshold variants instead of alpha-fading.
                if props.get("atest"): entry["alphatest"]=props["atest"]
            # animated nextbundle: ship the noise texture + tcmod params; the viewer
            # multiplies it over the sprite per frame (GL_MODULATE, tr_shader.c:1841-1853).
            # halpha flags a real alpha channel in the noise - then the erosion pattern
            # itself scrolls and the viewer takes the per-pixel compositing path.
            if _banim is not None:
                _abt,_abd=_banim
                # nextbundle is GL_MODULATE (tr_shader.c:1841-1853), and texture-env MODULATE
                # multiplies ALPHA as well as RGB (A = A0*A1). Ship the noise WITH its real
                # alpha channel (keep_alpha) so the viewer can modulate sprite alpha per
                # pixel - vsssource x vsssource2's counter-rotating soft smoke lives in that
                # alpha product. Alpha-TESTED emitters keep the opaque encode: their
                # in-game-verified erosion pattern is the BASE alpha only (mortar_dirthit
                # sign-off), so their shipped pixels stay byte-identical to before.
                _hal=bool(MTX.texture_has_varied_alpha(self._vfs,_abt))
                _ka=bool(_hal and not (props and props.get("atest")))
                _ndu=MTX.texture_to_dataurl(self._vfs,_abt,max_dim=256,keep_alpha=_ka)
                if _ndu:
                    _bn={"tex":_ndu,"scale":list(_abd.get("scale") or (1.0,1.0))}
                    if _abd.get("scroll"):
                        _bn["scroll"]=list(_abd["scroll"]); _bn["prescale"]=bool(_abd.get("prescale"))
                    if _abd.get("rotate"): _bn["rotate"]=float(_abd["rotate"])
                    if _abd.get("brot"): _bn["brot"]=float(_abd["brot"])
                    _bn["halpha"]=_hal
                    entry["bundle"]=_bn
                if _edu: entry["erode_sprite"]=_edu
            if is_vol:
                entry["volumetric"]=True
                entry["additive"]=False   # VSS smoke composites alpha (translucent), never additive
                # engine sizing: quad world width = texW * (radius/5) * spritescale (tr_sprite.c).
                # Carry the vsssource shader's spritescale (default 1.0) so the viewer matches it.
                entry["spritescale"]=float((props or {}).get("spritescale",1.0) or 1.0)
            # sprite_type is only set when the shader carried an explicit `spritegen` line;
            # export it verbatim, INCLUDING "parallel" - the viewer must know an explicit
            # parallel to suppress roll (SPRITE_PARALLEL ignores angles/avelocity,
            # tr_sprite.c:84-91), whereas an absent keyword keeps the legacy default.
            if props and props.get("sprite_type"):
                entry["sprite_type"]=props["sprite_type"]
            # deformVertexes lightglow (DEFORM_LIGHTGLOW, tr_shade_calc.c LightGlowDeform)
            # REBUILDS the sprite quad from the CAMERA's right/up axes every frame - a
            # camera-facing glow that grows toward the eye - regardless of the shader's
            # spritegen. fire_ring is `spritegen oriented` + `deformVertexes lightglow`: the
            # oriented (world-fixed) quad is overridden into a camera-facing billboard. Ship
            # the flag so the viewer renders it camera-facing instead of edge-on (it was drawing
            # the ring as a flat world quad that vanished at grazing angles).
            if props and props.get("lightglow"):
                entry["lightglow"]=True
            # shader spriteScale applies to EVERY spritegen quad, not just VSS smoke
            # (RB_DrawSprite: scale = spr->scale * ent scale, where spr->scale is the
            # shader's sprite.scale from SPR_RegisterSprite). muzsprite / *_spriteflash
            # declare spriteScale .3/.7 in effects.shader and rendered oversized when it
            # was dropped here for non-volumetric sprites.
            if "spritescale" not in entry:
                _ss=float((props or {}).get("spritescale",1.0) or 1.0)
                if _ss!=1.0: entry["spritescale"]=_ss
            if texw: entry["texw"]=texw
            if texh: entry["texh"]=texh
            if props and props.get("frames"):
                frames=[]
                for fp in props["frames"][:32]:
                    t=self._vfs.find_texture(fp)
                    if t:
                        d=MTX.texture_to_dataurl(self._vfs,t,max_dim=512,emitter_clean=True)
                        if _glone: d=MTX.dataurl_gl_one_additive(d)   # same GL_ONE rule per frame
                        if d: frames.append(d)
                if len(frames)>1:
                    entry["frames"]=frames; entry["fps"]=props.get("fps") or 15
                    entry["additive"]=bool(props.get("additive"))
            if basesize>0:
                entry["basesize"]=basesize; entry["baseaspect"]=baseaspect
            if _mesh is not None:
                entry["mesh"]=_mesh
            out[rl]=entry
        return out

    def _collect_subfx(self, sub_text):
        """Inner client fx of a dummy sub-.tik (a spawned tempmodel with no drawable
        surface): its animations{} `enter originspawn` one-shot blocks, its init-client
        `sfx originspawn` / `delayedsfx` one-shots, plus its init-client *emitter blocks
        exported with stream=True so the viewer runs them for the parent tempmodel's life
        (the engine runs the tempmodel's own anim entry commands + init sfx + emitters
        while it lives - cg_commands/cg_tempmodels). Returns a JSON-safe list of param
        dicts (possibly empty)."""
        out=[]
        try:
            import mohaa_view as MV
            for ta in MV.parse_tik_animations(sub_text):
                for c in ta.get("client",[]):
                    if c.get("prm") and (c.get("argv") or [""])[0].lower()=="originspawn":
                        out.append(dict(c["prm"]))
            # init{client{}} `sfx <spawncmd> ( ... )` / `delayedsfx <sec> ...` one-shots.
            # bazookaexp_base.tik (played by tankshellexplosion via explosioneffect) has NO
            # animation fx and NO *emitter blocks - its entire look is these sfx-wrapped
            # originspawns (gren_boom.spr, vsssource.spr). Without this they were collected
            # by nothing, so the whole sub-tik resolved to zero drawable sprites and the
            # launcher reported it as an unresolved white blob.
            for s in MV.parse_tik_init_sfx(sub_text):
                if s.get("prm"):
                    q=dict(s["prm"])
                    if s.get("delay"): q["startdelay"]=s["delay"]
                    out.append(q)
            for e in MV.parse_tik_emitters(sub_text):
                q=dict(e); q["stream"]=True
                out.append(q)
        except Exception:
            return []
        return out

    def _orig_tex_dims(self, texpath):
        """Original (w,h) of a VFS texture before any downscale. Tries a direct binary
        header read first (TGA/DDS/PNG/JPEG) so it works even when PIL is unavailable or
        chokes on an old TGA variant, then falls back to PIL. Returns (0,0) on failure.

        This mattered for the mortar/mine sprites: their .spr resolves to a big shader
        texture (mortarhit2.tga is 512x512), but a (0,0) return here dropped texw/texh, so
        the viewer fell back to the 32px default and sized every sprite ~16x too small
        (scale .0625 * 32 = 2u instead of * 512 = 32u)."""
        if not texpath or self._vfs is None: return (0,0)
        try:
            data=self._vfs.read(texpath)
        except Exception:
            data=None
        if not data: return (0,0)
        wh=self._dims_from_header(data, texpath)
        if wh[0] and wh[1]: return wh
        try:
            import io
            from PIL import Image
            with Image.open(io.BytesIO(data)) as im:
                return (int(im.size[0]), int(im.size[1]))
        except Exception:
            return (0,0)

    @staticmethod
    def _dims_from_header(data, texpath=""):
        """Parse width/height straight from image bytes for the formats MOHAA ships.
        No decode, no PIL - just the header fields. Returns (0,0) if unrecognised."""
        try:
            ext=texpath.rsplit(".",1)[-1].lower() if texpath else ""
            # PNG: 8-byte sig, then IHDR with big-endian w,h at offset 16
            if data[:8]==b"\x89PNG\r\n\x1a\n" and len(data)>=24:
                import struct
                w,h=struct.unpack(">II", data[16:24]); return (w,h)
            # DDS: 'DDS ' magic, height @ offset 12, width @ 16 (little-endian)
            if data[:4]==b"DDS " and len(data)>=20:
                import struct
                h,w=struct.unpack("<II", data[12:20]); return (w,h)
            # JPEG: scan segments for a SOF marker carrying height,width
            if data[:2]==b"\xff\xd8":
                import struct
                i=2; n=len(data)
                while i+9<n:
                    if data[i]!=0xFF: i+=1; continue
                    mk=data[i+1]
                    if 0xC0<=mk<=0xCF and mk not in (0xC4,0xC8,0xCC):
                        h,w=struct.unpack(">HH", data[i+5:i+9]); return (w,h)
                    if mk in (0xD8,0xD9) or 0xD0<=mk<=0xD7: i+=2; continue
                    seg=struct.unpack(">H", data[i+2:i+4])[0]; i+=2+seg
                # TGA: width @ offset 12, height @ 14 (little-endian, uint16). TGA has no
            # magic, so only trust it for a .tga path or a plausible header.
            if len(data)>=18 and (ext=="tga" or data[1] in (0,1)):
                import struct
                w,h=struct.unpack("<HH", data[12:16]); return (w,h)
        except Exception:
            pass
        return (0,0)

    # ------------------------------------------------------------ run/load ---
    def _browse(self):
        p=filedialog.askopenfilename(title="Select a .skd model or .tik effect",
            filetypes=[("MOHAA model / effect","*.skd *.tik"),("MOHAA Skeleton","*.skd"),
                       ("MOHAA effect/emitter","*.tik"),("All files","*.*")])
        if p: self._path_var.set(p)

    def _browse_and_run(self):
        self._browse()
        p=self._path_var.get().strip().strip('"')
        if p and not p.startswith("pk3://") and os.path.exists(p): self._run()

    def _run(self):
        path=self._path_var.get().strip().strip('"')
        if path.startswith("pk3://"): self._open_pk3_model(path[len("pk3://"):]); return
        # after a pk3 build the entry shows a friendly "pk3 model: <n>" display
        # string, not a real path - re-run the last build instead of failing on it
        if path.startswith("pk3 model:") and self._last_build:
            self._load(*self._last_build); return
        if not path: self._log_line("No file selected.","err"); return
        if not (path.lower().endswith(".skd") or path.lower().endswith(".tik")):
            self._log_line("File must be a .skd or .tik","err"); return
        if not os.path.exists(path): self._log_line(f"Not found: {path}","err"); return
        if not self._pyexe: self._log_line("Python not found on PATH.","err"); return
        if not os.path.exists(VIEWER): self._log_line("mohaa_view.py not found next to launcher.","err"); return
        self._load(path)

    def _load(self, path, animroot=None, manifest=None, emittex=None, subdir=None, _cont=False):
        # direct entry points (drag-drop, Recent menu, path-bar Run) respect the
        # open-in-viewer latch; _cont=True marks the internal continuation of a
        # pk3 open already holding the latch, which must not reject itself
        if not _cont and self._viewer_open_busy(): return
        # An individual file opened from disk (Browse / drag-drop / Recent / cmdline /
        # path-bar) is a "standalone" build: its HTML belongs in the standalone/ folder,
        # not the pak-mirroring models tree. Routed loose opens get this marker from
        # _open_pk3_tik/_open_pk3_model; this covers the direct (e.g. no-paks) build path
        # and makes the reuse probe below look in the right place.
        if (not _cont and subdir is None and os.path.isfile(path)
                and not (self._tmp and path.startswith(self._tmp))):
            subdir=STANDALONE_SUBDIR
        self._last_build=(path,animroot,manifest,emittex,subdir)   # lets Open Viewer re-run this build
        self._last_subdir=subdir
        disp=("pk3 model: "+os.path.basename(path)) if (self._tmp and path.startswith(self._tmp)) else path
        self._path_var.set(disp)
        self._push_recent(path)
        # loose files (Browse / drag-drop / Recent) can reuse a saved HTML too
        if self._reuse_ok():
            hp=self._html_out_path(path,subdir)
            if os.path.exists(hp) and self._html_current(hp):
                self._opening_view=False       # no build will run: release the open latch
                self._open_cached(hp,path,subdir); return
        # A loose .tik/.skd opened from disk while paks are loaded: its skelmodel, sibling
        # animations and textures usually live INSIDE the paks, not next to the file. Run the
        # same pak-resolution pipeline the tree uses (skelmodel + .skc + textures pulled from
        # the VFS by name), driven by the loose file's OWN edited content, so it opens exactly
        # like a tree entry. Without this, mohaa_view.py exits 1 ("skelmodel not found").
        if (not _cont and manifest is None and self._vfs is not None and self._tex_ready
                and self._tmp and not path.startswith(self._tmp) and os.path.isfile(path)):
            low=path.lower()
            if low.endswith(".tik"): self._open_pk3_tik(os.path.basename(path), loose_path=path); return
            if low.endswith(".skd"): self._open_pk3_model(os.path.basename(path), loose_path=path); return
        self._log_line(f"Loading {os.path.basename(path)} ...","dim")
        self._set_status(f"Building viewer for {os.path.basename(path)}...")
        self._building_name=os.path.basename(path)
        if self._auto_open.get() and not self._run_opts.get("no_open") and not self._run_opts.get("external"): self._opening_view=True
        threading.Thread(target=self._worker,args=(path,animroot,manifest,emittex,subdir,self._build_gen),daemon=True).start()

    def _worker(self, path, animroot=None, manifest=None, emittex=None, subdir=None, bgen=None):
        try:
            opts=self._run_opts; self._run_opts={}          # one-shot right-click options
            if bgen is not None and bgen!=self._build_gen: return   # Escape: cancelled before start
            cmd=[self._pyexe,VIEWER,path]
            if animroot: cmd.append("--animroot="+animroot)
            # the resolved animation catalogue for THIS model (names only - pose data is
            # solved per animation, on click) plus the bake budget
            if self._animcat_file and self._animcat_for==path:
                cmd.append("--animcat="+self._animcat_file)
                cmd.append("--animpreload="+str(self._anim_preload_n()))
            if manifest: cmd.append("--textures="+manifest)
            if emittex: cmd.append("--emittertex="+emittex)
            if self._outdir_on.get():
                if subdir==STANDALONE_SUBDIR:
                    cmd.append("--outdir="+self._standalone_dir())
                else:
                    # mirror the pak's models/ subfolders inside the output folder
                    cmd.append("--outdir="+(os.path.join(self._outdir,subdir) if subdir else self._outdir))
            if opts.get("theme") in ("light","dark"): cmd.append("--theme="+opts["theme"])
            ext=bool(opts.get("external"))          # drag-out: always open, own window
            will_open=ext or (self._auto_open.get() and not opts.get("no_open"))
            # ALWAYS --no-open: the viewer script must never launch the browser
            # itself, or every fresh build (drag-drop, tree open) bypasses the
            # embedded pane. The launcher opens the HTML below via _open_file.
            cmd.append("--no-open")
            # Popen (not run) so Escape-to-cancel can kill the build mid-flight
            p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,**NOWIN)
            self._proc=p
            try:
                out,err=p.communicate(timeout=180)
            except subprocess.TimeoutExpired:
                p.kill(); self._log_q.put(("err","Timed out")); return
            finally:
                self._proc=None
            if bgen is not None and bgen!=self._build_gen:
                return             # Escape: cancelled - _cancel_build already logged it in red
            self._log_q.put(("stdout",(out or "").strip()))
            if (err or "").strip(): self._log_q.put(("err",err.strip()))
            if p.returncode==0:
                self._log_q.put(("ok","Done - viewer opened." if will_open else "Done - viewer HTML written (not opened)."))
                self._log_q.put(("parse",(path,out or "")))
                if will_open: self._log_q.put(("openext" if ext else "openhtml",(path,subdir)))
                self._log_q.put(("status","Done"))
            else: self._log_q.put(("err",f"Exited with code {p.returncode}"))
        except Exception as e: self._log_q.put(("err",str(e)))
        finally:
            self._log_q.put(("done",None))          # clears the building-name latch
            self._log_q.put(("batchnext",None))     # step done (no-op outside a batch)

    def _poll_log(self):
        try:
            if getattr(self,"_drop_paths",None):
                p=self._drop_paths.pop(0); self._drop_paths.clear(); self._load(p)
            while True:
                try: kind,msg=self._log_q.get_nowait()
                except queue.Empty: break
                try:
                    if kind=="parse": self._update_info(*msg)
                    elif kind=="openhtml":
                        _p,_sub=msg; _hp=self._html_out_path(_p,_sub)
                        if os.path.exists(_hp): self._open_file(_hp)
                        else: self._log_line(f"(viewer HTML not found: {_hp})","err")
                    elif kind=="openext":            # drag-out: own standalone window
                        _p,_sub=msg; _hp=self._html_out_path(_p,_sub)
                        if os.path.exists(_hp): self._open_standalone(_hp)
                        else: self._log_line(f"(viewer HTML not found: {_hp})","err")
                    elif kind=="load": self._load(*msg,_cont=True)   # pipeline continuation: latch already held
                    elif kind=="status": self._set_status(msg)
                    elif kind=="stdout":
                        # The child marks its own failures with a leading "!" - all four
                        # sites in mohaa_view.py are real failures (.skc not found, .skc
                        # unparseable, "drives none of this skeleton's N bones"). They were
                        # printing in the default colour, so a skipped animation read like
                        # ordinary progress instead of something that went wrong.
                        for line in msg.splitlines():
                            self._log_line(line,"err" if line.lstrip().startswith("!") else "")
                    elif kind=="ok": self._log_line(msg,"ok")
                    elif kind=="batchnext": self._batch_signal()
                    elif kind=="done": self._building_name=None; self._opening_view=False
                    elif kind=="err":
                        self._log_line(msg,"err"); self._set_status("Error - see log")
                        self._building_name=None; self._opening_view=False
                        self._batch_signal()             # a failed step must not stall the batch
                    elif kind=="dim": self._log_line(msg,"dim")
                    elif kind=="closeview": self._close_viewer()   # viewer Esc (main thread)
                    elif kind=="setang": self._set_view_angles(msg)  # viewer angle dial
                    # MISSING-ASSET diagnostics: red like "err", but NOT a pipeline abort.
                    # The "err" branch above clears _building_name/_opening_view and fires
                    # _batch_signal(); a missing .tga must not kill the open or the batch.
                    elif kind=="warn": self._log_line(msg,"err")
                    elif kind=="js": self._embed_js(msg)
                except Exception as e:
                    # a bad handler must never kill the poll loop
                    try: self._log_line(f"(ui error: {e})","err")
                    except Exception: pass
            # a pk3 open queued while the texture/VFS index was still building
            # (see _open_pk3_tik): fire it the moment the index is ready, or drop it
            # if the wait was cancelled (Escape bumps _build_gen) or the index run
            # ended without success (the "err" handler above releases _opening_view).
            if self._pending_open is not None:
                entry,bgen=self._pending_open
                if self._tex_ready and self._vfs is not None and bgen==self._build_gen:
                    self._pending_open=None; self._opening_view=False; self._run_opts={}
                    self._open_pk3_model(entry)          # index ready - open for real now
                elif bgen!=self._build_gen or not self._opening_view:
                    self._pending_open=None              # cancelled / index unavailable
        finally:
            self.after(80,self._poll_log)

    def _log_line(self,text,tag=""):
        self._log.configure(state="normal"); self._log.insert("end",text+"\n",tag)
        self._log.see("end"); self._log.configure(state="disabled")
        # mirror to output_console.log (see __init__). The tag (ok/err/warn/dim/"") is
        # prefixed so the file stays useful without the console's colour coding.
        lf=getattr(self,"_logfile",None)
        if lf is not None:
            try:
                pre=("[%s] "%tag) if tag else ""
                lf.write(pre+text+"\n")
            except Exception:
                self._logfile=None          # stop trying after the first failure

    def _log_warn(self,msg):
        """Red, non-fatal Output line. Thread-safe (goes through _log_q like every
        other worker-thread message)."""
        try: self._log_q.put(("warn",msg))
        except Exception: pass

    def _asset_miss_reason(self, ref):
        """Why did this emitter `model` reference fail to produce a sprite?

        ENGINE: SPR_RegisterSprite (openmohaa code/renderergl1/tr_sprite.c:31-56)
        strips the extension off the .spr name and looks the REST up as a shader name
        via R_FindShader, then takes shader->unfoggedStages[0]->bundle[0].image[0] as
        the sprite image. There are three distinct ways that fails, and telling them
        apart is the whole point of this message:

          1. The .shader block exists but its `map` file is absent from the paks.
             ParseStage prints "WARNING: R_FindImageFile could not find '%s' in
             shader '%s'" and returns qfalse, dropping the stage (tr_shader.c:727-732);
             SPR_RegisterSprite then finds no image and returns 0 (tr_sprite.c:43-46).
             This is the adam-firefill case: sprites.shader:1536-1571 defines
             senn_fire1/senn_fire2 -> textures/sprites/senn_fire[12].tga, which the
             retail game never shipped. In-game it draws NOTHING.
          2. No .shader block of that name at all - R_FindShader falls through to the
             implicit-image path, prints "Couldn't find image for shader %s" and
             returns tr.defaultShader (tr_shader.c:3044-3047).
          3. The image is present but our decoder choked on it (Pillow absent, odd TGA).
        """
        rl=(ref or "").replace("\\","/").strip().strip('"').lower()
        # `model ""` (empty) is the same "no such model" case as `model none`: fall through to
        # the standard shader-lookup message so it reads `no shader block named '' (or '') ...`,
        # matching the `none` diagnostic rather than a terse special-case string.
        if self._vfs is None: return "no game-file index loaded"
        if rl.endswith(".tik"):
            if not self._vfs.exists(rl):
                bn="/"+os.path.basename(rl)
                if not any(k.endswith(bn) for k in self._vfs.names()):
                    return "sub-model .tik not found in any .pk3"
            return "sub-model .tik has no resolvable `surface ... shader ...` texture"
        base=os.path.splitext(os.path.basename(rl))[0]
        full=os.path.splitext(rl)[0]                 # SPR_RegisterSprite: name minus ext
        for k in (full, base):
            mp=(self._SH or {}).get(k)
            if mp:
                return ("shader '%s' resolves to '%s', but that texture file does not exist "
                        "in the loaded .pk3 files." % (k, mp))
        for c in (full+".tga", full+".jpg", "textures/sprites/"+base+".tga", base, "sprites/"+base):
            if self._vfs.find_texture(c):
                return "image '%s' exists but could not be decoded (Pillow missing / bad TGA?)" % c
        return ("no shader block named '%s' (or '%s') in any scripts/*.shader, and no matching "
                "image under textures/sprites/" % (full, base))

    def _warn_emitter_assets(self, ems, resolved):
        """One red Output line per emitter whose sprite could not be built. Before this,
        _resolve_emitter_sprites' `if not du: continue` dropped them silently and the
        viewer fell back to a synthetic white blob with no indication why."""
        seen=[]
        for e in (ems or []):
            try: raw=(e.get("model") or "")
            except Exception: continue
            ref=raw.replace("\\","/").strip().strip('"')
            # `model ""` (fx_smokeexample) is an empty/placeholder model, the same "no model"
            # case as `model none` (fx/steamworks) - the engine resolves neither to a sprite, so
            # the emitter draws nothing. Report it the same way instead of skipping silently: an
            # empty ref keys/prints as "" so the Output line reads `model ""  ->  no shader block
            # named "" ...`, matching the `none` diagnostic. (A missing `model` key entirely -
            # raw is None/"" with no emitter model line - is a different thing and still skipped.)
            has_model_line="model" in e  # the tik wrote a `model <x>` line (even if x is "")
            if not ref and not has_model_line: continue
            key=ref if ref else '""'
            rl=ref.lower()
            if (ref and rl in (resolved or {})) or key in seen: continue
            seen.append(key)
            disp=ref if ref else '""'
            self._log_warn("MISSING ASSET  emitter '%s'  model %s  ->  %s"
                           % (e.get("name") or "?", disp, self._asset_miss_reason(ref)))
        if seen:
            self._log_warn("  %d emitter sprite(s) unresolved - those particles fall back to an "
                           "untextured white blob." % len(seen))

    def _report_surface_misses(self, manifest, surfs, surf_shader=None):
        """Red Output line naming every .skd surface that got no texture. The manifest
        only carries surfaces that RESOLVED (mohaa_textures.write_textures_manifest
        `if not tp: continue` / `if not du: continue`), so surfs minus manifest keys is
        exactly the miss list.

        surf_shader is the OPENED .tik's own `surface <n> shader <s>` map (surface -> shader
        name). Two distinct cases, and conflating them is what produced false alarms:

          * surf_shader is None  - no .tik at all (a bare .skd open, e.g. mg42_sideflash.skd).
            Every unresolved surface is worth naming, because nothing could have mapped it.
          * surf_shader is a dict - a .tik WAS opened. Only surfaces the .tik actually declares
            (exact name, a `surface <glob>* shader ...` pattern, or a blanket `surface all`) can
            be "missing". A surface the .tik never mentions is not an error: emitter carrier
            .tiks are invisible `rendereffects +dontdraw` dummies whose skelmodel surfaces are
            never meant to be skinned (electric_arc.tik -> dummy3.skd's material1..material4 -
            its whole look is two originemitter blocks), and reporting those as MISSING ASSET
            was pure noise.

        When the .tik does declare a surface that failed, naming the dead shader is what makes
        it diagnosable: muzflash_bar.tik maps `surface material1 shader muzmodel_bar`, but no
        shader block of that name is shipped in any scripts/*.shader."""
        if not manifest or not surfs: return
        try: man=json.load(open(manifest,encoding="utf-8"))
        except Exception: return
        import fnmatch
        low={k.lower() for k in man}
        miss=[s for s in surfs if s not in man and s.lower() not in low]
        sm={str(k).lower():v for k,v in (surf_shader or {}).items()}
        def _declared(sl):
            """Shader the opened .tik maps this surface to - exact, longest matching glob, or a
            blanket `all` (TIKI_ParseSurface / SurfaceCommand wildcard semantics). None when the
            .tik says nothing about this surface."""
            if sl in sm: return sm[sl]
            best=None
            for pat,sh2 in sm.items():
                if "*" in pat and fnmatch.fnmatch(sl,pat) and (best is None or len(pat)>len(best[0])):
                    best=(pat,sh2)
            if best: return best[1]
            return sm.get("all")
        shown=0
        for s in miss:
            sh=_declared(s.lower())
            # .tik opened but silent about this surface -> undeclared, not missing.
            if surf_shader is not None and sh is None: continue
            mp=(self._SH or {}).get((sh or s).lower())
            if mp:
                why=("shader '%s' resolves to '%s', but that texture file does not exist in the "
                     "loaded .pk3 files." % ((sh or s).lower(), mp))
            elif sh:
                why=("the .tik maps it to shader '%s', but there is no shader block of that name "
                     "in any scripts/*.shader and no texture of that name - that shader is not "
                     "shipped in the loaded .pk3 files." % sh)
            else:
                why="no surface->shader mapping in the .tik and no texture of that name"
            self._log_warn("MISSING ASSET  surface '%s'  ->  %s" % (s, why))
            shown+=1
        if shown:
            self._log_warn("  %d of %d surface(s) untextured." % (shown, len(surfs)))

    def _clear_info(self):
        """Revert the bottom-right model-details panel to its fresh-launch state:
        'No model loaded' title, empty stats + tag/bone/surface list, and no Re-open/
        Browser buttons. Called when the viewer is closed (Esc or Clear built models) so
        the panel doesn't keep showing the last model's surfaces/anims/tags after the 3D
        pane has reverted to the start page."""
        self._last_info=None
        try: self._info_title.configure(text="No model loaded",foreground=DIM)
        except Exception: pass
        try: self._info_stats.configure(text="")
        except Exception: pass
        try:
            t=self._tag_text
            t.configure(state="normal"); t.delete("1.0","end"); t.configure(state="disabled")
        except Exception: pass
        try:
            for w in self._reopen_bar.winfo_children(): w.destroy()
        except Exception: pass

    def _update_info(self, path, stdout, html_path=None):
        stem=os.path.splitext(os.path.basename(path))[0]
        if html_path is None: html_path=self._html_out_path(path)
        self._last_info=(path,stdout,html_path)            # re-rendered (from this HTML) on theme toggle
        bones_n=""; anim_names=[]
        for line in stdout.splitlines():
            line=line.strip()
            if line.startswith("-") and "bones," in line and "surfaces" in line: bones_n=line
            if "animation(s):" in line: anim_names=line.split(":",1)[-1].strip().split(", ")
        tags_parsed=[]; surf_names=[]
        try:
            html=open(html_path,encoding="utf-8").read()
            # brace-balanced extraction of the DATA object (regex breaks on nested [] in "pos")
            i=html.find("const DATA=")
            if i>=0:
                j=html.find("{",i); depth=0; k=j
                while k<len(html):
                    c=html[k]
                    if c=="{": depth+=1
                    elif c=="}":
                        depth-=1
                        if depth==0: break
                    k+=1
                _data=json.loads(html[j:k+1])
                tags_parsed=_data.get("tags",[])
                surf_names=[s.get("name","") for s in _data.get("surfRanges",[])]
                if not (anim_names and anim_names[0]):
                    anim_names=[a.get("name","") for a in _data.get("anims",[])]
        except Exception: pass
        # cache-hit opens have no build stdout, so the "- N bones, M surfaces" summary
        # line is absent - reconstruct it from the parsed DATA so a reopened model shows
        # the same stats header a freshly-built one does.
        if not bones_n and (tags_parsed or surf_names):
            nb=sum(1 for tg in tags_parsed if tg.get("kind")=="bone")
            bones_n=f"- {nb} bones, {len(surf_names)} surfaces"
        for w in self._reopen_bar.winfo_children(): w.destroy()
        self._info_title.configure(text=stem,foreground=ACCENT)
        self._info_stats.configure(text=bones_n+("  .  "+str(len(anim_names))+" anims" if anim_names and anim_names[0] else ""))
        # selectable/copyable tag & bone list, coloured like the viewer's legend
        t=self._tag_text; self._retheme_tag_text()
        t.configure(state="normal"); t.delete("1.0","end")
        if surf_names:
            t.insert("end",f"Surfaces ({len(surf_names)})\n","thead")
            for nm in surf_names: t.insert("end","\u25aa "+nm+"\n","tdim")
            t.insert("end","\n")
        if anim_names and anim_names[0]:
            t.insert("end",f"Anims ({len(anim_names)})\n","thead")
            for nm in anim_names: t.insert("end","\u25aa "+nm+"\n","tdim")
            t.insert("end","\n")
        if tags_parsed:
            t.insert("end","Tags / bones\n","thead")
            def rank(x): return 0 if x.get("origin") else (1 if x.get("kind")=="tag" else 2)
            for tg in sorted(tags_parsed,key=lambda x:(rank(x),x.get("name","").lower())):
                origin=bool(tg.get("origin")); kind=tg.get("kind","bone")
                dot="torigin" if origin else ("ttag" if kind=="tag" else "tbone")
                t.insert("end","\u25cf ",dot)
                t.insert("end",tg.get("name","")+"\n",(dot if (origin or kind=="tag") else "tdim"))
        t.configure(state="disabled")
        if os.path.exists(html_path):
            b=self._mkbtn(self._reopen_bar,text="\u21bb Re-open",command=lambda p=html_path:self._open_file(p),
                          tip="Show the last-built viewer again (no rebuild)")
            b.pack(side="left")
            b2=self._mkbtn(self._reopen_bar,text="Browser",command=lambda p=html_path:self._open_in_browser(p),
                           tip="Open the last-built viewer HTML in your external browser")
            b2.pack(side="left",padx=(4,0))

    # ---- embedded 3D viewer pane -----------------------------------------------
    def _ensure_webview(self):
        """Create the embedded WebView2 in the middle pane on first use. Returns
        True when an embedded view is ready. Any failure (package missing, no
        WebView2 runtime, .NET init error) logs once and returns False so the
        caller falls back to the external browser - never fatal."""
        if self._webview is not None: return True
        if WEBVIEW2 is None or not self._embed_on.get(): return False
        try:
            if _WV_HAVE_RT is not None and not _WV_HAVE_RT():
                self._log_line("(WebView2 runtime not found - opening in browser instead; "
                               "install Microsoft Edge WebView2 Runtime to embed)","dim")
                return False
            self.update_idletasks()
            w=max(self._viewpane.winfo_width(),400); h=max(self._viewpane.winfo_height(),300)
            wv=WEBVIEW2(self._viewpane,w,h)
            self._view_placeholder.pack_forget()
            wv.pack(fill="both",expand=True)
            self._webview=wv
            self._hook_embed_drop()      # stop the pane hijacking file drags (see below)
            return True
        except Exception as e:
            self._log_line(f"(embedded viewer unavailable: {e}; using browser)","dim")
            self._webview=None
            return False

    # --- embedded-pane drag & drop --------------------------------------
    # WebView2's default for an external file drop is "navigate to it", which
    # for a .skd/.tik means the pane downloads the file. Three independent,
    # best-effort guards (each harmless on its own):
    #   1) AllowExternalDrop=False  - Chromium refuses the drop outright, so
    #      it can never navigate/download.
    #   2) WinForms DragEnter/DragDrop on the two host controls - if the
    #      refused drop falls through to them, the file loads exactly like a
    #      drop on the rest of the window (path -> _drop_paths -> _poll_log).
    #   3) a JS guard injected into every page - if 1) is unavailable (very
    #      old WebView2 runtime) the page preventDefault()s the drop itself,
    #      so nothing downloads, and posts a message so we log a hint.
    # Runs once per webview instance, retrying until the async core init
    # finishes (wv.core appears); everything here is wrapped so a missing
    # API on some runtime can never break the viewer.
    def _hook_embed_drop(self,_tries=0):
        wv=self._webview
        if wv is None or getattr(self,"_embed_drop_hooked",False): return
        if getattr(wv,"core",None) is None:            # WebView2 still initialising
            if _tries<150: self.after(200,lambda:self._hook_embed_drop(_tries+1))
            return
        self._embed_drop_hooked=True
        try: wv.web.AllowExternalDrop=False            # 1) no navigate-on-drop
        except Exception: pass
        try:                                           # 2) catch the drop ourselves
            from System.Windows.Forms import DataFormats,DragDropEffects
            def _enter(s,a):
                try:
                    if a.Data.GetDataPresent(DataFormats.FileDrop): a.Effect=DragDropEffects.Copy
                except Exception: pass
            def _drop(s,a):
                try:
                    for p in a.Data.GetData(DataFormats.FileDrop):
                        if str(p).lower().endswith((".skd",".tik")): self._drop_paths.append(str(p))
                except Exception: pass
            self._wv_drag_cbs=(_enter,_drop)           # pythonnet: keep delegates alive
            for c in (getattr(wv,"web",None),getattr(wv,"control",None)):
                if c is None: continue
                try: c.AllowDrop=True; c.DragEnter+=_enter; c.DragDrop+=_drop
                except Exception: pass
        except Exception: pass
        js=("(function(){if(window.__mohaaDropGuard)return;window.__mohaaDropGuard=1;"
            "function s(e){e.preventDefault();e.stopPropagation();"
            "if(e.dataTransfer)e.dataTransfer.dropEffect='none';}"
            "window.addEventListener('dragover',s,true);"
            "window.addEventListener('dragenter',s,true);"
            "window.addEventListener('drop',function(e){s(e);"
            "try{if(window.chrome&&chrome.webview)chrome.webview.postMessage('mohaa-drop-blocked');}catch(_){}"
            "},true);})();")
        try: wv.core.AddScriptToExecuteOnDocumentCreatedAsync(js)   # 3) every future page
        except Exception: pass
        try: wv.core.ExecuteScriptAsync(js)                         #    and the current one
        except Exception: pass
        try:
            def _msg(s,a):
                try: m=a.TryGetWebMessageAsString()
                except Exception: return
                try:
                    if m=="mohaa-drop-blocked":
                        self._log_q.put(("dim","(the 3D pane can't take drops here - drop onto the file tree or console instead)"))
                    elif m=="mohaa-close":
                        # viewer Esc: revert the pane to the start page. MUST NOT touch the
                        # WebView2 from inside its own WebMessage callback (this runs on the
                        # WebView2/COM thread; destroying the control here crashes the process
                        # even if deferred). Route it through the same thread-safe queue every
                        # other worker uses; _poll_log runs _close_viewer on the Tk main thread,
                        # exactly like the (working) Clear-built-models path does.
                        self._log_q.put(("closeview",None))
                    elif m and m.startswith("mohaa-ang "):
                        # viewer placement dial moved: persist the pitch/yaw/roll triple.
                        # Same thread rule as "mohaa-close" - this runs on the WebView2/COM
                        # thread, so the config write is handed to the Tk main thread via the
                        # queue rather than done inline.
                        self._log_q.put(("setang",m.split(" ",1)[1]))
                    elif m and m.startswith("mohaa-anim "):
                        # the viewer asked for an animation the page was not built with
                        p=m.split(" ",2)
                        self._build_anim(p[1], p[2] if len(p)>2 else p[1])
                    elif m and m.startswith("mohaa-attach "):
                        # attachmodel panel: the viewer wants a model's rigid geometry
                        self._build_attach(m.split(" ",1)[1].strip())
                    elif m=="mohaa-attach-models":
                        # The PAGE asks for the model list on boot rather than the launcher
                        # pushing it: no navigation-timing race, and a page opened straight
                        # in a browser simply never asks, so the panel stays hidden there.
                        self._send_attach_models()
                except Exception as e:
                    self._log_q.put(("dim",f"(viewer message: {e})"))
            wv.core.WebMessageReceived+=_msg
            self._wv_msg_cb=_msg                        # keep delegate alive
        except Exception: pass

    # --- on-demand animation builds -------------------------------------------
    # A character model reaches well over a thousand animations through its
    # $include chain, so the page ships the MENU and nothing else. Clicking an
    # animation it does not hold posts `mohaa-anim <id> <name>` up here; we pull
    # that one .skc out of the paks, run mohaa_view.py --animbuild against the same
    # model, and drop the solved frames into the cache folder beside the HTML as
    # a<id>.js. The page then loads it with a plain <script> tag - which a file://
    # page may do, unlike fetch/XHR - and plays it. It stays on disk, so the same
    # animation is never built twice.
    def _build_anim(self, aid, name):
        if not aid: return
        if aid in self._anim_busy:
            self._log_q.put(("dim",f"({name} is already building)")); return
        if not (self._animcat and self._animcat_file and self._animcat_for
                and os.path.exists(self._animcat_for)):
            if not self._ensure_anim_ctx():
                self._log_q.put(("err","No animation catalogue for the model on screen - "
                                       "right-click it in the tree and Rebuild once")); return
        if not self._anim_outdir:
            self._log_q.put(("err","No output folder for built animations - reopen the model")); return
        ent=next((e for e in self._animcat["anims"] if e.get("id")==aid), None)
        if ent is None:
            self._log_q.put(("err",f"{name}: not in this model's animation catalogue")); return
        self._anim_busy.add(aid)
        threading.Thread(target=self._build_anim_work,args=(aid,ent),daemon=True).start()

    # --- attachmodel geometry --------------------------------------------------
    # The panel in the viewer lets the user hang any model off any bone. Geometry comes
    # from the same paks the tree is built from, is resolved ONCE per model and cached as
    # at<key>.js beside the page, so picking the same weapon for a second bone is free.
    # This is launcher-only: a page opened straight in a browser has no bridge, so it
    # never receives MOHAA_ATTACH_MODELS and the panel stays hidden.
    def _attach_key(self, vpath):
        return MTX._cache_id("attach|"+(vpath or "").lower()) if MTX is not None \
               else hashlib.blake2s(("attach|"+(vpath or "").lower()).encode("utf-8","replace"),
                                    digest_size=6).hexdigest()

    def _send_attach_models(self):
        try:
            files=sorted({p for p,_k in (self._all_files or [])})
            self._log_q.put(("js","try{MOHAA_ATTACH_MODELS("
                                 +json.dumps(files,separators=(",",":"))+")}catch(e){}"))
        except Exception as e:
            self._log_q.put(("dim",f"(attachment model list unavailable: {e})"))

    def _build_attach(self, vpath):
        if not vpath: return
        if not self._anim_outdir:
            self._log_q.put(("err","No output folder for attachments - reopen the model")); return
        key=self._attach_key(vpath)
        jp=os.path.join(self._anim_outdir,"at"+key+".js")
        if os.path.exists(jp) and os.path.getsize(jp)>0:
            # already resolved this session or a previous one - hand it straight back
            self._log_q.put(("js",f"try{{MOHAA_ATTACH_LOAD({json.dumps(key)},{json.dumps(vpath)})}}catch(e){{}}"))
            return
        if key in self._attach_busy:
            return
        self._attach_busy.add(key)
        threading.Thread(target=self._build_attach_work,args=(vpath,key),daemon=True).start()

    def _build_attach_work(self, vpath, key):
        try:
            if self._vfs is None:
                self._log_q.put(("err","Paks are still loading - try the attachment again in a moment")); return
            self._log_q.put(("dim",f"Resolving attachment {vpath} ..."))
            tdir=os.path.join(self._tmp,"_attach")
            os.makedirs(tdir,exist_ok=True)
            self._attach_idle=None
            skd_path=self._extract_attach_files(vpath,tdir)
            if not skd_path:
                self._log_q.put(("err",f"{vpath}: no .skd geometry found for this model"))
                self._log_q.put(("js",f"try{{MOHAA_ATTACH_FAIL({json.dumps(key)},"
                                      f"{json.dumps('no .skd geometry found')})}}catch(e){{}}")); return
            manifest=None
            if MTX is not None and self._tex_ready and self._vfs is not None:
                try:
                    import mohaa_view as MV
                    surfs=[s["name"] for s in MV.parse_skd(skd_path)["surfaces"]]
                    manifest=os.path.join(tdir,"_tex_"+key+".json")
                    nt,ns=MTX.write_textures_manifest(self._vfs,vpath,surfs,self._SH,self._TI,
                                                      manifest,global_surf=self._GS,
                                                      shader_props=self._PROPS)
                    if nt==0: manifest=None
                except Exception as e:
                    self._log_q.put(("dim",f"(attachment textures skipped: {e})")); manifest=None
            cmd=[self._pyexe,VIEWER,skd_path,"--attachbuild="+skd_path,
                 "--attachkey="+key,"--attachout="+self._anim_outdir,"--no-open"]
            if manifest: cmd.append("--textures="+manifest)
            if getattr(self,"_attach_idle",None): cmd.append("--attachidle="+self._attach_idle)
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=180,**NOWIN)
            for line in (p.stdout or "").splitlines():
                if line.strip(): self._log_q.put(("stdout",line))
            jp=os.path.join(self._anim_outdir,"at"+key+".js")
            if p.returncode!=0 or not os.path.exists(jp):
                for line in (p.stderr or "").splitlines()[-6:]:
                    if line.strip(): self._log_q.put(("err",line))
                self._log_q.put(("js",f"try{{MOHAA_ATTACH_FAIL({json.dumps(key)},"
                                      f"{json.dumps('build failed - see Output')})}}catch(e){{}}")); return
            # NOTE: the tik's `setup { scale N }` is deliberately NOT sent. It is an
            # authoring/import factor (static_airtank.tik carries 0.65 to convert cm to
            # world units), not the scale an attached model gets in-game, which is 1.
            self._log_q.put(("js",f"try{{MOHAA_ATTACH_LOAD({json.dumps(key)},{json.dumps(vpath)})}}catch(e){{}}"))
        except subprocess.TimeoutExpired:
            self._log_q.put(("err",f"{vpath}: attachment build timed out"))
            self._log_q.put(("js",f"try{{MOHAA_ATTACH_FAIL({json.dumps(key)},"
                                  f"{json.dumps('timed out')})}}catch(e){{}}"))
        except Exception as e:
            self._log_q.put(("err",f"{vpath}: {e}"))
            self._log_q.put(("js",f"try{{MOHAA_ATTACH_FAIL({json.dumps(key)},"
                                  f"{json.dumps(str(e)[:120])})}}catch(e){{}}"))
        finally:
            self._attach_busy.discard(key)

    def _extract_attach_files(self, vpath, tdir):
        """Pull one model out of the paks into tdir and return its .skd.

        A .tik entry names its geometry through `path`/`skelmodel`, so the tik is read
        first and the .skd it points at is fetched by name; a .skd entry is taken as-is.
        Only these two extensions are ever written, and _extract_one confines every path
        to the workspace, so a hostile pak cannot use this route either."""
        low=(vpath or "").lower()
        want=None
        if low.endswith(".tik"):
            raw=self._vfs.read(vpath)
            if raw is None: return None
            try:
                import mohaa_view as MV
                txt=MTX.expand_tik_includes(raw.decode("latin-1","replace"),self._vfs)
                parts=MV.parse_tik_skelmodels(txt)
                base,skel=(parts[0] if parts else MV.parse_tik_setup_head(txt))
            except Exception:
                return None
            if not skel: return None
            want=("/".join(x for x in [(base or "").strip("/"),skel.strip("/")] if x)).lower()
            if not self._vfs.exists(want):
                # `path` may already be embedded in the skelmodel line, or be wrong
                cands=[skel.lower()]+[n for n in self._vfs.names()
                                      if n.endswith("/"+os.path.basename(skel).lower())]
                want=next((c for c in cands if self._vfs.exists(c)),None)
        elif low.endswith(".skd"):
            want=vpath
        if not want: return None
        data=self._vfs.read(want)
        if data is None: return None
        target=os.path.join(tdir,os.path.basename(want))
        with open(target,"wb") as f: f.write(data)
        # Idle .skc: the model's authored rest pose. Named by the tik's own
        # `animations { idle X.skc }` where there is one, else the .skd's own stem.
        self._attach_idle=None
        cands=[]
        if low.endswith(".tik"):
            try:
                m=re.search(r"^\s*idle\s+(\S+\.skc)", txt, re.M|re.I)
                if m: cands.append(m.group(1).strip('"'))
            except Exception: pass
        cands.append(os.path.splitext(os.path.basename(want))[0]+".skc")
        d0="/".join(want.split("/")[:-1])
        for c in cands:
            c=c.replace("\\","/").lstrip("/")
            for cand in ((d0+"/"+c) if d0 else c, c):
                if self._vfs.exists(cand):
                    sd=self._vfs.read(cand)
                    if sd:
                        ip=os.path.join(tdir,os.path.basename(cand))
                        with open(ip,"wb") as f: f.write(sd)
                        self._attach_idle=ip
                    break
            if self._attach_idle: break
        return target

    def _ensure_anim_ctx(self):
        """Rebuild just enough to solve an animation: the .tik, its catalogue, and every
        skelmodel it assembles. Needed after a CACHED open, which serves the saved HTML
        without extracting anything - but an animation solved later has to land on the
        exact same merged bone list the page was built from, so the head/hands/helmet
        parts must be on disk too (mohaa_view.py re-runs the same assembly)."""
        entry=getattr(self,"_anim_entry",None)
        if not entry or MTX is None or self._vfs is None or not self._tmp: return False
        try:
            import mohaa_view as MV
            if os.path.isfile(entry):
                tik=os.path.join(self._tmp,os.path.basename(entry)); shutil.copyfile(entry,tik)
            else:
                d=self._vfs.read(entry)
                if not d: return False
                tik=os.path.join(self._tmp,os.path.basename(entry))
                with open(tik,"wb") as f: f.write(d)
            raw=open(tik,"r",encoding="latin-1",errors="replace").read()   # match the VFS codec
            cat=MTX.build_anim_catalog(raw,self._vfs,entry)
            if not cat.get("anims"): return False
            open(tik,"w",encoding="utf-8",errors="replace").write(
                MTX.expand_tik_includes(raw,self._vfs))
            tdir=os.path.dirname(tik)
            for (pp,ps) in (MV.parse_tik_skelmodels(raw) or []):
                ps=(ps or "").replace("\\","/").strip().strip('"')
                pp=(pp or "").replace("\\","/").strip().strip('"')
                if not ps: continue
                pv=self._resolve_skel_vfs(ps,pp,entry)
                if not pv: continue
                dd=self._vfs.read(pv)
                if dd:
                    with open(os.path.join(tdir,os.path.basename(ps)),"wb") as f: f.write(dd)
            cf=os.path.join(self._tmp,"animcat_"+re.sub(r"[^A-Za-z0-9_.-]","_",
                            os.path.basename(entry))+".json")
            with open(cf,"w",encoding="utf-8") as f: json.dump(cat,f,separators=(",",":"))
            self._animcat=cat; self._animcat_file=cf; self._animcat_for=tik
            self._log_q.put(("dim",f"animation catalogue rebuilt for {os.path.basename(entry)} "
                                  f"({len(cat['anims'])} animations)"))
            return True
        except Exception as e:
            self._log_q.put(("dim",f"(animation catalogue rebuild failed: {e})")); return False

    def _movement_donor(self, ent, srcdir):
        """Extract the MOVEMENT-slot .skc for an action animation; return its path or None.

        MOHAA torso animations carry no leg channels and no "Bip01 pos" (weapon_bar/
        bar_reload.skc, weapon_rifle/prone/rifle_prone_shoot.skc) because in-engine they are
        ACTION animations blended over a MOVEMENT animation: skelAnimStoreFrameList_c keeps
        both frame lists and GetSlerpValue/GetLerpValue3 fill whatever the action lacks from
        the movement slot. Played alone the legs fall back to the A-pose template, whose foot
        target sits at full IK reach, so they render dead straight.

        The <weapon>_<stance>_hit_* pain animations ARE full-body - Bip01 pos, Bip01 Footsteps,
        ORIGIN and the whole L/R Thigh/Calf/Foot/Toe0 set - and their legs hold that weapon's
        real idle stance for that stance. Donor = the first <weapon>_<stance>_hit* alias in
        this model's catalogue, falling back to any weapon's <stance>_hit* when this weapon
        ships none. Only frame 0 is used."""
        try:
            nm=(ent.get("n") or "").lower()
            src=(ent.get("s") or "").replace("\\","/").lower()
            if re.search(r'_hit',nm): return None        # already a full-body pain anim
            st="stand"
            for s in ("prone","crouch","kneel"):
                pat=r'(?:^|[_/])'+s+r'(?:$|[_/])'
                if re.search(pat,nm) or re.search(pat,src):
                    st="crouch" if s=="kneel" else s; break
            wpn=re.split(r'[_/]',nm)[0]
            pri=re.compile(r'^'+re.escape(wpn)+r'_'+st+r'_hit')
            alt=re.compile(r'(?:^|_)'+st+r'_hit')
            cands=sorted((e for e in self._animcat["anims"] if e.get("n")),
                         key=lambda e:e["n"].lower())
            don=next((e for e in cands if pri.match(e["n"].lower())),None) \
                or next((e for e in cands if alt.search(e["n"].lower())),None)
            if don is None or don.get("id")==ent.get("id"): return None
            dp=os.path.join(srcdir,(don.get("id") or "legs")+".skc")
            if not os.path.exists(dp):
                d=self._vfs_read_skc(don.get("s"))
                if not d: return None
                with open(dp,"wb") as f: f.write(d)
            self._log_q.put(("dim",f"  movement slot: {don.get('n')}  ({don.get('s','')})"))
            return dp
        except Exception as e:
            self._log_q.put(("dim",f"  (no movement slot: {e})")); return None

    def _build_anim_work(self, aid, ent):
        name=ent.get("n") or aid
        try:
            self._log_q.put(("dim",f"Building animation {name}  ({ent.get('s','')}) ..."))
            self._log_q.put(("status",f"Building {name}..."))
            src=os.path.join(self._tmp,"_ondemand"); os.makedirs(src,exist_ok=True)
            sp=os.path.join(src,aid+".skc")
            if not os.path.exists(sp):
                d=self._vfs_read_skc(ent.get("s"))
                if d is None:
                    self._log_q.put(("err",f"{name}: {ent.get('s','')} is not in the loaded paks"))
                    self._log_q.put(("js",f"try{{MOHAA_ANIM_FAIL({json.dumps(aid)},'.skc not found in the loaded paks')}}catch(e){{}}"))
                    return
                with open(sp,"wb") as f: f.write(d)
            os.makedirs(self._anim_outdir,exist_ok=True)
            # Facial sibling: models/human/animation/scripted/smoking pairs lightup.skc with
            # lightupMORPH.skc, declared in the .tik as two separate animations (smoking01 /
            # smoking_lightup_face). The body build already absorbs the face as a layer, but
            # the face entry is its own catalogue row - so extract and build it in the SAME
            # child run. It then has a real cached sidecar, which is what the drop-down's
            # "already built" dot actually reflects.
            also=[]; face_stem=None
            _s=(ent.get("s") or "")
            if _s.lower().endswith(".skc") and not _s[:-4].upper().endswith("MORPH"):
                _sib=_s[:-4]+"MORPH.skc"
                # Prefer a catalogue row: it has an id, so the facial entry can also be
                # BUILT and get its own "already built" dot in the drop-down.
                for _e2 in self._animcat["anims"]:
                    if (_e2.get("s") or "").lower()==_sib.lower() and _e2.get("id")!=aid:
                        _d2=self._vfs_read_skc(_e2.get("s"))
                        if _d2:
                            with open(os.path.join(src,_e2["id"]+".skc"),"wb") as f2: f2.write(_d2)
                            also.append(_e2["id"]); face_stem=_e2["id"]
                        break
                if face_stem is None:
                    # No catalogue row - new_generic_human.tik declares
                    # smoking_lightup/firstinhale/inhale/buttout_face but simply forgot
                    # smoking_throwaway_face, even though throwawayMORPH.skc ships. Pull it
                    # straight out of the paks so smoking05 still gets its face layer; it
                    # just has no drop-down entry of its own to light up.
                    _d3=self._vfs_read_skc(_sib)
                    if _d3:
                        face_stem=aid+"_face"
                        with open(os.path.join(src,face_stem+".skc"),"wb") as f3: f3.write(_d3)
            legs=self._movement_donor(ent,src)
            # ONE --animbuild carrying every id, comma-separated: the child's parser takes
            # a list on that flag, and passing the flag twice used to make the second
            # occurrence replace the first.
            cmd=[self._pyexe,VIEWER,self._animcat_for,
                 "--animcat="+self._animcat_file,
                 "--animbuild="+",".join([aid]+also),
                 "--animsrc="+src,"--animout="+self._anim_outdir,"--no-open"]
            if face_stem: cmd.append("--animpair="+aid+":"+face_stem)
            if legs: cmd.append("--animlegs="+legs)
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=180,**NOWIN)
            # The child flags its own failures with a leading "!". Carrying that exact text
            # back to the viewer beats a generic "build failed - see Output": "drives none of
            # this skeleton's 72 bones" tells the user it can NEVER work (it is a facial
            # morph track, not a bone track), whereas a generic message invites them to keep
            # clicking. The animation name prefix is stripped because the viewer already
            # shows the .skc path beside the message.
            reason=None
            for line in (p.stdout or "").splitlines():
                if not line.strip(): continue
                self._log_q.put(("stdout",line))
                ls=line.strip()
                if reason is None and ls.startswith("!"):
                    r=ls.lstrip("!").strip()
                    if ":" in r and r.split(":",1)[0].strip().lower()==str(name).strip().lower():
                        r=r.split(":",1)[1].strip()
                    reason=r
            if p.returncode!=0:
                for line in (p.stderr or "").splitlines()[-6:]:
                    if line.strip(): self._log_q.put(("err",line))
                _m=json.dumps(reason or "build failed - see Output")
                self._log_q.put(("js",f"try{{MOHAA_ANIM_FAIL({json.dumps(aid)},{_m})}}catch(e){{}}"))
                self._log_q.put(("status","Animation build failed - see log")); return
            jp=os.path.join(self._anim_outdir,"a"+aid+".js")
            if not os.path.exists(jp):
                _m=json.dumps(reason or "nothing was written")
                self._log_q.put(("js",f"try{{MOHAA_ANIM_FAIL({json.dumps(aid)},{_m})}}catch(e){{}}"))
                self._log_q.put(("err",f"{name}: build wrote no animation file")); return
            self._log_q.put(("ok",f"{name} ready ({os.path.getsize(jp)//1024} KB cached)"))
            self._log_q.put(("status","Done"))
            # queued, not called directly: this runs on a worker thread and
            # ExecuteScriptAsync must be issued from the Tk/UI thread or it is lost
            self._log_q.put(("js",f"try{{MOHAA_ANIM_LOAD({json.dumps(aid)})}}catch(e){{}}"))
            for _a2 in also:
                if os.path.exists(os.path.join(self._anim_outdir,"a"+_a2+".js")):
                    # marks the facial entry as built in the drop-down without selecting it
                    self._log_q.put(("js",f"try{{MOHAA_ANIM_HAVE({json.dumps(_a2)})}}catch(e){{}}"))
        except subprocess.TimeoutExpired:
            self._log_q.put(("err",f"{name}: build timed out"))
            self._log_q.put(("js",f"try{{MOHAA_ANIM_FAIL({json.dumps(aid)},'build timed out')}}catch(e){{}}"))
        except Exception as e:
            self._log_q.put(("err",f"{name}: {e}"))
            self._log_q.put(("js",f"try{{MOHAA_ANIM_FAIL({json.dumps(aid)},'build error')}}catch(e){{}}"))
        finally:
            self._anim_busy.discard(aid)

    def _embed_js(self,js):
        """Fire-and-forget JS into the embedded viewer page. Safe no-op when no
        webview / core not initialised yet (core appears once WebView2 finishes
        its async init)."""
        wv=self._webview
        if wv is None: return
        try:
            core=getattr(wv,"core",None)
            if core is not None: core.ExecuteScriptAsync(js)
        except Exception: pass

    def _embed_merge_ui(self):
        """Merge the duplicated controls: the launcher's top-right Theme /
        Shortcuts buttons drive BOTH the launcher and the embedded viewer, so the
        viewer's own 'Model' row (bTheme / bHelp) is hidden and its theme is
        synced to the launcher's. Double-shot after load because the page may
        still be parsing on the first call."""
        light="true" if self._theme=="light" else "false"
        self._embed_js(
            "try{var b=document.getElementById('bTheme');"
            "if(b&&b.closest('.sect'))b.closest('.sect').style.display='none';"
            f"if(typeof setTheme==='function')setTheme({light});}}catch(e){{}}")

    def _close_viewer(self):
        """Revert the viewer pane to the initial 'select a .skd / .tik' placeholder - the
        same state as a fresh launch, and the same thing Clear-built-models does.

        MUST run on the Tk main thread. It is safe to destroy the WebView2 here because both
        callers reach this on the main thread: Clear-built-models is a menu command, and the
        viewer's Esc arrives via the _log_q -> _poll_log path (NOT directly from the WebView2
        message callback, which would crash). Leaves the _embed_on preference alone so
        re-embedding still works on the next open. No-op when nothing is open."""
        if self._webview is not None:
            wv=self._webview; self._webview=None
            self._embed_drop_hooked=False              # re-hook drops on a future webview
            try: wv.pack_forget()
            except Exception: pass
            try: wv.destroy()
            except Exception: pass
        self._embed_url=None
        # Keep _last_build so the top "Open Viewer" button can REOPEN the model the user just
        # Esc-closed (the path bar still shows its "pk3 model: <n>" name; _run re-runs this
        # build, which finds the cached HTML and reopens instantly). Only the details panel
        # and per-open anim dir are transient and get cleared. (Clear-built-models, whose
        # builds are deleted, clears _last_build + the path bar itself after this returns.)
        self._last_info=None; self._anim_outdir=None; self._attach_busy=set()
        self._clear_info()          # revert the bottom-right details panel to "No model loaded"
        # ...and the status bar, which would otherwise still read "Viewing <name>" over an
        # empty pane. Safe for the force-rebuild caller too: _open_pk3_model sets its own
        # status immediately afterwards.
        try: self._set_status("Ready")
        except Exception: pass
        try:
            if not self._view_placeholder.winfo_ismapped():
                self._view_placeholder.pack(fill="both",expand=True)
        except Exception:
            try: self._view_placeholder.pack(fill="both",expand=True)
            except Exception: pass

    def _toggle_embed(self):
        self._save_opts()
        if not self._embed_on.get() and self._webview is not None:
            try: self._webview.destroy()
            except Exception: pass
            self._webview=None
            self._embed_drop_hooked=False              # re-hook drops on a future webview
            self._view_placeholder.pack(fill="both",expand=True)
        elif self._embed_on.get() and self._embed_url and self._ensure_webview():
            try: self._webview.load_url(self._embed_url)
            except Exception: pass

    def _open_in_browser(self,path):
        import webbrowser, pathlib
        # as_uri() percent-encodes; hand-built file:// URLs truncate at the first '#' in
        # the path and mangle '%' and non-ASCII (a Cyrillic/CJK username is enough).
        webbrowser.open(pathlib.Path(os.path.abspath(path)).as_uri())

    def _open_standalone(self,path):
        """Open a built viewer HTML in a new browser tab window, using the
        browser-version of the page: opened WITHOUT the #embed hash, so it keeps
        its own Theme / Shortcuts buttons (unlike the embedded in-launcher pane).
        The old self-contained --app= 'standalone window' feature was removed - this
        now always goes through the default browser."""
        self._open_in_browser(path)

    def _reclaim_focus(self,e):
        """Clicking anywhere on the launcher (search bar, tree, log, buttons...)
        while the embedded WebView2 pane holds the keyboard takes typing back.
        Why plain clicks stop working: the WebView2 is a WinForms child HWND
        inside this Tk toplevel. When the viewer page loads, Chromium takes Win32
        keyboard focus; Tk gets WM_KILLFOCUS and marks the app unfocused. A later
        click on a Tk widget runs the widget's normal focus_set() binding, but an
        unfocused Tk only RECORDS the pending focus target - no Win32 SetFocus is
        issued (a click inside an already-active toplevel produces no WM_ACTIVATE
        to hand the keyboard back), so every keystroke keeps hitting the viewer
        page's hotkeys. focus_force() is the Tk call that forces the Win32-level
        focus change. Clicking the viewer pane itself never reaches Tk (it's a
        native child window), so Chromium re-takes the keyboard on its own and
        viewer hotkeys resume - the vice-versa, no code needed.
        Guarded so ordinary in-launcher clicks (Tk already owns the keyboard) are
        untouched: then focus_displayof() returns a widget, not None, and we do
        nothing - no focus stealing on every click."""
        if self._webview is None: return
        w=e.widget
        try:
            if isinstance(w,str): w=self.nametowidget(w)   # bind_all can hand back a path name
        except Exception: return
        try:
            if w is self._webview or str(w).startswith(str(self._webview)): return  # click landed on the pane
        except Exception: pass
        try:
            if self.focus_displayof() is None and w.winfo_exists(): w.focus_force()
        except Exception: pass

    def _open_file(self,path):
        """Show a built viewer HTML: in the embedded middle pane when available,
        otherwise in the external browser (the old behaviour). For the embedded
        pane the URL carries an #embed&theme=... hash so the page boots straight
        into the in-launcher layout + current theme (before first paint) instead
        of flashing the standalone 'webpage' layout and then swapping via JS."""
        # the on-demand animation cache lives in a folder next to the page and named
        # after it: <out>/allied_pilot_tik_view.html -> <out>/allied_pilot_tik_view/
        self._anim_outdir=os.path.splitext(os.path.abspath(path))[0]
        self._stamp_anim_cache()
        import pathlib
        base=pathlib.Path(os.path.abspath(path)).as_uri()   # percent-encoded; '#' safe
        if self._ensure_webview():
            try:
                url=base+"#embed&theme="+("light" if self._theme=="light" else "dark")
                _ang=self.view_angles()
                if _ang: url+="&ang="+",".join(str(x) for x in _ang)
                self._webview.load_url(url); self._embed_url=url
                self._set_status(f"Viewing {os.path.basename(path)}")
                self.after(700,self._embed_merge_ui); self.after(2200,self._embed_merge_ui)
                return
            except Exception as e:
                self._log_line(f"(embed failed: {e}; opening in browser)","dim")
        self._open_in_browser(path)

    def _on_close(self):
        # persist the current pane layout before anything is torn down
        self._save_panes()
        # Dispose the WebView2 control BEFORE tearing down Tk: letting it die in
        # the <Destroy> cascade mid-teardown is what produced the "Python has
        # stopped working" crash box on exit.
        if self._webview is not None:
            wv=self._webview; self._webview=None
            try: wv.pack_forget()
            except Exception: pass
            try: wv.web.Dispose()
            except Exception: pass
        if getattr(self,"_restore_drop",None):
            try: self._restore_drop()
            except Exception: pass
        if self._tmp and os.path.isdir(self._tmp): shutil.rmtree(self._tmp,ignore_errors=True)
        lf=getattr(self,"_logfile",None)
        if lf is not None:
            try: lf.close()
            except Exception: pass
            self._logfile=None
        self.destroy()

    def _enable_win_drop(self):
        if not sys.platform.startswith("win"): return
        try:
            import ctypes
            is64=ctypes.sizeof(ctypes.c_void_p)==8
            LONG_PTR=ctypes.c_int64 if is64 else ctypes.c_int32
            ULONG_PTR=ctypes.c_uint64 if is64 else ctypes.c_uint32
            LRESULT=LONG_PTR; WPARAM=ULONG_PTR; LPARAM=LONG_PTR
            HWND=ctypes.c_void_p; HANDLE=ctypes.c_void_p; UINT=ctypes.c_uint
            user32=ctypes.windll.user32; shell32=ctypes.windll.shell32
            hwnd=self.winfo_id(); WM_DROPFILES=0x0233; GWLP_WNDPROC=-4
            WNDPROC=ctypes.WINFUNCTYPE(LRESULT,HWND,UINT,WPARAM,LPARAM)
            SetWL=user32.SetWindowLongPtrW if (is64 and hasattr(user32,"SetWindowLongPtrW")) else user32.SetWindowLongW
            CallWP=user32.CallWindowProcW
            SetWL.argtypes=[HWND,ctypes.c_int,WNDPROC]; SetWL.restype=LONG_PTR
            CallWP.argtypes=[LONG_PTR,HWND,UINT,WPARAM,LPARAM]; CallWP.restype=LRESULT
            shell32.DragQueryFileW.argtypes=[HANDLE,UINT,ctypes.c_wchar_p,UINT]; shell32.DragQueryFileW.restype=UINT
            shell32.DragFinish.argtypes=[HANDLE]; shell32.DragAcceptFiles.argtypes=[HWND,ctypes.c_int]
            self._old_wndproc=0
            def py_wndproc(h,msg,wp,lp):
                if msg==WM_DROPFILES:
                    try:
                        n=shell32.DragQueryFileW(wp,0xFFFFFFFF,None,0)
                        for i in range(n):
                            need=shell32.DragQueryFileW(wp,i,None,0)
                            buf=ctypes.create_unicode_buffer(need+1)
                            shell32.DragQueryFileW(wp,i,buf,need+1)
                            if buf.value.lower().endswith((".skd",".tik")): self._drop_paths.append(buf.value)
                        shell32.DragFinish(wp)
                    except Exception: pass
                    return 0
                try: return CallWP(self._old_wndproc,h,msg,wp,lp)
                except Exception: return 0
            self._wndproc_cb=WNDPROC(py_wndproc)
            old=SetWL(hwnd,GWLP_WNDPROC,self._wndproc_cb)
            if not old: self._wndproc_cb=None; self._log_line("(drag-drop unavailable; use Browse)","dim"); return
            self._old_wndproc=old; shell32.DragAcceptFiles(hwnd,True)
            def _restore(*_):
                try: SetWL.argtypes=[HWND,ctypes.c_int,LONG_PTR]; SetWL(hwnd,GWLP_WNDPROC,self._old_wndproc)
                except Exception: pass
            self._restore_drop=_restore
            self.bind("<Destroy>",lambda e:_restore() if e.widget is self else None)
            self._log_line("Drag-and-drop ready - drop a .skd/.tik onto this window.","dim")
        except Exception as e:
            self._log_line(f"(drag-drop unavailable: {e}; use Browse)","dim")

if __name__=="__main__":
    init=None
    for a in sys.argv[1:]:
        if a.lower().endswith((".skd",".tik")) and os.path.exists(a): init=a; break
    def _run_app():
        App(initial_file=init).mainloop()
    if WEBVIEW2 is not None:
        # WebView2's WinForms control needs an STA COM apartment - run the whole
        # Tk app on a .NET STA thread (tkwebview2's documented pattern). Any
        # failure falls straight back to the plain main-thread run.
        try:
            from System.Threading import Thread as _NetThread, ApartmentState as _ApState, ThreadStart as _TStart
            _t=_NetThread(_TStart(_run_app)); _t.ApartmentState=_ApState.STA
            _t.Start(); _t.Join()
        except Exception:
            _run_app()
        # pythonnet's CLR + WebView2 do not survive normal interpreter shutdown:
        # their atexit/finalizer teardown is what raised the "Python has stopped
        # working" box AFTER the window closed. All real cleanup (temp dir,
        # config, WebView2 Dispose) already ran in _on_close - skip straight out.
        os._exit(0)
    else:
        _run_app()

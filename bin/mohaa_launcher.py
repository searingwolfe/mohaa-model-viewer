#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
#  mohaa_launcher.py  --  desktop launcher for mohaa_view.py
#  Open a loose .skd/.tik, or load MOHAA .pk3 paks and browse their models/ tree.
#  Each model is built into a viewer page by mohaa_view.py and shown in an embedded
#  WebView2 pane (or the default browser). Loaded paks and preferences persist
#  between sessions. Expects mohaa_view.py and mohaa_textures.py alongside.
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
import sys, os, re, subprocess, threading, queue, glob, json, zipfile, tempfile, shutil, hashlib, logging, time
# Some Linux distros package Tk separately; exit with install instructions rather
# than a bare ImportError.
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
LOG=MC.get_logger("launcher")       # module logger (self._log is the Output pane widget)
_MTX_ERR=""                                # why mohaa_textures failed to import, if it did
try:
    import mohaa_textures as MTX           # texture resolution over the loaded paks
except Exception as _mtx_e:
    # Not fatal (models still build, untextured), but never silent: the reason is logged
    # here and shown in the Output pane by _prepare_indexes.
    LOG.error("mohaa_textures could not be imported; models will load untextured", exc_info=True)
    _MTX_ERR="%s: %s"%(type(_mtx_e).__name__,_mtx_e)
    MTX=None

# Optional embedded viewer: Edge WebView2 inside the Tk window (Windows only).
# Requires `pip install pythonnet pywebview==4.4.1 tkwebview2` and the WebView2 runtime.
# If unavailable, WEBVIEW2 stays None and models open in the external browser.
# pywebview is pinned to 4.4.1 because tkwebview2 3.5.0 constructs its internals directly.
WEBVIEW2=None; _WV_HAVE_RT=None; _WEBVIEW_ERR=""
if sys.platform.startswith("win"):
    try:
        from tkwebview2.tkwebview2 import WebView2 as WEBVIEW2, have_runtime as _WV_HAVE_RT
    except Exception as _e:
        MC.swallowed()
        _WEBVIEW_ERR=str(_e)

# Hide the console windows of child processes (Python probes, viewer builds); needed
# when the launcher itself runs under pythonw.
NOWIN=dict(creationflags=0x08000000) if sys.platform.startswith("win") else {}   # CREATE_NO_WINDOW

# ------------------------------------------------------------------ themes ---
THEMES={
 "dark":dict(BG="#0e1116",PANEL="#161b22",LINE="#2b333d",TXT="#d6dde6",DIM="#8b97a6",
             ACCENT="#7ee787",TAG_C="#f2f5f8",ORIGIN="#c084fc",BONE_C="#566778",
             BTN_BG="#21272f",BTN_HOV="#2d3a2d",ERR_C="#f47067",WARN_C="#e3b341",SEL_BG="#243042",
             TIP_BG="#1c232c",TIP_TXT="#d6dde6",ENTRY_BG="#10151c"),
 "light":dict(BG="#f5f7fa",PANEL="#ffffff",LINE="#d0d7de",TXT="#1f2328",DIM="#57606a",
             ACCENT="#0969da",TAG_C="#7c6408",ORIGIN="#8250df",BONE_C="#57606a",
             BTN_BG="#eef1f4",BTN_HOV="#ddebff",ERR_C="#cf222e",WARN_C="#9a6700",SEL_BG="#ddf4ff",
             TIP_BG="#ffffff",TIP_TXT="#1f2328",ENTRY_BG="#ffffff"),
}
# Module-level colour names used throughout the UI; apply_theme() re-points them at the
# active palette.
BG=PANEL=LINE=TXT=DIM=ACCENT=TAG_C=ORIGIN=BONE_C=BTN_BG=BTN_HOV=ERR_C=WARN_C=SEL_BG=TIP_BG=TIP_TXT=ENTRY_BG=""

def set_palette(name):
    """Point the module-level colour names (BG, PANEL, ...) at the named palette.

    name: a key of THEMES; anything else selects "dark". Returns the palette dict.
    Written out name by name (no globals() tricks) so every colour's origin is visible."""
    global BG,PANEL,LINE,TXT,DIM,ACCENT,TAG_C,ORIGIN,BONE_C,BTN_BG,BTN_HOV,ERR_C,WARN_C,SEL_BG,TIP_BG,TIP_TXT,ENTRY_BG
    p=THEMES.get(name) or THEMES["dark"]
    BG=p["BG"]; PANEL=p["PANEL"]; LINE=p["LINE"]; TXT=p["TXT"]; DIM=p["DIM"]
    ACCENT=p["ACCENT"]; TAG_C=p["TAG_C"]; ORIGIN=p["ORIGIN"]; BONE_C=p["BONE_C"]
    BTN_BG=p["BTN_BG"]; BTN_HOV=p["BTN_HOV"]; ERR_C=p["ERR_C"]; WARN_C=p["WARN_C"]
    SEL_BG=p["SEL_BG"]; TIP_BG=p["TIP_BG"]; TIP_TXT=p["TIP_TXT"]; ENTRY_BG=p["ENTRY_BG"]
    return p
set_palette("dark")

def _mono_family():
    """First installed monospace family. Consolas is Windows-only, and Tk silently
    substitutes a proportional font for a missing family, which breaks the aligned file
    tree and console. "TkFixedFont" is the fallback."""
    try:
        import tkinter.font as _tkf
        have={f.lower() for f in _tkf.families()}
    except Exception:
        MC.swallowed()
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
# Shown in Help --> Privacy & Legal and summarised in About. Kept in the program so
# users who never visit the repo can read it; keep in sync with docs/PRIVACY.md.
PRIVACY_SUMMARY=("This program collects nothing and sends nothing, and has no\n"
                 "telemetry. It uses the network only when you check for updates.")

PRIVACY_TEXT = """PRIVACY NOTICE  --  MOHAA Model Viewer
Last updated: 12 November 2026

1. THE SHORT VERSION
   This program does not collect, transmit, sell, share or profile anything.
   It contains no telemetry, no analytics, no crash reporting, no advertising
   and no tracking identifiers, and it never checks for updates on its own. The
   program uses the network only when YOU open Help --> Check for updates, and
   the startup scripts only to install missing Python packages (see 3);
   everything else happens entirely on your computer.

2. WHAT IS STORED, AND WHERE
   The program stores six things, all on your own machine, all readable and
   deletable by you at any time:

     a) Settings file  --  mohaa_viewer_config.json
        Written to the program's "output" folder (the one beside the "bin" folder
        that holds the scripts). In a flat / portable install - all files in one
        folder - it sits in that folder instead. Same on Windows, macOS and Linux.
        Contains: the .pk3 paths you loaded, the recent-files list (unless
        Options --> Don't save recent files is on), your chosen output folder,
        theme, window layout, view angles, and the paths of any external
        programs you configured. It contains file paths, which on most systems
        include your user name. The previous copy is kept beside it as a .bak
        file, and a damaged file is set aside as .corrupt-<date>. Options -->
        Reset settings... clears it.

     b) Console log  --  output_console.log, in the same folder as (a).
        A copy of the Output pane, replaced on each launch (the previous
        launch's copy is kept with ".prev" in its name). It contains the file
        paths the program touched, so it too may include your user name.

     c) Program logs  --  the "logs" folder inside the folder of (a).
        A timestamped record of what the program did and of any errors, with
        their technical details, one file for each part of the program. Each
        file is capped at 2 MB, with five older copies kept. Like (b) it
        contains file paths. Options --> Open log folder shows it.

     d) Working files
        A temporary workspace under your system temp folder (mohaaview_*), and
        the generated .html viewers in your chosen output folder. Both are
        removable from File --> Clear built models / Clear %temp% files. On
        Windows, the embedded 3D pane (Microsoft Edge WebView2) also keeps its
        browser files in a "webview2" folder beside (a).

     e) Display choices in the browser
        The viewer pages remember a few display choices (theme, backdrop colour,
        renderer, placement angles, game cvars) in the browser's local storage.
        The embedded pane runs in private mode and forgets them when the program
        closes; in your own browser they stay with that browser's data for local
        files.

     f) Previous versions  --  the "previous-versions" folder beside (a).
        When Help --> Check for updates installs a new version, the files it
        replaces are copied here first, one numbered folder per update, with a
        changelog.txt listing them. Delete them whenever you like.

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

     - The startup script (MOH Model-Map Viewer (Windows x86-x64).bat, or the .sh
       file on Linux and macOS) installs any missing Python packages from
       pypi.org into the program's own bin folder. On Windows, if no suitable
       Python is found and you agree when asked, it runs
       python_installer_updater.bat, which downloads Python from python.org.
       Both sites apply their own privacy policies.

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
   Questions about this notice: open an issue on the project's GitHub
   repository (github.com/searingwolfe/mohaa-model-viewer).
"""

HERE=os.path.dirname(os.path.abspath(__file__))

def _write_base_dir():
    """Folder the program writes to (config, console log, default output folders).

    If the scripts live in a 'bin' folder (the shipped layout: bin/, docs/, output/), this
    is the sibling 'output' folder; otherwise (flat/portable install), or when the parent
    of 'output' isn't writable, it is HERE. Pure: init_runtime() creates the folder, so
    importing this module (as mohaa_map_launcher does) has no side effects."""
    return MC.data_dir()
DATADIR=_write_base_dir()
VIEWER=os.path.join(HERE,"mohaa_view.py")
# Largest pak entry that is extracted or read into memory; bigger ones are skipped as
# decompression bombs. Same limit as the pak index (mohaa_textures.Vfs.MAX_ENTRY).
PAK_ENTRY_MAX=getattr(getattr(MTX,"Vfs",None),"MAX_ENTRY",192*1024*1024)
# Minimum mohaa-viewer-rev a cached HTML must carry to be reused; older pages are
# rebuilt so new viewer features show up. Keep equal to VIEWER_REV in mohaa_view.py.
# Source mtimes are the usual rebuild trigger, but a zip round-trip can scramble them,
# so the baked rev is the backstop. Also gates the animation/attachment sidecar caches
# (see _stamp_anim_cache).
VIEWER_REV_REQUIRED=80
# Sentinel subdir for single-file builds (Browse / drag-drop / Recent / path bar). It
# routes the output HTML to a "standalone" folder beside "models" instead of the
# pak-mirroring tree; the null byte means it can't collide with a real folder name.
STANDALONE_SUBDIR="\x00standalone"
CONFIG=os.path.join(DATADIR,"mohaa_viewer_config.json")
# The paks both programs have loaded: one list beside their own settings, so the Model
# Viewer and the Map Viewer open with the same paks and follow each other's changes.
PAKS_SHARED=os.path.join(DATADIR,"mohaa_paks.json")
INFO_PANE_WIDTH=300                  # the bottom-right details pane's default width
# The bottom row (Output | details): its default height, and the least it can be dragged
# to, just the "Output" label and the details' title line, which sit level.
BOTTOM_ROW_HEIGHT=130
BOTTOM_ROW_MIN=26
PANES_LAYOUT=3                       # bumped when a saved sash should give way to a new default
                                     # (3: the bottom row's height and the details pane's width
                                     # are kept, not where their sashes were in the window)
_ICONS={}                            # (kind, colour, px) -> PhotoImage, kept alive here

def button_icon(kind,colour,px=14):
    """A small icon for a details-pane button, drawn with Pillow at 4x and scaled down so
    its edges are smooth: "rebuild" a hammer, "browser" a globe, "file" a page with lines.
    Drawn rather than typed because Tk on older Pythons can't show symbols outside the
    Basic Multilingual Plane (the globe emoji is one). None when Pillow can't draw it."""
    key=(kind,colour,px)
    if key in _ICONS: return _ICONS[key]
    try:
        Image=MC.pil_image()
        from PIL import ImageDraw, ImageTk
    except ImportError:
        MC.swallowed(); return None
    S=px*4; lw=max(2,S//9)
    img=Image.new("RGBA",(S,S),(0,0,0,0)); d=ImageDraw.Draw(img)
    c=colour
    if kind=="browser":
        m=lw//2+1; r=(S-2*m)/2; cx=cy=S/2
        d.ellipse([m,m,S-m,S-m],outline=c,width=lw)
        d.ellipse([S*0.32,m,S*0.68,S-m],outline=c,width=max(2,lw*3//4))
        d.line([m,cy,S-m,cy],fill=c,width=max(2,lw*3//4))
        for f in (-0.5,0.5):
            y=cy+f*r; hw=(r*r-(f*r)**2)**0.5
            d.line([cx-hw,y,cx+hw,y],fill=c,width=max(2,lw*2//3))
    elif kind=="rebuild":
        # handle from the bottom left up to the head, the head across it
        d.line([S*0.14,S*0.86,S*0.58,S*0.42],fill=c,width=int(S*0.14))
        hx,hy,L,T=S*0.62,S*0.36,S*0.30,S*0.13    # head centre, half-length, half-thickness
        ux,uy=0.7071,0.7071                       # along the head (across the handle)
        vx,vy=0.7071,-0.7071                      # along the handle
        pts=[(hx+ux*L+vx*T,hy+uy*L+vy*T),(hx+ux*L-vx*T,hy+uy*L-vy*T),
             (hx-ux*L-vx*T,hy-uy*L-vy*T),(hx-ux*L+vx*T,hy-uy*L+vy*T)]
        d.polygon(pts,fill=c)
    else:
        x0,y0,x1,y1,fo=S*0.18,S*0.06,S*0.82,S*0.94,S*0.24
        d.line([(x0,y0),(x1-fo,y0),(x1,y0+fo),(x1,y1),(x0,y1),(x0,y0)],fill=c,width=lw,joint="curve")
        d.line([(x1-fo,y0),(x1-fo,y0+fo),(x1,y0+fo)],fill=c,width=max(2,lw*2//3))
        for f in (0.45,0.62,0.79):
            d.line([x0+S*0.13,S*f,x1-S*0.13,S*f],fill=c,width=max(2,lw*2//3))
    try:
        im=ImageTk.PhotoImage(img.resize((px,px),Image.LANCZOS))
    except Exception:
        MC.swallowed(); return None
    _ICONS[key]=im
    return im

def info_button(app,kind,text,command,tip):
    """A details-pane button with its icon (button_icon) left of the text, sized to the
    pane's small font."""
    try:
        import tkinter.font as _tkf
        px=max(10,_tkf.Font(font=FONT_SMALL).metrics("linespace")-2)
    except Exception:
        MC.swallowed(); px=14
    ic=button_icon(kind,TXT,px)
    kw={"image":ic,"compound":"left"} if ic else {}
    return app._mkbtn(app._reopen_bar,text=text,command=command,tip=tip,**kw)

def make_info_pane(app,parent,title,tip):
    """The bottom-right details pane, shared by both programs: one scrollable column with
    the title, the stats line, the Rebuild / Browser / .tik (.map) buttons and the list, so a
    small pane scrolls as a whole instead of hiding the list's scrollbar or the buttons.
    Sets app._info_title, _info_stats, _reopen_bar, _tag_text, _info_canvas and
    app._info_refit() (call it after the list changes: it fits the list to its lines and
    the scroll area to the column). Returns the pane's frame."""
    info=ttk.Frame(parent,style="Panel.TFrame",width=INFO_PANE_WIDTH); info.pack_propagate(False)
    sb=ttk.Scrollbar(info,orient="vertical")
    cv=tk.Canvas(info,bg=PANEL,highlightthickness=0,borderwidth=0,yscrollincrement=18,yscrollcommand=sb.set)
    sb.configure(command=cv.yview)
    sb.pack(side="right",fill="y"); cv.pack(side="left",fill="both",expand=True)
    inner=ttk.Frame(cv,style="Panel.TFrame")
    win=cv.create_window(0,0,window=inner,anchor="nw")
    def _flow():
        # the buttons left to right, a new row when the next doesn't fit the pane's width
        # (place, so a narrow pane wraps them instead of cutting the last one off)
        bar=app._reopen_bar; avail=max(1,cv.winfo_width()-20); gap=4
        x=y=rowh=0
        for w in bar.winfo_children():
            if w.winfo_manager()=="pack": w.pack_forget()
            rw,rh=w.winfo_reqwidth(),w.winfo_reqheight()
            if x and x+rw>avail: x=0; y+=rowh+3; rowh=0
            w.place(x=x,y=y); x+=rw+gap; rowh=max(rowh,rh)
        h=y+rowh
        if int(bar.cget("height") or 0)!=max(1,h): bar.configure(height=max(1,h))
    def _fit(_e=None):
        try:
            cw=max(1,cv.winfo_width())
            cv.itemconfigure(win,width=cw)
            app._info_stats.configure(wraplength=max(60,cw-24))
            _flow()
            cv.configure(scrollregion=(0,0,cw,max(inner.winfo_reqheight(),cv.winfo_height())))
        except tk.TclError:
            MC.swallowed()
    inner.bind("<Configure>",_fit); cv.bind("<Configure>",_fit)
    def _wheel(e):
        if inner.winfo_reqheight()>cv.winfo_height():
            up=getattr(e,"num",0)==4 or getattr(e,"delta",0)>0
            cv.yview_scroll(-3 if up else 3,"units")
        return "break"
    def _bind_wheel(w):
        for seq in ("<MouseWheel>","<Button-4>","<Button-5>"): w.bind(seq,_wheel)
    app._info_title=ttk.Label(inner,text=title,style="Panel.TLabel",foreground=DIM)
    app._info_title.pack(anchor="w",padx=10,pady=(8,2))
    app._info_stats=ttk.Label(inner,text="",style="PanelDim.TLabel",wraplength=INFO_PANE_WIDTH-40,justify="left")
    app._info_stats.pack(anchor="w",padx=10,pady=(0,4))
    app._reopen_bar=ttk.Frame(inner,style="Panel.TFrame",height=1); app._reopen_bar.pack(fill="x",padx=10,pady=(0,6))
    # read-only Text so the list can be selected and copied, coloured per kind, with a
    # right-click menu; as tall as its lines, so the column scrolls, not the Text
    app._tag_text=tk.Text(inner,bg=PANEL,fg=TXT,insertbackground=TXT,font=FONT_SMALL,relief="flat",height=1,
                          wrap="none",state="disabled",highlightthickness=0,cursor="arrow")
    app._tag_text.pack(fill="x",padx=6,pady=(0,6))
    app._tag_text.bind("<Button-3>",app._show_tag_menu)
    app._tip(app._tag_text,tip)
    app._info_canvas=cv
    def _refit():
        try:
            t=app._tag_text
            n=int(t.index("end-1c").split(".")[0])
            t.configure(height=max(1,n))
            for w in app._reopen_bar.winfo_children():
                _bind_wheel(w)
                # compact buttons, at least as wide as their text (a negative width is a
                # minimum, so a wider glyph or the icon never cuts the text), so Rebuild,
                # Browser and .map / .tik fit side by side in the pane's default width (a
                # narrower pane wraps them: _flow)
                try: w.configure(style="Info.Tool.TButton",width=-len(str(w.cget("text"))))
                except tk.TclError: MC.swallowed()
            inner.update_idletasks(); _fit(); inner.update_idletasks(); _fit()
        except tk.TclError:
            MC.swallowed()
    app._info_refit=_refit
    for w in (cv,inner,app._info_title,app._info_stats,app._reopen_bar,app._tag_text): _bind_wheel(w)
    return info

def open_console_mirror(path):
    """Open the Output-pane mirror file for writing (line-buffered), first moving last
    session's copy to <name>.prev.log. Returns the file object, or None (logged) if the
    folder isn't writable."""
    try:
        if os.path.isfile(path):
            os.replace(path,os.path.splitext(path)[0]+".prev.log")
    except OSError:
        LOG.warning("could not keep the previous %s",path,exc_info=True)
    try:
        return open(path,"w",encoding="utf-8",buffering=1)
    except OSError:
        LOG.error("could not open %s; the Output pane is not mirrored this session",path,exc_info=True)
        return None

def read_shared_paks():
    """The shared pak list, or None when neither program has written one yet."""
    try:
        with open(PAKS_SHARED,encoding="utf-8") as f: v=json.load(f)
        ps=v.get("pk3s") if isinstance(v,dict) else None
        return [p for p in ps if isinstance(p,str)] if isinstance(ps,list) else None
    except Exception: MC.swallowed(); return None
def write_shared_paks(paths):
    """Save the shared pak list (atomic write, .bak kept). Returns True on success; a
    failure is logged (the other program just won't follow this change)."""
    try:
        MC.atomic_write_json(PAKS_SHARED,{"pk3s":list(paths)},backup=True)
        return True
    except (OSError,ValueError,TypeError):
        LOG.error("could not save the shared pak list %s",PAKS_SHARED,exc_info=True)
        return False

_runtime_ready=False
def init_runtime(app_name="mohaa_launcher"):
    """One-time start-up for a launcher process: create the output folder, start logging
    and the crash hooks, point WebView2 at its data folder and migrate an old flat config.

    app_name: log file stem (output/logs/<app_name>.log). Idempotent. Returns the log path.
    Kept out of module import so mohaa_map_launcher can import this module freely."""
    global _runtime_ready
    if _runtime_ready: return MC.setup_logging(app_name)
    try:
        MC.ensure_dir(DATADIR)
    except OSError as e:
        if sys.stderr is not None: sys.stderr.write("[ERROR] can't create %s: %s\n"%(DATADIR,e))
    logpath=MC.setup_logging(app_name)
    MC.install_crash_hooks(app_name)
    LOG.info("=== %s %s starting (Python %s, %s) ===",app_name,VERSION,sys.version.split()[0],sys.platform)
    if _MTX_ERR: LOG.error("textures disabled: %s",_MTX_ERR)
    # The embedded pane's WebView2 needs a folder for its browser files. tkwebview2 leaves it
    # unset, so WebView2 would create "pythonw.exe.WebView2" beside Python, which fails in a
    # read-only install such as C:\Program Files and leaves the pane blank. The environment
    # variable overrides that default (Microsoft's documented WEBVIEW2_USER_DATA_FOLDER).
    if sys.platform.startswith("win"):
        os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER",os.path.join(DATADIR,"webview2"))
    # Copy the config from the old flat location (HERE) on first run.
    if not os.path.exists(CONFIG):
        _old=os.path.join(HERE,"mohaa_viewer_config.json")
        if os.path.isfile(_old):
            try:
                shutil.copy2(_old,CONFIG); LOG.info("migrated %s -> %s",_old,CONFIG)
            except OSError:
                LOG.error("could not migrate the old config %s",_old,exc_info=True)
    _runtime_ready=True
    return logpath

# ============================================================================
#  Version + update channel
#  VERSION is shown in the status bar, the About box and the update window. The
#  updater reads docs/version.txt on the repo's main branch; if it names a newer
#  version, it downloads that version's release tag (v<version>) and refreshes bin/,
#  docs/ and the RUN .bat. On each release, bump VERSION here and in docs/version.txt,
#  then tag the release commit v<version>.
# ============================================================================
VERSION="1.0.003"
VERSION_LABEL="version "+VERSION
# GitHub coordinates for the update check. If GitHub can't be reached, the check
# reports it and changes nothing on disk.
GITHUB_OWNER="searingwolfe"
GITHUB_REPO="mohaa-model-viewer"
GITHUB_BRANCH="main"
UPDATE_UA="MOHAA-Model-Viewer/"+VERSION
# Version marker, release-tag zip, branch zip (codeload is where github.com/.../archive
# redirects), and the project page linked from the update window. The tag zip installs
# exactly the version the check reported; the branch zip is the fallback when that version
# was never tagged.
UPDATE_VERSION_URL=f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/docs/version.txt"
UPDATE_TAG_FMT="v{version}"
UPDATE_TAG_ZIP_URL=f"https://codeload.github.com/{GITHUB_OWNER}/{GITHUB_REPO}/zip/refs/tags/{{tag}}"
UPDATE_ZIP_URL=f"https://codeload.github.com/{GITHUB_OWNER}/{GITHUB_REPO}/zip/refs/heads/{GITHUB_BRANCH}"
UPDATE_PAGE_URL=f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
# Largest update zip accepted, and top-level folders an update never writes into (the
# user's data and the vendored packages).
UPDATE_MAX_BYTES=200*1024*1024
UPDATE_SKIP_DIRS={"output","libs","libs-linux","libs-mac",".git","__pycache__"}
# Files earlier versions shipped that the current one replaces: an update backs them up
# with the files it replaces (output/previous-versions/<n>/) and then removes them, once
# everything else is in place. The four RUN launchers became one per system,
# "MOH Model-Map Viewer (Windows x86-x64).bat" / "(Linux - Mac OS).sh", with a menu for the
# program (for a while named "RUN -- Medal of Honor Viewer").
UPDATE_RETIRED=("RUN -- Medal of Honor Model Viewer.bat","RUN -- Medal of Honor Map Viewer.bat",
                "RUN -- Medal of Honor Model Viewer.sh","RUN -- Medal of Honor Map Viewer.sh",
                "RUN -- Medal of Honor Viewer.bat","RUN -- Medal of Honor Viewer.sh")
# The restart helper run after an update whose files were locked: waits for each staged
# <file>.new to move into place (up to 2 minutes), then starts the launcher again.
UPDATE_FINISHER_SRC=r"""import json, os, subprocess, sys, time
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
def log(msg):
    try:
        with open(cfg["log"], "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass
pending = list(cfg["staged"])
deadline = time.time() + 120
while pending and time.time() < deadline:
    for d in list(pending):
        try:
            os.replace(d + ".new", d); pending.remove(d); log("installed " + d)
        except OSError as e:
            last = e
    if pending:
        time.sleep(0.5)
for d in pending:
    log("FAILED to install " + d + " (still locked); the new copy is " + d + ".new")
flags = {"creationflags": 0x08000000} if sys.platform.startswith("win") else {}
try:
    subprocess.Popen([cfg["exe"], cfg["launcher"]], **flags); log("restarted " + cfg["launcher"])
except OSError as e:
    log("FAILED to restart: %s" % e)
for p in (sys.argv[1], os.path.abspath(__file__)):
    try:
        os.remove(p)
    except OSError:
        pass
"""

def _install_root():
    """Folder the updater refreshes: the parent of bin/ (where the RUN .bat lives) in the
    shipped layout, else HERE for a flat install."""
    return os.path.dirname(HERE) if os.path.basename(HERE).lower()=="bin" else HERE

def find_python():
    """Interpreter for child mohaa_view.py builds: sys.executable first.

    A PATH lookup could pick a different Python without Pillow (models would silently
    render untextured), and on Windows a bare program name searches the current directory
    before PATH, so a planted py.exe could run instead. pythonw.exe is fine here because
    the build's output is captured."""
    exe=sys.executable
    if exe and os.path.isfile(exe): return exe
    for name in ("py","python","python3"):        # frozen/embedded host with no sys.executable
        p=shutil.which(name)
        if not p: continue
        try:
            if subprocess.run([p,"--version"],capture_output=True,**NOWIN).returncode==0: return p
        except OSError: MC.swallowed()
    return None

def _virtual_screen(w):
    """(x0,y0,x1,y1) of the whole desktop across all monitors. On Windows, Tk's
    winfo_screenwidth/height cover only the primary monitor, which would push popups back
    onto it. Uses SM_X/Y/CX/CYVIRTUALSCREEN (76-79)."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            u=ctypes.windll.user32
            x0=u.GetSystemMetrics(76); y0=u.GetSystemMetrics(77)
            return (x0,y0,x0+u.GetSystemMetrics(78),y0+u.GetSystemMetrics(79))
        except Exception: MC.swallowed()
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
        except Exception: MC.swallowed()
        ux[136]()
    except Exception: MC.swallowed()

# The keys both viewers' cameras hold, as Windows virtual-key codes: W A S D Q E C Z, Space, the
# arrows, Shift and Ctrl, and comma / period (the Map Viewer's Radiant-look strafe). See
# App._watch_camera_stop.
CAMERA_VKS=tuple(ord(c) for c in "WASDQECZ")+(0x20,0x25,0x26,0x27,0x28,0x10,0x11,0xBC,0xBE)

def _win_key_reader():
    """A function telling whether a virtual key is held down right now, read from the keyboard
    itself (GetAsyncKeyState), whichever window has the keyboard. None off Windows."""
    if not sys.platform.startswith("win"): return None
    try:
        import ctypes
        gaks=ctypes.windll.user32.GetAsyncKeyState
        gaks.argtypes=[ctypes.c_int]; gaks.restype=ctypes.c_short
        return lambda vk:bool(gaks(vk)&0x8000)
    except Exception: MC.swallowed(); return None
KEY_IS_DOWN=_win_key_reader()

def apply_theme(root, name):
    """(Re)apply the named palette to every ttk style. tk widgets that hold raw
    colours are refreshed by App._retheme_widgets() afterwards."""
    set_palette(name)
    root.configure(bg=BG); st=ttk.Style(root)
    try: st.theme_use("clam")
    except Exception: MC.swallowed()
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
    st.configure("Info.Tool.TButton",padding=(4,1),font=FONT_SMALL)   # the details pane's buttons
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

# True: popups (tooltips, drop-downs, context menus) use the OS-default look and native
# tk.Menu. False (default): custom themed windows that follow dark/light mode, including
# the border that native Windows menus always draw white.
OLD_POPUPS=False

def _add_popup_shadow(win):
    """Soft drop shadow behind a borderless popup: a 30% black Toplevel offset +3+3 that
    is destroyed with the popup. Skipped where per-window alpha isn't supported."""
    sh=None
    try:
        win.update_idletasks()
        sh=tk.Toplevel(win); sh.wm_overrideredirect(True)
        sh.configure(bg="#000000")
        sh.attributes("-alpha",0.30)
        try: sh.attributes("-topmost",True)
        except Exception: MC.swallowed()
        sh.wm_geometry(f"{win.winfo_width()}x{win.winfo_height()}"
                       f"+{win.winfo_rootx()+3}+{win.winfo_rooty()+3}")
        win.lift(sh)                     # popup above its own shadow
        win._shadow=sh
        def _cleanup(e,s=sh,w=win):
            if e.widget is w:
                try: s.destroy()
                except Exception: MC.swallowed()
        win.bind("<Destroy>",_cleanup,add="+")
    except Exception:
        MC.swallowed()
        try:
            if sh is not None: sh.destroy()
        except Exception: MC.swallowed()

def _tip_window(master,text,x,y,wrap=360):
    """One shared look for every floating popup: a borderless Toplevel with a 1px
    LINE-coloured border and the theme's tip colours - or the OS-default white +
    system font when 'Use old popup windows' is on."""
    tip=tk.Toplevel(master); tip.wm_overrideredirect(True); tip.wm_geometry(f"+{x}+{y}")
    try: tip.attributes("-topmost",True)
    except Exception: MC.swallowed()
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
        except Exception: MC.swallowed()
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
            except Exception: MC.swallowed()
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
            except Exception: MC.swallowed()
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
                except Exception: MC.swallowed()
            n=n.child
        return False
    def unpost_child(self):
        if self.child:
            self.child.unpost(); self.child=None
    def unpost(self):
        self.unpost_child()
        if self.top:
            try: self.top.destroy()
            except Exception: MC.swallowed()
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
            except Exception: MC.swallowed()
            self._id=None
    def _show(self):
        if self.tip or not self.text: return
        try:
            x=self.w.winfo_rootx()+12; y=self.w.winfo_rooty()+self.w.winfo_height()+6
            self.tip=_tip_window(self.w,self.text,x,y,wrap=340)
        except Exception:
            MC.swallowed()
            self.tip=None
    def _hide(self,_e=None):
        self._cancel()
        if self.tip:
            try: self.tip.destroy()
            except Exception: MC.swallowed()
            self.tip=None

# ------------------------------------------------------- keyboard shortcuts ---
# Rows for the shortcut tables, in the format of VIEWER_KEYS in mohaa_view.py (see the
# notes above it there): a heading carries its category (and view) to the rows below it.
def _kx_sub(title,cat,view=None):
    d={"sub":title,"c":cat}
    if view: d["v"]=view
    return d

def _kx(keys,text,*binds):
    """A shortcut row: the keys as the list shows them, what they do, and the
    (chord, keycap label[, what this key does]) of each key it covers."""
    return {"k":keys,"d":text,"b":[list(b) for b in binds]}

# The launcher's own shortcuts: the "Launcher" tab of the F1 window (its "3D viewer" tab
# shows VIEWER_KEYS from mohaa_view.py). Keep in step with _bind_hotkeys and the tree's
# bindings in _build_ui.
KEYS_LAUNCHER={
 "title":"Launcher keyboard shortcuts",
 "cols":[
  {"title":"Launcher","rows":[
   _kx_sub("Anywhere in the launcher","app"),
   _kx("Ctrl+O","add .pk3 pak(s)",("Ctrl+O","add paks")),
   _kx("Ctrl+Shift+O","open a loose .skd / .tik file",("Ctrl+Shift+O","open file")),
   _kx("Ctrl+F","focus the search box",("Ctrl+F","search")),
   _kx("Esc","clear the search / close a menu / cancel loading",("Esc","cancel")),
   _kx("F5","reload all loaded paks",("F5","reload")),
   _kx("Ctrl+T","dark / light theme",("Ctrl+T","theme")),
   _kx("Ctrl+Shift+T","old (OS-default) popup windows on / off",("Ctrl+Shift+T","old pop")),
   _kx("F1","this window",("F1","keys","the keyboard shortcuts (this window)")),
   _kx("right-click","on the Output console or the details panel: copy menu",
       ("RClick","copy","copy menu (Output console, details panel)")),
  ]},
  {"title":"Pak tree","rows":[
   _kx_sub("In the pak tree","tree"),
   _kx("Enter","open the file / go into the folder",("Enter","open")),
   _kx("Backspace","go up one folder",("Backspace","up")),
   _kx("Right|Left","expand / collapse the folder",("Right","expand","expand the folder"),("Left","collapse","collapse the folder")),
   _kx("Up|Down","move the selection",("Up","up","select the row above"),("Down","down","select the row below")),
   _kx("double-click",".skd / .tik opens in the viewer",("DblClick","open")),
   _kx("Ctrl+click|Shift+click","select several files / folders (Enter or right-click builds them all)",
       ("Ctrl+Click","select +","add a file / folder to the selection"),("Shift+Click","range","select a range of files / folders")),
   _kx("right-click","pak menu: view / remove loaded paks",("RClick","menu","pak menu (view / remove loaded paks)")),
   _kx("drag","a file off the window: open it in its own viewer window",
       ("Drag","drag out","drag a file off the window: open it in its own viewer window")),
  ]},
 ]}

class KeyMapWindow:
    """Help > Keyboard shortcuts (F1): a keyboard and a mouse with every shortcut coloured
    by what it does, and the same shortcuts as a list underneath, in columns that scroll on
    their own. Its tabs switch between the 3D viewer's keys and the launcher's own. The
    viewer pages' H window (KEYS_JS in mohaa_view.py) is the same thing in HTML, drawn from
    the same tables: KX_LAYOUT and KX_CATS, VIEWER_KEYS / MAP_VIEWER_KEYS, KEYS_LAUNCHER.

    Hovering a key (or pressing it) lists everything it does with every modifier; Shift,
    Ctrl and Alt, clicked or held, show their layer of the keyboard; hovering a row of the
    list rings its keys, and clicking a key finds its rows. Keys pressed here are only
    looked up, never acted on; Esc or F1 closes the window."""
    BIT = {"Shift": 1, "Ctrl": 2, "Alt": 4}
    MPART = {"Click": "L", "DblClick": "L", "Drag": "L", "RClick": "R", "RDrag": "R",
             "MClick": "M", "MDrag": "M", "Wheel": "M"}
    MNAME = {"Click": "click", "DblClick": "double-click", "Drag": "drag", "RClick": "right-click",
             "RDrag": "right-drag", "MClick": "middle-click", "MDrag": "middle-drag", "Wheel": "wheel"}
    MORDER = ("Click", "DblClick", "Drag", "RClick", "RDrag", "MClick", "MDrag", "Wheel")
    MWORDS = {"click", "double-click", "drag", "right-click", "right-drag", "middle-click",
              "middle-drag", "wheel", "type"}
    SEPS = {"…", "–", "or", "then"}
    PART_NAME = {"L": "Left mouse button", "R": "Right mouse button", "M": "Mouse wheel and middle button"}
    # Tk key names -> the keyboard's key ids (a shifted symbol is the key it's on)
    KEYSYM = {"Escape": "Esc", "BackSpace": "Backspace", "Tab": "Tab", "ISO_Left_Tab": "Tab",
              "Caps_Lock": "Caps", "Return": "Enter", "KP_Enter": "Enter", "space": "Space",
              "Shift_L": "Shift", "Shift_R": "Shift", "Control_L": "Ctrl", "Control_R": "Ctrl",
              "Alt_L": "Alt", "Alt_R": "Alt", "Meta_L": "Alt", "Meta_R": "Alt", "Super_L": "Win",
              "Super_R": "Win", "Win_L": "Win", "Win_R": "Win", "App": "Menu", "Menu": "Menu",
              "Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right", "Insert": "Ins",
              "Delete": "Del", "Home": "Home", "End": "End", "Prior": "PgUp", "Next": "PgDn",
              "Print": "PrtSc", "Scroll_Lock": "ScrLk", "Pause": "Pause",
              "grave": "`", "asciitilde": "`", "minus": "-", "underscore": "-", "equal": "=", "plus": "=",
              "bracketleft": "[", "braceleft": "[", "bracketright": "]", "braceright": "]",
              "backslash": "\\", "bar": "\\", "semicolon": ";", "colon": ";", "apostrophe": "'",
              "quotedbl": "'", "comma": ",", "less": ",", "period": ".", "greater": ".", "slash": "/",
              "question": "/", "exclam": "1", "at": "2", "numbersign": "3", "dollar": "4",
              "percent": "5", "asciicircum": "6", "ampersand": "7", "asterisk": "8",
              "parenleft": "9", "parenright": "0"}

    def __init__(self, app, tabs, cats, layout, tab=0, on_tab=None):
        import tkinter.font as _tkfont
        self.app, self.tabs, self.layout, self.on_tab = app, tabs, layout, on_tab
        self.catd = {c["id"]: c for c in cats}
        self.old = OLD_POPUPS
        self.light = self.old or getattr(app, "_theme", "dark") == "light"
        self.latch = self.held = 0
        self.q = ""; self.cat = None
        self.hot = self.ring = self.ring_cat = self.tmp_l = self.tmp_v = None
        self.view = None; self.views = []; self.pop = None; self.hot_row = None
        self._jobs = {}; self._capfit = {}
        if self.old:                            # "Use old popup windows": the system's colours
            probe = tk.Frame(app); bg = probe.cget("bg"); probe.destroy()
            self.C = dict(panel=bg, line="#a0a0a0", txt="#000000", dim="#5a5a5a", btn="#ffffff",
                          accent="#0060c0", on="#cce4ff", tip="#ffffe1", entry="#ffffff", hov="#e5f1fb")
        else:
            self.C = dict(panel=PANEL, line=LINE, txt=TXT, dim=DIM, btn=BTN_BG, accent=ACCENT,
                          on=BTN_HOV, tip=TIP_BG, entry=ENTRY_BG, hov=SEL_BG)
        sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
        self.U = U = max(26, min(40, (sw - 140) // 23))     # one key, in pixels
        fam = FONT_SMALL[0]
        px = lambda f: -max(8, int(round(U * f)))
        self.f_name, self.f_name0 = (fam, px(0.27), "bold"), (fam, px(0.27))
        self.f_cap, self.f_mark, self.f_ml = (fam, px(0.24)), (fam, -max(7, int(round(U * 0.19)))), (fam, px(0.25))
        self.f_row = self.f_chip = (fam, 9)
        self.f_chip_i = (fam, 9, "italic")
        self.f_bold, self.f_head, self.f_head_b = (fam, 10, "bold"), (fam, 8), (fam, 9, "bold")
        self._fm = _tkfont.Font(font=self.f_chip)
        self._fm_i = _tkfont.Font(font=self.f_chip_i)
        # keycap labels shrink a size or three to fit their key before they are cut short
        self._capfonts = [((fam, -n), _tkfont.Font(font=(fam, -n))) for n in range(-self.f_cap[1], 6, -1)][:4]
        self.W = max(23 * U + 28, min(sw - 80, 1200))         # window width
        self.colh = max(170, min(sh - 90, 900) - int(6.25 * U) - 150)
        self._build()
        self._fit_width()
        self._set_tab(max(0, min(tab, len(tabs) - 1)))
        self._place(sw, sh)

    # ---- colours and small helpers ------------------------------------------------------
    def _mix(self, c1, c2, a):
        try:
            r1, g1, b1 = (v // 257 for v in self.app.winfo_rgb(c1))
            r2, g2, b2 = (v // 257 for v in self.app.winfo_rgb(c2))
        except Exception:
            MC.swallowed()
            return c1
        return "#%02x%02x%02x" % (round(r1 * a + r2 * (1 - a)), round(g1 * a + g2 * (1 - a)), round(b1 * a + b2 * (1 - a)))

    def _ccol(self, c):
        x = self.catd.get(c)
        return (x["light"] if self.light else x["dark"]) if x else self.C["dim"]

    def _vname(self, v):
        return next((x["name"] for x in self.views if x["id"] == v), v)

    def _only(self, v):
        return any(x["id"] == v and x.get("only") for x in self.views)

    def _applies(self, b, v):
        return v is None or (b["v"] == v if b["v"] else not self._only(v))

    def _layer(self):
        return self.tmp_l if self.tmp_l is not None else (self.latch | self.held)

    def _cur_view(self):
        return self.tmp_v or self.view

    def _row_ok(self, R):
        return (not self.cat or R["c"] == self.cat) and (not self.q or self.q in R["text"])

    @staticmethod
    def _mabbr(m):
        return ("C" if m & 2 else "") + ("A" if m & 4 else "") + ("S" if m & 1 else "")

    def _after(self, name, ms, fn):
        j = self._jobs.pop(name, None)
        if j:
            try: self.w.after_cancel(j)
            except Exception: MC.swallowed()
        if fn is not None:
            def run():
                self._jobs.pop(name, None)
                try: fn()
                except tk.TclError: pass        # the window was closed meanwhile
            self._jobs[name] = self.w.after(ms, run)

    def _rr(self, x0, y0, x1, y1, r, **kw):
        """A rounded rectangle on the keyboard canvas."""
        p = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
             x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.cv.create_polygon(p, smooth=True, **kw)

    def _seg(self, parent, text, cmd):
        """A flat toggle button (the tabs, views and Shift / Ctrl / Alt)."""
        C = self.C
        b = tk.Label(parent, text=text, bg=C["btn"], fg=C["txt"], font=self.f_chip, padx=8, pady=2, bd=0,
                     highlightthickness=1, highlightbackground=C["line"], cursor="hand2")
        b.pack(side="left")
        b._on = False
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=C["on"]))
        b.bind("<Leave>", lambda e: b.configure(bg=C["on"] if b._on else C["btn"]))
        return b

    def _seg_set(self, b, on):
        C = self.C
        b._on = bool(on)
        b.configure(bg=C["on"] if on else C["btn"], fg=C["accent"] if on else C["txt"],
                    highlightbackground=C["accent"] if on else C["line"])

    def _chip(self, parent, text, col, bg=None):
        C = self.C
        return tk.Label(parent, text=text, bg=C["btn"], fg=C["txt"], padx=4, pady=0, bd=0,
                        font=self.f_chip_i if text in self.MWORDS else self.f_chip,
                        highlightthickness=1, highlightbackground=self._mix(col, C["line"], 0.6),
                        highlightcolor=self._mix(col, C["line"], 0.6))

    def _units(self, k):
        """A row's key text as ("sep", text) and ("chord", [keys]) pieces."""
        out = []
        for t in k.split(" "):
            if not t:
                continue
            if t in self.SEPS:
                out.append(("sep", t)); continue
            for j, a in enumerate(t.split("|")):
                if j:
                    out.append(("sep", "/"))
                out.append(("chord", a.split("+")))
        return out

    def _chips(self, parent, units, col, width, bg):
        """The keys of a row as chips, wrapped onto lines no wider than `width`."""
        C = self.C
        line, used = None, width + 1
        for kind, val in units:
            if kind == "sep":
                need = self._fm.measure(val) + 6
            else:
                need = sum((self._fm_i if p in self.MWORDS else self._fm).measure(p) + 12 for p in val) \
                    + (len(val) - 1) * (self._fm.measure("+") + 2)
            if line is None or used + need > width:
                line = tk.Frame(parent, bg=bg); line.pack(side="top", anchor="w", pady=1); used = 0
            u = tk.Frame(line, bg=bg); u.pack(side="left", padx=(0, 3))
            if kind == "sep":
                tk.Label(u, text=val, bg=bg, fg=C["dim"], font=self.f_chip).pack(side="left")
            else:
                for j, p in enumerate(val):
                    if j:
                        tk.Label(u, text="+", bg=bg, fg=C["dim"], font=self.f_chip).pack(side="left")
                    self._chip(u, self.MNAME.get(p, p), col).pack(side="left")
            used += need + 3

    # ---- the window --------------------------------------------------------------------
    def _build(self):
        C, U, app = self.C, self.U, self.app
        w = self.w = tk.Toplevel(app); w.title("Keyboard shortcuts")
        w.withdraw()                            # built out of sight, shown where it belongs (_place)
        w.transient(app); w.resizable(False, False); w.configure(bg=C["panel"])
        lab = lambda p, t: tk.Label(p, text=t, bg=C["panel"], fg=C["dim"], font=self.f_chip)
        top = self.top = tk.Frame(w, bg=C["panel"]); top.pack(side="top", fill="x", padx=12, pady=(10, 4))
        tf = tk.Frame(top, bg=C["panel"]); tf.pack(side="left")
        self.tab_btns = [self._seg(tf, t[0], lambda i=i: self._set_tab(i)) for i, t in enumerate(self.tabs)]
        self.title_l = tk.Label(top, text="", bg=C["panel"], fg=C["accent"], font=self.f_bold)
        self.title_l.pack(side="left", padx=(12, 0))
        tk.Frame(top, bg=C["panel"]).pack(side="left", fill="x", expand=True)
        self.view_lab = lab(top, "keys in"); self.view_lab.pack(side="left", padx=(8, 4))
        self.viewf = tk.Frame(top, bg=C["panel"]); self.viewf.pack(side="left")
        self.mod_lab = lab(top, "with"); self.mod_lab.pack(side="left", padx=(10, 4))
        mf = tk.Frame(top, bg=C["panel"]); mf.pack(side="left")
        self.mod_btns = {n: self._seg(mf, n, lambda n=n: self._toggle_mod(self.BIT[n])) for n in ("Shift", "Ctrl", "Alt")}
        lab(top, "search").pack(side="left", padx=(12, 4))
        self.qvar = tk.StringVar()
        self.search = tk.Entry(top, textvariable=self.qvar, width=18, font=self.f_chip, relief="flat",
                               bg=C["entry"], fg=C["txt"], insertbackground=C["txt"],
                               highlightthickness=1, highlightbackground=C["line"], highlightcolor=C["accent"])
        self.search.pack(side="left", ipady=2)
        self.qvar.trace_add("write", lambda *a: self._on_search())
        # keyboard and mouse
        self.pad = p = 6
        self.cv = tk.Canvas(w, width=23 * U + 2 * p, height=int(6.25 * U) + 2 * p, bg=C["panel"],
                            highlightthickness=0, bd=0)
        self.cv.pack(side="top", pady=(4, 2))
        self.cv.bind("<Button-1>", lambda e: self.cv.focus_set(), add="+")   # keys are looked up again
        self._draw_keyboard()
        # category chips, the list, Close
        self.catf = tk.Frame(w, bg=C["panel"]); self.catf.pack(side="top", fill="x", padx=12, pady=(2, 4))
        self.rule = tk.Frame(w, bg=C["line"], height=1); self.rule.pack(side="top", fill="x", padx=12)
        bot = tk.Frame(w, bg=C["panel"]); bot.pack(side="bottom", fill="x", padx=12, pady=(6, 10))
        if self.old:
            self.close_btn = tk.Button(bot, text="Close", command=self.close, takefocus=0)
        else:
            self.close_btn = ttk.Button(bot, text="Close", command=self.close, cursor="hand2", takefocus=0)
        self.close_btn.pack(side="left")
        self.colsf = tk.Frame(w, bg=C["panel"], width=self.W - 24)
        self.colsf.pack(side="top", fill="both", expand=True, padx=12, pady=(6, 0))
        # keys pressed here are looked up (and never reach the launcher's own shortcuts)
        w.bind("<KeyPress>", self._on_key)
        w.bind("<KeyRelease>", self._on_key_up)
        w.bind("<FocusOut>", self._focus_out)         # a modifier let go elsewhere never comes back
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            w.bind(seq, self._wheel)
        w.protocol("WM_DELETE_WINDOW", self.close)

    def _place(self, sw, sh):
        w, app = self.w, self.app
        try:
            w.update_idletasks()
            x = app.winfo_rootx() + (app.winfo_width() - w.winfo_reqwidth()) // 2
            y = app.winfo_rooty() + (app.winfo_height() - w.winfo_reqheight()) // 2
            x0, y0, x1, y1 = _virtual_screen(w)
            x = max(x0, min(x, x1 - w.winfo_reqwidth())); y = max(y0, min(y, y1 - w.winfo_reqheight() - 40))
            w.geometry(f"+{x}+{y}")
        except Exception:
            MC.swallowed()
        w.deiconify()
        if not self.old:
            try: app._apply_titlebar(w)
            except Exception: MC.swallowed()
        try: w.grab_set()
        except Exception: MC.swallowed()
        self.cv.focus_set()

    def close(self):
        for n in list(self._jobs):
            self._after(n, 0, None)
        try: self.w.grab_release()
        except Exception: MC.swallowed()
        try: self.w.destroy()
        except Exception: MC.swallowed()
        if getattr(self.app, "_keymap", None) is self:
            self.app._keymap = None

    # ---- keyboard and mouse ------------------------------------------------------------
    def _hook(self, K):
        cv = self.cv
        cv.tag_bind(K["tag"], "<Enter>", lambda e, K=K: self._hover(K))
        cv.tag_bind(K["tag"], "<Leave>", lambda e, K=K: self._unhover(K))
        cv.tag_bind(K["tag"], "<Button-1>", lambda e, K=K: self._click_key(K))

    def _draw_keyboard(self):
        C, U, p, cv = self.C, self.U, self.pad, self.cv
        self.KEYS = []
        for i, (kid, lab, x, y, wd) in enumerate(self.layout):
            x0, y0, ww, tag = p + x * U, p + y * U, wd * U, "k%d" % i
            K = dict(id=kid, lab=lab, ids=[kid], bit=self.BIT.get(kid, 0), tag=tag, cx=x0 + ww / 2, w=ww, mouse=False)
            K["body"] = self._rr(x0 + 2, y0 + 2, x0 + ww - 2, y0 + U - 2, 6, fill=C["btn"], outline=C["line"], tags=(tag,))
            K["ring"] = self._rr(x0 + 1, y0 + 1, x0 + ww - 1, y0 + U - 1, 7, fill="", outline="", width=3, tags=(tag,))
            K["name"] = cv.create_text(x0 + 7, y0 + 5, text=lab, anchor="nw", fill=C["dim"], font=self.f_name0, tags=(tag,))
            K["cap"] = cv.create_text(x0 + ww / 2, y0 + U - 6, text="", anchor="s", fill=C["txt"], font=self.f_cap, tags=(tag,))
            K["mark"] = cv.create_text(x0 + ww - 5, y0 + 3, text="", anchor="ne", justify="right", fill=C["dim"],
                                       font=self.f_mark, tags=(tag,))
            self._hook(K); self.KEYS.append(K)
        mx, my, mw, mh = p + 19.9 * U, p + 2, 1.9 * U, 2.95 * U
        mc, split = mx + mw / 2, my + 1.15 * U
        self._rr(mx, my, mx + mw, my + mh, mw / 2, fill=C["btn"], outline=C["line"], width=1.5)
        self.PARTS = []
        r = mw * 0.5
        shapes = {"L": [mc - 1, my + 1, mc - 1, my + 1, mc - 1, split, mc - 1, split, mx + 1, split, mx + 1, split,
                        mx + 1, my + r, mx + 1, my + 1, mc - 1, my + 1],
                  "R": [mc + 1, my + 1, mc + 1, my + 1, mc + 1, split, mc + 1, split, mx + mw - 1, split,
                        mx + mw - 1, split, mx + mw - 1, my + r, mx + mw - 1, my + 1, mc + 1, my + 1]}
        for pid in ("L", "R", "M"):
            tag = "m" + pid
            if pid == "M":
                body = self._rr(mc - 7, my + 12, mc + 7, my + 42, 6, fill=C["btn"], outline=C["line"], width=1.5, tags=(tag,))
            else:
                body = cv.create_polygon(shapes[pid], smooth=True, fill=C["btn"], outline=C["line"], width=1.5, tags=(tag,))
            K = dict(id=pid, lab=self.PART_NAME[pid], ids=[k for k in self.MORDER if self.MPART[k] == pid], bit=0,
                     tag=tag, cx=mc + (-mw / 4 if pid == "L" else mw / 4 if pid == "R" else 0), mouse=True, body=body)
            self._hook(K); self.PARTS.append(K)
        cv.tag_raise("mM")
        self.ml_x, self.ml_y = p + 18.95 * U, my + mh + 12
        self.ml_items = []

    def _lit(self, ids, L, V, filt):
        here, ok = [], []
        for i in ids:
            for b in self.BYKEY.get(i, ()):
                if b["m"] == L and self._applies(b, V):
                    here.append(b)
                    if not filt or self._row_ok(b["row"]):
                        ok.append(b)
        return here, ok

    def _fit_cap(self, s, width):
        """(text, font) for a keycap label: the largest size that fits, else cut short."""
        key = (s, width)
        if key not in self._capfit:
            room = width - 5
            for spec, fnt in self._capfonts:
                if fnt.measure(s) <= room:
                    self._capfit[key] = (s, spec)
                    break
            else:
                spec, fnt = self._capfonts[-1]
                t = s
                while len(t) > 1 and fnt.measure(t + "…") > room:
                    t = t[:-1]
                self._capfit[key] = (t + "…", spec)
        return self._capfit[key]

    def _paint(self):
        C, cv = self.C, self.cv
        L, V, filt = self._layer(), self._cur_view(), bool(self.q or self.cat)
        ring, rc = self.ring, self.ring_cat
        dim_off, dim_free = self._mix(C["dim"], C["panel"], 0.45), self._mix(C["dim"], C["panel"], 0.7)
        for K in self.KEYS:
            here, ok = self._lit(K["ids"], L, V, filt)
            b0 = ok[0] if ok else None
            held = bool(K["bit"] and (L & K["bit"]))
            ringed = bool(ring and any(i in ring for i in K["ids"])) or bool(rc and any(b["c"] == rc for b in ok))
            if held:
                fill, out, ow, nf, nfont = C["on"], C["accent"], 2, C["accent"], self.f_name
            elif b0:
                col = self._ccol(b0["c"])
                fill, out, ow, nf, nfont = self._mix(col, C["btn"], 0.3), col, 1.5, C["txt"], self.f_name
            else:
                fill, out, ow, nfont = C["btn"], C["line"], 1, self.f_name0
                nf = dim_off if here else dim_free
            cv.itemconfigure(K["body"], fill=fill, outline=out, width=ow)
            cv.itemconfigure(K["name"], fill=nf, font=nfont)
            if b0 and not held:
                t, f = self._fit_cap(b0["cap"], K["w"])
                cv.itemconfigure(K["cap"], text=t, font=f)
            else:
                cv.itemconfigure(K["cap"], text="")
            if ringed:
                cv.itemconfigure(K["ring"], outline=C["txt"], width=3)
            elif self.hot is K:
                cv.itemconfigure(K["ring"], outline=C["accent"], width=2)
            else:
                cv.itemconfigure(K["ring"], outline="")
            # the other modifiers this key works with, one to a line in the top-right corner
            oth = [self._mabbr(m) for m in sorted({b["m"] for b in self.BYKEY.get(K["id"], ())
                                                   if b["m"] and b["m"] != L and self._applies(b, V)})]
            cv.itemconfigure(K["mark"], text="\n".join(oth if len(oth) < 3 else [oth[0], " ".join(oth[1:])]))
        for K in self.PARTS:
            here, ok = self._lit(K["ids"], L, V, filt)
            b0 = ok[0] if ok else None
            ringed = bool(ring and any(i in ring for i in K["ids"])) or bool(rc and any(b["c"] == rc for b in ok))
            col = self._ccol(b0["c"]) if b0 else None
            cv.itemconfigure(K["body"], fill=self._mix(col, C["btn"], 0.3) if col else C["btn"],
                             outline=C["txt"] if ringed else C["accent"] if self.hot is K else (col or C["line"]),
                             width=3 if ringed else 2 if self.hot is K else 1.5)
        # what each mouse action does in this layer, under the mouse
        for i in self.ml_items:
            cv.delete(i)
        self.ml_items = []
        lines = [b for k in self.MORDER for b in self.BYKEY.get(k, ())
                 if b["m"] == L and self._applies(b, V) and (not filt or self._row_ok(b["row"]))]
        lh = max(12, int(self.U * 0.38))
        for n, b in enumerate(lines[:6 if len(lines) > 7 else 7]):
            y = self.ml_y + n * lh
            self.ml_items.append(cv.create_text(self.ml_x, y, text=self.MNAME[b["k"]], anchor="nw", fill=C["dim"], font=self.f_ml))
            self.ml_items.append(cv.create_text(self.ml_x + 2.05 * self.U, y, text=b["cap"], anchor="nw", fill=C["txt"], font=self.f_ml))
        if len(lines) > 7:
            self.ml_items.append(cv.create_text(self.ml_x, self.ml_y + 6 * lh, text="+%d more (hover the mouse)" % (len(lines) - 6),
                                                anchor="nw", fill=C["dim"], font=self.f_ml))
        for n, b in self.mod_btns.items():
            self._seg_set(b, (self.latch | self.held) & self.BIT[n])
        for v, b in getattr(self, "view_btns", {}).items():
            self._seg_set(b, self.view == v)

    # ---- one tab (a table) ----------------------------------------------------------------
    def _set_tab(self, i):
        self._hide_pop()
        self._load_tab(i)
        if self.on_tab:
            try: self.on_tab(i)
            except Exception: MC.swallowed()
        self._build_cols()
        self._refresh()

    def _fit_width(self):
        """One window size for every tab: the window is as wide as the widest head row any
        tab has (its title and view buttons, or its category chips and hint) and the columns
        fill that width, so switching tabs never resizes it. The rule under the chips is set
        to that width, which holds the window to it."""
        need = 0
        for i in range(len(self.tabs)):
            self._load_tab(i)
            self.w.update_idletasks()
            need = max(need, self.top.winfo_reqwidth(), self.catf.winfo_reqwidth())
        self.W = max(self.W, need + 24)
        self.rule.configure(width=self.W - 24)

    def _load_tab(self, i):
        """Tab i's shortcuts, filed by row and by key, and its head row: the title, the view
        buttons and the category chips."""
        self.tab = i
        for j, b in enumerate(self.tab_btns):
            self._seg_set(b, j == i)
        T = self.tabs[i][1]
        self.views = T.get("views") or []
        self.view = T.get("default") or (self.views[0]["id"] if self.views else None)
        self.latch = self.held = 0; self.cat = None; self.hot = self.ring = self.ring_cat = None
        self.tmp_l = self.tmp_v = None; self.hot_row = None
        self.title_l.configure(text=T.get("title", ""))
        self.ROWS, self.BYKEY, self.COLS = [], {}, []
        if self.qvar.get():
            self.qvar.set("")                  # (nothing to filter yet)
        self.q = ""
        # every binding, filed by key
        for col in T.get("cols", []):
            cat = view = None; sub = ""; items = []
            for r in col.get("rows", []):
                if "sub" in r:
                    cat, view, sub = r.get("c") or cat, r.get("v"), r["sub"]
                    items.append({"sub": r["sub"], "c": cat, "v": view}); continue
                R = {"k": r["k"], "d": r["d"], "c": r.get("c") or cat, "v": r.get("v") or view, "binds": []}
                for b in r.get("b", []):
                    parts = b[0].split("+")
                    m = 0
                    for x in parts[:-1]:
                        m |= self.BIT.get(x, 0)
                    B = {"ch": b[0], "k": parts[-1], "m": m, "cap": b[1] if len(b) > 1 else "",
                         "d": b[2] if len(b) > 2 else r["d"], "c": R["c"], "v": R["v"], "row": R}
                    R["binds"].append(B); self.BYKEY.setdefault(B["k"], []).append(B)
                R["text"] = " ".join([sub, self._vname(R["v"]) if R["v"] else "", r["k"], r["d"]] +
                                     ["%s %s %s" % (b["ch"], b["cap"], b["d"]) for b in R["binds"]]).lower()
                items.append(R); self.ROWS.append(R)
            self.COLS.append({"title": col.get("title", ""), "items": items})
        # views
        for ch in self.viewf.winfo_children():
            ch.destroy()
        self.view_btns = {v["id"]: self._seg(self.viewf, v["name"], lambda v=v["id"]: self._set_view(v)) for v in self.views}
        if self.views:
            self.view_lab.configure(text="keys in"); self.mod_lab.configure(text="with")
        else:
            self.view_lab.configure(text=""); self.mod_lab.configure(text="keys with")
        self._build_cats()

    def _set_view(self, v):
        self.view = v; self._refresh()

    def _toggle_mod(self, bit):
        self.latch ^= bit; self._paint()

    def _build_cats(self):
        C = self.C
        for ch in self.catf.winfo_children():
            ch.destroy()
        self.chip_w = {}
        used = []
        for R in self.ROWS:
            if R["c"] and R["c"] not in used:
                used.append(R["c"])
        for c in used:
            f = tk.Frame(self.catf, bg=C["panel"], highlightthickness=1, highlightbackground=C["panel"], cursor="hand2")
            f.pack(side="left", padx=(0, 8))
            dot = tk.Label(f, text="●", bg=C["panel"], fg=self._ccol(c), font=self.f_chip)
            dot.pack(side="left", padx=(4, 2))
            nm = tk.Label(f, text=self.catd.get(c, {}).get("name", c), bg=C["panel"], fg=C["dim"], font=self.f_chip)
            nm.pack(side="left", padx=(0, 4))
            for wdg in (f, dot, nm):
                wdg.bind("<Button-1>", lambda e, c=c: self._set_cat(c))
                wdg.bind("<Enter>", lambda e, c=c: self._ring_cat(c))
                wdg.bind("<Leave>", lambda e: self._ring_cat(None))
            self.chip_w[c] = (f, nm)
        # a tab may carry its own hint as a third item: (name, table, hint)
        tab = self.tabs[self.tab]
        tip = tab[2] if len(tab) > 2 and tab[2] else \
            "hover or press a key to see all it does · hover a row to find its keys"
        tk.Label(self.catf, text=tip, bg=C["panel"], fg=C["dim"], font=self.f_chip).pack(side="right")

    def _set_cat(self, c):
        self.cat = None if self.cat == c else c
        self._refresh()

    def _ring_cat(self, c):
        self.ring_cat = c
        self._paint()

    def _build_cols(self):
        C = self.C
        for ch in self.colsf.winfo_children():
            ch.destroy()
        n = max(1, len(self.COLS)); gap = 14
        # The columns sit in grid columns 0, 2, 4 ... with a fixed gap between each two, so
        # they share the width exactly. The last tab's settings are cleared first: a column
        # it had beyond this tab's would keep its share of the width, empty.
        for ci in range(self.colsf.grid_size()[0]):
            self.colsf.grid_columnconfigure(ci, weight=0, uniform="", minsize=0)
        colw = (self.W - 24 - gap * (n - 1)) // n
        self.keys_w = max(110, min(150, colw * 2 // 5))
        desc_w = max(120, colw - self.keys_w - 34)
        self.colw = []
        for ci, col in enumerate(self.COLS):
            cf = tk.Frame(self.colsf, bg=C["panel"])
            cf.grid(row=0, column=2 * ci, sticky="nsew")
            self.colsf.grid_columnconfigure(2 * ci, weight=1, uniform="kxcol")
            if ci:
                self.colsf.grid_columnconfigure(2 * ci - 1, minsize=gap)
            tk.Label(cf, text=col["title"].upper(), bg=C["panel"], fg=C["accent"], font=self.f_head_b, anchor="w"
                     ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 3))
            # the scrollbar's room is kept while it is hidden, so a column is as wide either way
            sb = (tk.Scrollbar(cf) if self.old else ttk.Scrollbar(cf, orient="vertical"))
            sbw = sb.winfo_reqwidth() + 2
            cv = tk.Canvas(cf, highlightthickness=0, bd=0, bg=C["panel"], width=colw - sbw, height=self.colh, yscrollincrement=20)
            sb.configure(command=cv.yview); cv.configure(yscrollcommand=sb.set)
            cv.grid(row=1, column=0, sticky="nsew"); sb.grid(row=1, column=1, sticky="ns", padx=(2, 0))
            cf.grid_rowconfigure(1, weight=1); cf.grid_columnconfigure(0, weight=1); cf.grid_columnconfigure(1, minsize=sbw)
            inner = tk.Frame(cv, bg=C["panel"])
            win = cv.create_window((0, 0), window=inner, anchor="nw", width=colw - sbw)
            r = 0
            for it in col["items"]:
                if "sub" in it:
                    hf = tk.Frame(inner, bg=C["panel"]); hf.grid(row=r, column=0, sticky="we", pady=(9, 3)); r += 1
                    if it["v"]:                 # the view tag first, so a long heading wraps beside it
                        tk.Label(hf, text=self._vname(it["v"]), bg=C["panel"], fg=C["dim"], font=self.f_head, padx=3,
                                 highlightthickness=1, highlightbackground=C["line"]).pack(side="right", anchor="n", padx=(6, 4))
                    tk.Label(hf, text="●", bg=C["panel"], fg=self._ccol(it["c"]), font=self.f_head).pack(side="left", anchor="n")
                    tk.Label(hf, text=it["sub"].upper(), bg=C["panel"], fg=C["dim"], font=self.f_head, justify="left",
                             anchor="w", wraplength=max(120, colw - (150 if it["v"] else 50))).pack(side="left", padx=(4, 0))
                    it["el"] = hf; it["seps"] = []
                    continue
                sep = tk.Frame(inner, bg=C["line"], height=1); sep.grid(row=r, column=0, sticky="we"); r += 1
                rf = tk.Frame(inner, bg=C["panel"]); rf.grid(row=r, column=0, sticky="we"); r += 1
                rf.grid_columnconfigure(0, minsize=self.keys_w)
                kf = tk.Frame(rf, bg=C["panel"]); kf.grid(row=0, column=0, sticky="nw", padx=(3, 6), pady=4)
                self._chips(kf, self._units(it["k"]), self._ccol(it["c"]), self.keys_w - 9, C["panel"])
                tk.Label(rf, text=it["d"], bg=C["panel"], fg=C["txt"], font=self.f_row, justify="left", anchor="w",
                         wraplength=desc_w).grid(row=0, column=1, sticky="nw", pady=5)
                it["el"], it["sep"] = rf, sep
                self._hook_row(it, rf)
            inner.grid_columnconfigure(0, weight=1)
            none = tk.Label(inner, text="Nothing in this column matches.", bg=C["panel"], fg=C["dim"], font=self.f_row)
            none.grid(row=r, column=0, sticky="w", pady=8)
            col.update(cv=cv, sb=sb, inner=inner, frame=cf, none=none, win=win)

            def _fit(e=None, col=col):
                cv_, inner_ = col["cv"], col["inner"]
                cv_.configure(scrollregion=(0, 0, inner_.winfo_reqwidth(), inner_.winfo_reqheight()))
                if cv_.winfo_height() + 1 >= inner_.winfo_reqheight():
                    col["sb"].grid_remove(); cv_.yview_moveto(0)
                else:
                    col["sb"].grid()
            inner.bind("<Configure>", _fit); cv.bind("<Configure>", _fit)

    def _descendants(self, wdg):
        out = [wdg]
        for ch in wdg.winfo_children():
            out.extend(self._descendants(ch))
        return out

    def _hook_row(self, it, rf):
        def enter(_e=None):
            self._after("row", 0, None)
            if self.hot_row is not it:
                self._row_hover(it)

        def leave(_e=None):
            self._after("row", 50, check)

        def check():
            try:
                wdg = self.w.winfo_containing(self.w.winfo_pointerx(), self.w.winfo_pointery())
            except Exception:
                MC.swallowed()
                wdg = None
            while wdg is not None and wdg is not rf:
                wdg = getattr(wdg, "master", None)
            if wdg is None and self.hot_row is it:
                self._row_hover(None)
        for wdg in self._descendants(rf):
            wdg.bind("<Enter>", enter, add="+"); wdg.bind("<Leave>", leave, add="+")

    def _row_bg(self, it, bg):
        C = self.C
        for wdg in self._descendants(it["el"]):
            try:
                if wdg.cget("bg") in (C["panel"], C["hov"], C["on"]):
                    wdg.configure(bg=bg)
            except Exception:
                MC.swallowed()

    def _row_hover(self, R):
        if self.hot_row is not None and self.hot_row is not R:
            self._row_bg(self.hot_row, self.C["panel"])
        self.hot_row = R
        if R is None:
            self.ring = None; self.tmp_l = self.tmp_v = None
            self._paint(); return
        self._row_bg(R, self.C["hov"])
        self.ring = {b["k"] for b in R["binds"]}
        self.tmp_l = R["binds"][0]["m"] if R["binds"] else None
        # a row for keys that work in another view shows that view while it is hovered
        if R["v"] and R["v"] != self.view:
            self.tmp_v = R["v"]
        elif not R["v"] and self._only(self.view):
            self.tmp_v = next((v["id"] for v in self.views if not v.get("only")), None)
        else:
            self.tmp_v = None
        self._paint()

    def _refresh(self):
        V = self.view
        for col in self.COLS:
            head, seen, shown = None, False, 0
            groups = []
            for it in col["items"]:
                if "sub" in it:
                    head = it; groups.append([it]); seen = False; continue
                if not groups:
                    groups.append([None])
                groups[-1].append(it)
            for g in groups:
                head, rows = g[0], g[1:]
                seen = False
                for it in rows:
                    ok = self._row_ok(it)
                    if ok:
                        it["el"].grid()
                        (it["sep"].grid() if seen else it["sep"].grid_remove())
                        seen = True; shown += 1
                        here = it["v"] == V if it["v"] else not self._only(V)
                        self._dim_row(it, not here)
                    else:
                        it["el"].grid_remove(); it["sep"].grid_remove()
                if head is not None:
                    (head["el"].grid() if seen else head["el"].grid_remove())
            (col["none"].grid_remove() if shown else col["none"].grid())
        for c, (f, nm) in getattr(self, "chip_w", {}).items():
            on = self.cat == c
            f.configure(highlightbackground=self._ccol(c) if on else self.C["panel"])
            nm.configure(fg=self.C["txt"] if on else self.C["dim"])
        self._paint()

    def _dim_row(self, it, na):
        if it.get("na") == na:
            return
        it["na"] = na
        C = self.C
        fg = self._mix(C["txt"], C["panel"], 0.5) if na else C["txt"]
        for wdg in self._descendants(it["el"]):
            if isinstance(wdg, tk.Label):
                try:
                    cur = wdg.cget("fg")
                    if cur in (C["txt"], self._mix(C["txt"], C["panel"], 0.5)):
                        wdg.configure(fg=fg)
                except Exception:
                    MC.swallowed()

    def _on_search(self):
        self.q = self.qvar.get().strip().lower()
        if hasattr(self, "COLS"):
            self._refresh()

    # ---- details of one key (or mouse button), under the keyboard ------------------------
    def _hide_pop(self):
        if self.pop is not None:
            try: self.pop.destroy()
            except Exception: MC.swallowed()
            self.pop = None

    def _show_pop(self, K):
        self._hide_pop()
        C = self.C
        lst = [b for i in K["ids"] for b in self.BYKEY.get(i, ())]
        lst.sort(key=lambda b: (b["m"], K["ids"].index(b["k"])))
        f = tk.Frame(self.w, bg=C["tip"], highlightthickness=1, highlightbackground=C["accent"], bd=0)
        name = K["lab"] if K["mouse"] or K["lab"] == K["id"] else K["id"] + " " + K["lab"]
        hd = tk.Frame(f, bg=C["tip"]); hd.grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 3))
        tk.Label(hd, text=name, bg=C["tip"], fg=C["accent"], font=self.f_bold).pack(side="left")
        if lst:
            tk.Label(hd, text="%d shortcut%s" % (len(lst), "s" if len(lst) > 1 else ""), bg=C["tip"], fg=C["dim"],
                     font=self.f_row).pack(side="left", padx=(6, 0))
        V = self._cur_view()
        r = 1
        for b in lst:
            fg = C["txt"] if self._applies(b, V) else self._mix(C["dim"], C["tip"], 0.7)
            u = tk.Frame(f, bg=C["tip"]); u.grid(row=r, column=0, sticky="w", padx=(8, 8), pady=1)
            self._chips(u, [("chord", b["ch"].split("+"))], self._ccol(b["c"]), 400, C["tip"])
            tk.Label(f, text=b["d"], bg=C["tip"], fg=fg, font=self.f_row, justify="left", anchor="w",
                     wraplength=330).grid(row=r, column=1, sticky="w", pady=1)
            if b["v"]:
                tk.Label(f, text=self._vname(b["v"]), bg=C["tip"], fg=C["dim"], font=self.f_head, padx=3,
                         highlightthickness=1, highlightbackground=C["line"]).grid(row=r, column=2, sticky="w", padx=(6, 8))
            r += 1
        note = ("Click it, or hold it, to see the %s+ shortcuts on the keyboard." % K["id"]) if K["bit"] else \
            ("" if lst else "Not used.")
        if note:
            tk.Label(f, text=note, bg=C["tip"], fg=C["dim"], font=self.f_row).grid(row=r, column=0, columnspan=3,
                                                                                  sticky="w", padx=8, pady=(2, 0))
            r += 1
        tk.Frame(f, bg=C["tip"], height=5).grid(row=r, column=0)
        f.update_idletasks()
        pw, ph = f.winfo_reqwidth(), f.winfo_reqheight()
        ww, wh = self.w.winfo_width(), self.w.winfo_height()
        x = int(self.cv.winfo_x() + K["cx"] - pw / 2)
        x = max(6, min(x, ww - pw - 6))
        y = self.cv.winfo_y() + self.cv.winfo_height() + 2
        if y + ph > wh - 4:
            y = max(4, wh - ph - 4)
        f.place(x=x, y=y); f.lift()
        self.pop = f

    def _hover(self, K):
        self._after("unhover", 0, None)
        if self.hot_row is not None:          # the pointer has left the list for the keyboard
            self._after("row", 0, None); self._row_hover(None)
        if self.hot is K and self.pop is not None:
            return
        self.hot = K; self._paint(); self._show_pop(K)

    def _unhover(self, K):
        def go():
            if self.hot is K:
                self.hot = None; self._paint(); self._hide_pop()
        self._after("unhover", 60, go)

    def _click_key(self, K):
        if K["bit"]:
            self._toggle_mod(K["bit"]); self._show_pop(K); return
        L, V = self._layer(), self._cur_view()
        rows = []
        for i in K["ids"]:
            for b in self.BYKEY.get(i, ()):
                if b["m"] == L and self._applies(b, V) and b["row"] not in rows:
                    rows.append(b["row"])
        self._flash_rows(rows)

    def _flash_rows(self, rows):
        """Bring each row into view in its column and light it up for a moment."""
        C, seen = self.C, set()
        for R in rows:
            el = R.get("el")
            if el is None or not el.winfo_ismapped() and not self._row_ok(R):
                continue
            col = next((c for c in self.COLS if R in c["items"]), None)
            if col is None:
                continue
            if id(col) not in seen:
                seen.add(id(col))
                try:
                    col["inner"].update_idletasks()
                    y, h = el.winfo_y(), max(1, col["inner"].winfo_reqheight())
                    top = col["cv"].canvasy(0); vis = col["cv"].winfo_height()
                    if y < top + 4 or y + el.winfo_height() > top + vis - 4:
                        col["cv"].yview_moveto(max(0.0, (y - 30) / h))
                except Exception:
                    MC.swallowed()
            self._row_bg(R, C["on"])
            self._after("flash%d" % id(R), 900, lambda R=R: self._row_bg(R, C["hov"] if self.hot_row is R else C["panel"]))

    def _press(self, K):
        C = self.C
        self.cv.itemconfigure(K["body"], fill=self._mix(C["txt"], C["btn"], 0.25))
        self._after("press", 180, self._paint)

    # ---- keys pressed in the window are looked up --------------------------------------
    @staticmethod
    def _mods(state):
        alt = state & (0x20000 if sys.platform.startswith("win") else 0x8)
        return (1 if state & 0x1 else 0) | (2 if state & 0x4 else 0) | (4 if alt else 0)

    def _key_id(self, keysym):
        if len(keysym) == 1 and keysym.isalnum():
            return keysym.upper()
        if keysym.startswith("F") and keysym[1:].isdigit():
            return keysym
        return self.KEYSYM.get(keysym)

    def _on_key(self, e):
        ks = e.keysym
        if e.widget is self.search:
            if ks == "Escape":
                if self.qvar.get():
                    self.qvar.set("")
                else:
                    self.close()
            elif ks == "F1":
                self.close()
            return "break"                       # typing still works; the launcher's keys don't fire
        mods = self._mods(e.state)
        if ks in ("Escape", "F1"):
            self.close(); return "break"
        if ks.lower() == "f" and mods & 2:
            self.search.focus_set(); self.search.select_range(0, "end"); return "break"
        kid = self._key_id(ks)
        if kid in self.BIT:
            self.held = mods | self.BIT[kid]; self._paint(); return "break"
        self.held = mods
        K = next((k for k in self.KEYS if k["id"] == kid), None)
        if K is not None:
            self._after("unhover", 0, None)
            self.hot = K; self._paint(); self._show_pop(K); self._press(K)
            self._click_key(K)
        else:
            self._paint()
        return "break"

    def _on_key_up(self, e):
        kid = self._key_id(e.keysym)
        if kid in self.BIT:
            self.held = self._mods(e.state) & ~self.BIT[kid]; self._paint()
        return "break"

    def _focus_out(self, _e=None):
        if self.held:
            self.held = 0
            try: self._paint()
            except tk.TclError: pass

    def _wheel(self, e):
        """The column under the mouse pointer scrolls, whichever widget has the focus."""
        try:
            wdg = self.w.winfo_containing(e.x_root, e.y_root)
        except Exception:
            MC.swallowed()
            wdg = None
        while wdg is not None and not any(wdg is c.get("frame") for c in self.COLS):
            wdg = getattr(wdg, "master", None)
        for c in self.COLS:
            if wdg is c.get("frame") and c["cv"].winfo_height() < c["inner"].winfo_reqheight():
                up = getattr(e, "delta", 0) > 0 or getattr(e, "num", 0) == 4
                c["cv"].yview_scroll(-3 if up else 3, "units")
                return "break"

class App(tk.Tk):
    def __init__(self, initial_file=None):
        init_runtime("mohaa_launcher")
        super().__init__()
        init_fonts()          # families() needs a live root; picks a real mono per-OS
        self.title("MOHAA Model Viewer")
        self.geometry("1380x820"); self.minsize(1000,600)
        self._config_path=CONFIG
        self._cfg=self._load_config(); self._pyexe=find_python()
        self._attach_busy=set()      # attachment keys currently building (see _build_attach)
        self._attach_lock=threading.Lock()   # one attachment build at a time (_build_attach_work)
        self._attach_parts=[]        # extra skelmodel parts (head/hands/hat) for the build
        self._theme=self._cfg.get("theme","dark")
        if self._theme not in THEMES: self._theme="dark"
        apply_theme(self,self._theme)
        self.configure(bg=BG)
        self._log_q=queue.Queue(); self._drop_paths=[]
        self._status_base="Ready"; self._pak_suffix=""    # status-bar left cell = "<state>  --  N pak(s)"
        self._upd_state=None; self._upd_dl_btn=None        # Check-for-updates window state
        # Mirror every Output-pane line to output_console.log in DATADIR (the previous
        # session's copy is kept as output_console.prev.log), line-buffered so a crash still
        # leaves it. The full, timestamped record is output/logs/mohaa_launcher.log.
        self._logfile=open_console_mirror(os.path.join(DATADIR,"output_console.log"))
        self._startup_extras()       # the RUN window's text, "saved <file>" lines, window-open signal
        self._pk3_paths=[]; self._tmp=None; self._animroot=None
        self._vfs=None; self._SH=None; self._TI=None; self._GS=None; self._PROPS=None; self._ED=None; self._tex_ready=False; self._tex_gen=0
        self._tree_entry={}
        self._all_files=[]           # (relpath, kind) kind in {"skd","tik"} from the last pak scan
        self._filter_after=None
        self._tips=[]                # Tooltip instances (colours are read at show time)
        self._auto_open=tk.BooleanVar(value=bool(self._cfg.get("auto_open",True)))
        self._remember=tk.BooleanVar(value=bool(self._cfg.get("remember_paks",True)))
        # Viewer renderer (View > Viewer renderer): "gl" (default) or "2d".
        self._renderer_var=tk.StringVar(value=("2d" if self._cfg.get("renderer")=="2d" else "gl"))
        self._outdir_on=tk.BooleanVar(value=bool(self._cfg.get("outdir_enabled",True)))
        self._outdir=self._cfg.get("outdir") or os.path.join(DATADIR,"models")
        self._run_opts={}          # one-shot per-build viewer options (right-click open)
        self._last_build=None      # (path,animroot,manifest,emittex,subdir) of the last build
        self._last_info=None       # (path,stdout,html_path) of the last info render, re-run on theme toggle
        self._last_subdir=None     # pak-relative output subfolder of the last build
        self._reuse_html=tk.BooleanVar(value=bool(self._cfg.get("reuse_html",True)))
        self._no_recent=tk.BooleanVar(value=bool(self._cfg.get("no_recent",False)))
        # Embedded WebView2 pane, created lazily on first open so a broken install can't block
        # startup (failures fall back to the browser).
        self._embed_on=tk.BooleanVar(value=bool(self._cfg.get("embed_viewer",True)))
        # Animation catalogue: every animation the model can reach through $include / $path /
        # includes{}. anim_preload caps how many of the .tik's own animations are baked into
        # the page; the rest are built on first click into a cache folder beside the HTML.
        self._anim_preload=tk.StringVar(value=str(self._cfg.get("anim_preload",150)))
        self._animcat=None          # the catalogue dict for the model now on screen
        self._animcat_file=None     # ...written out as JSON for mohaa_view.py
        self._animcat_for=None      # ...and the model path it belongs to
        self._anim_outdir=None      # <html stem>/ - where built animations are cached
        self._anim_busy=set()       # ids currently building, so a double-click is one build
        self._webview=None; self._embed_url=None
        # External programs: text editor (platform default) and legacy model viewer (unset).
        # Seed an absolute path: _launch_with only runs existing files at absolute paths (no
        # PATH or current-directory lookup), so a bare "notepad.exe" would fail. A bare name is
        # kept only if nothing resolves.
        _te=(self._cfg.get("text_editor") or "").strip()
        if (not _te) or (os.path.basename(_te)==_te and not os.path.isfile(_te)):
            self._cfg["text_editor"]=(self._default_program_path("text_editor") or _te or
                                      ("notepad.exe" if sys.platform.startswith("win")
                                       else ("open" if sys.platform=="darwin" else "xdg-open")))
        self._menus=[]; self._menubtns=[]      # themed menubar parts, recoloured on toggle
        self._treetip=None; self._treetip_row=None       # armed-hover tree tooltip
        self._treetip_after=None; self._treetip_armed=None
        global OLD_POPUPS
        self._old_popups=tk.BooleanVar(value=bool(self._cfg.get("old_popups",False)))
        OLD_POPUPS=bool(self._old_popups.get())
        self._open_popup=None; self._popup_owner=None; self._popup_serial=None
        self._batch=[]; self._batch_total=0; self._batch_waiting=False   # sequential folder builds
        # Escape-to-cancel state: the running viewer subprocess, the model being built, and a
        # build generation counter that worker threads check so they can bail out on cancel.
        self._proc=None; self._building_name=None; self._build_gen=0
        # True while a build that will open the viewer is running; further open requests are
        # rejected until it clears so click-spam can't stack builds. Build-only work
        # (right-click "Build only", batch builds) ignores it.
        self._opening_view=False
        # A pak open requested before the texture/VFS index is ready; _poll_log fires it once
        # the index finishes. Stored as (entry, build_gen) so an Escape-cancel drops it.
        self._pending_open=None
        # Clicking outside an open custom popup closes it.
        self.bind_all("<ButtonPress-1>",self._popup_dismiss_check,add="+")
        self.bind_all("<ButtonPress-3>",self._popup_dismiss_check,add="+")
        # Clicking any launcher widget takes the keyboard back from the embedded WebView2 (see
        # _reclaim_focus). Clicks inside the viewer pane never reach Tk, so the viewer keeps
        # its hotkeys there.
        self.bind_all("<ButtonPress-1>",self._reclaim_focus,add="+")
        self.bind_all("<ButtonPress-3>",self._reclaim_focus,add="+")
        # ...and stops the viewer's camera, which a key or button let go here would keep
        # moving (see _watch_camera_stop).
        self._watch_camera_stop()
        # Moving or minimizing the window closes tooltips and popups that would otherwise be
        # left at stale screen positions (see _dismiss_transients).
        self.bind("<Configure>",self._dismiss_transients,add="+")
        self.bind("<Unmap>",self._dismiss_transients,add="+")
        # PopupMenus are topmost Toplevels, so close them when the app loses focus; otherwise
        # they stay painted over other applications.
        self.bind("<FocusOut>",self._popup_focus_out,add="+")
        _win_dark_menus(self._theme=="dark")
        self._build_menu(); self._build_ui(); self._bind_hotkeys(); self._poll_log()
        self._show_startup_notices()
        self.after(150,self._enable_win_drop)
        self.after(250,self._apply_titlebar)
        self.protocol("WM_DELETE_WINDOW",self._on_close)
        # The paks both programs share, else this program's own (and the old single-pk3 key)
        saved=read_shared_paks()
        if saved is None:
            saved=self._cfg.get("pk3s")
            if not saved and self._cfg.get("pk3"): saved=[self._cfg["pk3"]]
        saved=[p for p in (saved or []) if os.path.exists(p)]
        if saved and self._remember.get(): self.after(200,lambda:self._add_pk3s(saved))
        self._paks_watch()
        if initial_file: self.after(350,lambda:self._load(initial_file))

    # ------------------------------------------------------------- config ---
    def _load_config(self, path=None):
        """This program's settings as a dict ({} on first run).

        A damaged file is repaired (hand-typed backslash paths), restored from its .bak, or
        set aside as .corrupt-<date>; what happened is kept in self._cfg_notice and shown in
        the Output pane once the window is up (see mohaa_common.load_settings)."""
        cfg,notice=MC.load_settings(path or CONFIG)
        self._cfg_notice=notice
        return cfg
    @staticmethod
    def _norm_angle(x):
        """Fold one placement angle into [0,360), rounded to the viewer's 3 decimals. Whole
        degrees become ints so the config and #ang= hash read "90", not "90.0". Callers reject
        NaN/inf first."""
        x=float(x)%360.0
        x=round(x,3)
        return int(x) if float(x).is_integer() else x

    def _set_view_angles(self,raw):
        """Save the viewer's pitch/yaw/roll placement dial to the config.

        The viewer posts "mohaa-ang <pitch>,<yaw>,<roll>" when the dial changes; _open_file
        passes the saved triple back through the page's #ang= hash so the next model opens with
        the same rotation. Any angle is kept (the dial's pencil editor accepts arbitrary values).
        An unchanged triple is ignored so dragging doesn't rewrite the config on every detent."""
        try: v=[float(x) for x in str(raw).split(",")[:3]]
        except Exception: MC.swallowed(); return
        if len(v)!=3: return
        # Reject NaN/inf: they survive the modulo, and json would write a bare NaN that strict
        # JSON readers (including the browser) reject.
        if not all(-1e9<x<1e9 for x in v): return
        v=[self._norm_angle(x) for x in v]
        if self._cfg.get("view_angles")==v: return
        self._cfg["view_angles"]=v; self._save_config()

    def view_angles(self):
        """The saved (pitch,yaw,roll) triple, or None when the model sits unrotated."""
        v=self._cfg.get("view_angles")
        if not (isinstance(v,(list,tuple)) and len(v)==3): return None
        try:
            v=[float(x) for x in v]
            if not all(-1e9<x<1e9 for x in v): return None
            v=[self._norm_angle(x) for x in v]
        except Exception: MC.swallowed(); return None
        return v if any(v) else None

    def _save_config(self, path=None):
        """Write the settings atomically, keeping the previous file as .bak.

        Returns True on success. A failure is logged with its traceback and reported in the
        Output pane (the setting then only lasts for this session)."""
        path=path or CONFIG
        try:
            MC.atomic_write_json(path,self._cfg,backup=True)
            return True
        except (OSError,ValueError,TypeError) as e:
            LOG.error("could not save settings %s",path,exc_info=True)
            if getattr(self,"_log_q",None) is not None:
                self._log_q.put(("err",f"Could not save settings ({os.path.basename(path)}): {e}"))
            return False

    def _reset_settings(self):
        """Options --> Reset settings...: forget every remembered choice (paks, recent files,
        folders, theme, programs) after a confirmation, keeping the old file as .bak, and
        restart the program so it starts like a first run."""
        path=getattr(self,"_config_path",CONFIG)
        if not messagebox.askyesno("Reset settings",
                "Forget every saved setting (recent files, output folder, theme, external "
                "programs) and the loaded-pak list both viewers share, and restart?\n\n"
                "The current files are kept as .bak copies beside them.",parent=self):
            return
        try:
            for p in (path,PAKS_SHARED):
                MC.make_backup(p)
                if os.path.exists(p): os.remove(p)
        except OSError as e:
            LOG.error("reset settings failed for %s",path,exc_info=True)
            self._log_line(f"Could not reset settings: {e}","err"); return
        LOG.warning("settings reset by the user (%s)",path)
        self._cfg={}
        self._restart_program()

    def _show_startup_notices(self):
        """Put start-up problems in the Output pane: a repaired / lost settings file, a
        missing or too-old Pillow, a texture module that failed to import."""
        n=getattr(self,"_cfg_notice",None)
        if n: self._log_line(n,"err")
        ok,why=MC.pil_status()
        if not ok: self._log_line("Textures disabled: "+why,"err")
        if _MTX_ERR: self._log_line("Textures disabled: mohaa_textures.py failed to load ("+_MTX_ERR+")","err")

    def report_callback_exception(self, exc, val, tb):
        """Tk calls this for an exception escaping any button, menu, key or timer callback.
        The default prints to stderr, which pythonw doesn't have, so the error vanished. Here
        it is logged with its traceback and shown in red in the Output pane."""
        LOG.critical("error in a window callback: %s: %s",exc.__name__,val,exc_info=(exc,val,tb))
        try:
            self._log_line(f"Internal error: {exc.__name__}: {val}  (details: {MC.logs_dir()})","err")
        except Exception:
            MC.swallowed()

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
        # Custom themed menubar: Tk can't recolour the native Windows menu bar, so File/Options/
        # View/Help are Menubuttons whose drop-downs are themed PopupMenus (or native tk.Menus
        # when "Use old popup windows" is on).
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
        # "Close file" mirrors the viewer's Esc: _close_viewer() returns the middle pane to the
        # start page but keeps _last_build, so "Open Viewer" can reopen the model instantly.
        # Only enabled while the embedded pane exists.
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
        return [{"type":"check","label":"Remember loaded paks between sessions","variable":self._remember,"command":self._save_opts},
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
                _mi("Open Legacy Model Viewer folder",lambda:self._open_program_folder("legacy_viewer","Legacy Model Viewer")),
                _MSEP,
                _mi("Open log folder",self._open_log_folder),
                _mi("Reset settings...",self._reset_settings)]

    def _menu_items_view(self):
        return [_mi("Expand all folders",lambda:self._expand_all(True)),
                _mi("Collapse all folders",lambda:self._expand_all(False)),
                _MSEP,
                _mi("Toggle Dark / Light",self._toggle_theme,"Ctrl+T"),
                {"type":"check","label":"Use old popup windows","variable":self._old_popups,
                 "command":self._toggle_old_popups,"accel":"Ctrl+Shift+T"},
                _MSEP,
                {"type":"cascade","label":"Viewer renderer","items":lambda:[
                    {"type":"radio","label":"WebGL (default)","variable":self._renderer_var,"value":"gl",
                     "command":lambda:self._set_renderer("gl")},
                    {"type":"radio","label":"2D canvas","variable":self._renderer_var,"value":"2d",
                     "command":lambda:self._set_renderer("2d")}]}]

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
        """Close every transient overlay (popup menu, tree tooltip, hover tooltips) when the
        window is moved or minimized. <Configure> events from child widgets are ignored, so
        in-window resizing (sash drags) is unaffected."""
        if e is not None and getattr(e,"widget",None) not in (self,None): return
        try:
            if self._open_popup is not None: self._open_popup.unpost()
        except Exception: MC.swallowed()
        try: self._hide_treetip()
        except Exception: MC.swallowed()
        for t in getattr(self,"_tips",()):
            try: t._hide()
            except Exception: MC.swallowed()

    def _popup_focus_out(self,_e=None):
        """Close menus/tooltips when the launcher loses focus to another application.

        <FocusOut> also fires for focus moves inside the app (child widgets, the WebView2 pane,
        popups), so check one tick later: focus_displayof() is None only when no window of this
        app has focus."""
        if self._open_popup is None and not getattr(self,"_tips",None): return
        def _check():
            try:
                if self.focus_displayof() is not None: return   # still inside the launcher
            except Exception: MC.swallowed(); return                            # unknown -> leave it alone
            self._dismiss_transients()
        try: self.after(60,_check)
        except Exception: MC.swallowed()

    # ---- housekeeping: built output + %TEMP% workspaces -----------------------
    @staticmethod
    def _dir_size(path):
        n=0
        for dp,_dn,fn in os.walk(path):
            for f in fn:
                try: n+=os.path.getsize(os.path.join(dp,f))
                except OSError: MC.swallowed()
        return n

    @staticmethod
    def _fmt_bytes(n):
        f=float(n)
        for u in ("B","KB","MB"):
            if f<1024.0: return ("%d %s"%(int(f),u)) if u=="B" else ("%.1f %s"%(f,u))
            f/=1024.0
        return "%.2f GB"%f

    # Safety guard for "Clear built models" (a recursive, unrecoverable delete): refuse
    # roots, the home folder and common system/user folders even if the output folder was
    # pointed at one, and require the folder to be named 'models' or 'standalone'.
    def _unsafe_to_wipe(self, d):
        try: d=os.path.abspath(d)
        except Exception: MC.swallowed(); return "unresolvable path"
        parent,leaf=os.path.split(d.rstrip(os.sep))
        if not leaf: return "a drive/filesystem root"
        if os.path.dirname(d.rstrip(os.sep))==d.rstrip(os.sep): return "a drive/filesystem root"
        home=os.path.abspath(os.path.expanduser("~"))
        if os.path.normcase(d)==os.path.normcase(home): return "your home folder"
        for name in ("desktop","documents","downloads","pictures","music","videos",
                     "onedrive","dropbox","program files","program files (x86)","windows",
                     "system32","users","applications","library","etc","usr","bin","var"):
            if os.path.normcase(leaf)==os.path.normcase(name): return "a system/user folder (%s)"%leaf
        # Only folders this program creates have these names.
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
            except Exception: MC.swallowed()
        return roots

    def _built_scan(self):
        """Everything this launcher built, and nothing else: '<stem>_skd_view.html' /
        '<stem>_tik_view.html' pages (_viewer_html_name) and their matching '<stem>_..._view/'
        animation-cache folders (_anim_outdir). Other files in the output folder are left
        alone. Returns (files, dirs, total_bytes)."""
        files=[]; dirs=[]; nb=0
        for root in self._built_roots():
            for dp,dn,fn in os.walk(root):
                for f in fn:
                    if f.lower().endswith("_view.html"):
                        fp=os.path.join(dp,f); files.append(fp)
                        try: nb+=os.path.getsize(fp)
                        except OSError: MC.swallowed()
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
        """All %TEMP%/mohaaview_* workspaces created by _reload_all, including leftovers from
        earlier or crashed sessions."""
        try: base=tempfile.gettempdir()
        except Exception: MC.swallowed(); return []
        out=[]
        try:
            for d in sorted(glob.glob(os.path.join(glob.escape(base),"mohaaview_*"))):
                if os.path.isdir(d): out.append(d)
        except Exception: MC.swallowed()
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
        # The builds are gone: forget the last build and clear the path bar so neither points
        # at a deleted page.
        self._last_build=None
        try: self._path_var.set("")
        except Exception: MC.swallowed()
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
        """This program's own __pycache__ beside the scripts (HERE), only if it holds one of our
        modules. Cleared along with the temp files for a clean reinstall state; Python
        regenerates it on the next run."""
        pc=os.path.join(HERE,"__pycache__")
        if not os.path.isdir(pc): return None
        try: names=os.listdir(pc)
        except OSError: MC.swallowed(); return None
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
                    MC.swallowed()
                    self._tmp=None; self._animroot=None
            n+=1
        pn=0
        if pyc:
            shutil.rmtree(pyc,ignore_errors=True)
            if not os.path.isdir(pyc): pn=1
        self._log_line("Cleared %%temp%% files: %d workspace folder(s)%s, %s freed."
                       % (n,(" + __pycache__" if pn else ""),self._fmt_bytes(nb)),"ok")

    def _window_zoomed(self):
        """Whether the window is maximized (Windows / macOS "zoomed", X11 -zoomed)."""
        try:
            if self.state()=="zoomed": return True
        except tk.TclError: MC.swallowed()
        try: return bool(int(self.attributes("-zoomed")))
        except (tk.TclError,ValueError): MC.swallowed()
        return False

    def _zoom_window(self):
        """Maximize the window, however this platform's Tk does it."""
        try: self.state("zoomed"); return
        except tk.TclError: MC.swallowed()
        try: self.attributes("-zoomed",True)
        except tk.TclError: MC.swallowed()

    def _save_panes(self):
        """Persist the layout so it is restored next launch: the tree's width (the outer
        sash's X), the bottom row's height and the details pane's width (the sizes of the
        panes that don't stretch, so they fit whatever size the window opens at), and
        whether the window was maximized. Called from _on_close before teardown."""
        try:
            outer,rightside,bottomrow=self._panes
            self._cfg["panes"]={"v":PANES_LAYOUT,"tree":int(outer.sash_coord(0)[0]),
                                "bottomH":int(rightside.winfo_height()-rightside.sash_coord(0)[1]),
                                "infoW":int(bottomrow.winfo_width()-bottomrow.sash_coord(0)[0]),
                                "zoomed":self._window_zoomed()}
            self._save_config()
        except Exception: MC.swallowed()

    def _restore_panes(self):
        """Restore the saved layout. The window is maximized again first if it was closed
        so; then the panes, outermost first with an update between each (they are nested,
        bottomrow in rightside in outer, and a sash placed against stale geometry lands
        wrong). The bottom row's height and the details pane's width are measured from the
        far edge of the window as it is now. sash_place clamps to each pane's minsize.
        Positions saved by an earlier layout (PANES_LAYOUT) give way to the defaults: they
        were sash positions in the window as it was then (closed maximized, they put the
        bottom row at its least height in a normal window)."""
        p=self._cfg.get("panes")
        if not p: return
        try: outer,rightside,bottomrow=self._panes
        except Exception: MC.swallowed(); return
        if p.get("zoomed") and not self._window_zoomed():
            self._zoom_window()
        self.update_idletasks()
        if "tree" in p:
            try: outer.sash_place(0,int(p["tree"]),0); self.update_idletasks()
            except Exception: MC.swallowed()
        if int(p.get("v",1) or 1)<PANES_LAYOUT: return
        if "bottomH" in p:
            try: rightside.sash_place(0,0,max(0,rightside.winfo_height()-int(p["bottomH"]))); self.update_idletasks()
            except Exception: MC.swallowed()
        if "infoW" in p:
            try: bottomrow.sash_place(0,max(0,bottomrow.winfo_width()-int(p["infoW"])),0); self.update_idletasks()
            except Exception: MC.swallowed()

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
        # ---- top bar: title, model path, Browse, Open Viewer, tool buttons ----------
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
        self._mkbtn(top,text="Browse...",command=self._browse_and_run,
                    tip="Pick a loose .skd model or .tik effect from disk and open it.\n(Ctrl+Shift+O)").pack(side="left",padx=(0,4))
        self._mkbtn(top,text="\u25b6 Open Viewer",style="Accent.TButton",command=self._run,
                    tip="Build the HTML viewer for the selected file and show it in the middle pane\n(also runs on double-click / Enter in the tree)").pack(side="left",padx=(0,14))
        self._lines=[tk.Frame(self,bg=LINE,height=1)]; self._lines[0].pack(fill="x",padx=8)
        body=ttk.Frame(self); body.pack(fill="both",expand=True,padx=10,pady=8)

        # Resizable layout from nested tk.PanedWindows:
        #   outer     (horizontal): [ file tree | rightside ]
        #   rightside (vertical)  : [ 3D viewer / bottomrow ]
        #   bottomrow (horizontal): [ output console | model-info panel ]
        # The console and info panel share one sash, so their top edges always move together.
        # tk (not ttk) panes so the sash follows the theme; minsize keeps every pane visible.
        _pw=dict(bg=LINE,bd=0,sashwidth=6,sashpad=0,sashrelief="flat",
                 showhandle=False,opaqueresize=True)
        outer=tk.PanedWindow(body,orient="horizontal",**_pw); outer.pack(fill="both",expand=True)
        rightside=tk.PanedWindow(outer,orient="vertical",**_pw)
        bottomrow=tk.PanedWindow(rightside,orient="horizontal",**_pw)
        self._panes=[outer,rightside,bottomrow]

        # ---- left panel: full-height pak file tree --------------------------------
        left=ttk.Frame(outer,style="Panel.TFrame",width=300)
        # Row 1: the pak summary label gets the whole row.
        lh=ttk.Frame(left,style="Panel.TFrame"); lh.pack(fill="x",padx=8,pady=(8,2))
        self._pk3_label=ttk.Label(lh,text="No .pk3 loaded",style="PanelDim.TLabel",cursor="hand2")
        self._pk3_label.pack(side="left")
        self._pk3_label.bind("<Button-3>",self._show_pak_menu)
        self._tip(self._pk3_label,"Right-click to list / manage every loaded Pak")
        # Row 2: search box + Add-pak button. The button is packed first so it keeps its full
        # width; the entry takes the rest.
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
        # Click-again tooltips: a second click on the selected row arms a hover tooltip.
        self._tree.bind("<Button-1>",self._on_tree_click,add="+")
        self._tree.bind("<Motion>",self._on_tree_motion,add="+")
        self._tree.bind("<Leave>",lambda e:self._hide_treetip(),add="+")
        # Drag-out: dragging a file row outside the window opens that model in its own
        # standalone browser window, so several models can be viewed side by side.
        self._dragout=None; self._dragout_live=False; self._dragout_xy=(0,0)
        self._tree.bind("<ButtonPress-1>",self._dragout_press,add="+")
        self._tree.bind("<B1-Motion>",self._dragout_motion,add="+")
        self._tree.bind("<ButtonRelease-1>",self._dragout_release,add="+")

        # ---- 3D viewer pane (full width above the bottom row). Hosts the embedded WebView2
        # (created lazily by _ensure_webview) or a placeholder when embedding is unavailable.
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

        # ---- bottom-left: output console ------------------------------------------
        lf=ttk.Frame(bottomrow,style="Panel.TFrame")
        self._outlab=ttk.Label(lf,text="Output",style="PanelDim.TLabel"); self._outlab.pack(anchor="w",padx=8,pady=(6,0))
        logwrap=ttk.Frame(lf,style="Panel.TFrame"); logwrap.pack(fill="both",expand=True,padx=6,pady=(2,6))
        self._log=tk.Text(logwrap,bg=PANEL,fg=TXT,insertbackground=TXT,font=FONT_SMALL,relief="flat",
                          height=8,state="disabled",wrap="word",highlightbackground=LINE,highlightthickness=1)
        sb=ttk.Scrollbar(logwrap,command=self._log.yview); self._log.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y"); self._log.pack(side="left",fill="both",expand=True)
        self._log.tag_config("ok",foreground=ACCENT); self._log.tag_config("err",foreground=ERR_C)
        self._log.tag_config("dim",foreground=DIM); self._log.tag_config("note",foreground=WARN_C)
        self._log.bind("<Button-3>",self._show_log_menu)
        # Escape cancels a build only while the Output pane has focus; clicking it focuses it
        # (a disabled Text doesn't always take focus on its own).
        self._log.bind("<Button-1>",lambda e:self._log.focus_set(),add="+")
        self._log.bind("<Escape>",self._cancel_build)
        self._tip(self._log,"Build / extraction log.\nRight-click to copy or clear.\nEscape to cancel loading / building.")

        # ---- bottom-right: model info (title, surfaces / anims / tags / bones) ------
        # one scrollable column: title, stats, Rebuild / Browser / .tik, then the list
        info=make_info_pane(self,bottomrow,"No model loaded",
                            "Surfaces / anims / tags / bones of the last-built model.\nSelect + copy freely.\nRight-click for Copy all / Select all / Open in Text Editor.")
        self._retheme_tag_text()

        # ---- assemble the panes (add() order = left->right / top->bottom) ----
        # stretch='always' panes absorb extra space when the window grows; 'never' panes keep
        # their size.
        outer.add(left,minsize=180,width=300,stretch="never")
        outer.add(rightside,minsize=340,stretch="always")
        rightside.add(upper,minsize=160,stretch="always")
        rightside.add(bottomrow,minsize=BOTTOM_ROW_MIN,height=BOTTOM_ROW_HEIGHT,stretch="never")
        bottomrow.add(lf,minsize=220,stretch="always")
        bottomrow.add(info,minsize=200,width=INFO_PANE_WIDTH,stretch="never")
        # Restore saved sash positions once the panes are mapped; the second attempt covers a
        # slow first map.
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
        # Left cell: "<state>  --  N pak(s)" (callers pass the pak count as `right`).
        # The right cell always shows the program version.
        try:
            if left is not None: self._status_base=left
            if right is not None:
                self._pak_suffix="" if str(right).strip() in ("","0 paks","0 pak(s)") else right
            self._status_l.configure(text=self._compose_left())
            self._status_r.configure(text=VERSION_LABEL)
        except Exception: MC.swallowed()

    # ------------------------------------------------------------ theming ---
    def _retheme_tree_tags(self):
        self._tree.tag_configure("skd",foreground=ACCENT); self._tree.tag_configure("folder",foreground=TXT)
        self._tree.tag_configure("tik",foreground=ORIGIN)   # .tik effects/emitters stand out

    def _set_theme(self,name):
        if name not in THEMES: return
        self._theme=name
        self._cfg["theme"]=name; self._save_config()
        apply_theme(self,name); self._retheme_widgets(); self._apply_titlebar()
        # Keep the embedded viewer's theme in sync.
        self._embed_js(f"try{{if(typeof setTheme==='function')setTheme({'true' if name=='light' else 'false'})}}catch(e){{}}")

    def _toggle_theme(self,_e=None):
        self._set_theme("light" if self._theme=="dark" else "dark")

    def _renderer(self):
        return "2d" if self._cfg.get("renderer")=="2d" else "gl"

    def _set_renderer(self,val,from_page=False):
        """View > Viewer renderer: "gl" (WebGL, default) or "2d" (canvas). Saved to the config,
        passed to each page as #renderer=, and applied live to the open page. from_page: the
        page's own Display > WebGL toggle changed it, so only the config and menu follow."""
        val="2d" if str(val).strip().lower()=="2d" else "gl"
        self._renderer_var.set(val)
        if self._renderer()==val: return
        self._cfg["renderer"]=val; self._save_config()
        if self._embed_url:
            self._embed_url=re.sub(r"&renderer=(?:gl|2d)","&renderer="+val,self._embed_url)
        if not from_page:
            self._embed_js("try{if(typeof setViewerRenderer==='function')setViewerRenderer(%s)}catch(e){}"
                           %("true" if val=="gl" else "false"))

    def _retheme_tag_text(self):
        t=self._tag_text
        t.configure(bg=PANEL,fg=TXT,insertbackground=TXT,selectbackground=SEL_BG,selectforeground=TXT)
        cv=getattr(self,"_info_canvas",None)
        if cv is not None: cv.configure(bg=PANEL)
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
        except Exception: MC.swallowed()

    def _tag_select_all(self):
        t=self._tag_text
        t.tag_remove("sel","1.0","end"); t.tag_add("sel","1.0","end-1c"); t.focus_set()

    def _tag_open_editor(self):
        txt=self._tag_text.get("1.0","end-1c").strip()
        if not txt:
            self._log_line("No tag/bone list to open yet - build a model first.","dim"); return
        try:
            base=os.path.join(self._tmp or tempfile.gettempdir(),"tags_bones.txt")
            MC.atomic_write_text(base,txt+"\n")
        except Exception as e:
            MC.swallowed()
            self._log_line(f"Could not write tag list: {e}","err"); return
        self._launch_with("text_editor","text editor","Text Editor",base)

    # ---- click-again tree tooltips -------------------------------------------
    def _on_tree_click(self,e):
        """A second click on an already-selected row arms the hover tooltip for that row: it
        appears after the normal delay if the pointer is still there. Clicking another row
        disarms it."""
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
        except Exception: MC.swallowed(); return
        self._show_treetip(self._treetip_text(row),
                           self._tree.winfo_pointerx()+14,self._tree.winfo_pointery()+14,row)

    def _show_treetip(self,text,x,y,row):
        self._hide_treetip()
        try: self._treetip=_tip_window(self,text,x,y,wrap=380)
        except Exception: MC.swallowed(); self._treetip=None; return
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
            except Exception: MC.swallowed()
            self._treetip_after=None

    def _hide_treetip(self):
        self._cancel_treetip_timer()
        if self._treetip:
            try: self._treetip.destroy()
            except Exception: MC.swallowed()
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
        """How many of the .tik's own animations may be baked into the page."""
        try: return max(0,int(self._anim_preload.get()))
        except (TypeError,ValueError): return 150

    def _vfs_read_skc(self,vpath):
        """Read one animation from the paks. The catalogue resolves the path the engine would
        use (currentScript->path + token, tiki_parse.cpp:470-472); a basename match is the
        fallback for the few retail entries whose $path is stale."""
        if self._vfs is None or not vpath: return None
        d=self._vfs.read(vpath)
        if d is not None: return d
        bn="/"+os.path.basename(vpath.replace("\\","/")).lower()
        k=next((kk for kk in self._vfs.names() if kk.endswith(bn)),None)
        return self._vfs.read(k) if k else None

    def _stamp_anim_cache(self):
        """Clear cached a<id>.js animation sidecars written by an older build.

        VIEWER_REV gates the cached HTML, but nothing else invalidates the sidecars beside it
        (e.g. a body animation cached before facial "mw" tracks existed would never gain a
        face). A one-line .rev stamp in the folder makes a format change clear the cache once."""
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
                        except OSError: MC.swallowed()
                if n: self._log_q.put(("dim","(animation cache rebuilt for viewer rev %s - %d cached file(s) cleared)"%(VIEWER_REV_REQUIRED,n)))
            os.makedirs(d,exist_ok=True)
            MC.atomic_write_text(stamp,str(VIEWER_REV_REQUIRED))
        except Exception:
            MC.swallowed()

    def _reuse_ok(self):
        """May this open serve the already-built HTML from the output folder? Not when
        the option is off, when a one-shot theme was requested (the theme is baked at
        build time), or when a Rebuild was requested."""
        o=self._run_opts
        return (self._reuse_html.get() and self._outdir_on.get()
                and not o.get("force") and o.get("theme") not in ("light","dark"))

    def _html_current(self,hp):
        """Reuse a cached viewer HTML only if it is newer than all three source scripts and
        its baked mohaa-viewer-rev is at least VIEWER_REV_REQUIRED; otherwise rebuild."""
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
            MC.swallowed()
            return False                     # unreadable cache: rebuild instead

    def _open_cached(self, hp, model_path=None, subdir=None):
        opts=self._run_opts; self._run_opts={}
        if subdir is not None: self._last_subdir=subdir
        self._log_line(f"Loaded existing {os.path.basename(hp)} from the output folder "
                       f"(right-click > Rebuild to regenerate).","ok")
        self._set_status("Loaded existing HTML")
        if opts.get("external"): self._open_standalone(hp)
        elif self._auto_open.get() and not opts.get("no_open"): self._open_file(hp)
        # Refresh the model-details panel from the opened HTML; a cache hit never runs the
        # builder, whose stdout normally fills it.
        if model_path is not None:
            try: self._update_info(model_path,"",html_path=hp)
            except Exception: MC.swallowed()
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

    def _default_program_path(self, key):
        """Absolute path to the platform's built-in program for `key`, or "".

        Only returns existing files in system locations, never a PATH lookup (on Windows that
        searches the current directory first), so the result is safe to launch unconfigured.

        Windows  notepad.exe in %SystemRoot%, System32 or SysWOW64, else the WindowsApps
                 execution alias (an AppExecLink that isfile can refuse to stat, hence lexists).
        macOS    /usr/bin/open (`open <file>`; TextEdit.app is a bundle directory).
        Linux    xdg-open, then common graphical editors, then a terminal one.
        Only text_editor has a default; legacy_viewer is always user-chosen."""
        if key!="text_editor": return ""
        if sys.platform.startswith("win"):
            win=os.environ.get("SystemRoot") or os.environ.get("WINDIR") or "C:\\Windows"
            lad=(os.environ.get("LOCALAPPDATA") or "").strip()
            alias=os.path.join(lad,"Microsoft","WindowsApps","notepad.exe") if lad else ""
            for c in (os.path.join(win,"notepad.exe"),
                      os.path.join(win,"System32","notepad.exe"),
                      os.path.join(win,"SysWOW64","notepad.exe")):
                try:
                    if os.path.isfile(c): return c
                except OSError: MC.swallowed()
            if alias:
                try:
                    if os.path.exists(alias) or os.path.lexists(alias): return alias
                except OSError: MC.swallowed()
            return ""
        if sys.platform=="darwin":
            return "/usr/bin/open" if os.path.isfile("/usr/bin/open") else ""
        for name in ("xdg-open","gedit","kate","mousepad","gnome-text-editor","nano","vi"):
            w=shutil.which(name)
            if not w: continue
            try:
                w=os.path.realpath(w)
                if os.path.isabs(w) and os.path.isfile(w): return w
            except OSError: MC.swallowed()
        return ""

    def _program_folder_default(self, key):
        """Fallback (folder, item-to-highlight) for "Open ... folder" when the program isn't
        configured, or is a bare command name with no folder of its own.

        Text Editor
          Windows  the folder holding notepad.exe (C:\\Windows where present).
          macOS    TextEdit.app in /System/Applications (10.15+) or /Applications.
          Linux    the bin folder of nano / vim / vi.
        Legacy Model Viewer (LightRay3D and Milkshape 3D are Windows programs)
          Windows  the system-drive root, covering both Program Files trees.
          mac/Lin  a Wine prefix's drive_c if present, else a common install root.
        Returns ("", None) when nothing resolves."""
        home=os.path.expanduser("~")
        def _pick(cands):
            for c in cands:
                if c and os.path.isdir(c): return c
            return ""
        if sys.platform.startswith("win"):
            win=os.environ.get("SystemRoot") or os.environ.get("WINDIR") or "C:\\Windows"
            if key=="text_editor":
                # notepad.exe has moved between Windows releases, so probe the root, System32, SysWOW64
                # and the WindowsApps alias; the first verified hit wins.
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
                        soft=soft or os.path.dirname(c)   # AppExecLink stat can raise; still a lead
                # No verified copy: use the unverified lead, then the alias folder, then the Windows root.
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
                    # explorer /select opens the folder with the item highlighted. Passed as one raw command
                    # string because Popen's list quoting wraps "/select,<path>" in quotes, which explorer
                    # can't parse. The absolute explorer.exe path keeps a copy in the current directory
                    # from running instead.
                    _expl=os.path.join(os.environ.get("SystemRoot",r"C:\Windows"),"explorer.exe")
                    subprocess.Popen('"%s" /select,"%s"'%(_expl,os.path.normpath(sel)))
                else: os.startfile(d)
            elif sys.platform=="darwin":
                subprocess.Popen(["open","-R",sel] if sel else ["open",d])
            else:
                # freedesktop FileManager1.ShowItems is the portable way to open a folder with an item
                # selected (Nautilus, Dolphin, Nemo, Thunar, PCManFM). Short reply timeout, then fall
                # back to xdg-open.
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
                    except Exception: MC.swallowed(); shown=False
                if not shown: subprocess.Popen(["xdg-open",d])
            self._log_line(f"{menu_label} folder: {d}","dim")
        except Exception as e:
            MC.swallowed()
            self._log_line(f"Could not open folder: {e}","err")

    def _launch_with(self, key, label, menu_label, filepath):
        """Run the configured external program on filepath, logging a pointer to Options if it
        is missing or invalid. Thread-safe (logs via the queue)."""
        prog=(self._cfg.get(key) or "").strip()
        if not prog:
            self._log_q.put(("err",f"Error. No {label} program was found. "
                                   f"Please go to Options --> Change {menu_label}..."))
            return
        # The config is data, not a command line: only launch an existing file at an absolute
        # path, never a name resolved through PATH or the current directory, so a config shipped
        # in a downloaded bundle can't run an arbitrary program.
        if not (os.path.isabs(prog) and os.path.isfile(prog)):
            # A bare command name ("notepad.exe", "open", "xdg-open") from an older config is
            # resolved against the system folders and saved back. A user-chosen path that has since
            # moved still gets the error below.
            fixed=self._default_program_path(key) if os.path.basename(prog)==prog else ""
            if not fixed:
                self._log_q.put(("err",f"Error. The saved {label} program is not a valid file "
                                       f"({prog[:120]}). Please go to Options --> Change {menu_label}..."))
                return
            prog=fixed; self._cfg[key]=fixed
            self._save_config()
            self._log_q.put(("dim",f"{menu_label}: {fixed}"))
        try:
            subprocess.Popen([prog,filepath])
            self._log_q.put(("dim",f"opened with {os.path.basename(prog)}: {os.path.basename(filepath)}"))
        except Exception:
            MC.swallowed()
            self._log_q.put(("err",f"Error. Please select a valid program for {label} "
                                   f"in Options --> Change {menu_label}..."))

    def _change_outdir(self):
        d=filedialog.askdirectory(title="Choose the viewer HTML output folder",
                                  initialdir=self._outdir if os.path.isdir(self._outdir) else HERE)
        if d:
            self._outdir=d; self._save_opts()
            self._log_line(f"Output folder: {d}","dim")

    def _open_log_folder(self):
        """Options --> Open log folder: output/logs, where every program keeps its log."""
        d=MC.logs_dir()
        try:
            MC.ensure_dir(d)
            if sys.platform.startswith("win"): os.startfile(d)
            elif sys.platform=="darwin": subprocess.Popen(["open",d])
            else: subprocess.Popen(["xdg-open",d])
            self._log_line(f"Log folder: {d}","dim")
        except OSError as e:
            LOG.error("could not open the log folder %s",d,exc_info=True)
            self._log_line(f"Could not open the log folder: {e}","err")

    def _open_outdir(self):
        try:
            os.makedirs(self._outdir,exist_ok=True)
            if sys.platform.startswith("win"): os.startfile(self._outdir)
            elif sys.platform=="darwin": subprocess.Popen(["open",self._outdir])
            else: subprocess.Popen(["xdg-open",self._outdir])
        except Exception as e:
            MC.swallowed()
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
            # Native popup-menu chrome (the white frame Tk can't recolour) follows Windows' own
            # per-process menu theme: uxtheme ordinal 135 SetPreferredAppMode (2=dark, 3=light),
            # 136 FlushMenuThemes. Undocumented; Win10 1903+, harmless elsewhere.
            try:
                ux=ctypes.WinDLL("uxtheme.dll")
                ux[135](2 if self._theme=="dark" else 3)
                ux[136]()
            except Exception: MC.swallowed()
        except Exception: MC.swallowed()

    def _retheme_widgets(self):
        """Refresh raw-tk widgets that hold palette colours directly."""
        try:
            self.configure(bg=BG)
            for ln in self._lines:
                try: ln.configure(bg=LINE)
                except Exception: MC.swallowed()
            for pw in getattr(self,"_panes",()):
                try: pw.configure(bg=LINE)
                except Exception: MC.swallowed()
            self._path_entry.configure(bg=PANEL,fg=TXT,insertbackground=TXT,
                                       highlightbackground=LINE,highlightcolor=ACCENT)
            self._log.configure(bg=PANEL,fg=TXT,insertbackground=TXT,highlightbackground=LINE)
            self._log.tag_config("ok",foreground=ACCENT); self._log.tag_config("err",foreground=ERR_C)
            self._log.tag_config("dim",foreground=DIM); self._log.tag_config("note",foreground=WARN_C)
            self._retheme_tree_tags()
            self._retheme_tag_text()
            self._menubar.configure(bg=PANEL); self._menubar_line.configure(bg=LINE)
            for b in self._menubtns:
                b.configure(bg=PANEL,fg=TXT,activebackground=SEL_BG,activeforeground=ACCENT)
            for mm in self._menus:
                try: mm.configure(bg=PANEL,fg=TXT,activebackground=SEL_BG,
                                  activeforeground=ACCENT,disabledforeground=DIM)
                except Exception: MC.swallowed()
            # Info-panel colours are baked at render time, so re-render it from the last build.
            if self._last_info:
                self._update_info(*self._last_info)
        except Exception: MC.swallowed()

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

    # Tree: Enter opens a file or descends into a folder.
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

    # Tree: Backspace goes up one folder (closing an open folder first).
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
    # Dragging a .skd/.tik row out of the window opens it in its own browser window (never
    # the embedded pane), so several models can be open at once. These builds skip the
    # open-in-viewer latch because they never touch the embedded pane.
    def _outside_win(self,xr,yr):
        try:
            x,y=self.winfo_rootx(),self.winfo_rooty()
            return not (x<=xr<=x+self.winfo_width() and y<=yr<=y+self.winfo_height())
        except Exception: MC.swallowed(); return False

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
        except Exception: MC.swallowed()
        if out: return "break"        # stop the Treeview auto-scrolling while outside

    def _dragout_release(self,e):
        entry,live=self._dragout,self._dragout_live
        self._dragout=None; self._dragout_live=False
        try: self._tree.configure(cursor="")
        except Exception: MC.swallowed()
        if not (entry and live): return
        self._set_status("Ready")
        if not self._outside_win(e.x_root,e.y_root): return
        self._open_external(entry)

    def _open_external(self,entry):
        """Build (or reuse) a tree entry's HTML and open it in a browser window instead of the
        embedded pane. Also used by drag-out."""
        self._log_line(f"Opening {os.path.basename(entry)} in a browser tab...","dim")
        self._run_opts={"external":True}
        self._open_pk3_model(entry)

    # ----------------------------------------------------- context menus ---
    def _show_pak_menu(self,e):
        # Decide what was right-clicked: a file row, a folder row, or the header / empty space.
        iid=""
        try:
            if e.widget is self._tree: iid=self._tree.identify_row(e.y)
        except Exception: MC.swallowed(); iid=""
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
        """Expand/collapse only the given folder and everything under it."""
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
        """Build each selected file in turn and open each page in its own browser window (the
        embedded pane can show only one at a time)."""
        self._start_batch(self._collect_entries(iids),"selection",open_mode="external")

    def _open_entries_with(self, entries, key, label, menu_label):
        """Extract each selected pak file to the temp workspace and open it with the configured
        external program (e.g. the Text Editor). Batched version of _open_entry_with."""
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
                    except Exception: MC.swallowed(); continue
                    for n in zf.namelist():
                        if n.lower() in found and not n.endswith("/"):
                            found[n.lower()]=self._extract_one(zf,n)
                    zf.close()
                for en in entries:
                    t=found.get(en.lower())
                    if t: self._launch_with(key,label,menu_label,t)
                    else: self._log_q.put(("err",f"Could not find {en} inside the loaded paks"))
            except Exception as ex:
                MC.swallowed()
                self._log_q.put(("err",f"Could not open: {ex}"))
        threading.Thread(target=work,daemon=True).start()

    def _start_batch(self, entries, what, open_mode=None):
        """Build many entries one after another in the background. open_mode=None never opens
        anything; 'external' opens each finished page in its own browser window. Each step uses
        the normal open pipeline (HTML cache, output subfolders, textures); the next one starts
        when the previous one finishes or fails."""
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
        """A build step ended (built, served from cache, or failed): advance the batch once.
        Latched, so duplicate signals are harmless."""
        if not self._batch_waiting: return
        self._batch_waiting=False
        self.after(80,self._batch_step)

    def _ctx_open(self, entry, theme=None, no_open=False, force=False):
        """Open a tree file with one-shot options: a baked initial theme, build-only (no_open),
        and/or force (rebuild even if a saved HTML exists). Global settings are untouched."""
        self._run_opts={"theme":theme,"no_open":bool(no_open),"force":bool(force)}
        # A forced rebuild must actually reload. Navigating the existing WebView2 to the same
        # file:// URL with only the #hash changed is an in-page hash change, not a reload, so
        # close the pane and let _open_file create a new one. Build-only opens nothing and is
        # left alone.
        if force and not no_open: self._close_viewer()
        self._open_pk3_model(entry)

    def _open_entry_with(self, entry, key, label, menu_label):
        """Extract the clicked pak file to the temp workspace and open it with the configured
        external program (.tik -> Text Editor, .skd -> Legacy Model Viewer)."""
        if not self._pk3_paths or not self._tmp:
            self._log_line("Load a .pk3 first.","err"); return
        def work():
            try:
                target=None
                for p in self._pk3_paths:               # later paks override earlier
                    try: zf=zipfile.ZipFile(p)
                    except Exception: MC.swallowed(); continue
                    for n in zf.namelist():
                        if n.lower()==entry.lower() and not n.endswith("/"):
                            target=self._extract_one(zf,n)
                    zf.close()
                if not target:
                    self._log_q.put(("err","Could not find that file inside the loaded paks")); return
                self._launch_with(key,label,menu_label,target)
            except Exception as ex:
                MC.swallowed()
                self._log_q.put(("err",f"Could not open: {ex}"))
        threading.Thread(target=work,daemon=True).start()

    def _remove_pak(self,path):
        if path in self._pk3_paths:
            self._pk3_paths.remove(path)
            self._cfg["pk3s"]=self._pk3_paths if self._remember.get() else []
            self._save_config(); self._paks_changed()
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
        except Exception: MC.swallowed()
    def _clear_log(self):
        self._log.configure(state="normal"); self._log.delete("1.0","end"); self._log.configure(state="disabled")

    # ------------------------------------------------ cancel loading / build ---
    def _cancel_build(self,_e=None):
        """Escape in the Output pane: abort the in-flight open. Bumps the build generation
        (worker threads check it and stop), kills the viewer subprocess, and abandons any
        pending batch."""
        name=self._building_name
        if not name:
            self._log_line("(nothing is loading / building right now)","dim"); return "break"
        self._build_gen+=1                 # stale-gen threads stop at their next check
        self._building_name=None; self._opening_view=False
        p=self._proc
        if p is not None:
            try: p.kill()
            except Exception: MC.swallowed()
        if self._batch:                    # cancelling also abandons the rest of a batch
            self._log_line(f"Batch cancelled with {len(self._batch)} file(s) left unbuilt.","err")
            self._batch=[]; self._batch_total=0; self._batch_waiting=False
        self._log_line(f"Cancelled building the viewer, {name} file was not finished building","err")
        self._set_status("Cancelled")
        return "break"

    # ------------------------------------------------------------ dialogs ---
    def _confirm_dialog(self, title, lines, ok_text="Delete", cancel_text="Cancel"):
        """Themed OK/Cancel dialog in the same style as Help > About, following Dark/Light.

        `lines` is a list of (text, kind) with kind 'title' (ACCENT), 'body' (TXT) or 'dim'
        (DIM). Returns True only on OK / Enter. Uses the OS messagebox when "Use old popup
        windows" is on."""
        if OLD_POPUPS:
            # The native box shows the title in its own title bar, so drop the 'title' rows.
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
        except Exception: MC.swallowed()
        self._apply_titlebar(w)
        w.grab_set(); ca.focus_set()
        self.wait_window(w)
        return res["ok"]

    # The hint on the F1 window's "3D viewer" tab: the page only hears keys once it has them.
    KEYMAP_VIEWER_HINT=("these work once you click in the 3D view · "
                        "hover or press a key to see all it does")

    def _keymap_tabs(self):
        """The F1 window's tabs: (name, shortcut table[, hint]). The Map Viewer has its own."""
        import mohaa_view as MV
        return [("3D viewer",MV.VIEWER_KEYS,self.KEYMAP_VIEWER_HINT),("Launcher",KEYS_LAUNCHER)]

    def _show_hotkeys(self):
        """Help > Keyboard shortcuts (F1): the KeyMapWindow, on the 3D viewer's keys while a
        page is open in the pane (else the launcher's), or the tab you last picked."""
        km=getattr(self,"_keymap",None)
        try:
            if km is not None and km.w.winfo_exists():
                km.w.deiconify(); km.w.lift(); km.cv.focus_set(); return
        except Exception: MC.swallowed()
        try:
            import mohaa_view as MV
            tabs=self._keymap_tabs()
        except Exception as e:
            MC.swallowed()
            self._log_line(f"(the keyboard shortcuts need mohaa_view.py: {e})","err"); return
        tab=getattr(self,"_keymap_tab",None)
        if tab is None: tab=0 if self._webview is not None else 1
        self._keymap=KeyMapWindow(self,tabs,MV.KX_CATS,MV.KX_LAYOUT,tab=tab,
                                  on_tab=lambda i:setattr(self,"_keymap_tab",i))

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
        except Exception: MC.swallowed()
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
            except Exception: MC.swallowed()
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
        except Exception: MC.swallowed()
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
        except Exception: MC.swallowed()

    def _check_for_updates(self):
        """Help --> Check for updates: shows the current version and repo link, checks
        docs/version.txt on the main branch in the background, then reports "up to date" or
        offers to install the newer files. The network is only used when this window is opened
        (see PRIVACY_TEXT, section 3)."""
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
        except Exception: MC.swallowed()
        if not old: self._apply_titlebar(w)
        w.grab_set()
        def worker():
            try:
                raw=MC.http_get(UPDATE_VERSION_URL,UPDATE_UA,timeout=(10,15),max_bytes=4096).decode("utf-8","replace")
                latest=""
                for ln in raw.splitlines():
                    if ln.strip(): latest=ln.strip(); break
                res={"ok":True,"latest":latest} if latest else {"ok":False,"error":"empty version file"}
            except Exception as e:
                MC.swallowed()
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
        except Exception: MC.swallowed(); return
        st=self._upd_state
        if st is None or st[0]!="checked":
            self.after(200,lambda:self._update_poll(w,status_lbl,btnrow)); return
        res=st[1]; self._upd_state=None
        if not res.get("ok"):
            status_lbl.configure(text="Couldn't reach GitHub - no update information found.\n"
                                      "Check your internet connection and try again later.\n"
                                      "("+str(res.get("error",""))[:160]+")")
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
        except Exception: MC.swallowed()
        status_lbl.configure(text="Downloading "+latest+" \u2026")
        self._upd_state=None
        def worker():
            res=self._update_download_and_apply(latest)
            self._upd_state=("installed",res)
        threading.Thread(target=worker,daemon=True).start()
        self.after(200,lambda:self._update_poll_install(w,status_lbl,btnrow))

    def _update_poll_install(self,w,status_lbl,btnrow):
        try:
            if not w.winfo_exists(): return
        except Exception: MC.swallowed(); return
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
        if res.get("backup"):
            self._log_line("Update: the previous version's files were saved to "+res["backup"],"dim")
        if staged:
            status_lbl.configure(text="Update downloaded. The program will now close and\n"
                                      "reopen to finish installing\u2026")
            self.after(1000,lambda:self._restart_program(staged))
        else:
            status_lbl.configure(text="\u2713  Update installed.\n"
                                      "Restart the program for the changes to take effect.")
            self._upd_add_button(btnrow,"Restart now",lambda:self._restart_program())

    def _update_download_and_apply(self, version=None):
        """Background worker: install release `version` over the program folder.

        Steps, each checked before the next:
          1. download the release-tag zip (3 tries, backoff); if that tag doesn't exist,
             the main-branch zip, accepted only if its docs/version.txt says `version`;
          2. test every zip member's CRC, extract to a temp folder;
          3. back up every file about to be replaced into
             output/previous-versions/<n>/ and note it in previous-versions/changelog.txt;
          4. write each new file as <file>.new beside its target, verify it (SHA-256)
             against the download, then os.replace it into place. A target Windows keeps
             locked stays staged as <file>.new for the restart helper;
          5. if any file fails for another reason, everything already replaced is restored
             from the backup and the update reports failure.
        Returns a result dict ("ok", "error", "replaced", "staged", "backup", "branch");
        makes no Tk calls."""
        import urllib.error
        root=_install_root()
        tmp=tempfile.mkdtemp(prefix="mohaaupd_")
        LOG.info("update to %s: install root %s, work folder %s",version,root,tmp)
        try:
            zpath=os.path.join(tmp,"repo.zip")
            used_branch=False
            if not (version and re.fullmatch(r"[0-9A-Za-z._-]{1,32}",version)):
                return {"ok":False,"error":"the version file named %r, which isn't a plain version"%(version,)}
            # The version string comes from the network, so only a plain token goes into a URL.
            tag_url=UPDATE_TAG_ZIP_URL.format(tag=UPDATE_TAG_FMT.format(version=version))
            try:
                MC.http_get(tag_url,UPDATE_UA,timeout=(15,90),dest=zpath,max_bytes=UPDATE_MAX_BYTES)
            except urllib.error.HTTPError as e:
                if e.code!=404: raise
                LOG.warning("release tag for %s not found; trying the %s branch",version,GITHUB_BRANCH)
                MC.http_get(UPDATE_ZIP_URL,UPDATE_UA,timeout=(15,90),dest=zpath,max_bytes=UPDATE_MAX_BYTES)
                used_branch=True
            exdir=os.path.join(tmp,"x")
            with zipfile.ZipFile(zpath) as z:
                bad=z.testzip()
                if bad: return {"ok":False,"error":"the download is damaged (bad entry: %s)"%bad}
                z.extractall(exdir)
            tops=[d for d in os.listdir(exdir)
                  if os.path.isdir(os.path.join(exdir,d)) and d!="__MACOSX"]
            src=os.path.join(exdir,tops[0]) if len(tops)==1 else exdir
            if not os.path.isfile(os.path.join(src,"bin","mohaa_launcher.py")):
                return {"ok":False,"error":"the download doesn't look like this program (no bin/mohaa_launcher.py)"}
            got=""
            try:
                with open(os.path.join(src,"docs","version.txt"),encoding="utf-8") as f:
                    got=next((ln.strip() for ln in f if ln.strip()),"")
            except OSError:
                MC.swallowed("no docs/version.txt in the download")
            if got!=version:
                return {"ok":False,"error":"the downloaded files are version %r, not %r; nothing was changed"%(got or "?",version)}
            # what will be written: every file of the download except folders this program owns
            plan=[]
            for dp,dn,files in os.walk(src):
                rel=os.path.relpath(dp,src)
                top=rel.replace("\\","/").split("/")[0]
                if top in UPDATE_SKIP_DIRS: dn[:]=[]; continue
                dn[:]=[d for d in dn if d not in UPDATE_SKIP_DIRS]
                for fn in files:
                    rp=fn if rel=="." else os.path.join(rel,fn)
                    plan.append((os.path.join(dp,fn),os.path.join(root,rp),rp.replace("\\","/")))
            if not plan: return {"ok":False,"error":"nothing to install (empty download?)"}
            planned={rp for _s,_d,rp in plan}
            retired=[(os.path.join(root,rp),rp) for rp in UPDATE_RETIRED
                     if rp not in planned and os.path.isfile(os.path.join(root,rp))]
            backup=self._update_backup(root,[(d,rp) for _s,d,rp in plan]+retired,version)
            replaced=[]; staged=[]; failed=[]
            for s,d,rp in plan:
                try:
                    with open(s,"rb") as f: data=f.read()
                    new=d+".new"
                    MC.atomic_write_bytes(new,data)
                    try:
                        os.replace(new,d); replaced.append((d,rp))
                    except PermissionError:
                        LOG.warning("%s is in use; staged as %s for the restart",d,new)
                        staged.append(d)
                except OSError as e:
                    LOG.error("update: could not write %s",d,exc_info=True)
                    failed.append("%s (%s)"%(rp,e))
            if failed:
                self._update_rollback(backup,replaced,staged)
                return {"ok":False,"error":"%d file(s) could not be written, so the update was undone: %s"
                                            %(len(failed),"; ".join(failed[:4])),"backup":backup}
            # only now, with every new file in place: the files this version no longer has
            # (already copied into the backup above)
            for d,rp in retired:
                try:
                    os.remove(d); LOG.info("update: removed %s (no longer part of the program)",rp)
                except OSError:
                    LOG.warning("update: could not remove %s",rp,exc_info=True)
            for pc in (os.path.join(root,"bin","__pycache__"),os.path.join(root,"__pycache__")):
                if os.path.isdir(pc):
                    shutil.rmtree(pc,onerror=lambda fn,p,ei:LOG.warning("could not remove %s: %s",p,ei[1]))
            LOG.info("update to %s: %d replaced, %d staged, backup %s%s",version,len(replaced),len(staged),
                     backup," (from the branch, version file checked)" if used_branch else "")
            return {"ok":True,"replaced":[rp for _d,rp in replaced],"staged":staged,"backup":backup,"branch":used_branch}
        except Exception as e:
            LOG.error("update to %s failed",version,exc_info=True)
            return {"ok":False,"error":"%s: %s"%(type(e).__name__,e)}
        finally:
            shutil.rmtree(tmp,onerror=lambda fn,p,ei:LOG.warning("could not remove %s: %s",p,ei[1]))

    def _update_backup(self, root, targets, new_version):
        """Copy every existing file in `targets` [(abs path, rel path)] into
        output/previous-versions/<n>/ (n = next free number), verify each copy's size, and
        add "<n> - version <old> (replaced by <new> on <date>)" to the changelog.txt there.
        Returns the backup folder. Raises OSError if any copy fails (nothing is installed)."""
        base=os.path.join(DATADIR,"previous-versions")
        MC.ensure_dir(base)
        nums=[int(d) for d in os.listdir(base) if d.isdigit() and os.path.isdir(os.path.join(base,d))]
        n=max(nums)+1 if nums else 1
        dest=os.path.join(base,str(n))
        os.makedirs(dest)
        count=0
        for d,rp in targets:
            if not os.path.isfile(d): continue
            b=os.path.join(dest,rp)
            os.makedirs(os.path.dirname(b),exist_ok=True)
            shutil.copy2(d,b)
            if os.path.getsize(b)!=os.path.getsize(d):
                raise OSError("backup of %s is incomplete"%d)
            count+=1
        line="%d - version %s (replaced by %s on %s, %d files)\n"%(n,VERSION,new_version,time.strftime("%Y-%m-%d"),count)
        log=os.path.join(base,"changelog.txt")
        old=""
        if os.path.isfile(log):
            with open(log,"r",encoding="utf-8",errors="replace") as f: old=f.read()
        MC.atomic_write_text(log,old+line)
        LOG.info("backed up %d files to %s",count,dest)
        return dest

    def _update_rollback(self, backup, replaced, staged):
        """Undo a partial update: put the backed-up copy of every replaced file back, delete
        files the update added, and drop staged .new files. Problems are logged."""
        for d,rp in replaced:
            b=os.path.join(backup,rp)
            try:
                if os.path.isfile(b): shutil.copy2(b,d)
                else: os.remove(d)                       # the update added this file
            except OSError:
                LOG.error("rollback: could not restore %s from %s",d,b,exc_info=True)
        for d in staged:
            try: os.remove(d+".new")
            except OSError: LOG.error("rollback: could not remove %s.new",d,exc_info=True)
        LOG.warning("update rolled back from %s",backup)

    def _launcher_path(self):
        """The script a restart runs again (the Map Viewer overrides this)."""
        return os.path.abspath(__file__)

    def _restart_program(self,staged=None):
        """Start a fresh launcher and close this one.

        If files were staged as *.new (locked during an update), a small Python helper
        (written to the temp folder, so it doesn't depend on any staged file) waits for them
        to unlock, moves them into place, logs to output/logs/mohaa_update.log and then
        starts the launcher. Python rather than a .bat, so non-ASCII paths survive and it
        works on every OS. If the new process can't be started, this window stays open and
        says so instead of vanishing."""
        launcher=self._launcher_path()
        exe=sys.executable or "pythonw"
        try:
            if staged:
                helper=os.path.join(tempfile.gettempdir(),"mohaa_update_finish_%d.py"%os.getpid())
                MC.atomic_write_text(helper,UPDATE_FINISHER_SRC)
                MC.atomic_write_text(helper+".json",json.dumps({"staged":list(staged),"exe":exe,"launcher":launcher,
                                                                 "log":os.path.join(MC.ensure_dir(MC.logs_dir()),"mohaa_update.log")}))
                subprocess.Popen([exe,helper,helper+".json"],**NOWIN)
            else:
                subprocess.Popen([exe,launcher],**NOWIN)
        except OSError as e:
            LOG.error("could not start the restart (%s %s)",exe,launcher,exc_info=True)
            try: self._log_line(f"Could not restart automatically ({e}). Close this window and start the program again.","err")
            except Exception: MC.swallowed()
            return
        LOG.info("restarting: %s %s",exe,launcher)
        try:
            if getattr(self,"_tmp",None) and os.path.isdir(self._tmp):
                shutil.rmtree(self._tmp,ignore_errors=True)
        except Exception: MC.swallowed()
        try: self.destroy()
        except Exception: MC.swallowed()
        logging.shutdown()
        os._exit(0)

    # ------------------------------------------------------------- search ---
    def _on_search(self,_e=None):
        if self._filter_after:
            try: self.after_cancel(self._filter_after)
            except Exception: MC.swallowed()
        self._filter_after=self.after(180,self._rebuild_tree)

    # --------------------------------------------------------------- paks ---
    def _choose_pk3(self):
        ps=filedialog.askopenfilenames(title="Select one or more .pk3 (Pak0, Pak2, expansions...)",
            filetypes=[("MOHAA pak","*.pk3"),("Zip","*.zip"),("All files","*.*")])
        if ps: self._add_pk3s(list(ps))

    # ------------------------------------------------- paks shared with the other program
    def _paks_watch(self):
        """Note the shared list's time now, and look again whenever this window gets the
        focus: a change made in the other program meanwhile is taken up here."""
        try: self._paks_seen=os.path.getmtime(PAKS_SHARED)
        except OSError: MC.swallowed(); self._paks_seen=None
        self.bind("<FocusIn>",self._paks_follow,add="+")
    def _paks_changed(self):
        """This program's paks changed: write the shared list for the other one."""
        write_shared_paks(self._pk3_paths)
        try: self._paks_seen=os.path.getmtime(PAKS_SHARED)
        except OSError: MC.swallowed(); self._paks_seen=None
    def _paks_follow(self,_e=None):
        try: t=os.path.getmtime(PAKS_SHARED)
        except OSError: MC.swallowed(); return
        if t==self._paks_seen: return
        self._paks_seen=t
        ps=read_shared_paks()
        if ps is None: return
        ps=[p for p in ps if os.path.exists(p)]
        if ps==self._pk3_paths: return
        self._log_line("The paks were changed in the other viewer; loading the same ones here","dim")
        if not ps: self._clear_pk3s(); return
        self._pk3_paths=[]; self._add_pk3s(ps)

    def _clear_pk3s(self):
        self._pk3_paths=[]; self._cfg["pk3s"]=[]; self._save_config(); self._paks_changed()
        self._tree.delete(*self._tree.get_children()); self._tree_entry.clear(); self._all_files=[]
        self._pk3_label.configure(text="No .pk3 loaded")
        self._vfs=None; self._SH=None; self._TI=None; self._ED=None; self._tex_ready=False
        self._set_status("Paks cleared","0 paks")

    def _add_pk3s(self, paths):
        added=0
        for path in paths:
            if not os.path.exists(path): continue
            try: zipfile.ZipFile(path).close()
            except Exception as e: MC.swallowed(); self._log_line(f"Could not open {os.path.basename(path)}: {e}","err"); continue
            if path not in self._pk3_paths: self._pk3_paths.append(path); added+=1
        if not added and paths: return
        self._cfg["pk3s"]=self._pk3_paths if self._remember.get() else []
        self._cfg.pop("pk3",None); self._save_config(); self._paks_changed()
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
        # Extract the shared human animations from all paks (used to pose characters).
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
                except Exception: MC.swallowed()
        except Exception: MC.swallowed()
        # Build the texture resolution indexes (shaders + tik skins) across all paks.
        if MTX is None:
            self._log_q.put(("dim","(mohaa_textures.py not found - models will load untextured)")); return
        try:
            ED={}                                # shader -> qer_editorimage, for missing-map stand-ins
            vfs=MTX.Vfs(paks); SH=MTX.build_shader_index(vfs,ED); TI=MTX.build_tik_index(vfs)
            GS=MTX.build_global_surface_shaders(TI)
            PROPS=MTX.build_shader_props(vfs)   # always present (no silent hasattr fallback)
            if gen!=self._tex_gen: return        # a newer reload superseded this one
            old=self._vfs
            self._vfs=vfs; self._SH=SH; self._TI=TI; self._GS=GS; self._PROPS=PROPS; self._ED=ED; self._tex_ready=True
            if old is not None and hasattr(old,"close"):
                try: old.close()                  # release the previous reload's pak handles
                except Exception: MC.swallowed()
            self._log_q.put(("ok",f"Textures ready: {len(SH)} shaders, {len(TI)} skinned models indexed."))
            self._log_q.put(("status","Textures ready"))
        except Exception as e:
            MC.swallowed()
            self._log_q.put(("err",f"Texture index failed: {e}"))

    # File types the viewer reads from the workspace. Nothing else in a pak is ever written
    # to disk, so a hostile pak can't drop an executable payload.
    _EXTRACT_OK={".skd",".skb",".skc",".tik",".map",".txt",".shader",".lod",
                 ".tga",".jpg",".jpeg",".png",".dds",".tif",".tiff"}
    # Names Windows treats as devices regardless of folder or extension.
    _WIN_RESERVED={"con","prn","aux","nul","clock$"} | {p+str(i) for p in ("com","lpt") for i in range(1,10)}

    def _safe_target(self, name):
        """Resolve a pak entry name to a path inside the workspace, or None to refuse it.

        Entry names are untrusted (e.g. "models/../../Startup/x.bat"), so every component is
        reduced to a plain name (no '..', drive tokens, alternate data streams or reserved
        device names), the extension must be in _EXTRACT_OK, and the result is re-checked
        against the workspace root with realpath so symlinks and junctions can't escape it."""
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
        except OSError: MC.swallowed(); return None
        if rt!=rr and not rt.startswith(rr+os.sep): return None
        return target

    def _extract_one(self, zf, name, force=False):
        """Extract one pak entry into the workspace and return its path (None if refused).

        The copy is atomic (temp file + os.replace) and its size must equal the entry's
        declared size, so a crash mid-extract can never leave a short file that later runs
        mistake for a cached copy. A cached file is reused only when its size matches the
        entry. zipfile checks the entry's CRC as it reads, so corrupt data raises here."""
        target=self._safe_target(name)
        if target is None:
            self._log_q.put(("dim","(skipped unsafe pak entry: %s)"%name[:120])); return None
        # zipfile stops reading at the entry's declared size, so checking that size bounds
        # what gets written.
        try: size=zf.getinfo(name).file_size
        except KeyError:
            LOG.warning("pak entry %s vanished from %s",name,getattr(zf,"filename","?")); return None
        if size>PAK_ENTRY_MAX:
            self._log_q.put(("dim","(skipped oversized pak entry: %s)"%name[:120])); return None
        if not force and os.path.isfile(target):
            try:
                if os.path.getsize(target)==size: return target      # cached, and complete
                LOG.warning("cached %s is %d bytes, entry is %d: extracting again",
                            target,os.path.getsize(target),size)
            except OSError:
                MC.swallowed("cached copy unreadable; extracting again")
        with zf.open(name) as src:
            MC.atomic_write_stream(target,src,expected_size=size)
        return target

    def _extract_model_map(self, stem, dest_dir):
        """Extract <stem>.map (the model's clip/box brushes) into dest_dir so the viewer can
        derive `setsize` from it (mohaa_view.parse_map_bounds). The .map isn't always beside the
        .skd, so match by basename across all paks, preferring a path under models/ over a
        same-named level .map; later paks win. Returns the written path or None."""
        if not self._pk3_paths: return None
        want=stem.lower()+".map"; best=None   # (score, data); lower score wins
        for p in self._pk3_paths:
            try: zf=zipfile.ZipFile(p)
            except Exception: MC.swallowed(); continue
            try:
                for n in zf.namelist():
                    if n.endswith("/") or os.path.basename(n).lower()!=want: continue
                    score=0 if "models/" in n.lower() else 1
                    if best is None or score<=best[0]:
                        try:
                            if zf.getinfo(n).file_size>PAK_ENTRY_MAX: continue
                            best=(score,zf.read(n))
                        except Exception: MC.swallowed(); continue
            finally: zf.close()
        if not best: return None
        try:
            tgt=os.path.join(dest_dir,stem+".map")
            MC.atomic_write_bytes(tgt,best[1])
            return tgt
        except OSError: MC.swallowed(); return None

    def _populate_tree(self, paks):
        """Scan every pak's models/ tree into self._all_files, then build the
        (optionally filtered) Treeview from it."""
        skds={}; tiks={}   # relpath -> display (later paks override earlier)
        for p in paks:
            try: names=zipfile.ZipFile(p).namelist()
            except Exception: MC.swallowed(); continue
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
        """True (and logs) if an open-in-viewer build is already running. Build-only and
        external opens are never blocked."""
        if self._run_opts.get("no_open") or self._run_opts.get("external"): return False
        if self._opening_view:
            self._log_line("Please wait until the current file(s) finish building.","err")
            return True
        return False

    def _queue_open_until_indexed(self, entry):
        """A pak open arrived before the texture/VFS index finished. Interactive opens are
        latched and fired by _poll_log once the index is ready (an Escape-cancel drops them),
        since building now would cache an untextured page. Non-interactive opens (build-only,
        drag-out) are skipped so a batch never stalls. Used by the .skd and .tik open paths."""
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
        # Already built? Open the saved HTML directly (right-click > Rebuild forces a build).
        # Loose files check their own cache in _load.
        if loose_path is None and self._reuse_ok():
            hp=os.path.join(self._outdir, subdir or "", self._viewer_html_name(entry))
            if os.path.exists(hp) and self._html_current(hp):
                self._last_subdir=subdir; self._open_cached(hp,entry,subdir); return
        if not self._pk3_paths or not self._tmp:
            self._log_line("Load a .pk3 first.","err"); return
        # Wait for the texture index rather than caching an untextured page. Without
        # mohaa_textures (MTX is None) there's no index to wait for.
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
                        MC.swallowed()
                        self._log_q.put(("err",f"Could not read {os.path.basename(loose_path)}: {e}")); return
                else:
                    prefix="/".join(entry.split("/")[:-1])+"/"; skd_target=None
                    for p in self._pk3_paths:                       # later paks override earlier
                        if bgen!=self._build_gen: return            # Escape: cancelled
                        try: zf=zipfile.ZipFile(p)
                        except Exception: MC.swallowed(); continue
                        for n in zf.namelist():
                            if n.startswith(prefix) and not n.endswith("/"):
                                t=self._extract_one(zf,n,force=True)
                                if n==entry: skd_target=t
                        zf.close()
                    if not skd_target:
                        self._log_q.put(("err","Could not find that .skd inside the loaded paks")); return
                # A loose .skd has only a basename: find its pak twin so the texture index (keyed by
                # full pak path) applies, and extract its sibling .skc/.tik/.map as a tree open would.
                tex_key=entry
                if loose_path and self._vfs is not None:
                    bn="/"+os.path.basename(entry).lower()
                    vk=next((k for k in self._vfs.names() if k.endswith(bn)),None)
                    if vk:
                        tex_key=vk
                        folder="/".join(vk.split("/")[:-1])+"/"
                        for k in list(self._vfs.names()):
                            if k.startswith(folder) and not k.endswith("/") and (k.endswith(".skc") or k.endswith(".tik") or k.endswith(".map") or k.endswith(".lod")):
                                d=self._vfs.read(k)
                                if d:
                                    with open(os.path.join(self._tmp,os.path.basename(k)),"wb") as f: f.write(d)
                # pull the model's .map (setsize source) next to the .skd, wherever it lives in the paks
                try:
                    mp=self._extract_model_map(os.path.splitext(os.path.basename(entry))[0], os.path.dirname(skd_target))
                    if mp: self._log_q.put(("dim",f"setsize .map: {os.path.basename(mp)}"))
                except Exception: MC.swallowed()
                # resolve textures -> manifest (if the index is ready)
                manifest=None
                if MTX is not None and self._tex_ready and self._vfs is not None and gen==self._tex_gen:
                    try:
                        import mohaa_view as MV
                        surfs=[s["name"] for s in MV.parse_skd(skd_target)["surfaces"]]
                        manifest=os.path.join(self._tmp,"_tex_"+os.path.basename(entry)+".json")
                        nt,ns=MTX.write_textures_manifest(self._vfs,tex_key,surfs,self._SH,self._TI,manifest,global_surf=self._GS,shader_props=self._PROPS,
                                                          editor_index=self._ED,log=self._log_kind)
                        self._log_q.put(("dim",f"textures: {nt}/{ns} surfaces"))
                        if nt<ns: self._report_surface_misses(manifest,surfs)
                        if nt==0: manifest=None
                    except Exception as e:
                        MC.swallowed()
                        self._log_q.put(("dim",f"(texture resolve skipped: {e})")); manifest=None
                elif MTX is not None and not self._tex_ready:
                    self._log_q.put(("dim","(textures still indexing - opening untextured for now)"))
                if bgen!=self._build_gen: return                # Escape: cancelled
                self._animcat=None; self._animcat_file=None; self._animcat_for=None
                self._log_q.put(("load",(skd_target,self._animroot,manifest,None,subdir)))
            except Exception as e:
                MC.swallowed()
                self._log_q.put(("err",f"Extract failed: {e}"))
        threading.Thread(target=work,daemon=True).start()

    def _resolve_skel_vfs(self, skel, pathhead, entry=None):
        """Resolve a .tik `skelmodel` reference to a VFS key, falling back to the .skb<->.skd
        twin. Some retail .tiks reference a <n>.skb the pak doesn't ship (flaregun, papers_o,
        wirecutters); the engine picks the loader by extension (tiki_skel.cpp:1116,1142-1150)
        and normalises bare skelmodels to .skd (tiki_files.cpp:243-251). The referenced
        extension is always tried first. Returns the key or None."""
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
        # Remember the entry for on-demand animation builds: a cache hit returns below without
        # extracting anything, so _ensure_anim_ctx rebuilds the catalogue lazily from it.
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
                        MC.swallowed()
                        self._log_q.put(("err",f"Could not read {os.path.basename(loose_path)}: {e}")); return
                else:
                    tik_target=None
                    for p in self._pk3_paths:
                        if bgen!=self._build_gen: return            # Escape: cancelled
                        try: zf=zipfile.ZipFile(p)
                        except Exception: MC.swallowed(); continue
                        for n in zf.namelist():
                            if n.lower()==entry.lower() and not n.endswith("/"):
                                tik_target=self._extract_one(zf,n,force=True)
                        zf.close()
                    if not tik_target:
                        self._log_q.put(("err","Could not find that .tik inside the loaded paks")); return
                # Decode as latin-1 like every other pak read; a bare open() would use the locale codec
                # and parse the same .tik differently per machine. latin-1 also never raises.
                txt=open(tik_target,"r",encoding="latin-1",errors="replace").read()
                # Build the animation catalogue from the raw text, before the $include splice below:
                # build_anim_catalog walks includes itself to keep each file's own $path scope, as the
                # engine does (tiki_script.cpp:50, 414-421), which a flat splice would lose.
                self._animcat=None; self._animcat_file=None; self._animcat_for=None
                if MTX is not None and hasattr(MTX,"build_anim_catalog"):
                    try:
                        _cat=MTX.build_anim_catalog(txt, self._vfs, entry)
                        if _cat.get("anims"):
                            _cf=os.path.join(self._tmp,"animcat_"+re.sub(r"[^A-Za-z0-9_.-]","_",
                                             os.path.basename(entry))+".json")
                            MC.atomic_write_text(_cf,json.dumps(_cat,separators=(",",":")))
                            self._animcat=_cat; self._animcat_file=_cf; self._animcat_for=tik_target
                            self._log_q.put(("dim",f"animations: {len(_cat['anims'])} unique across "
                                                  f"{len(_cat['nodes'])} menu group(s), {_cat['files']} file(s)"))
                            if _cat.get("missing"):
                                self._log_q.put(("dim","(unresolved $include: "+", ".join(_cat["missing"][:4])
                                                +(" ..." if len(_cat["missing"])>4 else "")+")"))
                    except Exception as _e:
                        MC.swallowed()
                        self._log_q.put(("dim",f"(animation catalogue failed: {_e})"))
                if MTX is not None: txt=MTX.expand_tik_includes(txt, self._vfs)   # splice $include'd _base.txt (grenades)
                MC.atomic_write_text(tik_target,txt,errors="replace")  # write back so mohaa_view.py sees expanded content
                emitters=MV.parse_tik_emitters(txt)
                # Anim-level client spawn blocks (tagspawn/originspawn) also reference sprites and
                # sub-models; collect their params so the sprite resolver covers them.
                anim_prms=[]; tikanims=[]
                try:
                    tikanims=MV.parse_tik_animations(txt)
                    for ta in tikanims:
                        for c in ta.get("client",[]):
                            # Any client command with a ( ... ) block is a spawn block, including wrapped forms
                            # like `entry commanddelay 0.100 originspawn` (fx_bike_explosion).
                            if c.get("prm"):
                                anim_prms.append(c["prm"])
                        # Server `explosioneffect <type>` (tankshellexplosion.tik) redirects to a base explosion
                        # .tik (MV._EXPLOSIONEFFECT_TIK, after cg_parsemsg CG_MakeExplosionEffect). It has no
                        # ( ) block, so add a prm with that model for the sub-tik resolver and expand_subfx.
                        for c in ta.get("server",[]):
                            av=c.get("argv") or []
                            _cmd,_rest,_dl=MV._strip_cmd_prefix(av)
                            if _cmd=="explosioneffect":
                                _et=(_rest[0].strip('"').lower() if _rest else "grenade")
                                _tik=MV._EXPLOSIONEFFECT_TIK.get(_et,MV._EXPLOSIONEFFECT_TIK["grenade"])
                                anim_prms.append({"model":_tik})
                except Exception: MC.swallowed()
                # init{client{}} `sfx originspawn ( ... )` one-shots (grenexp_water) reference sprites
                # too.
                try:
                    for _s in MV.parse_tik_init_sfx(txt):
                        if _s.get("prm"): anim_prms.append(_s["prm"])
                except Exception: MC.swallowed()
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
                MC.atomic_write_bytes(skd_out,data)
                self._log_q.put(("dim",f"skelmodel: {skel_vfs}"))
                # 3) pull the skelmodel's sibling .skc (animation), .tik (shaders), .map (the
                #    world-space clip box the viewer derives setsize from) and .lod (its level of
                #    detail curve, read beside the .skd as GetLODFile does) next to it
                skel_folder="/".join(skel_vfs.split("/")[:-1])+"/"
                sib=0
                for k in list(self._vfs.names()):
                    if k.startswith(skel_folder) and not k.endswith("/") and (k.endswith(".skc") or k.endswith(".tik") or k.endswith(".map") or k.endswith(".lod")):
                        d=self._vfs.read(k)
                        if d:
                            with open(os.path.join(tik_dir,os.path.basename(k)),"wb") as f: f.write(d); 
                            sib+=1
                if sib: self._log_q.put(("dim",f"+{sib} animation/shader sibling(s)"))
                # Also fetch the model's .map (setsize source) when it isn't in the skelmodel's folder.
                try: self._extract_model_map(os.path.splitext(os.path.basename(skel))[0], tik_dir)
                except Exception: MC.swallowed()
                # 4) Extract the .skc for the animations the .tik declares itself, so the page can bake
                #    them with their per-anim fx. The rest of the catalogue builds on click.
                try:
                    _pre=self._anim_preload_n()
                    _own=[e for e in (self._animcat or {}).get("anims",[]) if e.get("d")][:_pre]
                    if self._animcat and _own:
                        # Extracted under each entry's id, not its basename: `salute idle/salute.skc` and
                        # `american_salute misc/salute.skc` are different animations.
                        _ad=os.path.join(tik_dir,"_anims"); os.makedirs(_ad,exist_ok=True)
                        got=0; miss=0
                        for _e in _own:
                            if bgen!=self._build_gen: return    # Escape: cancelled
                            _tg=os.path.join(_ad,_e["id"]+".skc")
                            if os.path.exists(_tg): continue
                            _d=self._vfs_read_skc(_e["s"])
                            if _d is None: miss+=1; continue
                            MC.atomic_write_bytes(_tg,_d)
                            got+=1
                        if got: self._log_q.put(("dim",f"+{got} animation .skc extracted"
                                                       +(f" ({miss} unresolved)" if miss else "")))
                    elif self._animcat:
                        self._log_q.put(("dim",f"{len(self._animcat['anims'])} animation(s), none declared "
                                              f"by the .tik itself - each builds on first click"))
                    else:
                        # No catalogue (the resolver couldn't reach the animations{} block): fall back to a
                        # basename sweep of the parsed animation files.
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
                                MC.atomic_write_bytes(tgt,d)
                                got+=1
                            if got>=300:
                                self._log_q.put(("dim","(animation extraction capped at 300 .skc)")); break
                        if got: self._log_q.put(("dim",f"+{got} referenced animation .skc extracted"))
                except Exception as _e: MC.swallowed(); self._log_q.put(("dim",f"(animation extraction: {_e})"))
                # 4b) The .tik's `idle` animation, the last one loaded as TIKI_InitTiki takes it: the
                #     viewer sizes the model by its bounds (the game cvar sv_showbboxes) and measures
                #     its level of detail by its radius. Characters reach it through $include, so it
                #     isn't among the animations step 4 extracted.
                try:
                    _ie=None
                    for _e in (self._animcat or {}).get("anims",[]):
                        if (_e.get("n") or "").lower()=="idle": _ie=_e
                    if _ie and _ie.get("id"):
                        _ad=os.path.join(tik_dir,"_anims"); os.makedirs(_ad,exist_ok=True)
                        _tg=os.path.join(_ad,_ie["id"]+".skc")
                        if not os.path.exists(_tg):
                            _d=self._vfs_read_skc(_ie.get("s"))
                            if _d is not None:
                                MC.atomic_write_bytes(_tg,_d)
                except Exception: MC.swallowed()
                # 5) Extract the other skelmodels this .tik assembles (head, hands, helmet, ...) next to
                #    it so the viewer merges them into one model, as in-game.
                part_disk=[skd_out]                          # body first
                try: all_parts=MV.parse_tik_skelmodels(txt)
                except Exception: MC.swallowed(); all_parts=[]
                for (pp,ps) in all_parts[1:]:
                    ps=(ps or "").replace("\\","/").strip().strip('"')
                    pp=(pp or "").replace("\\","/").strip().strip('"')
                    if not ps: continue
                    pv=self._resolve_skel_vfs(ps, pp)   # twin-aware; parts can reference a stale .skb too
                    if not pv:
                        self._log_q.put(("dim",f"(attached part not found: {ps})")); continue
                    pd=self._vfs.read(pv)
                    if not pd: continue
                    pout=os.path.join(tik_dir,os.path.basename(ps))
                    MC.atomic_write_bytes(pout,pd)
                    part_disk.append(pout)
                    pfolder="/".join(pv.split("/")[:-1])+"/"     # pull that part's sibling .skc too
                    for k in list(self._vfs.names()):
                        if k.startswith(pfolder) and k.endswith(".skc"):
                            dd=self._vfs.read(k)
                            if dd:
                                with open(os.path.join(tik_dir,os.path.basename(k)),"wb") as f: f.write(dd)
                    # ...and its own level of detail curve (<part>.lod beside <part>.skd)
                    if pv.lower().endswith(".skd"):
                        dl=self._vfs.read(pv[:-4]+".lod")
                        if dl:
                            with open(os.path.splitext(pout)[0]+".lod","wb") as f: f.write(dl)
                if len(part_disk)>1:
                    self._log_q.put(("dim",f"assembled {len(part_disk)} parts: "+", ".join(os.path.basename(p) for p in part_disk)))
                # 6) Resolve textures for the skelmodel's surfaces.
                if bgen!=self._build_gen: return                # Escape: cancelled
                if MTX is not None and self._tex_ready and gen==self._tex_gen:
                    try:
                        # Combined surface list across all assembled parts (body + head + hands).
                        surfs=[]
                        for pdp in part_disk:
                            try: surfs+=[s["name"] for s in MV.parse_skd(pdp)["surfaces"]]
                            except Exception: MC.swallowed()
                        seen=set(); surfs=[s for s in surfs if not (s in seen or seen.add(s))]
                        manifest=os.path.join(self._tmp,"_tex_"+os.path.basename(entry)+".json")
                        # The opened .tik's own setup decides the skin (bangalore_pulsating, _ghosting and plain
                        # bangalore all use bangalore.skd); the global index keeps only one mapping per .skd.
                        local_TI=dict(self._TI)
                        allpairs=[]
                        try:
                            tik_map=MTX.parse_tik_setup(txt)
                            local_TI.update(tik_map)
                            # All parts are skinned as one mesh, so expose every part's surface->shader pairs under
                            # the body key the manifest uses.
                            for v in tik_map.values(): allpairs+=v
                            local_TI[skel_vfs]=allpairs; local_TI[skel_vfs.lower()]=allpairs
                        except Exception: MC.swallowed()
                        nt,ns=MTX.write_textures_manifest(self._vfs,skel_vfs,surfs,self._SH,local_TI,manifest,global_surf=self._GS,shader_props=self._PROPS,
                                                          editor_index=self._ED,log=self._log_kind)
                        self._log_q.put(("dim",f"textures: {nt}/{ns} surfaces"))
                        # Report unresolved surfaces, passing the tik's own surface->shader pairs so the message
                        # can name the shader that failed.
                        if nt<ns: self._report_surface_misses(manifest,surfs,dict(allpairs))
                        if nt==0: manifest=None
                    except Exception as e:
                        MC.swallowed()
                        self._log_q.put(("dim",f"(texture resolve skipped: {e})")); manifest=None
                # 7) Resolve each emitter's sprite/sub-model to a billboard texture (setup emitters and
                #    anim-level spawn blocks), then a second pass for sprites referenced inside flattened
                #    sub-tiks (e.g. snipesmoke's vsssource.spr).
                emittex=self._resolve_emitter_sprites(emitters+anim_prms)
                inner=[]
                for ent in emittex.values():
                    if isinstance(ent,dict) and ent.get("subfx"): inner+=ent["subfx"]
                if inner:
                    more=self._resolve_emitter_sprites(inner)
                    for k,v in more.items(): emittex.setdefault(k,v)
                # Warn about `model` refs that produced no sprite instead of silently drawing an
                # untextured blob.
                self._warn_emitter_assets(emitters+anim_prms+inner, emittex)
                emittex_file=None
                if emittex:
                    emittex_file=os.path.join(self._tmp,"_emit_"+os.path.basename(entry)+".json")
                    try:
                        MC.atomic_write_text(emittex_file,json.dumps(emittex))
                    except Exception: MC.swallowed(); emittex_file=None
                    self._log_q.put(("dim",f"emitter sprites: {len(emittex)} resolved"))
                self._log_q.put(("dim",f"{len(emitters)} particle emitter(s) parsed"))
                if bgen!=self._build_gen: return                # Escape: cancelled
                self._log_q.put(("load",(tik_target,self._animroot,manifest,emittex_file,subdir)))
            except Exception as e:
                MC.swallowed()
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
            MC.atomic_write_bytes(tmp,data)
            try: dims=MV.skd_bind_dims(MV.parse_skd(tmp))
            finally:
                try: os.remove(tmp)
                except OSError: MC.swallowed()
            longest=dims[0]; middle=dims[1] if len(dims)>1 and dims[1]>0.01 else longest
            aspect=round(longest/middle, 3) if middle>0.01 else 1.0
            return (round(longest*tscale, 3), aspect)
        except Exception:
            MC.swallowed()
            return (0.0, 1.0)

    def _submodel_pose_channels(self, sub_text, pathhead):
        """Frame-0 channels of the sub-tik's `idle` animation, used to pose its skelmodel.

        A tempmodel from an RT_MODEL .tik is posed by an animation, not the raw skeleton:
        SpawnTempModel uses Anim_NumForName(tiki,"idle"), falling back to animation 0, at frame
        0 (cg_tempmodels.cpp:1337-1347). With identity rotations instead, e.g. muzflash.tik
        lies across the barrel rather than along it. Returns {} on any miss."""
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
            MC.atomic_write_bytes(tmp,data)
            try: skc=MV.parse_skc(tmp)
            finally:
                try: os.remove(tmp)
                except OSError: MC.swallowed()
            fr=skc.get("frames") or []
            return dict(fr[0]) if fr else {}
        except Exception:
            MC.swallowed()
            return {}

    def _submodel_mesh(self, sub_text, max_aspect=3.0):
        """Bind-pose geometry for a .tik sub-model debris particle (metal_section, ibeam_piece):
        {v:[[x,y,z]...], t:[[a,b,c]...], ...} in model space (Z-up), scaled by the sub-tik
        `scale`, so the viewer can draw it as a 3D chunk. Returns None for thin slivers
        (aspect >= max_aspect, drawn as oriented billboards), sprite shaders, or on any miss."""
        if self._vfs is None: return None
        try:
            import mohaa_view as MV
            pathhead, skel = MV.parse_tik_setup_head(sub_text)
            if not skel: return None
            # Autosprite/animmap shaders (bh_wood_puff, bh_stone_puff) are camera-facing sprites
            # in-game, not meshes; their flat quad would otherwise render as a black square. Real
            # debris (bh_wood_piece) still gets a mesh.
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
            MC.atomic_write_bytes(tmp,data)
            try: skd=MV.parse_skd(tmp)
            finally:
                try: os.remove(tmp)
                except OSError: MC.swallowed()
            # Pose the skeleton like the engine: the sub-tik's `idle` animation at frame 0
            # (cg_tempmodels.cpp:1337-1347).
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
                # Per-vertex UVs so the viewer can texture the chunk with its real skin.
                _suv=s.get("uvs") or []
                for k in range(len(s["verts"])):
                    if k<len(_suv): uvs.extend([round(_suv[k][0],4),round(_suv[k][1],4)])
                    else: uvs.extend([0.0,0.0])
                for tr in s["tris"]:
                    tris.append([tr[0]+base,tr[1]+base,tr[2]+base])
                verts.extend(sv); base+=len(sv)
            if nv==0 or not tris: return None
            cen=[cen[k]/nv for k in range(3)]
            # Keep native model space (don't re-centre). A tempmodel's vertices rotate about the
            # entity origin with the particle's random angles (cg_tempmodels.cpp:1492-1494), so a
            # card authored away from its origin (bh_foliage_leaf's leaf.skd) is swung onto a shell
            # of radius |centroid|*scale. For fx_leaves_blowing that is the only per-leaf spread the
            # engine has; radialvelocity leaves the leaves at rest (cg_tempmodels.cpp:1511-1521).
            V=[[round(p[k]*tscale,3) for k in range(3)] for p in verts]
            out={"v":V,"t":tris}
            if any(uvs): out["uv"]=uvs
            # Texture from the sub-tik's first `surface <n> shader <s>` (tempmodels render with their
            # own skin in-game); the flat colour remains the fallback.
            try:
                m2=re.search(r'surface\s+\S+\s+shader\s+(\S+)', sub_text, re.I)
                if m2:
                    sh=m2.group(1).strip()
                    # Blend mode first, since it also decides the texture encoding. e.g. muzflash.tik's
                    # muzmodel shader is `blendFunc GL_SRC_ALPHA GL_ONE`: the card is added to the scene, so
                    # its black surround contributes nothing. `add` makes the viewer composite it additively
                    # without flat shading (no rgbGen -> CGEN_IDENTITY_LIGHTING, tr_shader.c:1755-1765).
                    _sp2=(self._PROPS or {}).get(sh.lower())
                    _add=bool(_sp2 and _sp2.get("additive"))
                    if _add: out["add"]=True
                    mp=self._SH.get(sh.lower()) if self._SH else None
                    t=self._vfs.find_texture(mp) if mp else self._vfs.find_texture(sh)
                    if t:
                        # Additive surfaces need a real alpha channel. In GL the black surround of a 24-bit
                        # texture adds nothing, but Canvas 'lighter' over a transparent canvas still adds alpha
                        # for every opaque texel, painting a black rectangle around e.g. the mg42 muzzle flash.
                        # emitter_clean (as used for additive sprites) keys near-black to transparent.
                        d=MTX.texture_to_dataurl(self._vfs,t,max_dim=512,keep_alpha=True,
                                                 emitter_clean=_add)
                        if d: out["tex"]=d
            except Exception:
                MC.swallowed()
            return out
        except Exception:
            MC.swallowed()
            return None

    def _avg_tex_color(self, texpath):
        """Mean RGB (0..1) of a VFS texture, for flat-shading 3D debris chunks. Metal-grey on miss."""
        default=[0.56,0.56,0.60]
        if not texpath or self._vfs is None: return default
        try:
            import io
            Image = MC.pil_image()          # Pillow >= 10.3, pixel limit set (mohaa_common)
            data=self._vfs.read(texpath)
            if not data: return default
            with Image.open(io.BytesIO(data)) as im:
                px=list(im.convert("RGB").resize((8,8)).getdata())
            n=len(px)
            if not n: return default
            return [round(sum(p[k] for p in px)/n/255.0,3) for k in range(3)]
        except Exception:
            MC.swallowed()
            return default

    def _resolve_emitter_sprites(self, emitters):
        """Resolve each emitter's `model` reference to a billboard sprite.

        Returns {model_ref_lower: entry}. An entry is {"tex": data URL, ...} plus render hints
        (additive, frames/fps, bundle, sprite_type, spritescale, texw/texh, basesize, mesh, ...),
        or {"subfx": [...]} for a dummy sub-tik whose effects the viewer flattens.
          .spr / volumetric -> the sprite's shader or image
          .tik              -> the sub-model's first `surface ... shader ...` texture"""
        out={}
        if self._vfs is None or MTX is None: return out
        for e in emitters:
            ref=(e.get("model") or "").replace("\\","/").strip().strip('"')
            if not ref: continue
            rl=ref.lower()
            if rl in out: continue
            du=None; shname=None; basesize=0.0; baseaspect=1.0; tp=None; _mesh=None; _banim=None; _edu=None
            # Volumetric smoke (`volumetric` flag, or `model <type>` naming one of the 12
            # cg_vsstypes) always renders with VSSSource.spr / VSSSource2.spr
            # (cg_volumetricsmoke.cpp), so map it to the vsssource sprite.
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
                    # Each VSS puff draws through the vsssource shader (AddVSSSources,
                    # cg_volumetricsmoke.cpp:1167-1168; model chosen by T_RANDOMROLL, :1331-1340) with its
                    # counter-rotating GL_MODULATE bundle. Ship the animated bundle like the .spr path so the
                    # puffs render as grey wisps rather than dense white blobs.
                    if tp is not None and self._PROPS:
                        _pp=(self._PROPS or {}).get(base)
                        if _pp and _pp.get("bundle"):
                            _bd=_pp["bundle"]
                            _bt=self._vfs.find_texture(_bd.get("map") or "")
                            if _bt and (_bd.get("scroll") or _bd.get("rotate")):
                                _banim=(_bt,_bd)
                elif rl.endswith(".spr"):
                    # SPR_RegisterSprite (renderergl1/tr_sprite.c:31-56): the shader name is the .spr path
                    # minus its extension (`textures/effects/bang.spr` -> "textures/effects/bang"), falling
                    # back to an implicit shader from the same-path image. Basename candidates follow.
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
                    # A static detail bundle (nextbundle GL_MODULATE) is baked into the sprite pixels, e.g.
                    # mortar_dirthit's 8x16 mortar_noise grain.
                    _pp=(self._PROPS or {}).get(shname)
                    _bpath=None; _bscale=(1.0,1.0)
                    if _pp and _pp.get("bundle"):
                        _bd=_pp["bundle"]
                        _bt=self._vfs.find_texture(_bd.get("map") or "")
                        if _bt:
                            if _bd.get("scroll") or _bd.get("rotate"):
                                # Animated tcmods aren't baked; they're exported for runtime compositing so the
                                # grain drifts/spins like in-game.
                                _banim=(_bt,_bd)
                            else:
                                _bpath=_bt; _bscale=tuple(_bd.get("scale") or (1.0,1.0))
                    _edu=None
                    for c in cands:
                        t=self._vfs.find_texture(c)
                        if t: tp=t; du=MTX.texture_to_dataurl(self._vfs,tp,max_dim=512,emitter_clean=True,bundle_path=_bpath,bundle_scale=_bscale); break
                    # Erosion source for animated bundles: the viewer thresholds its alpha-test pattern
                    # from a static base x noise bake at phase 0 (the noise alpha carries the granular
                    # dissolve). The unbaked `du` stays the RGB source so the grain still moves.
                    if tp is not None and _banim is not None:
                        _abt,_abd=_banim
                        _edu=MTX.texture_to_dataurl(self._vfs,tp,max_dim=512,emitter_clean=True,
                                                    bundle_path=_abt,
                                                    bundle_scale=tuple(_abd.get("scale") or (1.0,1.0)))
                    # animmap-only shaders (e.g. air_explosion) have no base `map`, so every candidate
                    # misses. Use the first animmap frame as the base; the frame list is applied below.
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
                            # animmap-only shader (bh_wood_puff / bh_stone_puff: `animmap 20 woodpuff1..7.tga`) has
                            # no base texture; use the first frame, as the .spr path does.
                            if not tp and self._PROPS:
                                _pp=(self._PROPS or {}).get(sh.lower())
                                if _pp and _pp.get("frames"):
                                    tp=self._vfs.find_texture(_pp["frames"][0])
                        if tp: du=MTX.texture_to_dataurl(self._vfs,tp,max_dim=512,emitter_clean=True)
                        # Dummy fx sub-tik (snipesmoke, gas_mushroom_cloud): nothing drawable itself; its look
                        # comes from its idle-anim originspawn one-shots and init-client emitters, exported for
                        # the viewer to flatten (expand_subfx).
                        if not du:
                            _sf=self._collect_subfx(sub)
                            if _sf:
                                out[rl]={"subfx":_sf}
                                continue
                        # A .tik particle is a real mesh: record its true size and aspect so the viewer draws it
                        # at geometry scale.
                        basesize,baseaspect=self._submodel_basesize(sub)
                        # Chunky debris (metal_section, ibeam_piece) renders as tumbling 3D geometry; thin
                        # slivers stay billboards (mesh is None for those).
                        _mesh=self._submodel_mesh(sub)
                        if _mesh is not None:
                            _mesh["color"]=self._avg_tex_color(tp)
            except Exception:
                MC.swallowed()
                du=None
            if not du: continue
            # Original (pre-downscale) texture size, used by the viewer to size .spr sprites.
            texw,texh=self._orig_tex_dims(tp)
            props=(self._PROPS or {}).get((shname or "").lower())
            # A GL_ONE source blend ignores alpha (tr_shader.c NameToSrcBlendMode), so re-encode the
            # sprite for Canvas 'lighter' (see dataurl_gl_one_additive). Debris chunks keep their
            # native alpha since they draw source-over through the mesh path.
            _glone=bool(props and props.get("additive")
                        and props.get("srcalpha") is False and _mesh is None)
            if _glone: du=MTX.dataurl_gl_one_additive(du)
            entry={"tex":du}
            # The sprite's real blend mode, so water/smoke alpha-blend instead of stacking to white.
            if props is not None:
                entry["additive"]=bool(props.get("additive"))
                # rgbvertex: whether the emitter `color` reaches the framebuffer (a plain `blendfunc add`
                # stage like corona_util stays white). srcalpha: whether the source factor reads alpha
                # at all; with `add`, alpha/fade/flickeralpha have no effect.
                if "rgbvertex" in props: entry["rgbvertex"]=bool(props.get("rgbvertex"))
                if "srcalpha"  in props: entry["srcalpha"]=bool(props.get("srcalpha"))
                # alphafunc on a blendfunc-less base stage: pixels are either fully opaque or holes
                # (tr_shader.c NameToAFunc); the viewer erodes these instead of alpha-fading.
                if props.get("atest"): entry["alphatest"]=props["atest"]
            # Animated nextbundle: ship the noise texture and tcmod params for the viewer to multiply
            # over the sprite each frame (GL_MODULATE, tr_shader.c:1841-1853). halpha marks noise
            # with real alpha, which makes the erosion pattern move as well.
            if _banim is not None:
                _abt,_abd=_banim
                # MODULATE multiplies alpha as well as RGB (A = A0*A1), so ship the noise with its alpha
                # (keep_alpha): vsssource x vsssource2's counter-rotating smoke lives in that product.
                # Alpha-tested emitters keep the opaque encode, since their erosion pattern comes from
                # the base alpha only.
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
                entry["additive"]=False   # VSS smoke is alpha-blended, never additive
                # Quad width = texW * (radius/5) * spritescale (tr_sprite.c); carry the vsssource
                # shader's spritescale.
                entry["spritescale"]=float((props or {}).get("spritescale",1.0) or 1.0)
            # sprite_type is set only for an explicit `spritegen` and exported as-is, including
            # "parallel": the viewer needs an explicit parallel to suppress roll (tr_sprite.c:84-91),
            # while no keyword keeps its default.
            if props and props.get("sprite_type"):
                entry["sprite_type"]=props["sprite_type"]
            # deformVertexes lightglow rebuilds the quad from the camera axes every frame
            # (tr_shade_calc.c LightGlowDeform) regardless of spritegen, so e.g. fire_ring
            # (`spritegen oriented` + lightglow) must render camera-facing, not as a world quad.
            if props and props.get("lightglow"):
                entry["lightglow"]=True
            # Shader spriteScale applies to every spritegen quad (RB_DrawSprite: spr->scale * entity
            # scale), e.g. muzsprite / *_spriteflash at .3/.7 in effects.shader.
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
        """Inner client fx of a dummy sub-.tik (a spawned tempmodel with no drawable surface):
        its animations' `enter originspawn` blocks, init-client `sfx originspawn` /
        `delayedsfx` one-shots, and init-client emitters (stream=True, so the viewer runs them
        for the tempmodel's lifetime). Returns a JSON-safe list of param dicts."""
        out=[]
        try:
            import mohaa_view as MV
            for ta in MV.parse_tik_animations(sub_text):
                for c in ta.get("client",[]):
                    if c.get("prm") and (c.get("argv") or [""])[0].lower()=="originspawn":
                        out.append(dict(c["prm"]))
            # init{client{}} `sfx <spawncmd> ( ... )` / `delayedsfx <sec> ...` one-shots.
            # bazookaexp_base.tik's entire look is these (gren_boom.spr, vsssource.spr); it has no
            # animation fx or emitter blocks.
            for s in MV.parse_tik_init_sfx(sub_text):
                if s.get("prm"):
                    q=dict(s["prm"])
                    if s.get("delay"): q["startdelay"]=s["delay"]
                    out.append(q)
            for e in MV.parse_tik_emitters(sub_text):
                q=dict(e); q["stream"]=True
                out.append(q)
        except Exception:
            MC.swallowed()
            return []
        return out

    def _orig_tex_dims(self, texpath):
        """Original (w,h) of a VFS texture before downscaling, read from the file header
        (TGA/DDS/PNG/JPEG) so it works without PIL or with odd TGA variants, then via PIL.
        Returns (0,0) on failure. The viewer sizes .spr sprites from this (e.g. mortarhit2.tga
        is 512x512; the 32px default would make those sprites 16x too small)."""
        if not texpath or self._vfs is None: return (0,0)
        try:
            data=self._vfs.read(texpath)
        except Exception:
            MC.swallowed()
            data=None
        if not data: return (0,0)
        wh=self._dims_from_header(data, texpath)
        if wh[0] and wh[1]: return wh
        try:
            import io
            Image = MC.pil_image()          # Pillow >= 10.3, pixel limit set (mohaa_common)
            with Image.open(io.BytesIO(data)) as im:
                return (int(im.size[0]), int(im.size[1]))
        except Exception:
            MC.swallowed()
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
            # TGA: width @ 12, height @ 14 (little-endian uint16). TGA has no magic, so only
            # trust it for a .tga path or a plausible header.
            if len(data)>=18 and (ext=="tga" or data[1] in (0,1)):
                import struct
                w,h=struct.unpack("<HH", data[12:16]); return (w,h)
        except Exception:
            MC.swallowed()
        return (0,0)

    # ------------------------------------------------------------ run/load ---
    def _browse(self):
        p=filedialog.askopenfilename(title="Select a .skd model or .tik effect",
            filetypes=[("MOHAA model / effect","*.skd *.tik"),("MOHAA Skeleton","*.skd"),
                       ("MOHAA effect/emitter","*.tik"),("All files","*.*")])
        if p: self._path_var.set(p)
        return p or ""

    def _browse_and_run(self):
        """Browse... (and File > Open File...): pick a file and open it at once. Only a file
        that was picked opens (Cancel leaves the path bar's own path alone), and only a kind
        the viewer opens (.skd / .tik here, .bsp / .map / .bak in the Map Viewer: _run says
        so for another); Open Viewer stays for a path typed into the bar."""
        p=self._browse()
        if p and os.path.isfile(p): self._run()

    def _run(self):
        path=self._path_var.get().strip().strip('"')
        if path.startswith("pk3://"): self._open_pk3_model(path[len("pk3://"):]); return
        # After a pk3 build the path bar shows "pk3 model: <n>", not a real path; re-run the
        # last build.
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
        # Direct entry points (drag-drop, Recent, path bar) respect the open-in-viewer latch;
        # _cont=True marks the continuation of a pk3 open that already holds it.
        if not _cont and self._viewer_open_busy(): return
        # A file opened from disk is a standalone build: its HTML goes in standalone/, not the
        # pak-mirroring models tree. The routed loose-open paths set this themselves; this covers
        # direct builds (e.g. no paks loaded) and the reuse check below.
        if (not _cont and subdir is None and os.path.isfile(path)
                and not (self._tmp and path.startswith(self._tmp))):
            subdir=STANDALONE_SUBDIR
        self._last_build=(path,animroot,manifest,emittex,subdir)   # lets Open Viewer re-run this build
        self._last_subdir=subdir
        disp=("pk3 model: "+os.path.basename(path)) if (self._tmp and path.startswith(self._tmp)) else path
        self._path_var.set(disp)
        self._push_recent(path)
        # Loose files (Browse / drag-drop / Recent) can reuse a saved HTML too.
        if self._reuse_ok():
            hp=self._html_out_path(path,subdir)
            if os.path.exists(hp) and self._html_current(hp):
                self._opening_view=False       # no build will run: release the open latch
                self._open_cached(hp,path,subdir); return
        # A loose .tik/.skd with paks loaded: its skelmodel, animations and textures usually live
        # inside the paks, so run the same pak pipeline as a tree open, driven by the loose
        # file's own content.
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
            # This model's animation catalogue (names only; poses are solved per animation on click)
            # and the bake budget.
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
            # Always --no-open: the launcher opens the HTML itself (embedded pane or browser).
            cmd.append("--no-open")
            # Popen (not run) so Escape-to-cancel can kill the build mid-flight
            p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",errors="replace",env=MC.child_env(),**NOWIN)
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
        except Exception as e: MC.swallowed(); self._log_q.put(("err",str(e)))
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
                        # The child prefixes real failures with "!" (.skc missing or unparseable, drives none of
                        # the skeleton's bones); show those in red.
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
                    elif kind=="setrenderer": self._set_renderer(msg,from_page=True)   # Display > WebGL
                    # Missing-asset warnings: shown in red but, unlike "err", they don't abort the open or
                    # stall a batch.
                    elif kind=="warn": self._log_line(msg,"err")
                    # Yellow: a problem worked around, e.g. a missing shader map replaced by a
                    # texture found elsewhere in the paks.
                    elif kind=="note": self._log_line(msg,"note")
                    elif kind=="js": self._embed_js(msg)
                except Exception as e:
                    # A bad handler must never kill the poll loop.
                    MC.swallowed()
                    try: self._log_line(f"(ui error: {e})","err")
                    except Exception: MC.swallowed()
            # Fire a pk3 open queued while the index was building (see _queue_open_until_indexed)
            # once the index is ready; drop it if Escape bumped _build_gen or indexing failed (the
            # "err" handler releases _opening_view).
            if self._pending_open is not None:
                entry,bgen=self._pending_open
                if self._tex_ready and self._vfs is not None and bgen==self._build_gen:
                    self._pending_open=None; self._opening_view=False; self._run_opts={}
                    self._open_pk3_model(entry)          # index ready - open for real now
                elif bgen!=self._build_gen or not self._opening_view:
                    self._pending_open=None              # cancelled / index unavailable
        finally:
            self.after(80,self._poll_log)

    # ---- start-up from the RUN file, and the files the program writes ------------------
    # The RUN .bat starts the program without a console (mohaa_envcheck.py start) and closes
    # once the window is open: MOHAA_READY_FILE names a file to create then. Its own text
    # (Python, the package checks, pip) is in MOHAA_RUN_LOG; it goes at the top of the Output
    # pane, so it is also in output_console*.log. Every file the program saves through the
    # atomic writers is announced in the Output pane ("saved <path>"), apart from its scratch
    # files (the temp folder, caches, logs).
    def _startup_extras(self):
        """Copy the RUN window's text into the Output pane, install the "saved" hook and
        schedule the window-open signal. Never raises."""
        try:
            rl=os.environ.get("MOHAA_RUN_LOG","")
            if rl and os.path.isfile(rl):
                with open(rl,encoding="utf-8",errors="replace") as f: lines=f.read().splitlines()
                if lines:
                    self._log_q.put(("dim","--- the RUN window (also in %s) ---"%rl))
                    for ln in lines:
                        tag="err" if ln.lstrip().startswith("[ERROR]") else ("warn" if ln.lstrip().startswith("[WARN]") else "dim")
                        self._log_q.put((tag,ln))
                    self._log_q.put(("dim","--- end of the RUN window ---"))
        except Exception:
            MC.swallowed("RUN window text not shown")
        MC.set_write_hook(self._on_file_written)
        if os.environ.get("MOHAA_READY_FILE"):
            self.after(300,self._signal_ready)

    def _signal_ready(self):
        """Create MOHAA_READY_FILE (once): the RUN window then closes."""
        p=os.environ.pop("MOHAA_READY_FILE","")
        if not p: return
        try:
            with open(p,"w",encoding="utf-8") as f: f.write(str(os.getpid()))
        except OSError:
            MC.swallowed("ready file")

    def _on_file_written(self,path):
        """The write hook: a "saved <path>" line in the Output pane, unless the file is
        scratch (temp folder, caches, logs) or the same file was just announced."""
        ap=os.path.normcase(os.path.abspath(path))
        skip=[tempfile.gettempdir(),MC.logs_dir()]
        if any(ap.startswith(os.path.normcase(os.path.abspath(d))+os.sep) for d in skip if d): return
        parts=ap.split(os.sep)
        if any(x in ("cache","webview2","__pycache__") or x.endswith("_cache") for x in parts[:-1]): return
        now=time.time(); last=getattr(self,"_saved_last",None)
        if last and last[0]==ap and now-last[1]<3: return
        self._saved_last=(ap,now)
        self._log_q.put(("dim","saved %s"%os.path.abspath(path)))

    def _log_line(self,text,tag=""):
        """Add a line to the Output pane, output_console.log and the program's log file."""
        LOG.log(logging.ERROR if tag=="err" else logging.INFO,"[out] %s",text)
        self._log.configure(state="normal"); self._log.insert("end",text+"\n",tag)
        self._log.see("end"); self._log.configure(state="disabled")
        # Mirror to output_console.log, prefixing the tag since the file has no colours.
        lf=getattr(self,"_logfile",None)
        if lf is not None:
            try:
                pre=("[%s] "%tag) if tag else ""
                lf.write(pre+text+"\n")
            except Exception:
                MC.swallowed()
                self._logfile=None          # stop trying after the first failure

    def _log_warn(self,msg):
        """Red, non-fatal Output line. Thread-safe (goes through _log_q like every
        other worker-thread message)."""
        try: self._log_q.put(("warn",msg))
        except Exception: MC.swallowed()

    def _log_kind(self,kind,msg):
        """Thread-safe Output line of any _poll_log kind ("warn" red, "note" yellow, ...)."""
        try: self._log_q.put((kind,msg))
        except Exception: MC.swallowed()

    def _asset_miss_reason(self, ref):
        """Explain why an emitter `model` reference produced no sprite.

        SPR_RegisterSprite (renderergl1/tr_sprite.c:31-56) looks up the .spr name minus its
        extension as a shader and uses its first stage image. It fails in three ways:
          1. The shader exists but its `map` file isn't in the paks: ParseStage drops the stage
             (tr_shader.c:727-732) and nothing is drawn (tr_sprite.c:43-46). e.g. adam-firefill:
             sprites.shader senn_fire1/2 point at .tga files retail never shipped.
          2. No shader of that name: R_FindShader falls back to tr.defaultShader
             (tr_shader.c:3044-3047).
          3. The image exists but couldn't be decoded (Pillow missing, unusual TGA).
        """
        rl=(ref or "").replace("\\","/").strip().strip('"').lower()
        # An empty `model ""` falls through to the shader-lookup message, like `model none`.
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
        """Log one red line per emitter whose sprite couldn't be built, instead of silently
        drawing the viewer's fallback blob."""
        seen=[]
        for e in (ems or []):
            try: raw=(e.get("model") or "")
            except Exception: MC.swallowed(); continue
            ref=raw.replace("\\","/").strip().strip('"')
            # `model ""` (fx_smokeexample) and `model none` (fx/steamworks) both draw nothing
            # in-game; report them like any other miss. An emitter with no `model` line at all is
            # skipped.
            has_model_line="model" in e  # the tik has a `model <x>` line, even if x is ""
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
        """Log a red line for each .skd surface that got no texture. The manifest only holds
        resolved surfaces, so surfs minus its keys is the miss list.

        surf_shader is the opened .tik's own surface -> shader map, or None for a bare .skd.
        With a .tik, only surfaces it declares (exact name, glob, or `surface all`) count as
        missing: emitter carrier .tiks (e.g. electric_arc.tik on dummy3.skd) never skin their
        surfaces. Naming the declared shader makes a miss diagnosable (e.g. muzflash_bar.tik's
        muzmodel_bar shader isn't shipped in any .pk3)."""
        if not manifest or not surfs: return
        try: man=json.load(open(manifest,encoding="utf-8"))
        except Exception: MC.swallowed(); return
        import fnmatch
        low={k.lower() for k in man}
        miss=[s for s in surfs if s not in man and s.lower() not in low]
        sm={str(k).lower():v for k,v in (surf_shader or {}).items()}
        def _declared(sl):
            """Shader the opened .tik maps this surface to: exact name, longest matching glob, or
            `all`. None if the .tik doesn't mention it."""
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
            # .tik opened but silent about this surface: undeclared, not missing.
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
        """Reset the model-details panel to its empty state. Called when the viewer is closed
        (Esc or Clear built models) so it doesn't keep showing the previous model."""
        self._last_info=None
        try: self._info_title.configure(text="No model loaded",foreground=DIM)
        except Exception: MC.swallowed()
        try: self._info_stats.configure(text="")
        except Exception: MC.swallowed()
        try:
            t=self._tag_text
            t.configure(state="normal"); t.delete("1.0","end"); t.configure(state="disabled")
        except Exception: MC.swallowed()
        try:
            for w in self._reopen_bar.winfo_children(): w.destroy()
        except Exception: MC.swallowed()
        self._info_refit()

    def _update_info(self, path, stdout, html_path=None):
        stem=os.path.splitext(os.path.basename(path))[0]
        if html_path is None: html_path=self._html_out_path(path)
        self._last_info=(path,stdout,html_path)            # re-rendered from this HTML on theme toggle
        bones_n=""; anim_names=[]
        for line in stdout.splitlines():
            line=line.strip()
            if line.startswith("-") and "bones," in line and "surfaces" in line: bones_n=line
            if "animation(s):" in line: anim_names=line.split(":",1)[-1].strip().split(", ")
        tags_parsed=[]; surf_names=[]
        try:
            html=open(html_path,encoding="utf-8").read()
            # Brace-balanced extraction of the DATA object (a regex breaks on nested [] in "pos").
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
        except Exception: MC.swallowed()
        # Cache-hit opens have no build stdout, so rebuild the "- N bones, M surfaces" line from
        # the parsed DATA.
        if not bones_n and (tags_parsed or surf_names):
            nb=sum(1 for tg in tags_parsed if tg.get("kind")=="bone")
            bones_n=f"- {nb} bones, {len(surf_names)} surfaces"
        for w in self._reopen_bar.winfo_children(): w.destroy()
        self._info_title.configure(text=stem,foreground=ACCENT)
        self._info_stats.configure(text=bones_n+("  .  "+str(len(anim_names))+" anims" if anim_names and anim_names[0] else ""))
        # Selectable tag/bone list, coloured like the viewer's legend.
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
            info_button(self,"rebuild","Rebuild",self._rebuild_shown,
                        "Build this model's viewer again from its files\n(ignores the saved HTML)").pack(side="left")
            info_button(self,"browser","Browser",lambda p=html_path:self._open_in_browser(p),
                        "Open the viewer page in your external browser").pack(side="left",padx=(4,0))
            if path.lower().endswith(".tik") and os.path.isfile(path):
                info_button(self,"file",".tik",lambda p=path:self._launch_with("text_editor","text editor","Text Editor",p),
                            "Open the model's .tik in your Text Editor\n"+path).pack(side="left",padx=(4,0))
        self._info_refit()

    def _rebuild_shown(self):
        """The details pane's Rebuild: build what it shows again (the last build, as Open
        Viewer re-runs it), ignoring a saved HTML, as right-click > Rebuild does; the open
        page is closed first so the new one really loads."""
        lb=getattr(self,"_last_build",None)
        if not lb:
            self._log_line("Nothing has been built yet to rebuild.","err"); return
        if self._viewer_open_busy(): return
        self._run_opts={"force":True}
        self._close_viewer()
        self._load(*lb)

    # ---- embedded 3D viewer pane -----------------------------------------------
    def _ensure_webview(self):
        """Create the embedded WebView2 in the middle pane on first use. Returns True when it
        is ready; any failure (package missing, no runtime, .NET init error) is logged and
        returns False so the caller falls back to the browser."""
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
            self._hook_embed_drop()      # stop the pane hijacking file drops (see below)
            return True
        except Exception as e:
            MC.swallowed()
            self._log_line(f"(embedded viewer unavailable: {e}; using browser)","dim")
            self._webview=None
            return False

    # --- embedded-pane drag & drop --------------------------------------
    # WebView2 navigates to an externally dropped file by default, which downloads a
    # .skd/.tik. Three independent guards:
    #   1) AllowExternalDrop=False: Chromium refuses the drop.
    #   2) WinForms DragEnter/DragDrop on the host controls: a drop that falls through loads
    #      like a drop anywhere else in the window (_drop_paths -> _poll_log).
    #   3) A JS guard in every page for old runtimes without (1): it preventDefault()s the
    #      drop and posts a message so a hint is logged.
    # Runs once per webview, retrying until the async core init finishes.
    def _hook_embed_drop(self,_tries=0):
        wv=self._webview
        if wv is None or getattr(self,"_embed_drop_hooked",False): return
        if getattr(wv,"core",None) is None:            # WebView2 still initialising
            if _tries<150: self.after(200,lambda:self._hook_embed_drop(_tries+1))
            return
        self._embed_drop_hooked=True
        try: wv.web.AllowExternalDrop=False            # 1) no navigate-on-drop
        except Exception: MC.swallowed()
        try:                                           # 2) catch the drop ourselves
            from System.Windows.Forms import DataFormats,DragDropEffects
            def _enter(s,a):
                try:
                    if a.Data.GetDataPresent(DataFormats.FileDrop): a.Effect=DragDropEffects.Copy
                except Exception: MC.swallowed()
            def _drop(s,a):
                try:
                    for p in a.Data.GetData(DataFormats.FileDrop):
                        if str(p).lower().endswith((".skd",".tik")): self._drop_paths.append(str(p))
                except Exception: MC.swallowed()
            self._wv_drag_cbs=(_enter,_drop)           # pythonnet: keep delegates alive
            for c in (getattr(wv,"web",None),getattr(wv,"control",None)):
                if c is None: continue
                try: c.AllowDrop=True; c.DragEnter+=_enter; c.DragDrop+=_drop
                except Exception: MC.swallowed()
        except Exception: MC.swallowed()
        js=("(function(){if(window.__mohaaDropGuard)return;window.__mohaaDropGuard=1;"
            "function s(e){e.preventDefault();e.stopPropagation();"
            "if(e.dataTransfer)e.dataTransfer.dropEffect='none';}"
            "window.addEventListener('dragover',s,true);"
            "window.addEventListener('dragenter',s,true);"
            "window.addEventListener('drop',function(e){s(e);"
            "try{if(window.chrome&&chrome.webview)chrome.webview.postMessage('mohaa-drop-blocked');}catch(_){}"
            "},true);})();")
        try: wv.core.AddScriptToExecuteOnDocumentCreatedAsync(js)   # 3) every future page
        except Exception: MC.swallowed()
        try: wv.core.ExecuteScriptAsync(js)                         #    and the current one
        except Exception: MC.swallowed()
        try:
            def _msg(s,a):
                try: m=a.TryGetWebMessageAsString()
                except Exception: MC.swallowed(); return
                try:
                    if m=="mohaa-drop-blocked":
                        self._log_q.put(("dim","(the 3D pane can't take drops here - drop onto the file tree or console instead)"))
                    elif m=="mohaa-close":
                        # Viewer Esc: revert the pane to the start page. This callback runs on the WebView2/COM
                        # thread, where touching the control crashes the process, so hand it to the Tk main
                        # thread via the queue.
                        self._log_q.put(("closeview",None))
                    elif m and m.startswith("mohaa-ang "):
                        # Placement dial moved: persist pitch/yaw/roll on the Tk main thread (same thread rule
                        # as "mohaa-close").
                        self._log_q.put(("setang",m.split(" ",1)[1]))
                    elif m and m.startswith("mohaa-renderer "):
                        # The page's Display > WebGL toggle: save it on the Tk main thread.
                        self._log_q.put(("setrenderer",m.split(" ",1)[1]))
                    elif m and m.startswith("mohaa-anim "):
                        # The viewer wants an animation the page wasn't built with.
                        p=m.split(" ",2)
                        self._build_anim(p[1], p[2] if len(p)>2 else p[1])
                    elif m and m.startswith("mohaa-attach "):
                        # Attach panel: the viewer wants a model's geometry.
                        self._build_attach(m.split(" ",1)[1].strip())
                    elif m=="mohaa-attach-models":
                        # The page requests the model list on boot (no navigation-timing race); a page opened
                        # in a plain browser never asks, so the panel stays hidden there.
                        self._send_attach_models()
                except Exception as e:
                    MC.swallowed()
                    self._log_q.put(("dim",f"(viewer message: {e})"))
            wv.core.WebMessageReceived+=_msg
            self._wv_msg_cb=_msg                        # keep delegate alive
        except Exception: MC.swallowed()

    # --- on-demand animation builds -------------------------------------------
    # A character can reach over a thousand animations through its $include chain, so the
    # page ships only the menu. Clicking an animation it doesn't hold posts
    # `mohaa-anim <id> <name>`; the launcher extracts that .skc, runs mohaa_view.py
    # --animbuild, and writes the solved frames beside the HTML as a<id>.js. The page loads
    # it with a <script> tag (allowed on file://, unlike fetch/XHR). Built files persist, so
    # each animation is built only once.
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
    # The viewer's attach panel hangs any model off any bone. Each model's geometry is built
    # once from the loaded paks and cached beside the page as at<key>.js. Launcher-only: a
    # page opened in a plain browser never receives MOHAA_ATTACH_MODELS, so the panel stays
    # hidden.
    def _attach_key(self, vpath):
        # "attach2|": attachments built before they carried their load_scale ("ls") are rebuilt
        return MTX._cache_id("attach2|"+(vpath or "").lower()) if MTX is not None \
               else hashlib.blake2s(("attach2|"+(vpath or "").lower()).encode("utf-8","replace"),
                                    digest_size=6).hexdigest()

    def _send_attach_models(self):
        try:
            files=sorted({p for p,_k in (self._all_files or [])})
            self._log_q.put(("js","try{MOHAA_ATTACH_MODELS("
                                 +json.dumps(files,separators=(",",":"))+")}catch(e){}"))
        except Exception as e:
            MC.swallowed()
            self._log_q.put(("dim",f"(attachment model list unavailable: {e})"))

    def _build_attach(self, vpath):
        if not vpath: return
        if not self._anim_outdir:
            self._log_q.put(("err","No output folder for attachments - reopen the model")); return
        key=self._attach_key(vpath)
        jp=os.path.join(self._anim_outdir,"at"+key+".js")
        if os.path.exists(jp) and os.path.getsize(jp)>0:
            # Already built (this session or earlier): hand it straight back.
            self._log_q.put(("js",f"try{{MOHAA_ATTACH_LOAD({json.dumps(key)},{json.dumps(vpath)})}}catch(e){{}}"))
            return
        if key in self._attach_busy:
            return
        self._attach_busy.add(key)
        threading.Thread(target=self._build_attach_work,args=(vpath,key),daemon=True).start()

    def _build_attach_work(self, vpath, key):
        """Worker thread: build one attachment's geometry (at<key>.js).

        Attachment builds run one at a time: each keeps its parts, idle animation and scale
        in self._attach_* and extracts into the shared _attach folder, so two builds running
        at once would hand one model's settings to the other's build."""
        with self._attach_lock:
            self._build_attach_work_locked(vpath, key)

    def _build_attach_work_locked(self, vpath, key):
        try:
            if self._vfs is None:
                self._log_q.put(("err","Paks are still loading - try the attachment again in a moment")); return
            self._log_q.put(("dim",f"Resolving attachment {vpath} ..."))
            tdir=os.path.join(self._tmp,"_attach")
            os.makedirs(tdir,exist_ok=True)
            self._attach_idle=None
            self._attach_skelvfs=None; self._attach_tikmap=None; self._attach_parts=[]
            self._attach_ls=1.0
            skd_path=self._extract_attach_files(vpath,tdir)
            if not skd_path:
                self._log_q.put(("err",f"{vpath}: no .skd geometry found for this model"))
                self._log_q.put(("js",f"try{{MOHAA_ATTACH_FAIL({json.dumps(key)},"
                                      f"{json.dumps('no .skd geometry found')})}}catch(e){{}}")); return
            manifest=None
            if MTX is not None and self._tex_ready and self._vfs is not None:
                try:
                    import mohaa_view as MV
                    # Every assembled part's surfaces, de-duplicated in order (head/hands have their own).
                    surfs=[]
                    for _sp in [skd_path]+self._attach_parts:
                        try: surfs+=[s["name"] for s in MV.parse_skd(_sp)["surfaces"]]
                        except Exception: MC.swallowed()
                    _seen=set(); surfs=[x for x in surfs if not (x in _seen or _seen.add(x))]
                    manifest=os.path.join(tdir,"_tex_"+key+".json")
                    # Resolve against the .skd's VFS path (the tik index is keyed by .skd path) and let the
                    # attachment's own setup{} win, as the main model build does. A .tik path would fall back
                    # to the sibling-folder guess and pick up an unrelated `material1` shader.
                    tex_key=self._attach_skelvfs or vpath
                    local_TI=dict(self._TI); allpairs=[]
                    if self._attach_tikmap:
                        try:
                            local_TI.update(self._attach_tikmap)
                            for v in self._attach_tikmap.values(): allpairs+=v
                            if allpairs:
                                local_TI[tex_key]=allpairs; local_TI[tex_key.lower()]=allpairs
                        except Exception: MC.swallowed()
                    nt,ns=MTX.write_textures_manifest(self._vfs,tex_key,surfs,self._SH,local_TI,
                                                      manifest,global_surf=self._GS,
                                                      shader_props=self._PROPS,
                                                      editor_index=self._ED,log=self._log_kind)
                    self._log_q.put(("dim",f"- attach textures: {nt}/{ns} surfaces"))
                    if nt<ns:
                        self._report_surface_misses(manifest,surfs,
                                                    dict(allpairs) if self._attach_tikmap else None)
                    if nt==0: manifest=None
                except Exception as e:
                    MC.swallowed()
                    self._log_q.put(("dim",f"(attachment textures skipped: {e})")); manifest=None
            cmd=[self._pyexe,VIEWER,skd_path,"--attachbuild="+skd_path,
                 "--attachkey="+key,"--attachout="+self._anim_outdir,"--no-open"]
            if manifest: cmd.append("--textures="+manifest)
            if getattr(self,"_attach_idle",None): cmd.append("--attachidle="+self._attach_idle)
            for _pt in getattr(self,"_attach_parts",[]): cmd.append("--attachpart="+_pt)
            cmd.append("--attachscale=%g"%(getattr(self,"_attach_ls",1.0) or 1.0))
            p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",env=MC.child_env(),timeout=180,**NOWIN)
            for line in (p.stdout or "").splitlines():
                if line.strip(): self._log_q.put(("stdout",line))
            jp=os.path.join(self._anim_outdir,"at"+key+".js")
            if p.returncode!=0 or not os.path.exists(jp):
                for line in (p.stderr or "").splitlines()[-6:]:
                    if line.strip(): self._log_q.put(("err",line))
                self._log_q.put(("js",f"try{{MOHAA_ATTACH_FAIL({json.dumps(key)},"
                                      f"{json.dumps('build failed - see Output')})}}catch(e){{}}")); return
            # The tik's `setup { scale N }` is deliberately not sent: it's an import factor
            # (static_airtank.tik: 0.65), not an attached model's in-game scale, which is 1.
            self._log_q.put(("js",f"try{{MOHAA_ATTACH_LOAD({json.dumps(key)},{json.dumps(vpath)})}}catch(e){{}}"))
        except subprocess.TimeoutExpired:
            self._log_q.put(("err",f"{vpath}: attachment build timed out"))
            self._log_q.put(("js",f"try{{MOHAA_ATTACH_FAIL({json.dumps(key)},"
                                  f"{json.dumps('timed out')})}}catch(e){{}}"))
        except Exception as e:
            MC.swallowed()
            self._log_q.put(("err",f"{vpath}: {e}"))
            self._log_q.put(("js",f"try{{MOHAA_ATTACH_FAIL({json.dumps(key)},"
                                  f"{json.dumps(str(e)[:120])})}}catch(e){{}}"))
        finally:
            self._attach_busy.discard(key)

    def _extract_attach_files(self, vpath, tdir):
        """Extract one model from the paks into tdir and return its .skd path.

        A .tik names its geometry via `path`/`skelmodel`; a .skd is taken as-is. Files are
        written into tdir by basename, so an entry name can't escape it."""
        low=(vpath or "").lower()
        want=None
        parts=[]; txt=""
        # One part -> its VFS path. The `path` may already be in the skelmodel token, or be
        # stale, so fall back to a basename sweep.
        def _part_vfs(_base,_skel):
            if not _skel: return None
            w=("/".join(x for x in [(_base or "").strip("/"),_skel.strip("/")] if x)).lower()
            if self._vfs.exists(w): return w
            cands=[_skel.lower()]+[n for n in self._vfs.names()
                                   if n.endswith("/"+os.path.basename(_skel).lower())]
            return next((c for c in cands if self._vfs.exists(c)),None)
        if low.endswith(".tik"):
            raw=self._vfs.read(vpath)
            if raw is None: return None
            try:
                import mohaa_view as MV
                txt=MTX.expand_tik_includes(raw.decode("latin-1","replace"),self._vfs)
                parts=MV.parse_tik_skelmodels(txt)
                base,skel=(parts[0] if parts else MV.parse_tik_setup_head(txt))
            except Exception:
                MC.swallowed()
                return None
            if not skel: return None
            want=_part_vfs(base,skel)
            # This .tik's own surface -> shader map for the texture pass (the global tik index is
            # keyed by .skd path, so a .tik path would never match).
            try: self._attach_tikmap=MTX.parse_tik_setup(txt)
            except Exception: MC.swallowed(); self._attach_tikmap=None
            # its setup `scale` (load_scale, $include'd files too: a player's is 0.52 from
            # models/player/base/include.txt): the game multiplies its verts by it
            try: self._attach_ls=MV.parse_tik_scale(txt)
            except Exception: MC.swallowed(); self._attach_ls=1.0
        elif low.endswith(".skd"):
            want=vpath
        if not want: return None
        self._attach_skelvfs=want          # the key build_tik_index uses
        data=self._vfs.read(want)
        if data is None: return None
        target=os.path.join(tdir,os.path.basename(want))
        MC.atomic_write_bytes(target,data)
        # Every other skelmodel the .tik lists. A player/human model is several meshes (e.g.
        # german_officer.skd + head2.skd + hand.skd + officer_hat.skd) whose bones merge into one
        # skeleton (MV.merge_skds), as in the main build.
        for (_pb,_ps) in parts[1:]:
            _pv=_part_vfs(_pb,_ps)
            if not _pv: 
                self._log_q.put(("dim",f"(attachment part not found: {_ps})")); continue
            _pd=self._vfs.read(_pv)
            if not _pd: continue
            _pt=os.path.join(tdir,os.path.basename(_pv))
            MC.atomic_write_bytes(_pt,_pd)
            self._attach_parts.append(_pt)
        if self._attach_parts:
            self._log_q.put(("dim","- attach parts: "+", ".join(
                [os.path.basename(target)]+[os.path.basename(p) for p in self._attach_parts])))
        # Idle .skc: the model's rest pose, from the tik's `idle` animation if it has one, else
        # the .skd's own stem.
        self._attach_idle=None
        cands=[]
        if low.endswith(".tik"):
            # A TIKI model's rest pose is frame 0 of an animation; without one every bone gets an
            # identity rotation and the mesh folds in on itself. Player models define `idle` in an
            # $include'd file under a `$path` scope (anims_shared.txt: scripted/flak88/offic_idle.skc
            # relative to models/human/animation), so use build_anim_catalog, which applies those
            # scopes. A plain `idle X.skc` regex is kept as a fallback.
            try:
                _cat=MTX.build_anim_catalog(txt,self._vfs,vpath)
                _an=_cat.get("anims") or []
                _pick=(next((a for a in _an if str(a.get("n","")).lower()=="idle"),None)
                       or next((a for a in _an if str(a.get("n","")).lower().startswith("idle")),None))
                if _pick and _pick.get("s"):
                    _sd=self._vfs_read_skc(_pick["s"])
                    if _sd:
                        _ip=os.path.join(tdir,os.path.basename(_pick["s"].replace("\\","/")))
                        MC.atomic_write_bytes(_ip,_sd)
                        self._attach_idle=_ip
                        self._log_q.put(("dim",f"- attach pose: {_pick['n']} -> {_pick['s']}"))
            except Exception as _e:
                MC.swallowed()
                self._log_q.put(("dim",f"(attachment pose lookup failed: {_e})"))
            try:
                m=re.search(r"^\s*idle\s+(\S+\.skc)", txt, re.M|re.I)
                if m: cands.append(m.group(1).strip('"'))
            except Exception: MC.swallowed()
        if self._attach_idle: return target
        cands.append(os.path.splitext(os.path.basename(want))[0]+".skc")
        d0="/".join(want.split("/")[:-1])
        for c in cands:
            c=c.replace("\\","/").lstrip("/")
            for cand in ((d0+"/"+c) if d0 else c, c):
                if self._vfs.exists(cand):
                    sd=self._vfs.read(cand)
                    if sd:
                        ip=os.path.join(tdir,os.path.basename(cand))
                        MC.atomic_write_bytes(ip,sd)
                        self._attach_idle=ip
                    break
            if self._attach_idle: break
        return target

    def _ensure_anim_ctx(self):
        """Recreate what's needed to solve an animation after a cached open (which extracts
        nothing): the .tik, its catalogue and every skelmodel it assembles, so the solved
        animation targets the same merged bone list the page was built with."""
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
                MC.atomic_write_bytes(tik,d)
            raw=open(tik,"r",encoding="latin-1",errors="replace").read()   # match the VFS codec
            cat=MTX.build_anim_catalog(raw,self._vfs,entry)
            if not cat.get("anims"): return False
            MC.atomic_write_text(tik,MTX.expand_tik_includes(raw,self._vfs),errors="replace")
            tdir=os.path.dirname(tik)
            for (pp,ps) in (MV.parse_tik_skelmodels(raw) or []):
                ps=(ps or "").replace("\\","/").strip().strip('"')
                pp=(pp or "").replace("\\","/").strip().strip('"')
                if not ps: continue
                pv=self._resolve_skel_vfs(ps,pp,entry)
                if not pv: continue
                dd=self._vfs.read(pv)
                if dd:
                    MC.atomic_write_bytes(os.path.join(tdir,os.path.basename(ps)),dd)
            cf=os.path.join(self._tmp,"animcat_"+re.sub(r"[^A-Za-z0-9_.-]","_",
                            os.path.basename(entry))+".json")
            MC.atomic_write_text(cf,json.dumps(cat,separators=(",",":")))
            self._animcat=cat; self._animcat_file=cf; self._animcat_for=tik
            self._log_q.put(("dim",f"animation catalogue rebuilt for {os.path.basename(entry)} "
                                  f"({len(cat['anims'])} animations)"))
            return True
        except Exception as e:
            MC.swallowed()
            self._log_q.put(("dim",f"(animation catalogue rebuild failed: {e})")); return False

    def _movement_donor(self, ent, srcdir):
        """Extract a movement-slot .skc to supply the legs for an action animation; return its
        path or None.

        Torso animations (e.g. weapon_bar/bar_reload.skc) have no leg channels or "Bip01 pos":
        in-engine they are action animations blended over a movement animation, which fills the
        missing channels (skelAnimStoreFrameList_c, GetSlerpValue/GetLerpValue3). Played alone,
        the legs fall back to the rest template and render dead straight.

        The <weapon>_<stance>_hit* pain animations are full-body and hold that weapon's idle
        stance, so the donor is the first such alias in the catalogue, falling back to any
        weapon's <stance>_hit*. Only frame 0 is used."""
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
                MC.atomic_write_bytes(dp,d)
            self._log_q.put(("dim",f"  movement slot: {don.get('n')}  ({don.get('s','')})"))
            return dp
        except Exception as e:
            MC.swallowed()
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
                MC.atomic_write_bytes(sp,d)
            os.makedirs(self._anim_outdir,exist_ok=True)
            # Facial sibling: e.g. scripted/smoking pairs lightup.skc with lightupMORPH.skc, listed in
            # the .tik as separate animations (smoking01 / smoking_lightup_face). Build the face entry
            # in the same child run so it gets its own cached sidecar and "built" marker.
            also=[]; face_stem=None
            _s=(ent.get("s") or "")
            if _s.lower().endswith(".skc") and not _s[:-4].upper().endswith("MORPH"):
                _sib=_s[:-4]+"MORPH.skc"
                # Prefer a catalogue row: it has an id, so the face entry gets built too.
                for _e2 in self._animcat["anims"]:
                    if (_e2.get("s") or "").lower()==_sib.lower() and _e2.get("id")!=aid:
                        _d2=self._vfs_read_skc(_e2.get("s"))
                        if _d2:
                            MC.atomic_write_bytes(os.path.join(src,_e2["id"]+".skc"),_d2)
                            also.append(_e2["id"]); face_stem=_e2["id"]
                        break
                if face_stem is None:
                    # No catalogue row (new_generic_human.tik omits smoking_throwaway_face although
                    # throwawayMORPH.skc ships): read it straight from the paks so the body still gets its
                    # face layer.
                    _d3=self._vfs_read_skc(_sib)
                    if _d3:
                        face_stem=aid+"_face"
                        MC.atomic_write_bytes(os.path.join(src,face_stem+".skc"),_d3)
            legs=self._movement_donor(ent,src)
            # One --animbuild carrying every id, comma-separated (the flag takes a list).
            cmd=[self._pyexe,VIEWER,self._animcat_for,
                 "--animcat="+self._animcat_file,
                 "--animbuild="+",".join([aid]+also),
                 "--animsrc="+src,"--animout="+self._anim_outdir,"--no-open"]
            if face_stem: cmd.append("--animpair="+aid+":"+face_stem)
            if legs: cmd.append("--animlegs="+legs)
            p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",env=MC.child_env(),timeout=180,**NOWIN)
            # Relay the child's own "!" failure text to the viewer instead of a generic message
            # (e.g. "drives none of this skeleton's 72 bones" means it can never work). The
            # animation-name prefix is stripped; the viewer shows the .skc path beside it.
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
            # Queued, not called directly: ExecuteScriptAsync must run on the Tk/UI thread.
            self._log_q.put(("js",f"try{{MOHAA_ANIM_LOAD({json.dumps(aid)})}}catch(e){{}}"))
            for _a2 in also:
                if os.path.exists(os.path.join(self._anim_outdir,"a"+_a2+".js")):
                    # Mark the facial entry as built in the drop-down without selecting it.
                    self._log_q.put(("js",f"try{{MOHAA_ANIM_HAVE({json.dumps(_a2)})}}catch(e){{}}"))
        except subprocess.TimeoutExpired:
            self._log_q.put(("err",f"{name}: build timed out"))
            self._log_q.put(("js",f"try{{MOHAA_ANIM_FAIL({json.dumps(aid)},'build timed out')}}catch(e){{}}"))
        except Exception as e:
            MC.swallowed()
            self._log_q.put(("err",f"{name}: {e}"))
            self._log_q.put(("js",f"try{{MOHAA_ANIM_FAIL({json.dumps(aid)},'build error')}}catch(e){{}}"))
        finally:
            self._anim_busy.discard(aid)

    def _embed_js(self,js):
        """Fire-and-forget JS into the embedded viewer page. No-op until the WebView2 core has
        finished its async init."""
        wv=self._webview
        if wv is None: return
        try:
            core=getattr(wv,"core",None)
            if core is not None: core.ExecuteScriptAsync(js)
        except Exception: MC.swallowed()

    def _embed_merge_ui(self):
        """Hide the embedded viewer's own Theme/Shortcuts row (the launcher's buttons drive both)
        and sync its theme. Called twice after load since the page may still be parsing."""
        light="true" if self._theme=="light" else "false"
        self._embed_js(
            "try{var b=document.getElementById('bTheme');"
            "if(b&&b.closest('.sect'))b.closest('.sect').style.display='none';"
            f"if(typeof setTheme==='function')setTheme({light});}}catch(e){{}}")

    def _close_viewer(self):
        """Revert the viewer pane to the start placeholder, as on a fresh launch.

        Must run on the Tk main thread: the viewer's Esc arrives via _log_q -> _poll_log, never
        directly from the WebView2 message callback (which would crash). Leaves the _embed_on
        preference alone. No-op when nothing is open."""
        if self._webview is not None:
            wv=self._webview; self._webview=None
            self._embed_drop_hooked=False              # re-hook drops on a future webview
            try: wv.pack_forget()
            except Exception: MC.swallowed()
            try: wv.destroy()
            except Exception: MC.swallowed()
        self._embed_url=None
        # Keep _last_build so "Open Viewer" can reopen the model instantly from its cached HTML;
        # only the details panel and per-open state are cleared. (Clear built models clears
        # _last_build itself.)
        self._last_info=None; self._anim_outdir=None; self._attach_busy=set()
        self._clear_info()          # details panel back to "No model loaded"
        # Reset the status bar too, which would otherwise still read "Viewing <name>".
        try: self._set_status("Ready")
        except Exception: MC.swallowed()
        try:
            if not self._view_placeholder.winfo_ismapped():
                self._view_placeholder.pack(fill="both",expand=True)
        except Exception:
            MC.swallowed()
            try: self._view_placeholder.pack(fill="both",expand=True)
            except Exception: MC.swallowed()

    def _toggle_embed(self):
        self._save_opts()
        if not self._embed_on.get() and self._webview is not None:
            try: self._webview.destroy()
            except Exception: MC.swallowed()
            self._webview=None
            self._embed_drop_hooked=False              # re-hook drops on a future webview
            self._view_placeholder.pack(fill="both",expand=True)
        elif self._embed_on.get() and self._embed_url and self._ensure_webview():
            try: self._webview.load_url(self._embed_url)
            except Exception: MC.swallowed()

    def _open_in_browser(self,path):
        import webbrowser, pathlib
        # as_uri() percent-encodes; a hand-built file:// URL breaks on '#', '%' and non-ASCII.
        webbrowser.open(pathlib.Path(os.path.abspath(path)).as_uri())

    def _open_standalone(self,path):
        """Open a built viewer HTML in the default browser, without the #embed hash, so the
        page keeps its own Theme/Shortcuts buttons."""
        self._open_in_browser(path)

    def _reclaim_focus(self,e):
        """Take keyboard focus back from the embedded WebView2 when a launcher widget is clicked.

        When the page loads, Chromium takes Win32 keyboard focus and Tk marks itself unfocused.
        A later click on a Tk widget only records a pending focus target (there is no
        WM_ACTIVATE inside an already-active window), so keys keep going to the viewer.
        focus_force() makes the Win32 focus change. Clicks on the pane itself never reach Tk.
        Does nothing when Tk already has focus."""
        if self._webview is None: return
        w=e.widget
        try:
            if isinstance(w,str): w=self.nametowidget(w)   # bind_all can hand back a path name
        except Exception: MC.swallowed(); return
        try:
            if w is self._webview or str(w).startswith(str(self._webview)): return  # click landed on the pane
        except Exception: MC.swallowed()
        try:
            if self.focus_displayof() is None and w.winfo_exists(): w.focus_force()
        except Exception: MC.swallowed()

    def _watch_camera_stop(self):
        """Stop the embedded viewer's camera when the launcher takes over. A key or mouse button
        let go outside the viewer pane never reaches the page, so the camera would keep moving.
          - A click on any launcher widget (any button) stops it: _stop_view_camera.
          - A key pressed or let go while the launcher has the keyboard lets go of the keys the
            page holds: _release_view_keys. A drag or a fly-to in the page goes on.
          - On Windows the keyboard itself is also read every 100 ms while a viewer is open, so
            letting go of the last camera key lets go of the page's keys wherever that key-up
            went: _poll_camera_keys.
        The page also ignores auto-repeats of a key it has let go of, so a key still held when
        the camera stopped doesn't start it again until it is pressed anew.
        Called by App.__init__ and MapApp.__init__ (which doesn't run App's)."""
        for seq in ("<ButtonPress-1>","<ButtonPress-2>","<ButtonPress-3>"):
            self.bind_all(seq,self._stop_view_camera,add="+")
        for seq in ("<KeyPress>","<KeyRelease>"):
            self.bind_all(seq,self._release_view_keys,add="+")
        self._camkeys_down=False
        if KEY_IS_DOWN is not None and not getattr(self,"_camkeys_polling",False):
            self._camkeys_polling=True
            self.after(100,self._poll_camera_keys)

    def _stop_view_camera(self,e):
        """A click on the launcher stops the embedded viewer's camera: the key or mouse button
        moving it is let go here, where the page never hears it, so it would keep moving
        (the page's X does the same by hand). Both viewers' pages have stopCamera()."""
        if self._webview is None: return
        try:
            w=e.widget
            if isinstance(w,str): w=self.nametowidget(w)
            if w is self._webview or str(w).startswith(str(self._webview)): return
        except Exception: MC.swallowed()
        self._embed_js("try{if(typeof stopCamera==='function')stopCamera();}catch(e){}")

    def _release_view_keys(self,_e=None):
        """The viewer page lets go of the keys it holds (releaseCameraKeys, in both viewers'
        pages): the keyboard is somewhere else, so their key-ups would never reach it."""
        if self._webview is None: return
        self._embed_js("try{if(typeof releaseCameraKeys==='function')releaseCameraKeys();}catch(e){}")

    def _poll_camera_keys(self):
        """Every 100 ms while a viewer is open: once no camera key (CAMERA_VKS) is held any more,
        the page lets go of its keys. Only that change acts, so a key held in the page is never
        let go of early, and the page hears nothing while no key is down."""
        try:
            if self._webview is None: self._camkeys_down=False
            else:
                down=any(KEY_IS_DOWN(vk) for vk in CAMERA_VKS)
                if self._camkeys_down and not down: self._release_view_keys()
                self._camkeys_down=down
        except Exception: MC.swallowed()
        try: self.after(100,self._poll_camera_keys)
        except Exception: MC.swallowed()

    def _open_file(self,path):
        """Show a built viewer HTML in the embedded pane when available, else in the browser.
        The embedded URL carries #embed&theme=...&renderer=...(&ang=...) so the page boots
        straight into the in-launcher layout, theme and renderer before first paint."""
        # The on-demand animation cache is a folder beside the page, named after it:
        # <out>/allied_pilot_tik_view.html -> <out>/allied_pilot_tik_view/
        self._anim_outdir=os.path.splitext(os.path.abspath(path))[0]
        self._stamp_anim_cache()
        import pathlib
        base=pathlib.Path(os.path.abspath(path)).as_uri()   # percent-encoded; '#' safe
        if self._ensure_webview():
            try:
                url=base+"#embed&theme="+("light" if self._theme=="light" else "dark")
                url+="&renderer="+self._renderer()
                _ang=self.view_angles()
                if _ang: url+="&ang="+",".join(str(x) for x in _ang)
                self._webview.load_url(url); self._embed_url=url
                self._set_status(f"Viewing {os.path.basename(path)}")
                self.after(700,self._embed_merge_ui); self.after(2200,self._embed_merge_ui)
                return
            except Exception as e:
                MC.swallowed()
                self._log_line(f"(embed failed: {e}; opening in browser)","dim")
        self._open_in_browser(path)

    def _on_close(self):
        # Save the pane layout before anything is torn down.
        self._save_panes()
        # Dispose the WebView2 before tearing down Tk; letting it die in the <Destroy> cascade
        # crashes Python on exit.
        if self._webview is not None:
            wv=self._webview; self._webview=None
            try: wv.pack_forget()
            except Exception: MC.swallowed()
            try: wv.web.Dispose()
            except Exception: MC.swallowed()
        if getattr(self,"_restore_drop",None):
            try: self._restore_drop()
            except Exception: MC.swallowed()
        if self._tmp and os.path.isdir(self._tmp): shutil.rmtree(self._tmp,ignore_errors=True)
        lf=getattr(self,"_logfile",None)
        if lf is not None:
            try: lf.close()
            except Exception: MC.swallowed()
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
                    except Exception: MC.swallowed()
                    return 0
                try: return CallWP(self._old_wndproc,h,msg,wp,lp)
                except Exception: MC.swallowed(); return 0
            self._wndproc_cb=WNDPROC(py_wndproc)
            old=SetWL(hwnd,GWLP_WNDPROC,self._wndproc_cb)
            if not old: self._wndproc_cb=None; self._log_line("(drag-drop unavailable; use Browse)","dim"); return
            self._old_wndproc=old; shell32.DragAcceptFiles(hwnd,True)
            def _restore(*_):
                try: SetWL.argtypes=[HWND,ctypes.c_int,LONG_PTR]; SetWL(hwnd,GWLP_WNDPROC,self._old_wndproc)
                except Exception: MC.swallowed()
            self._restore_drop=_restore
            self.bind("<Destroy>",lambda e:_restore() if e.widget is self else None)
            self._log_line("Drag-and-drop ready - drop a .skd/.tik onto this window.","dim")
        except Exception as e:
            MC.swallowed()
            self._log_line(f"(drag-drop unavailable: {e}; use Browse)","dim")

def run_gui(make_app, app_name):
    """Run a launcher window to completion and return a process exit code.

    make_app: callable returning the Tk app (App or MapApp). app_name: log file stem.
    With the embedded pane, Tk runs on a .NET STA thread (WebView2 needs an STA COM
    apartment; tkwebview2's documented pattern) and falls back to this thread if that
    can't start. An exception that escapes start-up is logged with its traceback, shown
    in a message box (pythonw has no console) and turned into exit code 1."""
    init_runtime(app_name)
    result={"code":0}
    def _run():
        """Build the window and run its event loop; record and report a failure."""
        try:
            make_app().mainloop()
        except Exception as e:
            result["code"]=1
            LOG.critical("%s failed: %s",app_name,e,exc_info=True)
            msg=f"{app_name} could not start:\n{type(e).__name__}: {e}\n\nDetails: {MC.logs_dir()}"
            if sys.stderr is not None: sys.stderr.write("[FATAL] "+msg.replace("\n"," ")+"\n")
            try:
                r=tk.Tk(); r.withdraw(); messagebox.showerror(app_name,msg,parent=r); r.destroy()
            except Exception:
                MC.swallowed("no display for the error box")
    if WEBVIEW2 is not None:
        try:
            from System.Threading import Thread as _NetThread, ApartmentState as _ApState, ThreadStart as _TStart
            _t=_NetThread(_TStart(_run)); _t.ApartmentState=_ApState.STA
        except Exception:
            LOG.warning("no .NET STA thread; running Tk on the main thread",exc_info=True)
            _run()
        else:
            _t.Start(); _t.Join()
    else:
        _run()
    LOG.info("=== %s exiting (code %d) ===",app_name,result["code"])
    logging.shutdown()
    return result["code"]

if __name__=="__main__":
    init=None
    for a in sys.argv[1:]:
        if a.lower().endswith((".skd",".tik")) and os.path.exists(a): init=a; break
    _code=run_gui(lambda:App(initial_file=init),"mohaa_launcher")
    if WEBVIEW2 is not None:
        # pythonnet's CLR + WebView2 crash during normal interpreter shutdown, and all cleanup
        # already ran in _on_close, so exit immediately (with the real exit code).
        os._exit(_code)
    sys.exit(_code)

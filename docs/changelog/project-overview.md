# Project overview

MOHAA Model Viewer opens any *Medal of Honor: Allied Assault* model, including emitters,
FX scripts, explosions, animated characters, projectiles, weapons, vehicles and static
props, and shows it the way the game draws it. The goal is in-game parity, not an
approximation: behaviour is taken from the engine source
([OpenMOHAA](https://github.com/openmoh/openmohaa)) and checked frame by frame against
in-game footage. Where the two disagree, the footage wins and the notes say why.

The repository also holds the **MOHAA Map Viewer**, which opens `.bsp` and `.map` files
with the same launcher window, pak handling and embedded pane. This file covers the
Model Viewer and what both share; the Map Viewer has its own notes in
[map-viewer.md](map-viewer.md).

## Repository layout

| Path | Role |
|---|---|
| `MOH Model-Map Viewer (Windows x86-x64).bat` | Windows entry point for both programs. Uses the py launcher's default Python if it's 3.8+ with tkinter, else the newest suitable one on PATH or in the default install folders (Store aliases skipped); if there is none, asks Y/N to run the installer below. Then a menu picks the program (`bin/mohaa_envcheck.py menu`: 1 Map Viewer, 2 Model Viewer, Up / Down and Enter; exit 11 / 12, 10 to quit), skipped when a `.bsp` / `.map` / `.bak` or `.skd` / `.tik` is dropped on it. Then `mohaa_envcheck.py deps bin\libs --embed --log map|model` (Pillow and the embedded-pane packages vendored into `bin\libs`, WebView2 Runtime reported) and `mohaa_envcheck.py start`, which starts the program without a console and lets the window close once it is open; on an error it pauses once at the end. Generated with the `.sh` from one template by `tools/make_launchers.py` (see [hardening-notes.md](hardening-notes.md)). |
| `MOH Model-Map Viewer (Linux - Mac OS).sh` | Linux / macOS entry point for both programs: the same steps and the same menu, vendoring into `bin/libs-linux` (`bin/libs-mac`); reopens itself in a terminal when double-clicked in a Linux file manager. Bash 3.2 compatible (macOS). |
| `bin/mohaa_common.py` | Shared hardening helpers every script imports: output folder, rotating logs and `swallowed()`, crash hooks, atomic writes, damage-tolerant settings, the Pillow security floor and pixel limit, HTTP with retries, child-process environment. |
| `bin/mohaa_envcheck.py` | What the RUN files call: dependency checks and installs into the vendored libs folder (`python -m pip install --target`), verified by importing in a fresh process; the Windows embedded-pane checks. |
| `bin/libs`, `bin/libs-linux`, `bin/libs-mac` | Vendored Python packages, one folder per OS. Created by the RUN files; git-ignored; never touched by updates. |
| `tests/` | Regression tests and checks to run before shipping (see [development-workflow.md](development-workflow.md)). |
| `bin/mohaa_launcher.py` | Tkinter desktop app: pak loading and tree, build orchestration, embedded WebView2 pane, on-demand animation and attachment builds, settings, updater. |
| `bin/mohaa_view.py` | Model builder. Parses `.skd` / `.skb` / `.skc` / `.tik` / `.map`, solves the skeleton and IK, writes an `.obj`, and fills the page template (`_HTML_TEMPLATE`, all of the viewer's HTML/CSS/JS) with the model payload. Also holds the keyboard-shortcut window both viewers' pages use (`KEYS_JS` / `KEYS_CSS`), the keyboard it draws (`KX_LAYOUT`, `KX_CATS`) and the Model Viewer's shortcut table (`VIEWER_KEYS`). |
| `bin/mohaa_textures.py` | Pak virtual filesystem (`Vfs`), `.shader` index and render hints, texture resolution and `data:` URL encoding, `$include` expansion, and the animation catalogue (`build_anim_catalog`). |
| `bin/mohaa_map_*.py`, `bin/mohaa_bsp.py`, `bin/mohaa_entdefs.py` | The Map Viewer, a separate program built on the same launcher (`MapApp` subclasses `App`); see [map-viewer.md](map-viewer.md). |
| `bin/python_installer_updater.bat` | Windows setup for both viewers: installs a per-user Python suited to the Windows version and CPU, then the packages into `bin\libs`. Run by the RUN .bat on request (`/fromrun` skips its closing pause and only fills in missing packages), or on its own (refreshes them). |
| `docs/` | Privacy, security and licensing notices, `requirements.txt`, `version.txt` (read by the updater) and these notes. |
| `screenshots/` | The pictures in the README. |
| `output/` | Created at runtime beside `bin/`: both programs' configs (with `.bak`) and console logs, `logs/` (rotating program logs), built pages, `previous-versions/` (files replaced by updates), and the embedded pane's WebView2 folder (`webview2/`). Git-ignored. |

## How a model gets built

1. **Paks.** The launcher merges the chosen `.pk3` files into one case-insensitive
   `Vfs` (later paks override earlier ones), then indexes shaders, shader render hints
   and `.tik` files in the background.
2. **Open.** The model is extracted to a temp workspace (`%TEMP%/mohaaview_*`). A `.tik`
   has its `$include`s expanded and is written back so the builder sees the full text; a
   matching `.map` is extracted for the `setsize` box, each skelmodel's `.lod` (its level
   of detail curve) beside it, and the animation the `.tik` names `idle` (the page sizes
   the model by its bounds). The launcher writes a texture
   manifest (`--textures=`), the emitter sprite table (`--emittertex=`) and the animation
   catalogue (`--animcat=`).
3. **Build.** `mohaa_view.py <model> --no-open [...]` runs as a subprocess and writes
   `<stem>_skd_view.html` or `<stem>_tik_view.html` (plus `<stem>.obj`). The page is
   self-contained: textures are `data:` URLs and the model is an inline `DATA` object.
4. **Show.** The launcher loads the page in its WebView2 pane with
   `#embed&theme=...&renderer=...&ang=...` in the URL (read by a boot script in `<head>`), or in the
   default browser without the hash.
5. **On demand.** The page and launcher talk over `chrome.webview.postMessage`:

   | Page sends | Launcher does |
   |---|---|
   | `mohaa-anim <id> <name>` | runs `--animbuild=`, writes `<stem>_view/a<id>.js`, calls `MOHAA_ANIM_LOAD` (or `MOHAA_ANIM_FAIL`) |
   | `mohaa-attach-models` | replies with `MOHAA_ATTACH_MODELS` (the model list for attach-to-bone) |
   | `mohaa-attach <path>` | runs `--attachbuild=`, writes `at<key>.js`, calls `MOHAA_ATTACH_LOAD` / `MOHAA_ATTACH_FAIL` |
   | `mohaa-ang <p,y,r>` | saves the placement angles to the config |
   | `mohaa-renderer <gl\|2d>` | saves the renderer choice (the page's Display > WebGL toggle) and updates View > Viewer renderer |
   | `mohaa-close` | returns the pane to the start page |

   In the other direction the launcher runs page functions: `MOHAA_*` for built sidecars,
   `setTheme`, `setViewerAngles` and `setViewerRenderer`. A page opened in a normal browser
   has no host, so these features hide themselves.

## Caching and versions

- `VIEWER_REV` (mohaa_view.py) is baked into each page as `<!--mohaa-viewer-rev:N-->`.
  `VIEWER_REV_REQUIRED` (mohaa_launcher.py) is the oldest rev the launcher will reuse.
  Raise both together whenever the page or its sidecars change in a way a cached copy
  must pick up. History is in [CHANGELOG.md](CHANGELOG.md).
- A cached page is also rebuilt when any of the three `.py` files is newer than it.
- Sidecar folders carry a `.rev` stamp; a mismatch with `VIEWER_REV_REQUIRED` clears the
  cached `a<id>.js` / `at<key>.js` files once.
- `VERSION` (mohaa_launcher.py) and `docs/version.txt` must match on each release; Help →
  Check for updates compares them. Both viewers share the version and update together.

## The renderer in brief

- **Hybrid.** WebGL draws the grid and skinned mesh with a depth buffer; a 2D canvas on
  top draws particles, autosprite billboards, tag/bone nodes, labels and the setsize box.
  The launcher's View > Viewer renderer (or the page's Display > WebGL toggle) switches to
  the 2D renderer; with that selected or WebGL unavailable, `GLR` is null and
  `draw2DScene()` draws everything. Both paths are supported and need testing.
- **Particles.** Emitters are simulated on the CPU following `cg_tempmodels.cpp` /
  `cg_commands.cpp`: 10 Hz physics with interpolation, engine spawn shapes and velocity
  order, fade/scale/roll rules, `T_SWARM`, friction, collision. Volumetric smoke follows
  `cg_volumetricsmoke.cpp` (density ramp and decay, radius growth, wind, repulsion).
- **Sprites.** Sprite types follow `tr_sprite.c` (parallel, parallel_oriented, oriented,
  upright); world-space quads are drawn with perspective-correct strips and near-plane
  clipping. See [sprite-roll-rules.md](sprite-roll-rules.md).
- **Game cvars.** Display > game cvars (or `` ` ``) does some of the game's debugging cvars
  to the model: `sv_showbboxes` (its boxes, and a person's 19 hit spheres on the Bip01
  bones), `r_shownormals`, `r_uselod` (the game's level of detail by distance, per part,
  with a LOD slider and triangle counts) and the particle counts of `cg_showemitters`,
  `cg_showtempmodels` and `vss_showsources`. The build sends what they need: the vertex
  normals, each surface's collapse data and each part's LOD control (`DATA.lods`), the
  frames' radii, and what the game makes of the model as an entity (`DATA.game`: whether
  it is a character or a Sentient, where its setsize came from, its idle bounds).
  `CVAR_DEFAULTS` / `CVAR_ROWS` in the page hold the list. Everything stays inert at its
  default, so a page draws exactly as before until a cvar is set.
- **Shaders.** Resolved in Python into render hints (additive, alphaFunc, animMap,
  nextbundle + tcMod, deformVertexes autosprite/autosprite2/lightglow, distFade, spriteGen,
  spriteScale, rgbGen vertex) that the JS applies. A stage map missing from the paks is
  replaced by the shader's `qer_editorimage` or a same-named texture, with an Output note.

## Current state

- Version 1.0.001 (pre-release), with both viewers. `VIEWER_REV` 80; the Map Viewer's
  `MAP_VIEWER_REV` 105 and `INDEX_VERSION` 10. 1.0.001 is the hardening pass (see
  [hardening-notes.md](hardening-notes.md)); page output is unchanged.
- Windows is the main platform (embedded pane); macOS and Linux run the launchers through
  their `.sh` files and open pages in the browser.

## Known issues and open work

- **WebGL is new in practice.** Until rev 66 the WebGL renderer never ran in a WebGL2
  browser (its shaders didn't compile there), so every page drew with the 2D renderer.
  WebGL now matches 2D on synthetic test models (culling, texture orientation, shading),
  but real models have only been checked in 2D. If something differs, compare with
  View > Viewer renderer > 2D canvas.
- **No map data.** Map-placed effects' placement rotation and light grid aren't available,
  so the corona orbit is synthetic (off by default) and volumetric smoke lighting is
  fixed at the engine-neutral 1.0.
- **Bone names ending in a space.** Fifteen models have a bone whose name ends in a space
  (the garands' `m1garand `, the Opel truck's and sdkfz's tags, the colt clip, the hidden
  cabinets' doors, the German shepherd's weapon tags, one of the player's helpers). The
  builder trims names, so the animation's channel (`m1garand  rot`, with both spaces)
  never reaches the bone and it keeps no rotation: the garand stands upright instead of
  lying along X as in game, so its `sv_showbboxes` boxes (which are right) cross it. The
  engine takes a bone's channels from the names stored with the bone in the `.skd`
  (`ofsChannelNames`, registered by `LoadBoneFromBuffer2`, tiki_skel.cpp); matching
  through those, instead of trimming, would fix it. Trimming the channel names instead
  would merge `opel_opening.skd`'s two bones `exhaust ` and `exhaust  `.
- **Idea:** fold the Setsizes toggle and its edit pencil into one Display control.

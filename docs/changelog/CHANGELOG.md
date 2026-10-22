# Changelog

Revision history and notable fixes for the viewer, launcher and installer. The source
comments describe current behaviour only; the history behind it lives here. Entries are in
ascending order, so add new ones at the end of their section.

## Documentation (September 2026)

- Comments and docstrings across `bin/*.py` and the `.bat` files were rewritten to describe
  current behaviour, with OpenMOHAA source references kept. Revision notes and fix history
  were moved into this file. No code changed in that pass.
- Project notes added under `docs/changelog/` (overview, workflow, engine notes, emitter
  command reference, sprite-roll rules).
- README, SECURITY and THIRD_PARTY_NOTICES brought in line with the code: Python 3.8 is
  the minimum (Pillow 10.3 needs it), the Clear commands are in the File menu, a Contact
  section replaces the missing contact address, and tkwebview2 is listed as MIT.
- Privacy notice (`docs/PRIVACY.md` and `PRIVACY_TEXT` in mohaa_launcher.py): now lists the
  recent-files list among the stored settings, points to File (not Options) for the Clear
  commands, and sends questions to GitHub issues.
- `tcmod rotate` comments cite `RB_CalcRotateTexCoords` (renderergl1 `tr_shade_calc.c:1599-1631`)
  instead of renderergl2's `RB_CalcRotateTexMatrix`.

## Documentation (October 2026)

- README split for the two programs: a shared introduction and table of contents, then
  How To Install / Uninstall, MOHAA .tik Model Viewer and MOHAA .bsp Map Viewer, then the shared
  sections (Updating, Where Your Files Go, Privacy & Security, Licence & Legal, For
  Developers, Contact & Credits). Map Viewer screenshots in `screenshots/map1-4.jpg`.
- The Map Viewer's comments and docstrings were reviewed the way the Model Viewer's were
  in September: current behaviour only, OpenMOHAA references kept. Unused code removed:
  `terrain_square_tris` (mohaa_bsp.py), `_fmtv` (mohaa_map_view.py), `spawnflag_names`
  (mohaa_entdefs.py), and a duplicate `twosided` test in the cull check.
- SECURITY lists the Map Viewer's attack surfaces (`.bsp` and `.map` parsing, decompiled
  files, the map page); THIRD_PARTY_NOTICES notes the q3map and OpenMOHAA `/*QUAKED*/`
  derivations and that a decompiled map stays its author's work; requirements.txt,
  project-overview, development-workflow (Map Viewer checks, values that change together,
  two more batch-file pitfalls), engine-notes (the WebView2 folder) and map-viewer.md
  (damaged files, planned work) cover both programs.
- Privacy notice (`docs/PRIVACY.md`, `PRIVACY_TEXT`), dated 15 October 2026: it now lists
  four stored things, adding the embedded pane's `webview2` folder and the display choices
  pages keep in browser storage. The Map Viewer's wording is in `_PRIVACY_SWAPS`
  (mohaa_map_launcher.py), which rewraps the paragraphs it changes; two of its lines had
  run wider than the rest.

## Viewer page revisions (VIEWER_REV)

- rev 2: backdrop colour picker.
- rev 3: dead-GL-canvas backdrop fix.
- rev 4: GL `tcmod rotate` propeller spin; embed-hash boot (in-launcher layout and theme applied before first paint).
- rev 5: the same propeller spin in the 2D fallback path.
- rev 6: 2D propeller clamp (no corner tiling) and no flat shading (a transparent disc, not a square).
- rev 7: `DEFORM_LIGHTGLOW` coronas render as camera-facing billboards (autosprite), with an opt-in toward-eye push and synthetic placement orbit ("Corona orbit" toggle, `view.tilt`).
- rev 8: the LightGlow toward-eye push became always-on (pins the glow ~4u in front so it grows as the camera nears); size cap lifted for lightglow; the "Corona orbit" toggle gates only the placement swing.
- rev 9: the LightGlow pin is divided by the tik `load_scale` (`DATA.setsizeScale`), so a scale>1 corona no longer freezes on zoom.
- rev 10: corona orbit reworked: distance-gated (game units), zero beyond ~50u, logarithmic growth, capped near the origin; the orbit is a pure perpendicular swing that doesn't change glow size (tuning: `ORBIT_START` / `ORBIT_CAP` / `ORBIT_MAX` in `lightGlowCenter`).
- rev 11: corona scaling reverted to real-object perspective (no toward-eye pull): the glow grows by radius*focal/dist and reaches max size only at closest approach.
- rev 37: security hardening. The model payload and title are escaped for inline-`<script>` embedding (a .pk3 string containing `</script>` used to break out of the block), and the page carries a CSP pinning every source to self/file/data/blob with `connect-src 'none'`.
- rev 62: two new editors. (a) A model whose .tik declares no `setsize` (and has no sibling .map) shows a dimmed placeholder `setsize ( 0 0 0 ) ( 0 0 0 )` whose pencil creates the box and enables the Display > Setsizes toggle. (b) The placement-angle dial gained a pencil, so pitch/yaw/roll accept any value, not just the four quarter-turn detents.
- rev 63: attached models are textured like the model they hang off. The launcher resolves an attachment's surfaces against its own .tik (it had been passing a .tik path where a .skd path was needed, so muzflash.tik picked up an unrelated sibling's `material1`), and the `at<key>.js` sidecar carries the shader's render hints (additive, cull none, autosprite, animmap frames, alphaFunc). A muzzle flash now draws as an additive two-sided sprite instead of an opaque card.
- rev 64: attach-to-bone offsets are in engine world units (what a .tik or script `attachmodel` line carries) instead of the viewer's unscaled model units; calibrated in-game against 15cmcannon and 20mmflak (see `ATT_OFS`).
- rev 65: attached models are assembled and posed like the main build: `--attachpart` passes the head/hands/hat skelmodels a player .tik lists beside its body, merged onto one skeleton, and the bind pose is reported with its bone coverage so an unposed skeleton is flagged.
- rev 66: the WebGL renderer actually runs. Its shaders were GLSL ES 1.00 with `dFdx`, which a WebGL2 context rejects, so every page in a modern browser or WebView2 had silently fallen back to the 2D renderer; they're now compiled as GLSL ES 3.00 on WebGL2. WebGL also culled the wrong faces (it kept the ones the engine and the 2D path drop); it now culls `GL_FRONT` like `GL_Cull` (`tr_backend.c:137-175`). A Display > WebGL toggle switches between the renderers, remembered per browser, with WebGL the default. Also removed: the unused start-anim emitter schedule (`fxcmds` / `FXC`, never emitted since the schedule was retired) and a size clamp that never applied; the Corona orbit tooltip no longer mentions the toward-eye growth removed in rev 11.
- rev 67: the launcher can choose the renderer. The page reads `#renderer=gl|2d` from its boot hash (ahead of the browser's saved choice), exposes `setViewerRenderer()` so View > Viewer renderer switches the open page, and reports its own Display > WebGL toggle to the launcher (`mohaa-renderer gl|2d`) so both stay in sync.
- rev 68: attach-to-bone models draw in WebGL. The WebGL pass listed only the host's own surfaces (`DATA.surfRanges`) instead of the live list that includes attachments (`LSR`), so attachments showed only in 2D. Its index and UV buffers now follow attachments too (32-bit indices once the combined model passes 65535 vertices, re-cut whenever the surface list changes). Attached surfaces also get a vertex range, which fixes attached autosprite surfaces (a muzzle flash): WebGL threw an error on every frame and 2D never drew them. Attachments now also hide particles behind them in the 2D renderer.
- rev 69: translucent bases (`blendFunc blend`, e.g. barbed wire) are flagged `blend`. WebGL draws them after the opaque surfaces without depth writes, as the engine does for a blended stage (`tr_shader.c:1149-1153`), and the 2D renderer no longer darkens their see-through part into a grey box.
- rev 70: the keyboard shortcuts window (`H`) is a keyboard map, shared with the Map Viewer: a keyboard and mouse with every key the viewer uses coloured by kind (camera, playback, display, tag list, window, pop-up lists). Hovering a key, or pressing it, lists everything it does with every modifier and in which view; Shift / Ctrl / Alt (clicked or held) show their layer; Free-look / Tag-lock / Pop-up list switch the view (the page's camera mode is shown first); a search box and the category chips narrow it down; the list underneath has one column per section, each scrolling on its own, with a line between rows; hovering a row rings its keys and clicking a key finds its rows. One table, `VIEWER_KEYS`, feeds it and the launcher's `F1` window; the window itself is `KEYS_JS` / `KEYS_CSS`, built on first open. While it is open, keys are looked up instead of acting on the model (R used to reset the camera behind it, W to fly). Esc with it open closes only the window; it used to close the viewer too (in the launcher, back to the start page).

## Launcher cache floor (VIEWER_REV_REQUIRED)

VIEWER_REV_REQUIRED is raised to the live VIEWER_REV whenever cached pages or sidecars must be rebuilt.

- rev 3: dead-GL-canvas backdrop fix.
- rev 4: embed-hash boot (in-launcher layout and theme applied before first paint).
- rev 35: Display-panel placement-angle dial (pitch/yaw/roll) replaces the smoke-light slider; the page must read the `#ang=` boot hash.
- rev 36: drawn tick marks on that dial plus a `( pitch yaw roll )` readout.
- rev 37: pages built before the inline-`<script>` escaping and CSP hardening must be rebuilt.
- rev 58: load-time `surface <n> +nodraw` from the tik's `init{server{}}` / `setup{}` blocks; the surfaces `<select>` became a popup that stays open across toggles. Older cached DATA has no `tikNodraw` key.
- rev 59: sidecar animations carry their own `fx.surf` (frame commands the catalogue always had but the sidecar builder discarded). Older sidecars have no fx.
- rev 60: the attach-to-bone `<select>` became a searchable popup.
- rev 62: the setsize line and the placement-angle readout gained pencil editors (`#angEdit`).
- rev 63: `at<key>.js` attachment sidecars. Older ones hold a texture resolved the wrong way (the texture pass was given a .tik path where the tik index wants a .skd path) and carry no shader render hints. `_build_attach` serves existing sidecars straight from disk, so bumping this constant (which gates `_stamp_anim_cache`) is the only thing that clears them.
- rev 64: attachment offsets changed units to engine world units (what a .tik/script `attachmodel` line carries) instead of the viewer's unscaled model units.
- rev 65: attachment sidecars again: a multi-part model (player/human) cached before this holds only its body mesh, and a rigged one holds an unposed, folded skeleton.
- rev 66: pages built before the WebGL fixes never use WebGL and have no renderer toggle.
- rev 67: pages built before this ignore the launcher's renderer setting.
- rev 68: pages built before this don't draw attachments in WebGL.
- rev 69: pages and attachment sidecars built before this draw barbwire_long_pulse with a black background and the pulse_map models untextured.
- rev 70: pages built before this have the old shortcut table, and Esc there closes the viewer along with it.

## Launcher (mohaa_launcher.py)

- rev 62: saved placement angles are no longer snapped to the four quarter turns; the dial pencil editor accepts any angle and the typed value is kept.
- The self-contained `--app=` standalone-window mode was removed; drag-out and "Open in browser" always use the default browser.
- Pak extraction goes through `_safe_target()`. The old `os.path.join(tmp, *name.split("/"))` let a crafted entry name (`models/x/../../../Startup/pwn.bat`, or a bare `C:` component) write outside the temp workspace.
- The default text editor is seeded as an absolute path, and a config holding a bare command name (`notepad.exe`, `open`, `xdg-open`) is resolved against the system folders and rewritten. A fresh install used to fail with "The saved text editor program is not a valid file" on the first .tik open.
- A cache hit fills the model-details panel from the opened HTML; it used to keep showing the previous model's details.
- An open requested before the pak texture index finishes is queued and fired when the index is ready, so an untextured page is never built and cached.
- Clearing built models also resets the path bar and the remembered build, so Open Viewer can't point at a deleted page.
- Stale `.skb` skelmodel references fall back to the shipped `.skd` twin (flaregun, papers_o, wirecutters), as the engine does.
- `.spr` models given as a full path (`textures/effects/bang.spr` in explosion_tank) resolve to their shader; only basenames under `textures/sprites/` used to work.
- Emitter sprites that can't be built are reported in red in the Output pane instead of silently falling back to a white blob.
- The shader's `spriteScale` is shipped for every spritegen sprite, not just volumetric smoke (muzsprite / `*_spriteflash` were oversized).
- `deformVertexes lightglow` is shipped as a flag, so an `oriented` + lightglow sprite (fire_ring) renders camera-facing instead of as a flat quad that vanished edge-on.
- Attachment rest poses come from `build_anim_catalog` (which follows `$include` and `$path` scopes). The old `idle <file>.skc` regex couldn't find a player model's idle, so attached player models folded in on themselves.
- On-demand animation builds pass one `--animbuild=` with comma-separated ids; passing the flag twice made the second replace the first.
- The keyboard-shortcut window shows launcher and viewer keys side by side, so it fits on a 768px-high screen.
- Updates download the release tag for the version the check reported (`v<version>`), so the files installed are exactly that version; if the tag doesn't exist, the `main` branch zip is used as before.
- View > Viewer renderer (WebGL, the default, or 2D canvas) sets the renderer for every page and switches the open one; it follows the page's own Display > WebGL toggle too.
- The Theme submenu was removed from Options; View > Toggle Dark / Light (Ctrl+T) covers it.
- Pak entries over 192 MB are skipped when extracting to the workspace or reading a `.map`, as they already were for reads through the pak index.
- New yellow Output lines (`note`) for problems that were worked around, such as a missing shader map replaced by a texture found elsewhere in the paks.
- The embedded pane's WebView2 keeps its browser files in `output/webview2` (the `WEBVIEW2_USER_DATA_FOLDER` environment variable, set before the pane is created). tkwebview2 names no folder, so WebView2 created `pythonw.exe.WebView2` beside Python, which fails where Python is installed read-only (`C:\Program Files`) and left the pane blank. A `pythonw.exe.WebView2` folder left beside Python by older versions can be deleted. This applies to both viewers.
- Help > Keyboard shortcuts (`F1`) is a keyboard map (`KeyMapWindow`), the same as the viewer pages' `H` window: a keyboard and mouse with every shortcut coloured by kind, the details of a key on hover (or when you press it), Shift / Ctrl / Alt layers, the views of a table (Free-look, Tag-lock...), a search box and category chips, and the list underneath in columns that each scroll on their own, with a line between rows. Tabs switch between the 3D viewer's keys and the launcher's own (`KEYS_LAUNCHER`); it opens on the viewer's while a page is in the pane, else on the launcher's, or on the tab last picked. Keys pressed in it are looked up and never run (F5 used to reload the paks behind it); Esc or F1 closes it. With old popup windows on it uses the system's colours. It replaces the two side-by-side lists (`HOTKEYS_LAUNCHER`, `HOTKEYS_VIEWER`, `_fill_hotkeys`).
- The keyboard-shortcut window (`F1`) keeps one size on both of its tabs, in both viewers. Switching from the 3D viewer's keys (three columns) to the launcher's (two) left the third column's settings in the grid, so the empty column kept its share of the width and the window grew to about one and a half times as wide. The settings are cleared on each switch, the columns sit between fixed gaps, and each keeps its scrollbar's room while the scrollbar is hidden. The window is as wide as the widest title or category row any tab has, so neither tab changes its size.

## Notable fixes (mohaa_view.py)

### Skeleton and animation

- Removed the ankle-ring vertex Z-negate workaround; the ankle helper's skinning frame is now built up-limb in `_solve_helper_world` (flipped 180 degrees about the calf's local Y), which made the negate unnecessary (and harmful on top of the fix).
- `mat_to_localquat` added: baking IK-solved frames with plain `mat_to_quat` stored the transpose of the intended rotation, which twisted/stretched the legs in the JS viewer while isolated renders looked correct.
- Leg IK is a port of `skelBone_IKshoulder` / `IKelbow` / `IKwrist`: thigh and calf share one bend-plane frame, which removed the shin twist/pinch of the earlier shortest-arc swing.
- Leg IK now runs on demand during bone resolution (engine order) instead of after a full FK pass, fixing leg-garment spikes on animations that take their legs from a movement-slot donor.
- SKD morph blocks (`skeletorMorph_t`) are now read instead of skipped; they drive facial blend shapes.
- Rotation-only animation channels (4 numbers) take their translation from the base pose, as the engine's movement slot does. Sidecars cached before this hold only 7-number entries.
- Humanoid rigs (`Bip01 Spine` + `Bip01 Pelvis`) rest on the allied_pilot A-pose template rather than whatever shared idle `.skc` was found first, which had left assembled player models with disconnected limbs.
- The default animation is initialised through `selectAnim` at boot. grenexp_base and similar models used to boot on the bind-pose sentinel, so their effect ran once and Play couldn't restart it.
- `--animbuild=` accumulates ids. It used to assign, so when the launcher appended a facial sibling the body animation was dropped ("build wrote no animation file").
- The attachment build reports how much of the skeleton its bind pose covers, so an unposed attachment is flagged instead of looking like broken geometry.

### .tik parsing

- TikiScript comment stripping removes `//` lines before `/* */` blocks; the old order let banner lines swallow whole animations{} blocks (fx_oceanspray, fx_leaves_blowing).
- `tagemitter` accepts a tag argument, quoted or not. The old regex skipped every tagemitter with a tag, so breath_emitter / breath_steam_emitter showed nothing.
- Comments are stripped before looking for `skelmodel`, so `// Set path to set skelmodel from` is no longer read as a directive (every player/scientist .tik failed with "skelmodel 'from' not found").
- `case` blocks are evaluated like `TIKI_LoadSetupCase`: only the matching branch's skelmodels load. The old flat regex stacked every head mesh of a head .tik at the origin.
- Emitter `avelocity` / `angles` accept `crandom` / `random` / `range` per component; previously `avelocity crandom ...` failed to parse and debris never rotated.
- Effect anchors hidden by `hide` or `surface all +nodraw` are hidden like `rendereffects +dontdraw` ones (fx_cannonsmoke, fx_lowsmoke and fx_nebelwerfer showed a stray model at the origin).
- Retired the load-time emitter schedule built from the `start` anim (e.g. adamspark's emitters pulsed in bursts instead of streaming like the idle in-game entity); emitteron/off windows now apply only when the anim is played.

### Particles and sprites

- Emitter colour is converted to a byte with the engine's wrap (mod 256) instead of being clamped, so adam-hallfire2's `color 4.5 0.2 0` is a dim brown and its x2/x3 emitters near-white; the old clamp gave solid red blobs.
- Spawn shapes are built in MOHAA space. T_CIRCLE rings (higgins, barracks `test`, explosion_tank) used to come out vertical and above the origin.
- `radius` defaults to 0 like the engine; the old fallback of 12 spread water_splash2 out.
- `offset` and `offsetalongaxis` both apply; the old `offset||offsetalongaxis` dropped fireandsmoke's scatter.
- `radialvelocity` replaces the forward velocity and `randvel` adds on top; it used to override `randvel`.
- With no `angles`, a tempmodel inherits the tag/entity axis. All three angles used to be randomised, which sent the mg42 / jeep_30cal muzzle-flash card off in a random direction every shot.
- `spawnrate` is exact: no `max(2, count/life)` floor (`spawnrate 1` flashes fired ~7x too often) and a 300/s ceiling instead of 120/s (blowtorch_cutter's spark fountain).
- One-shot volumetric bursts use SpawnVSSSource's `count x life` puff count (capped by `VSS_BURST_CAP`) instead of a single puff.
- Volumetric `life` only scales the spawn count; puffs fade by density decay. tanksmoke's `life 40` cloud now fades in ~1.5 s as in-game instead of lasting 40 s.
- Without shader info, only an over-bright colour makes a particle additive. An `alpha > 0.45` rule used to turn dark smoke into white orbs.
- `T_SWARM` runs on a fixed tick. It was tied to the browser frame rate (2.5 re-rolls/s at 60 fps against ~5-6.5/s in-game).
- Friction compounds per 10 Hz physics step (`pow(base, dt*10)`). The old per-frame linear form blew up negative friction (electrical_fire's sparks became full-screen bars).
- `scalerate` grows the base scale multiplicatively, and the grown size is no longer clamped to `scalemax` (mortar/mine dirt sprites froze tiny; electric_arc's lightning2 ballooned).
- `fadedelay` is in seconds, not a fraction of life. The old formula made any `fadedelay >= 1` particle invisible from birth (gren_exp rings, bombdirt, dirtplumes, dustclouds).
- animmap sprites are timed from each particle's spawn; `bang.spr` used to start mid-animation.
- No per-sprite screen cap (the old 0.55 x view cap made electric_panelmelt's corona stall before dying).
- Sprite size is texture-proportional (`SPR_K`), replacing the fixed `SPR_UNIT` base and, before it, pure pixel sizing (scale .0625 sprites were ~16x too small). VSS puffs are `texpx x (radius/5) x spritescale` (~64u at radius 10, was ~20u).
- Upright and oriented sprite quads use perspective-correct strips with near-plane clipping and adaptive subdivision. A single affine smeared tall quads (mortar_dirthit) and fixed strip counts flickered.
- Sprites whose shader has no `spritegen` never roll (SPRITE_PARALLEL); electric_panelmelt's coronas used to spin. This also replaced a counter-rotating tcMod special case for explosed.
- Debris chunks multiply the flat shade into the texel instead of painting a black facet over it (black squares around bh_foliage_leaf cards).
- Pending textures skip a frame instead of drawing the fallback, removing first-play white flashes (bh_wood_piece, bh_carpet_* puffs).
- The ground grid sits at the lower of the old radius heuristic and the bind-pose mesh floor, so characters' boots no longer sink into it.

### Viewer UI

- The unused `sprite` Display button was removed; it never gated particles, only autosprite surfaces, which now always billboard.
- The setsize line lives outside `#stats`, so an animation streaming in can't wipe an open editor, and the pencil always switches the Setsizes box on.
- The Texture toggle follows the live surface list, so an attachment with its own texture can be shown on an untextured host (rev 63).
- The effect clock can start after load, so an attached muzzle flash animates on a static model (rev 63).
- Attachments bind on the path the launcher names. The old tik-to-skd name guess never matched static_airtank (submodels/AIRTANK.skd), so it never appeared.
- User surface hides are tracked separately from the .tik's spawn state and the animation's commands, so Reset and animation changes keep them.
- The pop-up lists capture keys while open (the global hotkeys would otherwise toggle Display buttons while typing a filter), and clicks inside a list no longer close it.
- The surfaces panel initialises after the bindings it reads; calling it earlier threw inside a try/catch and left an empty menu.
- A failed animation build shows the `.skc` path, not just the animation name.
- Pages are opened with `Path.as_uri()`; the old `"file://"+path` broke on Windows drive letters and on paths with `#`, `%` or non-ASCII characters.

## Textures and shaders (mohaa_textures.py)

- Additive sprites use premultiply compensation (`_gl1_lut`) instead of their native alpha or flattened alpha. Native alpha under-lit sparks (~0.5x size) and flattening punched opaque black squares into the backdrop (corona boxes).
- The `.shader` block scanner is linear-time (explicit `pos` matching). Slicing the remaining text per block was O(n^2) and the name pattern could backtrack.
- The animation cache id tries `md5(usedforsecurity=False)` and falls back to plain md5, then blake2s, so FIPS-mode systems don't lose the animation catalogue.
- A pulse shader's base stage keeps its alpha when it blends (bplane_pulse / bspindle_pulse were encoded as opaque JPEGs, so barbwire_long_pulse drew a black background) and carries its cull, alphaFunc and distFade hints like the plain shader. distFade near/range are per shader, so the last `alphaGen distFade` in the block applies to every stage that uses it.
- A shader map missing from the paks falls back to the shader's `qer_editorimage`, then to a texture of the same file name elsewhere in the paks, and the Output pane says so (red for the miss, yellow for the stand-in). The pulse_map1-4 shaders (mapfrance, mapcarentan, mapstlo, mapstrehaia) point at `textures/models/items/`, but their textures ship in `textures/models/maps/`; in-game they are untextured. A pulse surface with a missing base used to be reported as textured.

## Windows scripts (.bat)

Changes to `python_installer_updater.bat` unless noted.

- The user's PATH is no longer hand-edited. The old script read the user PATH with `[Environment]::GetEnvironmentVariable` (which expands `%VAR%` references) and wrote the expanded text back, permanently flattening `REG_EXPAND_SZ` entries such as `%USERPROFILE%\...` with no backup. It also stripped any entry ending in `\PythonNN`, including unrelated toolchains. Python's own installer now sets PATH (`PrependPath=1`).
- Every `if <cond> cmd1 & cmd2` is parenthesised. `&` is a command separator, so `if X endlocal & exit /b 1` ran the `exit` unconditionally; this made the old `:compare_versions` always report "older" and re-download Python on every run.
- Paths are passed to PowerShell as arguments instead of being pasted into single-quoted strings. A path containing an apostrophe (`C:\Users\O'Brien\...`) used to end the string early and have the rest parsed as code.
- The download is pinned to TLS 1.2 and the installer's Authenticode signature is verified before it runs.
- The Python version is chosen for the running Windows release (3.8.10 on Windows 7, 3.11.9 on Windows 8/8.1, the latest release on Windows 10/11); Python 3.9+ refuses to install on Windows 7, so the old "always fetch latest" failed there.
- CPU architecture is detected (x64 / ARM64 / x86) instead of assuming amd64, and Pillow is version-checked (>= 10.3) rather than merely imported.
- Microsoft Store execution aliases are no longer deleted (a system-wide change outside the program's remit); the interpreter search skips them instead.
- An existing Python install must be 3.8 or newer (Pillow 10.3 needs it; 3.7 used to pass and then fail to get Pillow), and the closing message names the current RUN .bat.
- The RUN .bat no longer sets an unused `PYSCRIPT` variable.
- Fixed the installer closing the moment it opened. Its Windows-version probe passed PowerShell a string with `\"` inside a `FOR /F` command; cmd has no `\"` escape, so the `)` in `$($v.Major)` ended the command list and cmd exited with a syntax error. The probe now reads `[Environment]::OSVersion.Version.ToString()`, with every parenthesis inside the quotes.
- The RUN .bat checks everything before starting the launcher: it uses the py launcher's default Python if that is 3.8+ with tkinter, otherwise the newest suitable one on PATH or in the default install folders (so a Python installed moments ago is found without a new window), and if there is none it explains why (none, too old, or no tkinter) and asks Y to run the installer or N to close. It then installs Pillow and the embedded-pane packages if missing (the latter only on Windows 8.1+), reports a missing WebView2 Runtime, and starts the launcher with the `pythonw.exe` beside the chosen Python, so the launcher always runs on the interpreter that has the packages. Also fixed: its Pillow message echoed `(>=10.3)` unescaped, which redirected the text into a file named `=10.3)`.
- The installer accepts `/fromrun`, which skips its closing pause and PATH note when the RUN .bat calls it.
- The installer serves both viewers (both RUN .bat files call it the same way) and looks for Python where the RUN .bat files do: the py launcher's default first, then PATH, then the per-user and all-users install folders (`%ProgramFiles%\Python3*` is new).
- Its Microsoft Store alias check never matched: `echo !CAND! | find` runs on a pipe, where delayed expansion is off, so `find` saw the literal text `!CAND!`; it now pipes `%~1`. It also read each version through `for /f`, which hands the command to `cmd /c` and mangles a quoted path containing `(`, `)` or `&`; Python is now run directly and its output read back with `set /p`.
- After installing, it finds the new Python with the same search, so per-user folders with a `-32` or `-arm64` suffix are found too (it only tried `Python3XY`), and it reports the installer's exit code when that isn't 0.
- Python is installed with `InstallLauncherAllUsers=0`. The py launcher's all-users default needs administrator rights, so the otherwise per-user quiet install could stop at a UAC prompt.
- Messages say "models and maps" and the closing note names both RUN .bat files.

## Map Viewer (October 2026)

- First version of the MOHAA Map Viewer: `RUN -- Medal of Honor Map Viewer.bat` and
  `bin/mohaa_map_launcher.py`, `mohaa_map_view.py`, `mohaa_map_page.py`, `mohaa_bsp.py`,
  `mohaa_entdefs.py`. It opens `.bsp` files (turned back into `.map` source by its own
  decompiler) and `.map` files in a WebGL2 viewer with Free-look and Radiant-look cameras,
  info cards for any clicked face or entity, same-kind selection, find, and MOHRadiant's
  filters. Details in [map-viewer.md](map-viewer.md).
- `MAP_VIEWER_REV` 1, `MAP_VIEWER_REV_REQUIRED` 1, `INDEX_VERSION` 2.
- The Model Viewer's files are unchanged: the map launcher subclasses `mohaa_launcher.App`.
- Map Viewer page rev 2 (`MAP_VIEWER_REV` 2, `MAP_VIEWER_REV_REQUIRED` 2,
  `INDEX_VERSION` 4):
  - The game's own lighting. A `.bsp` now opens lit the way the game lights it: the
    compiled polygons with their lightmaps (brightened like `R_ColorShiftLightingBytes`
    with `r_mapOverBrightBits 1`), vertex light where the engine uses it, patches and
    terrain with their lightmap pages, static props with their baked vertex light, other
    models with the light grid at their origin, and the sky box (`skyParms` far box)
    behind the sky brushes. Show > **Full Brightness** (B), off by default, switches back
    to MOHRadiant's look. A `.map` has no compiled light, so the button is disabled there.
    Water, slime and lava keep their editor picture at Full Brightness (as MOHRadiant
    shows them) but are drawn with the shader's own picture, solid unless the shader
    blends, with the game's lighting.
  - See-through editor brushes (hint, clip, trigger, nodraw...) are drawn one-sided as
    MOHRadiant draws them: looking through a hint brush no longer shows the letters of
    its far side. With the camera inside such a brush, its inner sides are drawn instead.
  - Caulk is pushed half a unit back in depth, so it no longer sparkles along the corner
    where a wall meets the caulked end of the next brush.
  - With Fog on, everything past the fog's far end is the fog colour.
  - A brush entity whose faces are all filtered out (a trigger with Triggers off) loses
    its label, setsize box and target links too.
  - The FOV slider runs from 60 to 150 (was 30 to 120).
  - A shader's picture is the last opaque stage it draws (the stage that covers the
    surface), not its first stage: frenchfloor_wood1 showed `poster4` from its
    environment-map stage. The cached shader index is rebuilt for this.
  - The decompiler finds a face's draw surface through a spatial index instead of a scan
    of every surface on the plane, so large maps decompile much faster. The output is the
    same apart from rare ties between two equally good surfaces.
- Map Viewer page rev 3 (`MAP_VIEWER_REV` 3, `MAP_VIEWER_REV_REQUIRED` 3,
  `INDEX_VERSION` 5):
  - With the game's lighting, a surface's picture is drawn the way its shader stage
    draws it in game: the stage's `tcMod scale` (`RB_CalcScaleTexCoords`; the Omaha sea
    was one stretched tile, it now repeats 16 x 22 times as in game), its `alphaGen`
    (`const`, the `sCoord` / `tCoord` fades of `RB_CalcAlphaFromTexCoords` that make the
    shoreline see-through toward the beach, vertex alpha), and `depthWrite` on a blended
    stage (the surf hides what is under it).
  - See-through surfaces are drawn in layers: the game's own (water, glass, glows), then
    the models', then the editor's volumes (triggers, clips, hints, nodraw). Water used
    to be drawn after the triggers and painted over every trigger face above it.
  - The picture a shader shows: a stage that multiplies its texture by the lightmap
    (`map X` / `nextBundle` / `map $lightmap`) is the surface's own texture, then the
    stage drawing the `qer_editorimage` (unless it is a glow added on top), then the last
    solid stage; reflection stages (`tcGen environment`) count only when nothing else is
    left. Snow shaders that draw a sparkle layer first now show their snow, and
    cathedral walls, bookcases and broken windows no longer show their gold or sky
    reflection map. `clampmapx` / `clampmapy` stages are read too.
- Map Viewer page rev 4 (`MAP_VIEWER_REV` 4, `MAP_VIEWER_REV_REQUIRED` 4): lines are
  hidden behind walls. X-ray used to draw every setsize box, target link and facing
  arrow through walls, and the link arrowheads were painted over the 3D view, so a wall
  in front of a group of path nodes showed a web of lines and triangles. Now only the
  selection's own outline, box, links and arrow show through walls (with X-ray on), and
  the arrowheads are drawn in 3D, camera-facing, hidden by walls like their lines.
  Labels still show through walls.
- Map Viewer page rev 5 (`MAP_VIEWER_REV` 5, `MAP_VIEWER_REV_REQUIRED` 5): point-entity
  boxes are coloured the way MOHRadiant's camera colours them (read from its brush
  drawing in `mohradiant.exe`):
  - `info_pathnode` looks as it does in MOHRadiant, which has no definition for the
    class ("Not found in source.") and draws its stand-in: a dark green 16-unit cube on
    the origin. The viewer drew the magenta 32 x 32 x 32 box from entdefs' navigate.cpp.
    A node with a `"targetname"` is pink (MOHRadiant turns an `info_path...` class's
    colour inside out when it has one; `"target"` and `"$targetname"` don't count), and
    a `"_color"` key paints the box flat (the cyan friendlynodes).
  - A path node with AI flags gets MOHRadiant's thick outline by its spawnflags, first
    match: COVER green, CORNER_LEFT yellow, CORNER_RIGHT yellow-green, SNIPER red, CRATE
    dark red, CONCEALMENT blue, DUCK cyan; black for flags that don't go together
    (`IsValidPathnode` in navigate.cpp, whose `ai_editmode` node colours are the same).
    A node's info card says which colours it has and why.
  - Box sides are shaded as MOHRadiant shades them (`SetShadeForPlane`: 0.6 facing x,
    0.8 facing y, 1.0 up and down), and any other point entity with a `"_color"` key
    (`info_waypoint`, `script_origin`...) is drawn flat in that colour.
- Map Viewer page rev 6 (`MAP_VIEWER_REV` 6, `MAP_VIEWER_REV_REQUIRED` 6):
  - Every point entity whose class is defined in the game code (code/*.cpp in
    entdefs.pk3) is drawn as MOHRadiant draws it, as its "Not found in source." stand-in:
    a dark green 16-unit cube on the origin. Player starts were tall 32 x 32 x 96 boxes;
    script origins, spline paths, grenade hints and waypoints change the same way.
    Classes defined in a .tik keep their definition's colour and box.
  - Facing arrows are MOHRadiant's (`Brush_DrawFacingAngle`): white, 4 pixels wide, from
    the middle of the box out to 2.5 times its half-width, with a head that opens up and
    down. They were thin lines in the entity's colour from the floor.
  - A legend: `L` in the viewer (or the new "L legend" chip next to "H hotkeys", or the
    Legend button in the info card of a node), and Help > Legend (`F2`) in the launcher.
    It lists the path-node box and border colours, the entity markers, and every editor
    surface (caulk, the clips, trigger, hint, vis, skip, areaportal, origin, nodraw,
    ladder, sky, liquids...) with its picture and what it does in game. Both read one
    table, `LEGEND` in mohaa_map_view.py; the page carries its editor pictures.
  - The viewer's theme key moved from `L` to `T`.
- Map Viewer page rev 7 (`MAP_VIEWER_REV` 7, `MAP_VIEWER_REV_REQUIRED` 7): hovering a
  model or a marker outlines its box in the accent colour, as hovering a brush outlines
  its edges; until now only a click showed an entity's (red) box. Selecting what is
  under the mouse takes its hover outline away. The legend lists the hover outline too.
- Map Viewer page rev 8 (`MAP_VIEWER_REV` 8, `MAP_VIEWER_REV_REQUIRED` 8): the sky.
  - The game's sky is drawn behind everything, as `RB_StageIteratorSky` draws it
    (`qglDepthRange(1, 1)` in `tr_sky.c`), so whatever is behind a sky brush shows
    through it, as in game. It used to be painted on the sky brush and hide what was
    behind. The sky box now also shows with Full Brightness on and on `.map` pages; it
    used to need the game's lighting.
  - Simple Sky (`K`, a new button beside Full Brightness, off by default) draws sky
    brushes as MOHRadiant does: solid, with the shader's picture tiled. Editor look turns
    it on, In-game look off; it is remembered with the other options.
  - The Sky filter has a key, `Ctrl+K`, and shows or hides sky brushes completely.
  - Where only the game's sky is under the mouse, a click (or the hover outline) goes to
    the nearest sky brush.
  - Sky shaders use their editor picture (`qer_editorimage`, else the image named after
    the shader, such as `textures/sky/africanight.jpg`) instead of their first stage's
    picture. Africanight's is a dark additive cloud layer, so its sky brushes looked
    black.
  - The decompiler writes `0 0 0 1 1` on sky faces, as EA's sources do. A sky polygon's
    texture coordinates are laid out on their own, not projected from the face, so the
    fitted alignment was meaningless (`19 58 180 172.624994 -59.500001`).
  - The legend's Sky row and the launcher's shortcut list (`F1`) list `Ctrl+K` and `K`.
- Map Viewer page rev 9 (`MAP_VIEWER_REV` 9, `MAP_VIEWER_REV_REQUIRED` 9):
  - Editor look also turns Full Brightness on (MOHRadiant is always full bright), and
    In-game look turns it off (the game's own lighting), as they already did Simple Sky.
  - Ctrl+Alt+click selects the whole path through an entity: everything its `"target"`
    chain leads to and everything whose target leads to it, so a path node in the middle
    of a chain selects the whole chain (forks and loops included; Shift adds the path to
    the selection). The Links section of an entity's info card offers the same as a link.
  - Ctrl+Shift+click shows the clicked face's texture, as middle-click does (in Radiant,
    Ctrl+Shift+click selects a single face). Middle-click didn't work on Windows,
    although it does in Chromium tests. A likely cause is the mouse moving a few pixels
    as the wheel is pressed, which turned the click into a middle-drag, so a middle
    click now has 10 pixels of slack instead of 4. Ctrl+Shift+click on a model or
    marker, which has no face, says so instead of showing "Nothing selected".
  - The Radiant-look camera hints show `Shift` fast and `Ctrl` grid step, like Free-look's
    `Shift` fast; both hint blocks were regrouped so no line wraps in the middle.
  - The shortcut list (`H`), the launcher's (`F1`) and the Radiant-look button's tooltip
    list the new clicks and `Shift`.
- Map Viewer page rev 10 (`MAP_VIEWER_REV` 10, `MAP_VIEWER_REV_REQUIRED` 10): looking
  around follows the camera tilt (Q / E), as the Model Viewer's free-look does. Mouse
  look, the arrow keys, A / Z and the Radiant-look right-drag turn used to change yaw and
  pitch as if the camera weren't tilted, so dragging down on a tilted screen looked off to
  the side (at 90 degrees of tilt, entirely sideways). The movement is now rotated by the
  roll first (`lookBy`). Space / C rise along the tilted screen's up instead of straight
  up; A / D already strafed along its right. The camera hints in the panel list one key
  per row, with End and a spacer row (laid out by hand in mohaa_map_page.py).
- Damaged files and cleanup (October 2026, no page rev change; all 54 retail maps
  decompile byte for byte as before):
  - The `.bsp` size check counts the 29 lump entries that are always read.
  - A brush with more sides than q3map writes (300, `MAX_BUILD_SIDES`) is skipped as
    damaged.
  - A face spanning more cells of the decompiler's spatial index than there are filled
    cells (a huge sky face, or an unclosed brush in a damaged file) walks the filled cells
    instead of every empty one in its bounds.
  - NaN or infinite numbers in a damaged `.bsp` (planes, vertices, texture fits, static
    model origins) are skipped or written as 0; they used to crash the decompiler. A file
    that still breaks the reader stops with "looks damaged" (exit code 5) instead of a
    traceback, and `mohaa_bsp.py` on its own does the same (exit code 3). Checked with
    randomly corrupted copies of retail maps.
  - `image_dims` returns None for a damaged image header instead of raising.
  - The page refuses a `terrainDef` past 257 x 257 points and a patch over the engine's
    129-point grid limit (`MAX_GRID_SIZE`, `cm_patch.c`), so a crafted `.map` can't make
    it allocate without bound. Like other broken primitives, they're listed as warnings.
  - `.dcl` files (binary decal data) are listed as map data instead of opening in the
    text editor, where they showed as garbage.
  - `mohaa_map_view.py` prints its usage when run without arguments.
- Map Viewer page rev 11 (`MAP_VIEWER_REV` 11, `MAP_VIEWER_REV_REQUIRED` 11,
  `INDEX_VERSION` 6): trees no longer draw their long-range stand-in. MOHAA's tree models
  carry a flat card of the whole tree (`deformVertexes autoSprite2` with `alphaGen
  oneMinusDistFade`) that the game fades in only far away, as the tree's own leaf cards
  fade out (`alphaGen distFade`). The page draws the whole tree at any distance, so the
  card was drawn on top of it, turned to face the camera on every axis (a top-down view
  showed side-on trunks). Model surfaces with such a shader are now left out of the page
  (19 shaders, used by 12 tree and palm models in the retail paks); the build log counts
  them. The shader index records the pairing (`lod`), hence the new `INDEX_VERSION`.
- Map Viewer page rev 12 (`MAP_VIEWER_REV` 12, `MAP_VIEWER_REV_REQUIRED` 12):
  - The flat tree pictures some maps stand beside their trees
    (`textures/misc_outside/commontreeshadow`: `nodraw`, `alphashadow`, `nonsolid`) are
    shadow casters: world brushes the map compiler uses to give a tree its shadow, never
    drawn in game. Their texture is nodraw but in no editor group, so they were filed as
    ordinary (detail) world brushes: they stayed in the In-game look, and no Show button
    hid them. They aren't part of the trees, so hiding the trees left them too. A nodraw
    texture outside the other editor groups now counts as Nodraw, so the Nodraw button
    and the In-game look hide them (m4l1, m4l2, m5l1b and mohdm1 use them). The legend
    has a row for them.
  - Show > **Simple models** (`M`, beside Simple Sky, off by default, remembered) draws
    each tree that has a sprite version as that sprite alone, as the game draws trees far
    away. It replaces the Static models filter, which did what Models already does
    (static props still hide with Models and Entities); a saved setting that hid only
    static models is cleared on load. The sprite (the long-range card left out since rev
    11) is back in the page, marked `TF_LOD`, and is drawn the way `deformVertexes
    autoSprite2` draws it (`Autosprite2Deform` in `tr_shade_calc.c`): each quad turns about
    its long axis to face the camera, so the tree stays upright. It is lit like the rest
    of its static prop, can be clicked, and hides with its tree (Models, Entities, Hide).
    Models with no sprite version (bushes, props) don't change.
  - A selected model's red tint follows what is drawn of it: alpha-tested leaves and the
    sprite are tinted, not their whole cards.
  - The build log counts the models with a sprite version instead of the sprites left out.
- Map Viewer page rev 13 (`MAP_VIEWER_REV` 13, `MAP_VIEWER_REV_REQUIRED` 13,
  `INDEX_VERSION` 7): the sky's cloud layers. A sky shader's stages are drawn over its far
  box as `R_BuildCloudData` draws them, so the clouds of `textures/sky/africanight` (m1l1,
  m1l2a/b, m6l3b, mohdm7) drift across the night sky as in game. Texture coordinates
  come from each pixel's direction met with a sphere 4096 units in radius whose top is
  the `skyParms` cloud height above the eye (`R_InitSkyTexCoords`); each stage keeps its
  blendFunc, alphaFunc, rgbGen, alphaGen (including `skyAlpha`) and tcMods (`scroll`,
  `scale`, `rotate`, `transform`, `stretch`, `offset`, `wavetrans` / `wavetrant`), worked
  out each frame. No new button: Simple Sky and Fog turn them off with the game's sky.
  Moving clouds redraw the view up to 30 times a second while some sky is in view; an
  occlusion query on the sky tells when none is, and the redrawing then stops until the
  view changes. A sky without clouds uses the same program as before, so it costs nothing
  extra. The shader index keeps the cloud height and stages, hence the new
  `INDEX_VERSION`, and the build log counts the cloud layers.
- Map Viewer page rev 14 (`MAP_VIEWER_REV` 14, `MAP_VIEWER_REV_REQUIRED` 14):
  - The legend lists the editor surfaces it was missing: `common/rain`, the volume of a
    `func_rain` entity (8 retail maps), and `common/caulksky`, sky with no sky box (15
    maps; the game clears it to the fog colour, `RB_BeginDrawingView` in
    `tr_backend.c`, or leaves the last frame there on a map without fog). It also has
    rows for the setsize boxes (`4`) and for the flat grey of a texture the paks don't
    have. A check of every texture in the 54 retail maps and the sample `.map` sources
    found no other editor surface missing; `common/black` and `switchflat` are drawn
    textures.
  - Both legends (`L` and Help > Legend, `F2`) show one column per section (AI path
    nodes, entities, brushes and editor surfaces), each scrolling on its own under its
    title. The page's legend is 640 px tall (at most 86% of the view; a narrow window
    stacks the columns). The launcher's opens 640 px tall at most, never taller than the
    launcher window, and can be resized; the mouse wheel scrolls the column under the
    pointer, and a column's scroll bar shows only while it has more than fits.
  - A **Same path** button beside Same kind selects the whole path through the selected
    entity, as Ctrl+Alt+click does. It shows when the entity's `"target"` leads
    somewhere or something targets it (for several selected entities, the one last
    clicked).
  - The shortcut lists (`H`, and `F1` in the launcher) name the Same kind and Same path
    buttons.
- Map Viewer page rev 15 (`MAP_VIEWER_REV` 15, `MAP_VIEWER_REV_REQUIRED` 15): blocks the
  page can't read.
  - Spearhead's `t1l1` and `t1l1_sml` showed "1 unreadable block(s) skipped". The block is
    the one brush of entity 1072 (`script_object`, `$targetname` `tracer_1`): its shader in
    the `.bsp` is `textures/(0`, a texture name q3map took from EA's map source. The
    decompiler writes it back as it is; the page's tokenizer split it into `(` and `0` and
    gave up on the brush. A texture name is now one word, as q3map and MOHRadiant read it
    (`GetToken` stops only at white space), so the brush loads (drawn flat grey: no such
    texture). Every other map checked reads exactly as before: the 54 retail Allied
    Assault maps, the other 34 Spearhead maps and the 17 sample `.map` sources.
  - The red line now says which blocks: it opens a card listing each skipped block with
    its entity (linked, unless it is part of the world), the brush, patch or terrain
    block, its line in the `.map` (the decompiled one for a `.bsp`), the reason and the
    line itself. In the launcher's pane the page also sends the list to the Output
    console, in red.
  - After a block it can't read, the reader carries on past the `}` that closes that
    block. It used to stop at the first `}` it met, which inside a patch or terrain block
    is the inner one: the entity then ended early, and everything after it was read as
    new entities (a test copy of m1l1 with a damaged patch listed 616 errors and 613
    entities too many; now the patch is one error and the entity count is right).
  - Messages say what was found instead of a text offset (`expected "(" but found "0"`).
- Map Viewer page rev 16 (`MAP_VIEWER_REV` 16, `MAP_VIEWER_REV_REQUIRED` 16):
  - `X` stops the camera, and the Camera panel lists it. The camera also stops when the
    page loses the keyboard or the window, while the page doesn't have the focus, when a
    drag's mouse button was let go outside the page, and on any click on the launcher
    while the map is in its pane. A key or button let go outside the page never reached
    it, so the camera kept moving (or turning with the mouse) until the next click in it.
  - Show buttons of their own for Rain (`Ctrl+I`, `common/rain`, hidden at first, also in
    the Editor look) and Foliage clips (`Ctrl+G`, `common/foliageclip`, apart from
    Clips); Nodraw has a key, `Ctrl+O`. The In-game look hides both new groups. Saved
    options from before start with Rain hidden. The legend shows the keys.
  - The Entities button stays on (dashed) while only some of its kinds are hidden by their
    own buttons (AI nodes, Lights, Models, Paths, Point ents), and its tooltip names them;
    it used to look off. Details was never one of them.
  - `Ctrl+Z` (and an Undo button beside Show all) undoes the last Hide or Show all, one
    step at a time.
  - Open beside Copy on an info card's `.map source`: the `.map` in the Text Editor at
    that line (in the launcher's pane), or as text in a new tab (in a browser).
  - The map's stats count real entities (an entity number in game, against MOHAA's 1024),
    simple ones and static props; so do the launcher's map details and the build log
    (`entity_kind` in mohaa_entdefs.py, from OpenMoHAA's class tree). Static props of a
    `.bsp` are now found by the decompiler's static-model index, not the `static_` prefix,
    which some lack (24 in Spearhead's t2l4), so they also lose their labels as other
    static props do.
  - Find / Classes: clicking a class row anywhere opens its list (it took the arrow), and
    hidden entities show red, a partly hidden class yellow with its hidden count.
  - Shortcut lists (`H`, launcher `F1`): `X`, `Ctrl+Z`, `Ctrl+O / I / G`.
  - The launcher shows the builder's `!` lines in red as warnings; they used to end the
    build's status as an error.
- Map Viewer page rev 17 (`MAP_VIEWER_REV` 17, `MAP_VIEWER_REV_REQUIRED` 17): the
  keyboard shortcuts.
  - The shortcut windows (`H` in the viewer, Help > Keyboard shortcuts `F1` in the
    launcher) are a keyboard map, as in Adobe Audition: a keyboard and a mouse with every
    key the viewer uses coloured by kind (camera, selecting, show / hide, display,
    window), with its short name on the key. Hovering a key, or pressing it, lists
    everything it does with every modifier and in which camera; Shift, Ctrl and Alt
    (clicked, or held) show their layer of the keyboard, and Free-look / Radiant-look
    switch the camera keys (the viewer opens on the camera in use). A search box and the
    category chips narrow it down. The list underneath has three columns that each scroll
    on their own, with a line between rows; hovering a row rings its keys (in their
    layer), and clicking a key finds its rows. While the window is open, keys are looked
    up instead of acting on the map; Esc, H or `?` closes it. Both windows read one table,
    `MAP_VIEWER_KEYS` in mohaa_map_view.py; the page's window is the Model Viewer's
    (`KEYS_JS` / `KEYS_CSS` in mohaa_view.py), the launcher's is `KeyMapWindow`.
  - The All, In-game look and Editor look buttons have keys, shown on them: `Ctrl+A`,
    `G` and `Shift+G`. `Ctrl+A` in the Find box still selects its text.
  - The Editor look tooltip says it hides rain too (it has since rev 16).
- Map Viewer page rev 18 (`MAP_VIEWER_REV` 18, `MAP_VIEWER_REV_REQUIRED` 18): the game's
  debugging cvars.
  - A **game cvars** list under Display, below backdrop (or `` ` ``, the game's console
    key): `r_showtris 1 / 2 / 3`, `cm_noAreas 1` and `ai_showroutes 1`, with number boxes
    for `ai_showroutes_distance` (1000) and `ai_fallheight` (96); each row's tooltip says
    what it does. A click on a row sets it, a second click puts it back to the game's
    default. The filter box doubles as the console: `r_showtris 2` then Enter sets a cvar,
    and a name alone answers as the game does (`"ai_fallheight" is:"96" default:"96"`).
    The list's foot shows the camera's cluster and area in the game's BSP tree, what is
    drawn from there, and where the path file came from. The cvars that are set are named
    beside the button and remembered with the other options. A row the page can't do is
    greyed out with the reason: r_showtris needs a `.bsp` (a `.map` has no PVS yet), and
    ai_showroutes needs the map's `.pth`.
  - `r_showtris` outlines every triangle the game draws from where the camera is
    (`DrawTris` in `tr_shade.c`; in game it also needs `developer 1`). At 1 the outlines
    are hidden behind walls. At 2 they show through walls, with an axis cross at the
    origin of the world and of each brush entity and model drawn (red up, green along y,
    blue a diagonal: the engine's own slip). At 3 only the crosses are drawn. What gets
    outlined follows the renderer:
    - the camera's leaf and cluster (`R_PointInLeaf`), that cluster's row of the vis lump
      and the areas joined to the camera's (`R_MarkLeaves`);
    - the farplane (worldspawn `farplane` and `farplane_cull`);
    - faces turned away from the camera dropped, with 8 units of slack (`R_CullSurface`);
    - curved patches with only the rows and columns their distance allows
      (`r_lodCurveError` 250, on the grid `R_SubdividePatchToGrid` makes with
      `r_subdivisions` 3);
    - terrain blocks and static props listed by the kept leafs;
    - the brush entities and models the server sends (`sv_snapshot.c`): a cluster their
      box touches in the PVS, and their area joined to the camera's.

    Step out of a bunker and the rest of the map comes in at once, as in game.
  - `cm_noAreas 1` counts every area portal as open. Without it, the level is as it
    starts: every door shut except those that start open (`func_door`,
    `func_rotatingdoor` and `script_door` with spawnflags 1). So the rooms behind a shut
    door aren't drawn even when they are in the PVS.
  - `ai_showroutes 1` draws the connections the AI can walk between path nodes, as
    `DrawAllConnections` in `navigate.cpp` draws them, for the nodes within
    `ai_showroutes_distance` of the camera:
    - a green line 36 units up for a connection both ways;
    - a red arrowhead 16 units along a one-way connection (the way back drops further
      than `ai_fallheight`);
    - a red X on a node with no connections;
    - a blue circle on a DONT_LINK node.

    The connections come from the map's `.pth` (`maps/<map>.pth` in the paks, else the
    file beside the map), read as the game reads it (`navigate.cpp`, `archive.cpp`, and
    the LZ77 packing of `lz77.cpp`); Allied Assault and Spearhead files both work. Node i
    is the map's i-th `info_pathnode`. The list warns when the counts differ: the `.pth`
    was made for another version of the map, and the game rebuilds it.
  - A path node's info card has an **AI paths** section: the node's number in the `.pth`,
    the point where the game dropped it to the floor, and the nodes it connects to (both
    ways, one way to, one way from), each a link with its drop.
  - The legend has rows for the ai_showroutes lines and the r_showtris outlines and
    crosses. The shortcut lists (`H`, and `F1` in the launcher) have `` ` ``.
  - The Free-look camera hints say `mouse wheel = move`, and the blank row under the
    camera hints is gone.
  - The cvars' lines are cut at the near plane in the vertex shader when one end is
    behind the camera. The headless test renderer (SwiftShader) dropped such lines
    entirely, so walls lost their outlines up close.
  - The build adds what these need to the page:
    - `vis_payload`: the BSP tree, the leafs, the vis lump and the lines of every surface
      the game draws, using `Bsp.vis_tree()` and the patch tessellation
      `subdivide_patch` in mohaa_bsp.py;
    - `paths_payload`: the path file, using `read_path_file` in mohaa_bsp.py.

    m5l1a's page grows by about 0.6 MB.
- Map Viewer page rev 19 (`MAP_VIEWER_REV` 19, `MAP_VIEWER_REV_REQUIRED` 19):
  - The decompiler gives a ladder's and a rotating door's origin brush the shape EA's own
    map sources give it, and MOHRadiant shows: a thin column from the bottom of the entity
    up through its origin and as far again above it. A `func_ladder`'s is 4 units across
    and marks the line the player climbs (`FuncLadder` puts the player 16 units in front
    of it); a `func_rotatingdoor`'s is 8 across and marks the hinge. They were 16-unit
    cubes. Every ladder now gets its column, even one whose origin is the centre of its
    brushes, where no origin brush was written before. The column is centred on the
    origin, so the map compiles back to the same origin. In the 54 retail maps only these
    origin brushes change (275 reshaped, 4 added). Of the 58 columns in EA's sources
    (mohdm6, mohdm7, obj_team2, obj_team4), 56 come back exactly; the other two are a unit
    taller, because their centre was on a half unit.
  - The game cvars list says when a map has no AI path nodes at all, instead of saying its
    path file is missing.
- Map Viewer page rev 20 (`MAP_VIEWER_REV` 20, `MAP_VIEWER_REV_REQUIRED` 20): the Find
  lists and the Selection panel.
  - Double-clicking a class in Find > Classes leaves its list of entities open and flies to
    the class. The first click rebuilds the list, so the browser could count the second
    click as a new single click: that closed the list again, and the fly-to never came.
    A second click on the same class or texture row within half a second now counts as the
    double-click.
  - Shift+click a coloured square in the Find lists to hide that entity, or every entity of
    that class; Shift+click it again to show them. It goes on the Hide stack, so Ctrl+Z
    undoes it. Entities that a Show button hides stay hidden, and the message names the
    button.
  - Each tab's counts and hints sit above a line, with the list in a section of its own
    under it. The Classes tab gives the counts and two hints on separate lines, and
    Results now shows how many were found.
  - **Same targetname** (after Same kind and Same path, or `$`, that is Shift+4) selects
    every entity with the selected entity's targetname: the group a script reaches as
    `$name`. It shows when another entity shares the name. The shortcut lists (`H`, and
    `F1` in the launcher) have `$` and the Shift+click on a square.
- Map Viewer page rev 21 (`MAP_VIEWER_REV` 21, `MAP_VIEWER_REV_REQUIRED` 21): doors open
  and close as in game.
  - **Open door** (in Selection, after Same targetname, or `O`) opens the selected
    `func_rotatingdoor` or `func_door` the way the use key does (`Door::DoorUse`,
    `doors.cpp`). While the door is open or opening the button reads **Close door**; with
    several doors selected it reads Open doors / Close doors.
  - A rotating door swings `openangle` degrees (90) about its origin. With `alwaysaway` 1
    (the default) it swings away from the camera, inwards or outwards depending on the side
    you stand; with `alwaysaway` 0 it always swings the same way, the side its box lies
    toward (`RotatingDoor::DoOpen`). No spawnflag picks this: OPEN_DIRECTION (2) only
    counts for a door opened with nobody opening it. A `func_door` slides along `angle`
    (-1 up, -2 down) by its size that way less `lip` (8) (`SlidingDoor::Setup`).
  - A door moves at an even speed from wherever it is (`Mover::MoveTo`). A whole move takes
    `time` seconds, or `doortype` wood 1 s / metal 1.5 s, whichever of those keys comes
    last (wood unless set); a `func_door`'s `speed` (units a second) overrides both, and on
    a `func_rotatingdoor` `speed` is the rate itself (1 / time).
  - Once open it closes by itself `wait` seconds later (3 unless set), as `Door::OpenEnd`
    does; it stays open with TOGGLE (32) or with `wait` -1 or 0. Closing a door that is
    still opening sends it back from where it is, and opening a closing door sends it back
    the way it went.
  - Doors of one class whose boxes touch open and close as one, led by the first of them
    in the .map (`Door::LinkDoors`), so both leaves of a double door swing away from the
    camera. DOOR_DONT_LINK (4) keeps a door from leading others.
  - Everything of the door moves with it: its faces and the game's lit polygons, the
    selection and hover outlines, its setsize box, label and target links. It can be
    clicked where it is, and Fly to goes to it there.
  - `r_showtris` follows the door: its lines move and turn with it, its axis cross turns,
    the server links it where it is, and its area portal is open from the moment it starts
    to open until it is shut again (`gi.AdjustAreaPortalState`, counted as
    `CM_AdjustAreaPortalState` counts them), so the rooms behind it are drawn while it is
    open. A door that starts open (spawnflags 1) opens its portal only if it leads its
    group, as `LinkDoors` does it, and stays where the .map has it until it is closed.
  - A door's info card has a **Door** section: how it opens, how long that takes, when it
    closes, what opens it in game (the use key, AUTO_OPEN, TARGETED, or being shot), the
    doors linked to it and the areas its portal joins.
  - A `script_door` moves only when its map script tells it to, so its button is greyed out
    with the reason.
  - The info card's Script lines no longer give a door the angles of its `angle` key, which
    sets the way it opens, not its angles (`Door::SetDir`).
  - The shortcut lists (`H`, and `F1` in the launcher) have `O`.

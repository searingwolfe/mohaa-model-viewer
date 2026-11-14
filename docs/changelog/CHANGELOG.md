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
- Privacy notice (`docs/PRIVACY.md`, `PRIVACY_TEXT`), dated 28 October 2026: the pages also
  keep the game cvars that are set among their display choices in browser storage, in both
  viewers' wording (`_PRIVACY_SWAPS`). SECURITY adds `.lod` files to the model files it
  bounds.

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
- rev 71: the game's debugging cvars, as in the Map Viewer: a **game cvars** list under Display, below backdrop (or `` ` ``, the game's console key), with the Map Viewer's list, console and foot. A click on a row sets it (again: back to its default); `name value` then Enter in the filter box sets a cvar and a name alone tells its value. The cvars set are named beside the button and kept for this browser.
  - `sv_showbboxes` draws what `Entity::DrawBoundingBox` (`entity.cpp`) draws for the model, within 1000 units of the player (here the camera; `findradius` measures to the linked box's centre): 1 a yellow box turned with the model, its uprights blue (`G_DebugRotatedBBox`), 2 the magenta box the server links it with (the turned box's bounds, a unit bigger, `SV_LinkEntity`), 3 and 4 the yellow box, 7 a cyan box of the .tik's own bounds, 8 the yellow box and a small cyan one on the origin. The box is the entity's size as the game sets it: the .tik's `setsize` (or the one being edited with the pencil), else the bounds of its `idle` animation times its scale (`Entity::setModel`, `TIKI_CalculateBounds`); a player model gets the box a player gives itself (standing, pmove). A `.map`'s box is never the game's. 7 shows the idle animation's bounds (the union of its frames, the last `idle` loaded winning, `TIKI_InitTiki`), not bounds that follow the animation playing.
  - `sv_showbboxes 9` draws the 19 hit-location spheres (`cm_trace_lbd.cpp`) as circles facing the camera, 24 segments each (`G_DebugCircle`): blue on each location's Bip01 tag at its offset along the tag's axes, purple for the second sphere off the same tag. They follow the animation and the placement angles. 10 to 27 show one location (value - 10; 28 shows nothing, so the left foot only shows with 9), and a missing tag ends the loop as in game. Only a Sentient gets them (classname Actor and the like, or a player model); anything else solid gets a plain yellow box, not turned. Negative values are the player's own and draw only on a player model.
  - `r_shownormals 1` draws a white line 2 units long along each drawn vertex's normal, over everything (`DrawNormals`, `tr_shade.c`), turned by the vertex's first weight's bone (`SkelVertGetNormal`). The build now reads the normals stored in the `.skd` / `.skb` (`DATA.normals`, base64 bytes).
  - `r_uselod 1` draws the model at the game's level of detail for its distance from the player: `R_CalcLod` (radius x 100 / fov over the distance; radius 92 for a `ischaracter` .tik, else the playing frame's radius times load_scale), `GetLodCutoff` with `r_lodscale` (1.1) and `r_lodcap` (1), and `RB_SkelMesh`'s render count, collapse map and dropped triangles, per part (`tr_model.cpp`). Each part's curve is its `.lod` file, or the default curve built from `lodIndex` (`GetLODFile`, `TIKI_CalcLodConsts`, `tiki_skel.cpp`). `cg_fov` (80) sets the field of view it measures with, at 4:3 (fov_x = cg_fov). A **LOD** slider under the list's button moves the model away without moving the camera, with the triangles drawn of the total beside it. The viewer starts with `r_uselod 0` and draws every triangle (the game's default is 1); with 0 the LOD code does nothing at all. The build reads each surface's collapse map and index (`lc`, `li`) and each part's LOD control (`DATA.lods`); animations carry their frames' radii (`rad`).
  - `cg_showemitters 1`, `cg_showtempmodels 1` and `vss_showsources 2` print the game's lines (`0:emitter:N tempmodels emitted`, `TC:N`, `VSS Sources In Use: N`) in a console box over the stage, each frame the effect clock runs; `vss_showsources` 1 and 2 ring each volumetric smoke source at its radius, where the game draws `VSSSource.spr`.
  - The list's foot says what was drawn and why not: the box and where it came from, how many hit locations, the camera out of range, a missing tag, the triangles drawn per part with the part's cutoff and curve.
  - `HOST_T` / `HOST_SR` hold the host's triangles as drawn; `attRebuild` appends attachments to them, through `attLive`, which the level of detail also runs. An attachment's texture records are made once, not on every rebuild.
  - The shortcut lists (`H`, and `F1` in the launcher) have `` ` ``.
- rev 72: an AI's box. `sv_showbboxes` boxes a model of class Actor as a standing player, ( -15 -15 0 ) ( 15 15 94 ), whatever its `setsize`: `Actor::EventStart` (`actor.cpp`) calls `setSize(MINS, MAXS)` as the AI starts, after its spawn args and its .tik have set theirs (`SpawnArgs::Spawn` runs the pending events before `EV_Entity_Start`; a map posts the args at -7 and the start at -1), and `MINS` / `MAXS` are the player's standing box (`bg_pmove.cpp`, from `MINS_X`...`MAXS_Z` in `bg_public.h`). The dog gets it too. The list's foot names it, and says the setsize being edited with the pencil doesn't change an AI's or a player's box; it no longer says that an AI's box can differ in game.
- rev 73: attach-to-bone slots. The bone is a picker like the model beside it: it opens the tags & bones list for that slot, current node highlighted and scrolled into view, and a pick moves the attachment to the new node with its model, scale, offset and angles kept (Enter with nothing typed keeps the node). A copy button after the angles puts the slot on the clipboard as a script line, `local.entity attachmodel <model> "<tag>" <scale> "entity_targetname" 1 -1 -1 -1 -1 ( x y z )`, in the argument order of `EV_AttachModel` (`entity.cpp:379-395`, `Entity::AttachModelEvent` :4294-4386) with the model path written as `CanonicalTikiName` resolves it (`g_utils.cpp:1524-1535`); its tooltip shows the line. attachmodel has no angles argument, so the angles are not in it. If the Clipboard API is refused it falls back to a copy command, and if that fails too the line is shown under the animation list to copy by hand. The `building...` note has a line of its own under the model picker, since the first line no longer wraps.
- rev 74: stopping the camera, as in the Map Viewer. `X` stops it (the CAMERA panel's Free-look lines have `X stop camera` under `R reset camera`, and the shortcut lists, `H` and `F1` in the launcher, have it under Both cameras). It also stops by itself when the page loses the keyboard or the window (`blur`, or the tab hidden), each frame while the page doesn't have the focus, and in the launcher's pane on any click on the launcher, since a key or mouse button let go outside the page never reaches it and the camera kept flying or turning. A drag ends when its button turns out to have been let go outside the page (the next mouse move comes with that button up). Opening the shortcuts window stops it too. `stopCamera()` clears the keys held and ends the drag.
- rev 75: the camera stays stopped. An auto-repeat of a key the camera has let go of (`e.repeat`) no longer takes the key up again; only a new press does. When the camera was stopped with the key still held (X, a click on the launcher, the page losing the keyboard), the repeats still arriving started it again, and the key's release then went to the launcher, so it flew on. A held key is kept by its lower-case letter (`heldKey`), so a key let go with Shift down (key-up `W` for a `w` pressed before Shift) is let go. `releaseCameraKeys()` lets go of the keys only, and a drag goes on; the launcher calls it when the keyboard went elsewhere (see Launcher). X shows "Camera stopped" in the accent colour beside `H hotkeys` for a moment, as the Map Viewer does (`flash`; `#hint` holds two chips). Pages draw pixel for pixel as before.
- rev 76: a right-click that opens the browser's own menu stops the camera (a `contextmenu` the page doesn't cancel). The page cancels none, so that is any right-click on it. The menu takes the keyboard while it is open, so a key let go then never reached the page and the camera flew on; in the launcher's pane only the key watch (rev 75) let go of it, once the key came up. In the pane the menu is Edge's (Back, Refresh, Inspect...), which tkwebview2 turns on. Pages draw pixel for pixel as before.
- rev 77: a Reset button in the game cvars list's head, at its right, after the "N set" / "all at default" count: it sets every cvar that is set back to its default (`resetCvars`), so the count beside the game cvars button reads "none set" again. Greyed while none is set.
- rev 78: every popup list closes when the window changes size (maximize, restore, a drag of its edge): the surfaces list, which was moved back beside its button, and the game cvars list, which was left where it was (far from its button once the window grew), now close like the animations and attach-to-bone lists.
- rev 79: an attached model is sized by its own .tik's setup `scale` over the host's, as the game multiplies each entity's verts by its own load_scale. Before, it was drawn at its raw size in the host's unscaled space, so a player (`scale 0.52`, from models/player/base/include.txt) on the jeep (`scale 1.33`) was 2.6 times too big. A rifle (0.52) in a player's hand (0.52) is unchanged. The launcher reads the attached .tik's scale (`$include`s too) and passes it as `--attachscale`; the attachment's record carries it as `ls`, and its cache key changed (`attach2|`) so old attachments are rebuilt.
- rev 80: Up / Down move the free-look camera forward and back level with the ground (the view's forward with its height taken out), where W / S follow the view. The keyboard window says so.

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
- rev 71: pages built before this have no game cvars list, and animation sidecars built before this carry no frame radii, which `r_uselod` measures a playing animation by.
- rev 72: pages built before this box an AI by its setsize instead of the box it gives itself as it starts.
- rev 73: pages built before this show an attachment's bone as plain text (no picker) and have no copy button.
- rev 74: pages built before this have no `stopCamera()` for the launcher to call, and no X.
- rev 75: pages built before this have no `releaseCameraKeys()` for the launcher to call, a key's auto-repeats start the camera again after it stopped, and X shows no message.
- rev 76: pages built before this keep flying while a right-click's browser menu is open.
- rev 77: pages built before this have no Reset button in the game cvars list.
- rev 78: pages built before this leave the surfaces and game cvars lists open when the window changes size.
- rev 79: pages built before this draw an attached model at its raw size, without its own or the host's .tik `scale`.
- rev 80: pages built before this move along the view with Up / Down.

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
- `.lod` files are extracted with the model: they were refused as unsafe entries (an Output line `(skipped unsafe pak entry: ....lod)` on every open of a folder that has one). A `.tik`'s skelmodel and each part it assembles get their own `.lod` beside the `.skd`, where `GetLODFile` reads it.
- A `.tik` open also extracts the animation the `.tik` names `idle` (the last one, as `TIKI_InitTiki` takes it), which characters reach only through `$include`: the page sizes the model by its bounds and measures its level of detail by its radius.
- A click anywhere on the launcher (not on the pane) stops the embedded viewer's camera (`_stop_view_camera`, calling the page's `stopCamera()`), now in the Model Viewer too: it moved from `MapApp` into `App`, which both launchers bind it in.
- The launcher stops the embedded viewer's camera however it takes over (`_watch_camera_stop`, run by `App` and `MapApp`). A right-click on the launcher while W was held left the camera flying after W was let go, in both viewers.
  - A click with any mouse button on a launcher widget stops it (`<ButtonPress-1>` to `-3`, `_stop_view_camera`).
  - A key pressed or let go while the launcher has the keyboard makes the page let go of its keys (`<KeyPress>`, `<KeyRelease>`, `_release_view_keys` calling the page's `releaseCameraKeys()`); a drag or a fly-to in the page goes on. The launcher's own shortcuts still work: Tk runs the most specific binding of the `all` tag, so F1 runs F1's.
  - On Windows the keyboard itself is read every 100 ms while a viewer is open (`GetAsyncKeyState` through `KEY_IS_DOWN`, over the camera keys `CAMERA_VKS`). When the last camera key comes up, wherever its key-up went, the page lets go of its keys (`_poll_camera_keys`). Only that change acts, so a key held in the page is never let go of early.

- The Model Viewer and the Map Viewer share their loaded paks through one list,
  `mohaa_paks.json` beside their settings (`PAKS_SHARED`, `read_shared_paks`,
  `write_shared_paks`).
  - Each program writes the list whenever it adds, removes or clears paks
    (`_paks_changed`).
  - Each starts with that list (its own `pk3s` when there is none yet) if "Remember
    loaded paks" is on.
  - When its window gets the focus, it takes up a list the other changed meanwhile
    (`_paks_watch`, `_paks_follow`), with a line in its output.

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
- Typing a value into an attachment's boxes and then clicking one of its buttons works on the first click. Committing the value rebuilt the attachment rows, which replaced the button between its mousedown and mouseup, so the click was lost (x and the model picker needed a second click); a commit now only re-poses the model (rev 73).

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
- Map Viewer page rev 22 (`MAP_VIEWER_REV` 22, `MAP_VIEWER_REV_REQUIRED` 22,
  `INDEX_VERSION` 8): the rest of the game's debugging cvars that the page can show, in
  groups (What the renderer draws, Lighting, Entities, AI paths, The game the entities
  spawn for). Each row's tooltip says what it does, and a row the map can't use is greyed
  out with the reason. A cvar can take a number box (`r_farplane`) or a colour
  (`r_farplane_color 1 .5 0`, three words in the console).
  - `r_lockpvs 1` keeps the leafs the renderer marked from where the camera was
    (`R_MarkLeaves` stops), so flying out with `r_showtris 2` shows the whole of what the
    game draws from that spot; the entities still follow the camera, as the server sends
    them from where the player is. `r_novis 1` ignores the vis data and the doors (every
    leaf is kept). The server's marks and the renderer's are kept apart for this.
  - `r_showsky 1` draws the parts of the sky box the game draws from here in front of
    everything: the sky polygons in view, projected onto the six sides of a box round the
    eye and rounded out to quarters of a side (`ClipSkyPolygon`, `tr_sky.c`). In game the
    walls are drawn after the sky and still cover it, unless the sky has a solid cloud
    layer. The build sends the sky surfaces (`sk`).
  - `r_farplane N` fogs and culls at N units instead of the map's farplane, in
    `r_farplane_color` (.5 .5 .5), culling what `r_farplane_nocull` says (0 the BSP nodes
    and models past it, 1 nothing, -1 the models only); `r_farplane_nofog 1` drops the fog
    (the map's or r_farplane's) and keeps the culling.
  - `r_lightmap 1` shows lightmapped surfaces with their lightmap in place of their
    texture: the game draws a surface's stages only as far as its lightmap stage, and a
    stage joined with the texture replaces the colour (`CollapseMultitexture` emulated per
    shader, `lmr` in the shader index). `r_lightmap 2` colours the lightmaps by how bright
    their raw bytes are, as the game makes them when the map loads (`tr_bsp.c`); the
    brightest value is under the list. The lightmaps are now sent raw (`raw`, `shift`) and
    brightened in the page as `R_ColorShiftLightingBytes` does, byte for byte as before.
  - `r_light_showgrid 1` puts a small square on each light grid point within 256 units of
    the camera, in the colour the grid gives there (`R_GetLightingGridValueFast`). The build
    sends the light grid.
  - `r_showstaticbboxes 1` draws a magenta box round each static model the game draws from
    here: its .tik's bounds times its scale, turned with it. The build sends each model's
    .tik bounds (`tb`, from its idle animation's frame bounds).
  - `sv_showentnums 1` writes each entity's number (the one script errors give) in yellow
    over it, within 1000 units of the player: the world 1022, then every map entity from
    `sv_maxclients` up in the order the game spawns them. Path nodes, player starts and
    other simple entities have none; `g_gametype`, `skill` and `developer` decide which
    entities spawn (spawnflags 256 / 512 / 1024 / 2048 / 8192).
  - `sv_showbboxes 1`, `2`, `3`, `4`, `7` and `8` draw `Entity::DrawBoundingBox`'s boxes
    within 1000 units: 1 solid entities turned with them (yellow, blue uprights), 2 the
    box the server links a solid entity with (magenta), 3 entities with a .tik, 4 every
    entity, 7 a model's .tik bounds (cyan), 8 the box and a small cyan box on the origin.
    9 to 27 (a person's hit spheres) are in the Model Viewer.
  - `g_entinfo 1` to `4` tell about the entity you look at (within 1024 units and 18
    degrees; an AI within `g_entinfo_max` and 25): its number, radnum, targetname and
    health over it, a door's state, an AI's think state. 1 adds an AI's green leash circle
    round its home and its mindist (red) and maxdist (blue) circles, 2 its hearing (red)
    and sight (blue) circles, 3 the text alone, 4 the text of every AI whatever the
    direction. The radii come from the AI's keys or the game's defaults, fixed up as
    `Actor::FixAIParameters` does. An info card says the entity number and radnum.
  - `sv_showcameras 1` draws the cameras (a wire stand-in: `func_camera.tik` isn't in the
    game's files) and their spline paths in yellow; `g_showflypath 1` the paths a
    `script_object` can fly along: a cyan box on each `info_splinepath` and a green line to
    the next. The curves follow `CreatePath` and the B-spline's clamped or looped ends.
  - `cg_rain_drawcoverage 1` draws a red rectangle at the bottom of each `func_rain`, cut
    to `rain_min_dist` round the player (the map script's, else 512): where its drops
    land. The build reads the script's value (`rain`).
  - `ai_shownodenums 1` writes each path node's number in yellow over it, within
    `ai_showroutes_distance`. `ai_shownode N` shows up to N path nodes the game finds for
    where you stand: the nodes of your 256-unit cell within 94 units of your height that a
    player-sized box can reach (traced against the world's brushes, bevels included), nearest
    first, else the nearest, each a 31 x 31 x 36 box in its type's colour with a line
    toward its yaw; a red circle when there is none. `ai_showallnode 1` shows every node at
    your height. The feet are lifted out of solid ground first.
  - `g_nodecheck 1` says whether the build the map's `.pth` was saved from failed the node
    check (the file's `failed` flag, sent as `fail`) and lists nodes with 48 connections
    or more.
  - The foot of the list adds the lock, the sky blocks, the farplane and fog, the brightest
    lightmap value, the light grid, the rain distance, the entities that spawn and their
    numbers, and what ai_shownode found.
  - World text (entity and node numbers, g_entinfo) is drawn camera-facing and depth
    tested from a canvas atlas; the cvars' lines have their own depth-tested pass.
- Map Viewer page rev 23 (`MAP_VIEWER_REV` 23, `MAP_VIEWER_REV_REQUIRED` 23): an AI's box.
  An entity of class Actor gets a standing player's box, ( -15 -15 0 ) ( 15 15 94 ),
  whatever its `setsize` key or its .tik's setsize: `Actor::EventStart` calls
  `setSize(MINS, MAXS)` as it starts, after its spawn args (posted at -7, the start at
  -1). `sv_showbboxes`, `sv_showentnums` (the number sits on the box's top) and
  `g_entinfo` (its text, circles and leash line) all use it, and the `sv_showbboxes 1`
  tooltip says how each entity is sized. On m4l3 that is all 98 AI, none of whose .tik
  setsizes is that box.
- Map Viewer page rev 24 (`MAP_VIEWER_REV` 24, `MAP_VIEWER_REV_REQUIRED` 24):
  `r_shownormals 1` in the game cvars list (What the renderer draws). A white line 2 units
  long along the normal of each point the game draws from where the camera is, over
  everything, on the points r_showtris uses (`DrawNormals` runs on every batch drawn, as
  `DrawTris`). A face takes its plane (`lightmapVecs[2]`, as `ParseFace` copies it), a
  triangle soup its vertex normals, a patch its grid's normals at the rows and columns
  kept (`MakeMeshNormals`, ported as `grid_normals` in mohaa_bsp.py), and a model each
  vertex's normal turned by its first weight's bone (`SkelVertGetNormal` /
  `pStaticNormal`); an entity's lines are 2 world units, a static prop's 2 of its own
  units, stretched by its scale. Terrain has none (`tr_terrain.c` never fills them in).
  The tooltip says that in game a face or patch fills its normals in only when its shader
  uses them or a dynamic light is in the scene, and otherwise shows stale ones; the page
  always draws each surface's own. The build sends a normal for every point of the
  surfaces (`vn`), each face's and soup's run of points (`si` 5 and 6) and each model's
  vertex normals (`n`): the m4l3 page grows by 1.6%. The lines are built the first time
  the cvar is on, from where the doors are then, and a moving door turns its normals. The
  foot counts the lines by kind; the legend has a Vertex normals row. Defaults are pixel
  for pixel as rev 23.
- Map Viewer page rev 25 (`MAP_VIEWER_REV` 25, `MAP_VIEWER_REV_REQUIRED` 25): an
  `angles: pitch yaw roll` box and a **Copy ang** button under `go to: x y z` / Copy pos in
  CAMERA. Enter turns the camera, where it stands, to the angles typed or pasted, as the
  game takes them (`AngleVectors`: looking down is a positive pitch); Copy ang copies its
  own as `( pitch yaw roll )` for a script. The page's roll turns the other way to the
  game's, so both swap its sign (`camAngles`, `turnTo`); `flyTo` can now turn the roll
  too (the angles box uses it).
  Both boxes read numbers like `.5` and `1e3` (`vecNums`). `ai_showroutes_distance`
  starts at 8200 (the game's default, 1000, is in its tooltip and the console's answer,
  `CVAR_GAMEDEF`), so the routes and node numbers show from far away. Defaults are pixel
  for pixel as rev 24.
- Map Viewer page rev 26 (`MAP_VIEWER_REV` 26, `MAP_VIEWER_REV_REQUIRED` 26): the camera
  stays stopped. An auto-repeat of a key the camera has let go of no longer takes the key
  up again (Shift and Ctrl too); only a new press does. When the camera was stopped with
  the key still held (X, a click on the launcher), its repeats started it again and its
  release went to the launcher. `releaseCameraKeys()` lets go of the keys only (a drag,
  Radiant-look's flight and a fly-to go on), for the launcher to call when the keyboard
  went elsewhere (`_watch_camera_stop`, in the Launcher section). Defaults are pixel for
  pixel as rev 25.
- Map Viewer page rev 27 (`MAP_VIEWER_REV` 27, `MAP_VIEWER_REV_REQUIRED` 27): camera keys.
  - Q tilts the view to the left (the head to the left shoulder: the horizon's right end
    drops on screen) and E to the right, as in the Model Viewer; they were the wrong way
    round. A positive `cam.roll` turns `camAxes`' right axis up, so Q adds to it. The
    angles box (Copy ang) gives a tilt to the left as a negative roll, as the game takes
    it (`AngleVectors`).
  - `U` levels the view (no pitch, no tilt), in place of `End`, in both cameras, the
    CAMERA lines and the shortcut lists. End's own job in a browser is to scroll what has
    the focus to its end, so with the focus in the side panel the panel jumped to its
    bottom. End is the browser's again.
  - A right-click that opens the browser's own menu stops the camera, as in the Model
    Viewer's rev 76: anywhere but the 3D view, whose right button flies and looks (its
    `contextmenu` is cancelled, so it opens no menu).
  - Defaults are pixel for pixel as rev 26.
- Map Viewer page rev 28 (`MAP_VIEWER_REV` 28, `MAP_VIEWER_REV_REQUIRED` 28): the Show and
  Find sections.
  - In-game look and Editor look are a row of two wide buttons at the bottom of Show, under
    All, like the cameras' Free-look and Radiant-look. Each is on while the Show buttons,
    the light and the sky are still as it set them (`GAME_LOOK`, `EDIT_LOOK`). A look's
    name never breaks across lines: where the panel is too narrow for the name and its
    key, the key goes under it, and both buttons stay the same height.
  - Find has a fourth tab, **Entities**: "N real entities with entnums", the entities the
    game numbers (`gameEnts`, following the game cvars' g_gametype, skill, developer and
    sv_maxclients), in that order. Each row is the targetname, else `entity` and its
    number, with the number on the right when the name doesn't give it; a click selects
    the entity and flies there, and Shift+click its square hides it. The world (1022) and
    the entities that remove themselves as they spawn (misc_model, func_remove) aren't
    listed.
  - Textures: a click selects every brush and entity shown that uses the texture
    (`texUse`), models included. Only brush faces were looked at, so a texture only models
    use selected nothing: `armchairposh` on mohdm1, on its nine armchairs, gave "0 brushes /
    entities". Shift+click a texture's square hides all of them, as Hide does (again: shows
    them; Ctrl+Z undoes it), as the Textures hints say. A texture row is green while
    everything shown that uses it is selected, red when all of it is hidden, yellow with
    the hidden count when some is, like a class row.
  - The lists show the selection however it is made. Enter in the search box selected its
    results but left them uncoloured; `selectionChanged` now draws the lists again a frame
    later (`listSoon`). A class row is green while every one of its shown entities is
    selected.
  - The Results and Textures hints are split into lines, and Free-look's `U level camera`
    line sits under `Shift fast camera` (the user's own edits to rev 27).
  - Defaults are pixel for pixel as rev 27.
- Map Viewer page rev 29 (`MAP_VIEWER_REV` 29, `MAP_VIEWER_REV_REQUIRED` 29): keys written
  with `$` or `#` in front, read as the game reads them.
  - A spawn key that starts with `$` or `#` goes to the class's setter of that name when it
    has one (`SpawnArgs::SpawnInternal`, g_spawn.cpp; `#` as a whole number), so
    `"$targetname" "mg42guy"` names an entity just as `"targetname"` does. The retail maps
    use `$targetname` some 3600 times in 39 maps, and the page read only `targetname`. On
    m1l1, 101 of the 167 numbered entities showed as `entity N` in the Entities tab
    (entity number 33 is `$mg42guy`), and so did path nodes such as .map entity 136
    (`$enemyspawnerdestination`). The labels, links, Same targetname, Same path and the
    info card's name and Links missed them too.
  - Without a setter of that name a `$` or `#` key only sets a script variable (`#set` is
    `self.set`, `$type` is `self.type`), so it stays a key of its own, shown as written.
    Of the prefixed keys in the retail maps only `$targetname`, `#leash`, `#health`,
    `#turnspeed` and `#breathsteam` reach a setter.
  - Which form wins: an entity's keys are posted for one moment and the event queue runs
    them last to first (`Listener::PostEventInternal` puts each in front of the ones
    posted before it), so the first written of `name`, `$name` and `#name` wins. On m4l0
    that is `$targetname "hallway2"` over the editor's `targetname "t177"`. A plain
    `model` is due before the other keys (`EV_PRIORITY_SPAWNARG`), so a `$model` outlasts
    it. An actor's plain keys are posted after its `$` and `#` ones (`EV_SPAWNACTOR`), so
    there the plain key wins (m4l3's two `ai_german_elite_sentry`).
  - The setters' names (`SETTER_KEYS`, from the game's `EV_SETTER` events) are in
    mohaa_bsp.py and come with the page (`D.sk`). `spawnKeys` applies them to every
    entity's keys once the .map is read, and the build reads entities the same way
    (`MB.kv_dict`). `gameKey` (g_entinfo, the spline paths) now reads that view. It had let
    the last of `name` and `$name` win, and took `$loop` for `loop`, which has no setter.
  - MOHRadiant's look stays MOHRadiant's: a path node turns pink only for a `targetname`
    written as such (`edKey`), since the editor reads `$targetname` as any other key; on
    m1l1, 98 nodes named only that way stay green. The decompiler still reads the keys the
    map compiler wrote, as written (`ent_get`), and its .map files are byte for byte as
    before.
  - Defaults are pixel for pixel as rev 28.
- Map Viewer page rev 30 (`MAP_VIEWER_REV` 30, `MAP_VIEWER_REV_REQUIRED` 30): the sun flare.
  - Show has a fourth switch, **Sun flare** (J), on at first. In-game look turns it on and
    Editor look turns it off; each look counts it as one of the things it set, on a map
    that has a flare. It is kept with the other display choices (`sf`; options saved
    before it start with it on).
  - The page draws the game's lens flare the way `renderergl1/tr_sun_flare.cpp` does
    (`drawSunFlare`). It shows only while the view faces within the flare's `dot_min` of
    the sun. The sun counts as seen when a line from the camera toward it first meets a sky
    face (`SunCheckRay`). The flare's brightness follows the angle to the sun, and the
    screen whitens by that brightness to the 4th power times `fullscale`.
  - Once the sun goes out of sight, the glare fades over `fullfade` ms (600 for "sun"),
    and so does the flare while the view still faces the sun. Each flare is a square of
    ±`size` screen units, stretched with the window, on the sun's place on the screen. The
    glare, the flare and `RB_DrawSun` being compiled out are in engine-notes.
  - The page only draws when something changes, so a fade starts when the sun was in
    view in the last frame drawn, however long ago that was. While a fade runs the view
    keeps redrawing.
  - The line toward the sun (`sunTrace`) meets the world's solid brushes as
    `CM_TraceThroughBrush` does, a sky face being one with `SURF_SKY` or a sky shader. It
    also meets solid patches and the terrain, by their drawn triangles. Brush entities,
    models, static props and fences let it through, as the game's trace does, and the
    Show buttons don't change it. It is traced again only when the camera moves.
  - In a .bsp, `Bsp.sun_leafs` reads which leafs list the sun from the sphere-light vis
    lump (`LUMP_SPHERELIGHTVIS`, 20) and the page gets them as `D.vis.sun`. As in game,
    the page looks for the sun only from those leafs, from a leaf outside the map, or from
    anywhere when the map has no vis or no leaf lists the sun.
  - The build reads the worldspawn's sun keys from the entity lump as the renderer does
    (`world_sun`), then the flare's section of `global/lensflaredefs.txt`
    (`lens_flare_def`). The flare's picture is the first stage of its shader, kept as PNG
    so its glow has no JPEG blocks (`_flare_picture`). All of it goes to the page as
    `D.sun`.
  - On a map without a flare the button is greyed out and its tooltip says why (J says the
    same). The reason is one of: no sun, `"sunflarename" "none"`, no direction, no such
    flare, or no paks.
  - 17 retail Allied Assault maps have a flare: m2l2a-c, m2l3, m3l2, m3l3, m4l0, m5l2a,
    m5l2b, m5l3, m6l3b-d, mohdm1, mohdm3, mohdm6 and obj_team2. Most others name
    `sunflarename none`. m6l3c and m6l3d have no sky face to see it through.
  - The build log has a `sun flare:` line.
  - The legend's Sky entry says the sun is seen through the sky faces.
  - With Sun flare off the page is pixel for pixel as rev 29. With it on, only views
    facing a map's sun change.
- Map Viewer page rev 31 (`MAP_VIEWER_REV` 31, `MAP_VIEWER_REV_REQUIRED` 31): turning the
  map's lights off.
  - Display has **Lights off** (`0`), off at first: every light entity off, as if it had
    never been in the map. Pressed again, every light comes back on. While only some
    are off, the button has a dashed border and its tooltip counts them.
  - Selection has **Turn off** and **Turn on** after Clear, shown when the selection holds
    a light entity (a class starting with `light`, as the compiler takes them). Turn off is
    greyed out when they are all off, Turn on when none is.
  - What changes is the light the game draws with: the lightmaps (polygons, patches,
    terrain, brush entities), vertex-lit polygons, the static props' baked vertex light
    and the light grid colour of models lit by it. Coronas, flares and bright textures
    stay as they are.
  - Nothing is kept: every page opens with all lights on.
  - The compiler doesn't store which light gave which part of a texel's light, so the
    page works it out on the graphics card (`ltWeigh`), from what the compiler did with
    each light (engine-notes, Baked light):
    - each light's share at each lightmap texel and probe, with q3map's formula, behind
      a distance cube of the drawn opaque surfaces and the solid brushes, plus a small
      share without shadows within its reach;
    - on a map with sky faces, the sun's and the sky's (`ltSun`, from a distance map
      toward each of 17 directions).
  - The texel's new value keeps the ambient floor and scales the rest by the share
    still on: `min(V, A) + max(V - A, 0) x (lights on + sun) / (all lights + sun)`. With
    every light off on a map without sky, only the floor is left.
  - No more is taken out than the lights turned off could have given there: at most
    twice their light without shadows (`LT.kap`), read from their share without shadows
    in the OFF sum. Without that cap, shaded open ground and eaves far from any light
    (lit by the sky in ways the page doesn't trace) went black with the lights off: on
    mohdm1, light 108 off darkened 857 texels 512-1224 units away by more than 16 levels
    (49 with the cap), and all lights off left hard black patches in its sunny
    courtyards. Rooms still go black (mohdm1's rooms 4-5 out of 255 on average).
  - The weights are summed in half floats at a sixteenth of their size, so a texel next
    to several strong lights can't overflow (m1l2b's largest sum is 14384 before
    scaling). The share is kept within 0-1.
  - Probes are the props' vertices, the vertex-lit polygons' vertices and one per
    grid-lit model at its origin. The relit lightmaps (`LT.lmOut`) and probes (`LT.pOut`)
    replace the baked ones while a light is off. The models read theirs at their slot
    (`aISlot` in the model shader), the vertex-lit polygons at theirs (`aVP`).
  - The first time takes a while; a progress line counts the lights. In a software
    renderer (SwiftShader) mohdm1's 156 lights and its sun took about 22 s, and m4l3's
    313 lights about 60 s; a graphics card is many times faster. After that each light
    turned off or on is one light's work.
  - Greyed out, with the reason in the tooltip (`0` says the same):
    - on a `.map` page, which has no baked light (the map compiler bakes it into the
      `.bsp`);
    - on a `.bsp` without lightmaps;
    - on a map without light entities;
    - where the graphics driver can't draw into float textures (`EXT_color_buffer_float`).
  - The build also sends each patch's control-point normals (`pn` in the lighting
    payload), so a patch is lit from its front, as the compiler lights it.
  - Checked on m6l3d (no sky: the rooms go black), mohdm1 (the courtyards stay sunlit,
    the houses go dark) and m4l3 (the moonlight stays).
  - With no light turned off the page is pixel for pixel as rev 30 (mohdm1 with the sun
    flare, m4l3, m6l3d, m4l0.map). Turning every light back on gives the same picture
    again. The decompiled .map files are byte for byte as before.
- Map Viewer page rev 32 (`MAP_VIEWER_REV` 32, `MAP_VIEWER_REV_REQUIRED` 32): Lights off on
  a graphics card.
  - On an RTX 3080 Ti in the launcher (WebView2, ANGLE on Direct3D 11), the first Lights
    off or Turn off on mohdm3 reset the graphics driver. The screen went black for several
    seconds, and the page then reported the reset.
  - It doesn't happen here: SwiftShader and Mesa's llvmpipe (ANGLE's OpenGL backend) both
    finish mohdm3's 94 lights and its sun in about 0.4 s. A reset on that card means a
    shader that never finishes rather than too much work.
  - The relight pass had the only loop in any of the page's shaders: the dilation's ring
    loop, whose condition was read inside it (`r<=2&&n==0.0`), with `continue`. It was also
    the only draw without vertex attributes (`gl_VertexID`).
  - What changed in the shaders and passes:
    - The dilation reads its 24 neighbours with loops of fixed length: a table of
      offsets, the ring beside the texel summed apart from the one two texels out, and a
      0/1 weight instead of `continue`.
    - The full-screen passes take their triangle from a buffer (`LT.vQ`).
    - The shadow maps are read with `texelFetch`, so the sun pass sets `uSz`.
    - Depth writes are on before the depth clears.
  - The work goes a few steps at a time (`LT.batch`, 4). The next batch starts only after
    a fence says the graphics card has finished the last, and each batch ends with a
    `flush` (`ltRun`). The relight is two steps, pages then probes.
  - Step notes: the names of the steps the card is working on go into the browser's
    storage (`mohaa-map-lights-step`, with the page's title), all of a batch's, since the
    card runs them together. The note is dropped 1.2 s after the result is drawn.
    - The driver-reset message names those steps.
    - On the next load of the same map, the Lights off tooltip says so and the first
      press only warns. A second press within 6 s runs it one step at a time.
  - The relit pages and probes are byte for byte as rev 31 on mohdm1, all lights off and
    light 108 off, in SwiftShader and llvmpipe. With no light turned off the page is pixel
    for pixel as rev 30.
- Map Viewer page rev 33 (`MAP_VIEWER_REV` 33, `MAP_VIEWER_REV_REQUIRED` 33): Sun light.
  - Display has **Sun light** (`-`), on at first, after Lights off. Off takes the sun's and
    the sky's light (the `ltSun` share: `suncolor` toward `sundirection`, and
    `sundiffuse` x `sundiffusecolor` from 16 sky directions) out of the baked light.
  - In the relight (`uSunOn` 0), the share left is the lights still on over all lights and
    the sun, and a texel nothing traced explains is taken out (it was the sky's).
  - The light left is no more than twice what the lights still on could give there
    without shadows: `uCap` x (TOT - OFF), the bound Lights off uses the other way round.
    Without it, shaded open ground near a light's reach would keep its sky light.
  - With every light off too, only the ambient floor is left (`ltDark`).
  - It works with Lights off and Turn off / Turn on in any order. The first time costs
    what the first Lights off does; after that it is one relight. Nothing is kept: a page
    opens with the sun on.
  - Greyed out, with the reason as the tooltip (`-` says the same):
    - where Lights off is (a `.map` page, no lightmaps, no light entities, no float
      targets);
    - on a map without sky faces or a sun colour (m6l3c, m6l3d).
  - The keys table has a `-` row.
  - Fix: whether the map has sky came from `LIT.sky`. That list holds only the sky polygons
    shown, so it was empty when the panel was built. With the Sky filter (`Ctrl+K`) hiding
    the sky before the first Lights off, the sun's share was left out. The page now looks
    at the `.bsp`'s polygons themselves (`ltHasSky`).
  - Checked on mohdm1 (open ground goes dark, the rooms keep their lamps) and m4l3 (the
    moonlight goes and the lamps' pools stay).
  - Lights off alone is byte for byte as rev 32. With the sun and every light back on, the
    page is as it opened; with nothing turned off, pixel for pixel as rev 30.
- Map Viewer page rev 34 (`MAP_VIEWER_REV` 34, `MAP_VIEWER_REV_REQUIRED` 34):
  - The game cvars list starts with its own group, "Render distance: farplane fog and
    culling" (`r_farplane`, `r_farplane_color`, `r_farplane_nocull`, `r_farplane_nofog`),
    above What the renderer draws.
  - The camera line at the bottom of the view adds `roll` after pitch while the camera
    is tilted (Q / E, or angles typed with a roll), the game's way round as Copy ang
    gives it.
- Map Viewer page rev 35 (`MAP_VIEWER_REV` 35, `MAP_VIEWER_REV_REQUIRED` 35): actors stand
  in their idle pose.
  - A placed model is posed at frame 0 of its `idle` animation. `parse_tik_animations`
    read only the first animations{} section of the `.tik` with its `$include`s spliced
    in, but every section counts (TIKI_ParseFile), and a character's idle is in
    new_generic_human.tik's.
  - Where an include came first with an animations section of its own (the dialogue
    .tiks, as in german_waffenss_shutze.tik), no idle was found. The model then had no
    animation and was drawn in its bind pose: lying flat and half under the floor. That
    happened to m4l1's Waffen-SS actors.
  - Where new_generic_human.tik came first, its first section (the balcony scene) gave
    the first animation in place of idle (m4l1's gestapo officers stood in
    death_balcony_intro's first frame).
  - The map builder now reads every section (`every=True`); the Model Viewer's own uses
    of the parser are unchanged.
- Map Viewer page rev 36 (`MAP_VIEWER_REV` 36, `MAP_VIEWER_REV_REQUIRED` 36): decals,
  the leak trail and `.bak` files.
  - **Decals** (Display, `=`): the map's permanent decals from `maps/<stem>.dcl`
    (`read_dcl`, `dcl_payload`; tr_marks_permanent.c's format, versions 1 and 2), drawn
    as fans with their shader times the lit colour the file keeps (white with Full
    Brightness), blended, polygon-offset, no depth writes. Checked on m2l1 (22 decals:
    the barracks' letters and numbers, the eagle poster, cracks).
  - **Leak** (Display, `P`): the compiler's leak trail from `<stem>.lin` (`leak_payload`),
    drawn through walls with the hole and the entity marked. Turning it on opens a card
    with the hole, the entity (selectable), every point with Go / Copy, what to fix, and
    a note when the `.lin` is older than the `.map` beside it. Checked on
    NormandyBridge_V1.
  - **.bak** opens like a `.bsp` or `.map` (by its first bytes). Its page is
    `<stem>_bak_view.html` and a `.bsp` backup's decompile `<stem>_bak.map`. The
    launcher takes `.bak` in Browse, drag-and-drop, the command line and the tree, and
    File -> Clear built maps knows its pages. The tree's tooltip on a `.pth`, `.dcl` or
    `.lin` says the viewer shows it with its map.
  - Display buttons that are greyed out no longer show as on.
  - Keys table: `=` and `P` rows.
- Map Viewer page rev 37 (`MAP_VIEWER_REV` 37, `MAP_VIEWER_REV_REQUIRED` 37): the level
  script's entities.
  - The build reads the map's `.scr` and the map scripts it runs (`LevelScript`,
    `script_payload`): `spawn` lines and the lines that give the same entity its origin,
    angles, targetname, target, model, scale or setsize, plus `setcvar` and `$world`
    lines. Scripts are found as the game finds them: a loose `main/maps/<map>.scr` before
    the paks, the file beside the one opened first.
  - The page adds the entities it could place after the map's own (`scriptEnts`), so
    waypoints and their `target` paths, script models, origins and actors are drawn,
    labelled, linked and selectable. Show -> Script ents (`Ctrl+E`) hides them. Their info
    card shows the script lines that placed them; the stats line opens a Level script
    card with the files, the placed and unplaced spawns, the setcvars and the `$world`
    lines.
  - They have no entity number, aren't counted with the map's entities, and aren't `.pth`
    nodes or static props (`pnEnts`, `isStaticProp`, `entityKinds`, `gameEnts`,
    `dlStaticBoxes` skip them).
  - Launcher: a page is rebuilt instead of reused when a loose file it was built from
    changed, appeared or went (`deps` in the page's summary: the map opened from disk,
    its `.scr`, `.dcl`, `.lin`, `.pth`, and the loose scripts read). Before, editing a
    loose `.map` and opening it again showed the old page.
  - Keys table: `Ctrl+E`.
  - `RUN -- Medal of Honor Map Viewer.bat` opens a `.bak` dropped on it (rev 36 missed it).
- Docs: the README's Map Viewer section brought up to date (lighting, Lights off, Sun
  light, decals, leak trail, `.bak`, level script, doors, game cvars); `doors-notes.md`
  and `game-cvars-candidates.md` added to these notes.
- Map Viewer page rev 38 (`MAP_VIEWER_REV` 38, `MAP_VIEWER_REV_REQUIRED` 38): the level
  script is walked, not just read line by line.
  - `LevelScript` reads the script as a tree (blocks, `for`, `while`, `if` / `else`,
    `switch`) and runs it once with what it can work out: loops with a known condition run
    turn by turn with their counter set (up to 4096 turns), `if` takes its known branch or
    both, and a variable the branches or an uncounted loop leave different is unknown.
  - `$( expression )` names an entity, `NULL` and `!= NULL` work, and so do comparisons,
    `&&` / `||` / `!`, `* / %`, `++`, `--` and `+=`. Conditions with a call in them
    (`getcvar(x)`) are unknown: before, `getcvar` read as a word and counted as true.
  - So `$("fhe" + local.q).target = $("fhe" + (local.q + 1))` in a `for` loop gives each
    waypoint its target, and the waypoint chains of a remastered m3l1b are linked.
  - A line setting the `target` of one of the map's own entities is applied in the page
    (`mods`), with a "Changed by the level script" section on its card and a list in the
    script card.
  - `setcvar` and `$world` lines run in a loop are listed once.
  - The map's title (its worldspawn message) is under the stats, above the level script's
    line, which now reads "N entities placed, R real placed, M not, K setcvar".
- Map Viewer page rev 39 (`MAP_VIEWER_REV` 39, `MAP_VIEWER_REV_REQUIRED` 39): the level
  script's threads run with their `self` and parameters.
  - Each script is split at its labels. `thread`, `waitthread`, `exec file.scr::label`
    (with an entity in front or not) read the label then, with that entity as `self` and
    the arguments in its parameters (`NIL` where none is given). A thread run for each
    MG42 gun (`bipod local.exists local.origin local.angles:`, `self.origin + ( -1.4 0 1 )`)
    now puts a bipod under each gun.
  - `self`, `self.<prop>`, `local.x.<prop>` for an entity passed in, and `<ent>.origin +=`
    are followed. Labels nothing runs by name are still read once on their own.
  - Guards: no recursion, 24 calls deep at most; a `while` that waits runs once; a
    `thread` / `exec`'s changes to `level.` variables don't reach its caller (m6l3a's
    respawn loop ran 4096 times through its death thread); one line spawns at most 1024;
    identical spawns of one line are drawn once. All 54 retail map scripts read in 0.9 s.
- Map Viewer page rev 40 (`MAP_VIEWER_REV` 40, `MAP_VIEWER_REV_REQUIRED` 40): weather.
  - **Weather** (Display, `Y`; `cg_rain`): rain and snow in the map's `func_rain` boxes the
    client has, made as `CG_Rain` makes them each client frame (`com_maxfps`, 85): drops
    per box from its area and the density, cut to `rain_min_dist` round the viewer, the
    game's random numbers, beams that fall to the bottom of the box (through roofs, as in
    game), drawn as streaks or, for the snow shaders, camera-facing flakes, additive.
    All drops share MAX_BEAMS (4096), so slow snow from high boxes clumps and gaps as in
    game. 1.11 (drops from the top of the box) or 2.0 / OpenMoHAA (anywhere in its height,
    10 s at most) with `com_target_game`.
  - Game cvars, Weather group: `cg_rain`, `cg_weather` (weather.scr's presets, or `map`),
    `cg_rain_density`, `_speed`, `_speed_vary`, `_slant`, `_length`, `_width`,
    `_min_dist`, `_shader`, `_numshaders`, `vss_wind_x` / `_y`, `com_maxfps`,
    `com_target_game`, `cg_rain_wholemap` (viewer only: the whole map one rain box) and
    `cg_rain_drawcoverage` (moved here; it now uses `cg_rain_min_dist`). The list's foot
    counts the beams falling and the drops not started for want of a beam.
  - Their defaults are the map's: the build reads `level.rain_*` and `setcvar "cg_rain_*"`
    from its script (m6l1a's snow, m6l2a's), and global/weather.scr's middle setting for
    m5l1a / m5l1b. The pictures of textures/rain and textures/snow0 to snow11 and their
    `rgbGen constant` come with every page (`weather_payload`).
  - Keys table: `Y`.
- Map Viewer page rev 41 (`MAP_VIEWER_REV` 41, `MAP_VIEWER_REV_REQUIRED` 41,
  `INDEX_VERSION` 9): thunder and moving leaves.
  - `cg_thunder` (game cvars, under `cg_rain`; not a game cvar): global/weather.scr's
    lightning at its own timings, without sound. A flash clears the screen without the sky
    (`r_fastsky 1`) to the farplane colour 0.9 0.9 0.9 (or 0.5 0.5 1 without a farplane)
    and shows the `$weatherF` windows, which are hidden between flashes. The time between
    strikes is the map script's `level.thundertime`, else 6 on weather.scr maps, else 20.
  - Models move by their shader's `deformVertexes wave` / `flap` (the trees' leaves), with
    the vertex normals and a per-instance static flag; static models' waves are scaled by
    `r_static_shadermultiplier0` .. `3` (new rows in the Weather group, default 1; 1.8 for
    multiplier 1 on weather.scr maps, its `(raindensity + 1.5) / 2.5` at the middle storm).
    The build reads each shader's first wave or flap deform (`_deform`).
  - LevelScript also keeps `level.thundertime`.
- Map Viewer page rev 42 (`MAP_VIEWER_REV` 42, `MAP_VIEWER_REV_REQUIRED` 42): Shift+click a
  green (selected) row in the Find, Classes, Textures or Entities list to deselect that
  entity, every entity of the class, or everything using the texture (`deselectRow`), with
  a "Shift-click any green text to deselect it" hint under each tab's counts. Shift+click
  an entity row that isn't green adds it to the selection instead of replacing it.
- Map Viewer page rev 43 (`MAP_VIEWER_REV` 43, `MAP_VIEWER_REV_REQUIRED` 43): the Find
  section's Entities tab starts with the client slots, `entity 0` to `sv_maxclients - 1`,
  greyed out and not clickable. Entity 0's tooltip is "reserved for $player, or $player[1]
  in multiplayer", each other slot's "reserved for $player[N] in multiplayer".
- Map Viewer page rev 44 (`MAP_VIEWER_REV` 44, `MAP_VIEWER_REV_REQUIRED` 44): the
  `cg_weather` and `cg_rain_shader` tooltips start their list of choices on a new line.
- Map Viewer page rev 45 (`MAP_VIEWER_REV` 45, `MAP_VIEWER_REV_REQUIRED` 45): each weather
  beam keeps the shader, length and width it started with (`WX.sh` is now a number in
  `WX.shTab`, with `WX.len` / `WX.wid`), as CG_CreateBeam stores them. Before, changing
  cg_weather redrew the drops already falling with the new settings: map snow's
  snow0..snow11 drops became white squares (their shader number pointed past the new list)
  and snow_original's flakes grew at once to blizzard's width.
- Map Viewer page rev 46 (`MAP_VIEWER_REV` 46, `MAP_VIEWER_REV_REQUIRED` 46): a Reset
  button at the right of the game cvars list's head, after the "N set" / "all at default"
  count, sets every cvar that is set back to its default (`resetCvars`; cg_weather first,
  whose `map` puts the cg_rain_ cvars back to the map's own). Greyed while none is set.
- Map Viewer page rev 47 (`MAP_VIEWER_REV` 47, `MAP_VIEWER_REV_REQUIRED` 47): the
  mouse-over's green outline and the selection's outline are drawn after the lines
  (`drawOutlines`), so with Wire on the hovered brush's edges turn green instead of staying
  under Wire's white edges.
- Map Viewer page rev 48 (`MAP_VIEWER_REV` 48, `MAP_VIEWER_REV_REQUIRED` 48): the game cvars
  list closes when the window changes size (maximize, restore...); it used to stay where it
  was, far from its button once the window grew.
- Map Viewer page rev 49 (`MAP_VIEWER_REV` 49, `MAP_VIEWER_REV_REQUIRED` 49): exploders.
  Run exploder and Reset exploder (Selection) appear with an exploder, explodersmashed,
  exploderchunk, exploderfire or explodertrigger selected. Run plays global/exploder.scr's
  "explode" for its #set: the $exploder hides after its #pause, the smashed brushes turn
  solid, and the chunks are thrown toward their targets. A chunk moves as a mover for 0.2 s,
  then bounces with physics_on (G_Physics_Toss, a box trace through the solid world,
  func_ entities and the set's brushes), spins, sinks after its first touch (moveitout)
  and hides 10 s after its spin stops. Reset puts the set back and shows its chunks
  (Hide's too). Nothing is hidden at the start. There are no emitters or sounds.
  - `doorPose` is now `entPose`, shared with the chunks; `doorXf` and `movObj` give a
    flying chunk's place to the boxes, labels and r_showtris.
  - The info card has an Exploder section.
- Map Viewer page rev 50 (`MAP_VIEWER_REV` 50, `MAP_VIEWER_REV_REQUIRED` 50): the search
  box takes `"exact value"`, `$targetname`, `key: value` (`*` for any letters; `texture:`,
  `entity:`, `entnum:`, `origin:`), `key:` alone, `entity 25`, `( x y z )` for an origin,
  and `-` before any term to leave out what it matches (`findTerms`). Results show an
  entity's targetname before its class. Every Results row has a tooltip with the whole row
  (targetname, class, entity number, origin, and whether it is hidden), where it used to
  say only "hidden".
- Map Viewer page rev 51 (`MAP_VIEWER_REV` 51, `MAP_VIEWER_REV_REQUIRED` 51): weather from
  the sky. With no func_rain in the map, or all of them hidden with Hide, the drops start
  under the highest sky brush over their spot and stop at the first solid thing below
  (`wxSkyMode`, `wxCol`). Indoors and in tunnels nothing falls. The Weather button, the
  cvar rows and the list's foot say so.
- Map Viewer page rev 52 (`MAP_VIEWER_REV` 52, `MAP_VIEWER_REV_REQUIRED` 52): drawing
  speed.
  - **One draw a frame.** The frame loop draws, and `requestDraw` only asks it to. Before,
    looking with the mouse while moving with the keys drew twice a frame, as did the
    clouds' timer and the hover outline.
  - **View culling.** World faces and the game's polygons are sorted by 1024-unit cell
    within each texture's run, and parts outside the view, past the far plane (fog,
    r_farplane, cubic clip) or outside the cubic clip are skipped. Model instances are
    culled by their bounding spheres.
  - **Overlay and text.** The overlay canvas is cleared only when used, and the camera
    line and the game cvars list's foot are updated about 8 times a second while moving.
  - On m5l1a a frame sends about 3.6 times fewer triangles (14 times fewer with Cubic clip
    2048), with the same picture.
- Map Viewer page rev 53 (`MAP_VIEWER_REV` 53, `MAP_VIEWER_REV_REQUIRED` 53): on a map
  whose own settings make no weather (no density from its script), `cg_weather` and the
  `cg_rain_*` cvars start at the "rain" preset instead of "map", so turning Weather on
  makes rain (from the sky on maps without func_rain). The cg_weather tooltip says so.
- Map Viewer page rev 54 (`MAP_VIEWER_REV` 54, `MAP_VIEWER_REV_REQUIRED` 54): the level
  script reader handles `break` and `continue`.
  - **The bug:** they were read as plain statements, so every counted loop ran to its end.
    A path walk `for (local.n = 1; local.n <= 1025; ...)` that breaks on its last node ran
    1025 turns on each call, and a big script used up its 400,000 statements on that
    before reaching its spawns ("stopped after 400000 statements").
  - **How they work now:** in a `switch` a `break` ends only the case, and a `break`
    under an undecidable `if` stops the loop with its counter unknown.
  - **Repeated labels:** a label run 8 times without spawning anything new or setting a
    target, cvar or `$world` line is skipped from then on (`LABEL_IDLE`): actors' AI
    threads run for every actor.
  - **Result:** m3l1b's remaster script now places 4228 entities in 1.6 s, up from 130
    in 14 s when it stopped; m3l1a's goes from 240 to 253. The retail maps' placements
    are unchanged.
- Map Viewer page rev 55 (`MAP_VIEWER_REV` 55, `MAP_VIEWER_REV_REQUIRED` 55): an **AI
  routes** button in Show turns `ai_showroutes` on and off, and follows the cvar when it
  is set in the list; it is greyed on a map with no `.pth`. In Free-look, Up / Down move
  forward and back level with the ground (yaw only), where W / S follow the view's pitch;
  Radiant-look's arrows stay MOHRadiant's. The keyboard window says so.
- Map Viewer page rev 56 (`MAP_VIEWER_REV` 56, `MAP_VIEWER_REV_REQUIRED` 56): a **Modify**
  section under Find adds entities (Add, Edit parameters, Trim origin with a trim step
  slider, To view, Fly to, Delete) and saves the map with them (Save as .bsp through the
  launcher, Save as .map, Copy).
  - **AI paths in the page.** OpenMoHAA's path building (`CreatePaths`, `CheckMove`,
    `MmoveSingle`, capsule brush traces and the terrain's collision code) is ported, so a
    new `info_pathnode`'s links show in AI routes as soon as it is placed. Worked out again
    for whole maps, it gives 98 to 100 % of the links in eight retail `.pth` files.
  - **No `.pth`:** a map with path nodes but no `.pth` gets its routes worked out by the
    page, and the AI routes button is no longer greyed for it.
  - **Build data:** the decompiler keeps each brush's own contents where they differ from
    its first face's (`bsp.bcont`), the level script reader keeps the `solid` /
    `notsolid` lines before `level waittill prespawn` (`scr.presolid`), and the page
    records the file it was built from (`srcFile`).
  - **Launcher:** a `mohaa-modify-save` message; `mohaa_bsp.write_bsp_entities` writes
    the `.bsp` (new entity lump at the end, new
    `map_time`, other lumps checked byte for byte, at most 4096 path nodes).
- Map Viewer page rev 57 (`MAP_VIEWER_REV` 57, `MAP_VIEWER_REV_REQUIRED` 57): Modify's Add
  places by a click, as the path-editor branch's Place node did: after Add, a click on the
  map puts the entity there (a path node 16 units up), with an outline following the
  cursor until then; Esc or Add again cancels. Edit parameters moves by its title bar
  (its place is remembered), and its Done / Revert buttons sit at its bottom right.
- Map Viewer page rev 58 (`MAP_VIEWER_REV` 58, `MAP_VIEWER_REV_REQUIRED` 58): Modify gets
  **Move** (the selected new entity follows the mouse until a click puts it down; Move and
  Trim origin grey each other out). New entities are drawn as the map's own markers of
  the same keys (a path node the 16-unit dark green stand-in), see-through. Edit
  parameters' Revert is replaced by Undo and Redo (from when it opened, greyed when
  there is nothing to undo or redo; Ctrl+Z / Ctrl+Y), with Done the bottom-right button.
- Map Viewer page rev 59 (`MAP_VIEWER_REV` 59, `MAP_VIEWER_REV_REQUIRED` 59): a new path
  node's spawnflags outline shows while it is selected or edited (thick, as the map's
  nodes; the selection is a yellow box round it), so it changes as "spawnflags" is typed.
  The Modify section moved above Find, and the AI routes button to the end of the Show
  group buttons, after Origin and Point ents.
- Map Viewer page rev 60 (`MAP_VIEWER_REV` 60, `MAP_VIEWER_REV_REQUIRED` 60): selecting one
  of the map's point entities gives it a Modify row (hollow square, "#N map", "#N changed"
  once edited; new ones say "new"), so its parameters, Move and Trim origin work as for
  new entities, Restore puts it back, and a changed path node's AI routes are worked out
  again both ways. Save as .bsp writes the changed entities into the entity lump (found by
  number, checked by class and old origin; `mohaa_bsp.write_bsp_entities(replace=)`),
  Save as .map writes their blocks again. Modify's entities are drawn with the markers'
  own shader, see-through, so the spawnflags outline is the single bold one the map's
  nodes have.
- Map Viewer page rev 61 (`MAP_VIEWER_REV` 61, `MAP_VIEWER_REV_REQUIRED` 61): Modify's class
  drop-down is a searchable list, as the Model Viewer's attach-to-bone list (filter box,
  counts in the map, arrows / Enter / Esc). Checked: changing a node's classname in Edit
  parameters takes its AI routes away when the box closes, and back when changed back.
- Map Viewer page rev 62 (`MAP_VIEWER_REV` 62, `MAP_VIEWER_REV_REQUIRED` 62; `INDEX_VERSION`
  10): Simple Sky turns the sun flare off. A page opens at the player start every time (it
  no longer goes back to where the camera was left; the launcher's privacy text says so).
  Entities drawn only by camera-facing sprites (`static_fx_fire`) are in the pick pass, so
  they can be hovered and clicked. Built-in definitions for `info_grenadehint`,
  `info_splinepath`, `ai_actor` and `func_window`, the classes whose definitions are only
  in MOHRadiant's entdefs.pk3 (colour, box and spawnflags from it).
- Map Viewer page rev 63 (`MAP_VIEWER_REV` 63, `MAP_VIEWER_REV_REQUIRED` 63): the first
  Lights off or Sun light, which works out every light's share of the baked light, prints a
  line in the launcher's Output as it starts and another with the time when it is ready
  (a `mohaa-log` message: tag and text). The map launcher's Re-open / Browser / .map
  buttons are packed at the bottom of the details pane before its list, so they show in
  the default window size.
- Map Viewer page rev 64 (`MAP_VIEWER_REV` 64, `MAP_VIEWER_REV_REQUIRED` 64): Modify's rows
  work like the Find lists: Shift+click the selected (green) name deselects it,
  Shift+click a row's square hides / shows that entity (in red while hidden; a hidden map
  entity's own marker stays hidden too, and its row stays in the list).
- Map Viewer page rev 65 (`MAP_VIEWER_REV` 65, `MAP_VIEWER_REV_REQUIRED` 65): a new entity
  selected in the 3D view deselects with Shift+click (Ctrl+click opens its card) and with
  Esc, which clears Modify's selection before it closes the map. Ctrl+Z undoes Modify's
  hide / show. N (More info) on a new entity opens its own card: not saved, no entity
  number yet, its origin, box and spawnflag names, for a path node the node number the
  saved map will give it and its links both ways, the class description, and its
  parameters in an editable box applied as typed.
- Map Viewer page rev 66 (`MAP_VIEWER_REV` 66, `MAP_VIEWER_REV_REQUIRED` 66): a new entity
  of a class that faces a way (most of the map's own of that class have an angle; with
  none in the map, player starts, actors, turrets and vehicles) is placed with an
  `"angle"`, the camera's yaw to 45 degrees, and Modify's entities draw the same white
  facing arrows (Arrows, 5) and target links with arrowheads (Links, 7) as the map's own,
  both ways, in place of the thin lines before. **Make path** (after Trim origin): click
  another entity to set the selected one's `"target"` to it; it keeps its targetname or
  gets the next free `t<N>` (a map entity given one becomes a changed row; brush entities
  and static props can't be). The clicked one is selected after, so Make path again goes
  on along the path. Esc cancels.
- Map Viewer page rev 67 (`MAP_VIEWER_REV` 67, `MAP_VIEWER_REV_REQUIRED` 67): **Grid** (+, in
  Display under the backdrop) with a grid-size slider of MOHRadiant's sizes, 1 to 512
  ({ and } step it), and a grid colour beside the backdrop's (Default resets both). The grid
  is a see-through 3D lattice a grid size apart, about a dozen cells round Modify's moving
  or selected entity (else a point ahead of the camera), fading out from there, fainter
  still where it goes behind or into the map, lines through multiples of 64 (or of 8 grid
  sizes) and through ( 0 0 0 ) brighter, with its coordinates written along the three lines
  through its centre. While it is on, Add and Move snap to its nearest corner (moved up a
  grid size rather than leave the box in the floor). Its on / off, size and colour are
  remembered.
- Map Viewer page rev 68 (`MAP_VIEWER_REV` 68, `MAP_VIEWER_REV_REQUIRED` 68): the leak trail
  says where the void gets in. The brushes that seal a map for the compiler (the world's
  structural, solid, not see-through brushes; not detail, patches, terrain, clips or
  water) are tested along the trail from its start with rays 26 ways: the last place the
  void is still in a straight line, before the trail is shut in, is where it gets in, and
  from there toward the void the place the way out passes closest to those brushes is
  the gap. It is marked with a light blue circle ("leak: gets in here, fix this", with
  the gap's width when small) and the card is in sections: Found (start, gets in,
  reaches), Where it gets in (the gap's width along each axis and between which
  coordinates, which way the void is, the brushes either side with Select them, how far
  along the trail the void stays in sight, anything the game collides with there that
  doesn't seal), Recommended fix (a hairline crack: snap to the grid or overlap; a small
  gap; a missing wall, floor or sky; caulk behind terrain and patches; the entity itself
  out in the void: move it in), Reading the trail (why it zigzags: the compiler's BSP
  cells; the entity at the end is only the first the void reaches) and the points. A
  click on a trail point or circle in the view opens the card at that point (the entity's
  selects it too), and the stats under the map's name have a "leak trail: the map isn't
  sealed" line that opens it. BSunrise3-3: a 0.39-unit crack along x between two caulk
  floor slabs (x 318 and 318.39), open to the void below.
- Map Viewer page rev 69 (`MAP_VIEWER_REV` 69, `MAP_VIEWER_REV_REQUIRED` 69): the leak gap,
  checked on eight custom maps that leak. From where the trail gets in, looking toward the
  void: the first thing in the way that the game collides with but the compiler doesn't
  take as a seal (terrain, a patch, a detail, clip or see-through brush, a brush entity)
  is where the void comes through, named on the card with Select it, and the fix is caulk
  under or behind it; else the opening is the last place along that way still between
  sealing brushes (within 1024 units across), its gap measured at its narrowest within 64
  units of it, and gaps under 1024 units are listed. A crack under 2 units or with sides
  at fractions of a unit is called a hairline crack off the grid. A `.bsp` with vis data
  didn't leak when compiled: its card says the `.lin` is left over from an earlier
  compile. The sealing brushes were checked on sealed maps (obj_team2, mohdm7, m1l1,
  m3l1a, m5l1a, m6l3e, Tirtagen-Kechtat: no player start or path node of 1,270 sees the
  void). BSunrise3-3a: a 1.33-unit crack (x 3444 to 3445.33) open below;
  NormandyBridge_V1 and abydos: in under terrain with no caulk beneath; pleviathan: an
  8-unit slit (z 192 to 200) at the map's -x edge; SiDvFinal: an 8-unit gap along x (1680
  to 1688) open below; V2revamped: an opening toward +y; Tirtagen-Kechtat (both of its
  paks): a `.lin` left over beside a `.bsp` with vis.
- Map Viewer page rev 70 (`MAP_VIEWER_REV` 70, `MAP_VIEWER_REV_REQUIRED` 70): the game's
  limits. The stats' "real" tooltip gives the entity limit on its own paragraph:
  maxentities 1024, the world and "none" keep two, the client slots come first (1 in
  single player, sv_maxclients in multiplayer), past that `Level::AllocEdict: no free
  edicts`; with this map's count (its real entities and the real ones its level script
  spawns) of 1021 with one player (and of 990 with 32 for a dm/obj map). The "simple"
  tooltip gives MAX_PATHNODES (4096, `navigate.h`; "Exceeded MAX_PATHNODES!") with the
  map's path node count; the other simple entities have no fixed limit. Modify counts its
  new entities and changed classes in: Add and placing a new one are refused past 1021
  real entities or 4096 path nodes, with a warning near them, and its status line gives
  both counts, yellow when close, red when past (a classname changed in Edit parameters
  can get there).
- Map Viewer page rev 71 (`MAP_VIEWER_REV` 71, `MAP_VIEWER_REV_REQUIRED` 71): Modify's path
  problems, as the game meets them (`paIssues`). For its new and changed path nodes: 48
  paths to check (`NUM_PATHSPERNODE`; "^~^~^ 48 paths per node at (...) exceeded", linked
  no further, and g_nodecheck 1 stops the level), a full 256-unit cell (`PATHMAP_NODES`
  128; "^~^~^ PathSearch::AddToGrid: Node overflow at ( x, y )"), no path at all (nothing
  it can walk to within 384 units, or only drops past ai_fallheight), and nodes cut off
  from the map's others (an AI sent across gets "^~^~^ Path not found", g_patherror 1 by
  default); also the map's own nodes the new ones crowd past 48. Each shows as an orange
  tag over the node in the view, a line on its card and in the launcher's Output, a
  flash when it first appears, and a count in Modify's status (yellow, the lines in its
  tooltip). They follow ai_fallheight as it is changed, as the game's routes do.
- Map Viewer page rev 72 (`MAP_VIEWER_REV` 72, `MAP_VIEWER_REV_REQUIRED` 72): Selection's
  **Eye view** (after Same kind), for an entity with angles, a target to look at, or a
  player start: the camera flies to where it sees from and looks the way its angles say
  (pitch, yaw and roll), else at its target, else (a player start) yaw 0. Player starts:
  82 units above the start (DEFAULT_VIEWHEIGHT, `bg_public.h`). Path nodes, waypoints,
  vehicle points and actors: dropped to the floor (as droptofloor) and 82 above it.
  Spline paths, cameras and everything else: exactly at the origin.
- Map Viewer page rev 73 (`MAP_VIEWER_REV` 73, `MAP_VIEWER_REV_REQUIRED` 73): no more mention of
  the separate `.bsp` entity script, whose work `mohaa_bsp.write_bsp_entities` does: Save as
  .bsp outside the launcher says to open the map there.
- Map Viewer page rev 74 (`MAP_VIEWER_REV` 74, `MAP_VIEWER_REV_REQUIRED` 74): the grid is
  drawn only in front of the map's surfaces (the fainter pass through floors and walls is
  gone), centred, when Modify has nothing selected or moving, on the first surface the
  camera looks at (a trace straight ahead) instead of a point in the air, and its numbers
  behind a floor or a wall aren't written.
- Map Viewer page rev 75 (`MAP_VIEWER_REV` 75, `MAP_VIEWER_REV_REQUIRED` 75): **Ctrl+C** over
  the 3D view copies the point under the cursor as `( x y z )` (the face's exact point, or
  a marker's origin; not the camera's place), unless text is picked out on the page. In
  the keyboard shortcuts window.
- Map Viewer page rev 76 (`MAP_VIEWER_REV` 76, `MAP_VIEWER_REV_REQUIRED` 76): Make path only
  takes an entity that has a targetname (a click on one without is refused, with why; the
  selected one needs none); it no longer gives the clicked one a new `t<N>`.
- Map Viewer page rev 77 (`MAP_VIEWER_REV` 77, `MAP_VIEWER_REV_REQUIRED` 77): **Grid** (+)
  moves into Display's buttons after Decals, and the button left of the grid-size slider
  picks its planes, in turn: **Grid XY** (one flat plane, the default), **Grid XZ** and
  **Grid YZ** (one upright plane), **Grid all** (the 3D lattice as before). A single plane
  is laid on the grid line nearest the point, on the camera's side of the surface, reaches
  8 to 24 cells each way, and only its two axes are numbered. The choice is remembered.
- Map Viewer page rev 78 (`MAP_VIEWER_REV` 78, `MAP_VIEWER_REV_REQUIRED` 78): the copy notes
  say what was copied, with the value: "Camera's origin ( ... ) copied to the clipboard"
  (Copy pos), "Camera's angles ( ... )" (Copy ang), "Mouse cursor's origin ( ... )"
  (Ctrl+C over the 3D view).
- Map Viewer page rev 79 (`MAP_VIEWER_REV` 79, `MAP_VIEWER_REV_REQUIRED` 79): the level script
  card has an **Open .scr** button between Copy and X, and each row of its Files list an
  **Open** button. In the launcher a script on disk opens in the text editor (Options ->
  Open with); one in a pak is extracted first, as the tree's Open does
  (`mohaa-open-scr` message, `MapApp._open_scr`). In a browser the button copies the
  script's path instead.
- Both launchers: the details pane at the bottom right is one scrolling column (title,
  stats, the Re-open (now Rebuild) / Browser / .map buttons, then the tag list) with a scrollbar that is
  always there, so nothing is cut off at the default size. The buttons sit above the list
  and are compact; the pane starts 300 px wide (`INFO_PANE_WIDTH`). The mouse wheel scrolls
  it anywhere over the pane (`make_info_pane`, shared by both programs).
- Map Viewer page rev 80 (`MAP_VIEWER_REV` 80, `MAP_VIEWER_REV_REQUIRED` 80): a model
  entity's box (selection, hover, the setsize-box lines) turns with its angles where the
  game turns it. In MOHAA, unlike Quake 3, `CM_TransformedBoxTrace` rotates even a
  `setsize` box by the entity's angles once `EF_LINKANGLES` is set, which ScriptSlave
  (script_model and the rest), Vehicle and VehicleCollisionEntity do and `rotatedbbox`
  sets or clears. So a script_model barbwire turned 45 degrees with `setsize ( -47 -140 0 )
  ( 47 350 1000 )` now gets its box along the wire, not along X / Y. A model with no setsize
  is boxed by its own bounds turned with it, so a turned higgins boat's box fits the boat
  instead of the X / Y box around it. Classes the game doesn't turn (Actor, Animate...)
  keep an unturned box, and the info card says so. `absmin` / `absmax`, Fly to and the
  area / PVS links use the turned box's world bounds. The level script's `rotatedbbox`
  lines are read (`_SCR_PROPS`).
- Both launchers' details pane: **Re-open** is now **Rebuild**. Re-open loaded the same
  page into the pane again, which looked like nothing happened; Rebuild builds what the
  pane shows again, ignoring the saved HTML, as right-click > Rebuild does
  (`App._rebuild_shown`: the last build with the one-shot `force` option, the open page
  closed first so the new one really loads). The buttons have icons drawn with Pillow (a
  hammer, a globe for **Browser**, a page for the file button; `button_icon`, drawn
  rather than typed since Tk on older Pythons can't show symbols past the Basic
  Multilingual Plane). The Model Viewer gets a **.tik** button, as the Map Viewer's **.map**:
  it opens the model's .tik in the Text Editor. The buttons are a little tighter
  (`Info.Tool.TButton`), never narrower than their text (a cut "Re-open" before), and
  wrap onto a second row when the pane is too narrow for one; the stats line wraps to
  the pane's width.
- Both launchers: the bottom row (Output | details) starts 130 px tall instead of 210
  (`BOTTOM_ROW_HEIGHT`), and its sash drags down to 26 px (`BOTTOM_ROW_MIN`, was 130),
  where only the "Output" label and the details' title show, side by side. Saved sash
  positions now carry a layout number (`PANES_LAYOUT` 2): a bottom-row height saved by
  an earlier version is dropped once, so the new default shows; later drags are kept.
- Both launchers: **Browse...** opens the file picked, as File > Open File... (Ctrl+Shift+O)
  does; Open Viewer stays for a path typed into the bar. Only a picked file opens: Cancel
  no longer re-runs the path already in the bar (`_browse` returns the pick, "" on
  Cancel), and a file of the wrong kind (All files) gets the usual "File must be..." line.
- Map Viewer page rev 81 (`MAP_VIEWER_REV` 81, `MAP_VIEWER_REV_REQUIRED` 81): an entity
  added in Modify is let go of when a click in the view picks something else, a brush, a
  static prop or the sky, as a map entity is. It stayed selected (see-through, its
  buttons live) because the Modify list keeps its own selection when the click picks
  something it doesn't take. Shift+click (adding to the selection), Ctrl+Shift+click
  (reading a face) and an entity being edited, trimmed or moved keep it.
- Map Viewer page rev 82 (`MAP_VIEWER_REV` 82, `MAP_VIEWER_REV_REQUIRED` 82): labels
  behind walls show only half as far. In sight they keep their range (2048 units named,
  700 unnamed); past 1024 / 350 a label needs a clear sight line from the camera to its
  spot through the world's shown, solid, opaque brushes (detail included; clip,
  see-through, patches, terrain and brush entities don't hide labels). The brushes sit
  in a box tree (`lblOccluders`) and each sight line is kept until the camera moves, so
  a crowded room costs about 2 ms when the camera moves (m3l1b's bunker: 135 labels past
  half range, 4 of them in sight).
- Map Viewer page rev 83 (`MAP_VIEWER_REV` 83, `MAP_VIEWER_REV_REQUIRED` 83): a path
  node's label names its highest spawnflag: `info_pathnode [COVER]`, `[CORNER_LEFT]`,
  `[CORNER_RIGHT]`, `[SNIPER]`, `[CRATE]`, `[CONCEALMENT]`, `[DUCK]` (`nodeFlagTag`).
  Only one, so COVER + CORNER_RIGHT reads `[CORNER_RIGHT]` (a corner node is a cover node
  anyway) and the label stays short. Its outline was the only sign of its kind before.
- Map Viewer page rev 84 (`MAP_VIEWER_REV` 84, `MAP_VIEWER_REV_REQUIRED` 84): named
  labels behind walls reach 512 units (was 1024; unnamed stay 350), and every label fades
  out over the last 40% of its own range to nothing at its end, in sight (2048 / 700) or
  behind a wall alike. Before, a label stayed at least 40% opaque and one behind a wall
  vanished at once at its limit. The sight check starts at 60% of the wall range so
  the fade is smooth.
- Map Viewer page rev 85 (`MAP_VIEWER_REV` 85, `MAP_VIEWER_REV_REQUIRED` 85): brush
  entities without a targetname are labelled (func_rotatingdoor, func_ladder, trigger_*
  and the rest), at the unnamed range, 700 in sight and 350 behind a wall. Before, only
  named ones (or the selection) were. The label sits at the middle of the entity's box,
  moving with a door that opens, not on its origin (a door's hinge, often in the wall).
  func_group and detail stay unlabelled, being part of the world.
- Map Viewer page rev 86 (`MAP_VIEWER_REV` 86, `MAP_VIEWER_REV_REQUIRED` 86): while
  ai_showroutes draws the AI routes, every path node with a mark gets a tag saying what
  it means, the map's own nodes as well as Modify's new ones: "⚠ no paths" (orange; the
  red X, no connection the AI can take), "⚠ N one-way" (red; the red arrowheads, ways
  the AI can go but not come back, a climb past ai_fallheight), "DONT_LINK" (blue; the
  blue circle, a node its spawnflag keeps unlinked on purpose). Before, only Modify's new
  and changed nodes had tags. A map node's tag sits just under its class label; within
  ai_showroutes_distance, past 350 units only when in sight, as the labels. The tags
  come from the pass that draws the marks (`buildRoutes`), so they always agree.
- Map Viewer page rev 87 (`MAP_VIEWER_REV` 87, `MAP_VIEWER_REV_REQUIRED` 87): the blue
  circle's tag tells its two causes apart. With the node's own DONT_LINK spawnflag it
  reads "⊘ DONT_LINK" (blue, on purpose). Without it the game set the flag itself while
  loading: dropped to the floor, the node lands on the very spot of an earlier one
  (`^~^~^ Duplicate node at (...) not linked`, `PathSearch::LoadNodes`), so it reads
  "⚠ duplicate of entity N $name: not linked" (orange), naming the node the game keeps
  (`nodeDupOf`, `nodeName`). The routes that seem to end at the circle are that earlier
  node's. m1l1 has one: entities 111 and 705 are both `$friendlynode` at
  ( -5824 768 448 ). A new node put on another's spot in Modify gets the same tag.

- Map Viewer page rev 88 (`MAP_VIEWER_REV` 88, `MAP_VIEWER_REV_REQUIRED` 88): triggers
  the level script spawns get their volumes. The reader kept only the keys it knows, so a
  setsize given through fields of the script's own (`local.minefield.setsize1 = ( 0 -430
  -500 )`, `.setsize2`, then `local.minefield setsize local.minefield.setsize1
  local.minefield.setsize2`) wasn't worked out and the trigger was a small cube; now any
  `<entity>.<field> = value` is kept (`LevelScript.fields`, `+=` too) and read back by
  later lines. A new **Show → Script trigs** button (`C_SCRTRIG`, on by default, off in the
  In-game look) draws each such trigger's setsize as a see-through box in the trigger
  green with its edges (`drawScriptTrigs`); under Script ents the trigger stays a small
  marker of its class's size (`markerBoxOf`), and selecting it outlines the whole volume.
  Tested with m3l1b's 11 respawned `$minefield` triggers.
- Map Viewer page rev 106 (`MAP_VIEWER_REV` 106, `MAP_VIEWER_REV_REQUIRED` 106): Modify's
  work can't be lost to a reload. A session's work was lost with no question asked: the
  log shows the page starting over (its AI paths worked out again) with no build, which is
  the pane reloading itself, most likely a browser key (F5, Ctrl+R while a text box had
  the focus, Alt+Left / Right). Now:
  - the launcher turns the pane's browser keys off (`AreBrowserAcceleratorKeysEnabled`;
    copy, cut, paste and select-all still work), and the page blocks F5, Ctrl+R and
    Alt+Left / Right / Home itself, text boxes included;
  - leaving or reloading the page with unsaved work asks first (`beforeunload`), also
    when the launcher opens another map or closes the viewer;
  - a moment after each change the work is copied to the launcher, which keeps it in
    `output/modify_recovery/<map>_<hash>.json` (per map and map_time; `MapApp._modify_backup`),
    or, in a browser, to local storage; when the map opens again with such a copy the page
    offers it back (Restore / Discard; `modRecoverAsk`, `MOHAA_MODIFY_RECOVERY`,
    `mohaa-modify-recovery`). A save or Discard changes clears it.
  The privacy notice names the folder.
- Map Viewer page rev 105 (`MAP_VIEWER_REV` 105, `MAP_VIEWER_REV_REQUIRED` 105): a new AI
  error tag, **no angle: CORNER_RIGHT** (or CORNER_LEFT, CRATE, LOW_WALL_ARC), on a path
  node with one of the spawnflags whose special attack faces the node's way but with no
  "angle" or "angles" key, so it faces yaw 0 (east) whatever the wall
  (`PathNode::GetSpecialAttack` measures the enemy's angle from the node's yaw and
  actor_cover.cpp turns the man to it; `nodeNoAngle`). For the map's nodes, Modify's
  changed ones and its new ones, with AI errors on. Retail m3l1b has three (two corners
  and a crate). The other flags don't use the node's facing (COVER, CONCEALMENT, DUCK,
  SNIPER).
- Map Viewer page rev 104 (`MAP_VIEWER_REV` 104, `MAP_VIEWER_REV_REQUIRED` 104): putting
  down an entity Modify places (Add / Alt+A, Copy / Alt+C, Move) makes it the selection
  everywhere: a new one lets go of the map's selected brushes and entities, as a click on
  it does, and More info (N), when open, turns to it (`modPlacedSel`). Before, the card
  stayed on what was selected before, so editing parameters there changed that entity.
- Map Viewer page rev 103 (`MAP_VIEWER_REV` 103, `MAP_VIEWER_REV_REQUIRED` 103): turning AI
  routes on says in Output where its paths come from: "from maps/m3l1b.pth (Pak5.pk3), 258
  nodes", "worked out here (no .pth for this map)", plus Modify's new nodes (`routesFrom`).
  A .pth made for another version of the map is no longer used: the game keeps a .pth only
  when the map_time stored in it is the .bsp's worldspawn "map_time" and builds the paths
  again otherwise (`PathSearch::ArchiveLoadNodes`), which is what happens to a copy Save
  as .bsp wrote (it bumps map_time) given the map's own name, so the paks' .pth was
  being drawn for it. Now the page works the paths out instead (`pathsStale`) and says
  why, with both times; the build's Output says it too (`paths_payload`, `map_time`). A
  .map, which has no map_time yet, keeps using the .pth.
- Map Viewer page rev 102 (`MAP_VIEWER_REV` 102, `MAP_VIEWER_REV_REQUIRED` 102): a .bsp
  saved with a broken Modify entity, and the viewer's misreading of it. Edit parameters
  took a quote left open as running on into the next lines (`"([^"]*)"` matched across
  them), so a slip like a lone `"` line turned the rest of the text, braces included, into
  keys and values of one entity; Save as .bsp wrote it as it was. The game reads it the
  same way (`COM_ParseExt`'s quoted strings run across lines; `SpawnArgs::Parse`), so the
  map loads, but that entity gets junk keys and the node written after the slip is lost.
  The viewer's decompiler then wrote the multi-line value into the .map as it was, the
  .map read back with one entity more than the lump, and every entity after it was one
  place out: static props showed their neighbour's model (a chair where the radar is) and
  the level script's entities lost theirs. Now: Edit parameters reads one `"key" "value"`
  pair per line and refuses a quote not closed on its line, a key without a value on its
  line, and a { or } inside a key or value, naming the line (`modParse`); Save as .bsp
  refuses an added entity with a line break, quote or brace in a key or value, or an empty
  key (`write_bsp_entities`, as it already did for changed ones); and the decompiler
  writes such a key or value on one line with braces taken out (`_map_safe`), with an
  Output line naming the entity, so the .map always has the lump's entities, one for one.
- Map Viewer page rev 101 (`MAP_VIEWER_REV` 101, `MAP_VIEWER_REV_REQUIRED` 101): Modify's
  entities get labels (Labels, 6), as the map's do: class, a path node's flag tag
  (`[COVER]`, `[CORNER_RIGHT]`, ...) and `$targetname`, with the same distances, fading,
  sight checks and no-overlap rule, and the selection colour when selected. A small
  filled tab in front tells them apart: **NEW** (amber) on an added entity, **EDIT** (blue)
  on one of the map's that Modify has changed (Modify draws that one instead of the
  map's marker, so it had lost its label too). `$targetname` / `#spawnflags` keys count as
  the game reads them (`simKvl`). A new node's AI tag now sits under its label, as a map
  node's does, instead of 40 units over its spot.
- Map Viewer page rev 100 (`MAP_VIEWER_REV` 100, `MAP_VIEWER_REV_REQUIRED` 100): a new
  **AI errors** button in SHOW, after AI routes (no hotkey), shows or hides the path-node
  tags that report a problem: "no paths", "N one-way", "own group of N" and "in the wall",
  for the map's nodes and Modify's. It turns on when AI routes is turned on and off when
  AI routes is turned off (whichever way: the button, `I`, the cvar list), and can be
  turned off while AI routes stays on (`AIERR`, `AIERR_KINDS`; followed in `setCvar`). Tags
  that aren't errors (DONT_LINK, a duplicate node, 48 paths full, cell full) are always
  shown. A group of new nodes not yet joined to the map's no longer tags every node with
  "own group of N" unless AI errors is on.
- Map Viewer page rev 99 (`MAP_VIEWER_REV` 99, `MAP_VIEWER_REV_REQUIRED` 99): Esc can no
  longer close the viewer and lose Modify's work without asking. When the last Esc would
  close it while Modify has new entities or changed map entities that no Save as wrote
  (`modUnsaved`, against what the last successful save wrote, `MOD.savedKey`), the page
  sends `mohaa-close-ask` and the launcher shows a choice (`MapApp._close_ask`,
  `_unsaved_dialog`; dark / light, or the system's look with "Use old popup windows"):
  **Save as .bsp** (greyed out when the map came from a .map), **Save as .map**, **Discard
  changes**, **Cancel** (also Esc and the window's X; it has the focus, so Enter can't
  throw anything away). Saving closes the viewer once the file is written
  (`modSaveThenClose`); cancelling the file box or a failed save leaves it open
  (the launcher calls `modSaveCancelled` when the box is cancelled). In a
  browser the page asks with the browser's own confirm box.
- Map Viewer page rev 98 (`MAP_VIEWER_REV` 98, `MAP_VIEWER_REV_REQUIRED` 98): Modify.
  The class list leaves out classnames that are model paths (`human/dday_ranger_private`,
  `human//german_wehrmact_grenadier`: the game spawns those as the .tik's own class), so it
  lists classes only (`modClassOk`). An added entity whose class or "model" key names a
  model is drawn with it (`modTik`, `modModelR`, `modModelsInst`): the map's own mesh when
  the map places that model, else one the launcher builds from the paks as Simulate's
  (`mohaa-sim-build`), its box only outlined meanwhile; before, every added entity was its
  class's box. A path node in a group of its own (joined to Modify's other nodes but not to
  the map's) is no longer a problem: "own group of N", blue, in the node's card in the
  note colour, and left out of the problem count and the Output lines. It used to read
  "cut off: Path not found", which only happens when someone is sent across. New check,
  not one the game makes: **in the wall**, a path node where a man standing on it (the
  actor's 30-by-94 capsule, lifted one 18-unit step) starts inside the map, with how far
  and which way clears it (`nodeWall`), for Modify's nodes in their issues and for the
  map's own in their card and, with AI routes on, as a tag. **Alt+A** is Add. In free-look,
  **Ctrl+W** / **Ctrl+S** move forward and back level with the ground, as Up / Down do
  (plain W / S still go along the view line). Modify's list is under its buttons, newest
  first. Shift+click on added entities (in the view or the list) selects several
  (`MOD.multi`); **Copy** (Alt+C) copies the selection, the map's own selected entities too,
  without targetname or target, and the copies follow the mouse together, spaced as they
  were, until a click puts them down (Esc takes them away); **Move** and **Trim origin** take
  the whole selection, and **Delete** removes it. **Undo** (Alt+Z) and **Redo** (Alt+Y or
  Alt+Shift+Z) step through every change to Modify's entities back to none added
  (`modHist`, `modUndoGo`; a whole Trim origin is one step). The Save row's Copy is now
  **Copy text**.
  Every note the status line flashes (green, at the bottom of the view: "No .pth for this
  map: its AI paths were worked out here", "Placed ...", "Undone ...") is also a line in the
  launcher's Output pane (`hostLog`, tag `ok`); the same note again within 2 s only once.
- Map Viewer page rev 97 (`MAP_VIEWER_REV` 97, `MAP_VIEWER_REV_REQUIRED` 97): a script
  trigger's volume (Script trigs) can be clicked: its sides go into the pick pass with the
  entity's pick id (`pickScriptTrigs`), so a click on one selects the whole trigger, as a
  click on a trigger brush does, and the mouse-over outlines it. While selected it is
  tinted with the selection's colour instead of a brighter green. With Script trigs off it
  can't be clicked. Before, a click went through it to the terrain.
- Map Viewer page rev 96 (`MAP_VIEWER_REV` 96, `MAP_VIEWER_REV_REQUIRED` 96): Simulate's
  controls. **Simulate** and **Reset** moved from SELECTION to the top of the SIMULATE
  section. Follow with the camera is split into **Follow** and **Eye view**: Follow alone
  rides behind the model as before but much lower (just above it rather than high over
  it); Eye view alone puts the camera on the path's first node at its angles when the
  simulation starts and leaves it there; both ride behind the model along its own facing
  at its exact angles, turning, climbing and banking with it. A **camera zoom** slider
  (24 to 4096 units behind, log scale) sets how far back the camera follows, and the mouse
  wheel changes it while the camera follows (Shift for bigger steps). Speed reads 0.25x
  and 0.5x instead of the fractions.
- Map Viewer page rev 95 (`MAP_VIEWER_REV` 95, `MAP_VIEWER_REV_REQUIRED` 95): **Simulate**,
  phase 1. With an `info_splinepath` selected (one of the map's, or one Modify added),
  SELECTION gets **Simulate** and **Reset** and a new SIMULATE section (between SELECTION and
  CAMERA) shows the path, its length in game time and what ends it. Simulate flies a model
  along it as a script's `followpath` does: the path starts at its first node (the selected
  node's chain followed back), each next node is the first entity its `target` names
  (`G_FindTarget`; a target that isn't an `info_splinepath` ends it), and each server frame
  (0.05 s) the model goes where `BSpline::EvalClamp` puts it for `splineTime`, which starts
  at -2 and moves on by 0.05 times the blended node `speed` until it passes the number of
  nodes less 2 (`ScriptSlave::FollowingPath`, fgame/scriptslave.cpp, fgame/bspline.cpp).
  Origins, angles (pitch, yaw and roll, so it banks) and speeds come from the nodes as
  Modify has them, so a node can be moved or retimed and the path flown again. The frames
  are worked out when it starts and drawn between, as the game's client does; the curve is
  drawn while the section shows (faintly through walls), with each node's facing. Simulate
  greys out while it flies and Reset stops it; at the end it resets by itself. **Choose...**
  opens a model picker with a search box: the models the map places, and (in the Map
  Viewer) every `models/**.tik` in the loaded paks, which the launcher builds as the map
  build builds a map's models (`mohaa-sim-models`, `mohaa-sim-build`; the path is checked
  against the paks) and hands back as page data (`MOHAA_SIMMODEL`). Until it arrives, or if
  it can't be drawn, a box with a nose flies instead. The model is lit by the light grid
  where it is, has no emitters, and is drawn but can't be clicked. Speed (1/4x to 4x) and
  **Follow with the camera** (behind and above it; moving the camera stops it) are in the
  section; the picked model is remembered (`mohaaMapViewerSimModel`, added to the Map
  Viewer's privacy wording among the display choices). Checked on m3l2's
  `$bomberpath` with the Stuka, against a Python copy of `EvalClamp`.
- Map Viewer page rev 94 (`MAP_VIEWER_REV` 94, `MAP_VIEWER_REV_REQUIRED` 94): Modify gets
  hotkeys for its selected entity, **Alt+M** Move, **Alt+T** Trim origin, **Alt+E** Edit
  parameters (every plain letter already has a job), each button's tooltip naming its own
  on a line of its own (Delete's: the Delete key). **Eye view** replaces To view (Move does
  its job better now): the camera where the entity sees from, by the map's entities' Eye
  view rules (`eyeViewFrom`, shared with `eyeView`), facing yaw 0 when it has neither
  angles nor a target. A click on the selected (green) row in Modify's list, so the second
  click of a double-click, does **Fly to**; a double-click no longer opens Edit parameters
  (Alt+E does). The keyboard list (H, F1) has the Alt keys.
- Map Viewer page rev 93 (`MAP_VIEWER_REV` 93, `MAP_VIEWER_REV_REQUIRED` 93): the keys the
  map's things take work on entities added in Modify too: **Backspace** hides the selected
  one (as its square in the list does; Ctrl+Z shows it again) and lets go of it, beside
  hiding the map's selection as before; **Delete** removes it, as Modify's Delete button
  does, and selects nothing after (so a second press can't take the next one). Delete
  leaves the map's own entities alone and says so. The keyboard list (H, F1) has both.
- Map Viewer page rev 92 (`MAP_VIEWER_REV` 92, `MAP_VIEWER_REV_REQUIRED` 92): a plain click on
  an entity added in Modify selects only it: the map's selected brushes and entities are let
  go, as a plain click on anything does. Before, they stayed selected beside it (only the
  other way round was fixed, rev 81). Shift+click still adds it and keeps them.
- Map Viewer page rev 90-91 (`MAP_VIEWER_REV` 91, `MAP_VIEWER_REV_REQUIRED` 91): hotkeys for
  the two Show buttons that had none. **I** turns AI routes (ai_showroutes) on and off,
  as its button does (on a map with no paths it says why); **Ctrl+B** (trigger boxes) shows
  or hides Script trigs. Shift now counts in a Ctrl or Alt combination (it used to be
  ignored there, so Ctrl+Shift+X was Ctrl+X); on its own it is still part of the key
  (Shift+G, `$`). The buttons, the keyboard list (H, F1) and the docs show them.
- Both launchers: closing one maximized no longer drops its bottom row to its least
  height when it opens again. The layout saved the sashes' places in the window (the
  bottom row's sash 683 pixels down in a maximized window), and the window opens at its
  normal size, where that is past the bottom. Now it saves the sizes of the panes that
  don't stretch, the bottom row's height (`bottomH`) and the details pane's width
  (`infoW`), measured back from the window's far edge however big it opens, and whether
  the window was maximized (`zoomed`), which it is again on the next start. The tree's
  width is kept as before. A layout saved before (`PANES_LAYOUT` 3) keeps the tree and
  gives the defaults for the rest.
- Map Viewer page rev 89 (`MAP_VIEWER_REV` 89, `MAP_VIEWER_REV_REQUIRED` 89): Show's **All**
  (`Ctrl+A`) sits on the line of AI routes, at the end of the Show buttons and in their
  style, instead of on a row of its own.
- The two launchers are renamed **`MOH Model-Map Viewer (Windows x86-x64).bat`** and
  **`MOH Model-Map Viewer (Linux - Mac OS).sh`** (they were `RUN -- Medal of Honor Viewer`
  `.bat` / `.sh` for a while, as the entry below says); the README, the privacy notice,
  `docs/requirements.txt`, the installer's messages and the docs name them so, and the
  updater retires the earlier pair too (`UPDATE_RETIRED`). Added `.gitattributes`: the
  `.bat` files are stored byte for byte (CRLF) and the `.sh` files with LF, whatever Git's
  line-ending setting on the machine, so a download from GitHub runs as written.
- One launcher per system for both programs: **`RUN -- Medal of Honor Viewer.bat`**
  (Windows) and **`RUN -- Medal of Honor Viewer.sh`** (Linux and macOS) replace the four
  `RUN -- Medal of Honor Model/Map Viewer .bat/.sh`. They open with a short title and a
  menu: **1** Map Viewer, **2** Model Viewer, or Up / Down and Enter (1 is selected at
  first); Q or Esc quits. The menu is `bin/mohaa_envcheck.py menu` (exit 11 / 12, 10 to
  quit), so it works alike on every system: `msvcrt` keys on Windows, the terminal in
  cbreak mode elsewhere (restored however it ends), reverse video for the selection where
  the console takes ANSI codes (Windows 10+ switched on with
  `ENABLE_VIRTUAL_TERMINAL_PROCESSING`), else one updated "Selected:" line; with no
  keyboard (input piped in) a plain prompt. A `.bsp` / `.map` / `.bak` or `.skd` / `.tik`
  dropped on the launcher (or passed to the `.sh`) skips the menu and opens in its
  program. Python is found first, since both need it, with one message for both. The
  `.sh` reopens itself in a terminal when double-clicked in a Linux file manager (in
  Terminal on macOS) and is bash 3.2 compatible (macOS's bash; no `${a,,}`). Both are
  generated by `tools/make_launchers.py`, which also removes the old four from the
  project; the in-app updater backs up and removes them too, once an update is in place
  (`UPDATE_RETIRED`). The privacy notice names the new `.bat` (one fewer
  `_PRIVACY_SWAPS`), and the README, `docs/requirements.txt` and the installer's
  messages follow.

## 1.0.001 hardening pass (November 2026)

A review against publicly hardened, standard coding practices (fail loud, atomic writes, vendored
dependencies, batch-file discipline) found seven bugs and a set of rule gaps; all are
fixed here. Page output is unchanged, so `VIEWER_REV` / `MAP_VIEWER_REV` stay at 80 / 78.
Design decisions and what was deliberately left out: [hardening-notes.md](hardening-notes.md).

Bugs fixed:

- **Half-extracted pak files were reused forever.** `_extract_one` wrote straight to the
  final path and treated any file larger than 0 bytes as cached, so an extract cut short
  by a crash or a kill left a short `.skd` / `.tga` / `.skc` that every later run reused.
  Extraction now streams to a temp file, must match the entry's declared size, and moves
  into place atomically; a cached copy is reused only when its size matches the entry.
- **Settings could be wiped without a word.** Both launchers wrote their JSON settings
  straight over the live file and ignored every error; a damaged file (half-written, or
  hand-edited with `C:\...` paths) loaded as `{}` and the next save replaced it with
  defaults, losing the pak list. Settings are now written atomically with a `.bak`; on load
  a damaged file is repaired (backslash paths), restored from the `.bak`, or kept aside as
  `.corrupt-<date>`, and the Output pane says which.
- **The updater could leave a mixed-version install and report success.** Files were copied
  over the program in place, a file that failed to copy was skipped silently, there was no
  backup, and a missing release tag quietly installed whatever was on `main`. Now: retried
  HTTPS download with a size cap, every zip CRC tested, the downloaded `docs/version.txt`
  must equal the version offered, the replaced files are first copied to
  `output/previous-versions/<n>/` (with `changelog.txt`), each new file is verified before
  it moves into place, and any failure restores the files already replaced. The locked-file
  swap after a restart is a small Python helper instead of a generated `.bat` (which lost
  non-ASCII paths and only ran on Windows); a restart that can't start now says so instead
  of closing the window.
- **Errors in the window vanished.** Under `pythonw` there is no stderr, and nothing
  installed `report_callback_exception`, so an exception in any button, menu, key or timer
  callback left no trace, and a crash at start-up looked like nothing happening (exit code
  0). Callback errors are now logged with their traceback and shown in red; a start-up
  failure shows a message box, is logged, and exits with code 1.
- **Model builds could crash on non-ASCII file names (Windows).** The Map launcher ran its
  builds with `PYTHONIOENCODING=utf-8`; the Model launcher's three build calls didn't, so a
  child printing a name outside the Windows code page raised `UnicodeEncodeError`. Every
  child build now uses `mohaa_common.child_env()` (UTF-8 output, vendored libs on
  `PYTHONPATH`) and decodes as UTF-8.
- **Two attachment builds at once could swap settings.** Overlapping attach-to-bone builds
  shared `self._attach_*` and one `_attach` folder, so one model's parts, idle animation or
  scale could end up in the other's build. Attachment builds now run one at a time.
- **Save as .bsp checked its file after putting it in place.** A copy that failed the
  read-back check was already sitting under the chosen name. The check now runs on the temp
  file, and only a verified copy replaces the destination (an earlier copy is kept as
  `.bak`).
- **The embedded pane fell back to the browser** ("'EdgeChrome' object has no attribute
  'web_view'"). tkwebview2 3.5.0 needs pywebview 4.4.1's `EdgeChrome.web_view` (pywebview 5
  renamed it), but installing tkwebview2 let pip put the newest pywebview over the pinned
  one in `bin/libs`, and the check only read the version in the metadata, where a stale
  `pywebview-4.4.1.dist-info` could sit beside newer code. `mohaa_envcheck.py` now treats
  "==" as an exact pin (another version, or a second version's `.dist-info`, is replaced
  and the stale metadata deleted), checks the installed pywebview code itself for
  `self.web_view`, and installs tkwebview2 with `--no-deps`. The next launch repairs a
  folder that has the wrong pywebview.
- **Every package could keep an old install record.** pip `--target` leaves an older
  version's `.dist-info` beside the new one on any upgrade, not only pywebview's, and the
  version reader could pick the old one and reinstall on every launch. It now reads the
  newest, reinstalls a package that has more than one, and after each pip run deletes the
  extra records of every package (dependencies pip re-resolved, like pythonnet, included).
- **`except ...: MC.swallowed(); pass`.** The `pass` after the call did nothing; 167 of them
  are gone from the five modules that had them (no change in behaviour).
- **The RUN window stayed open beside the program, and its text was lost when it closed.**
  It now closes by itself once the program's window is open (`mohaa_envcheck.py start`
  runs the launcher with `pythonw.exe` and waits for its ready signal; a program that stops
  first leaves the window open with what it printed, and one pause). Its text, pip's output
  included, is saved in `output/logs/run_map.log` / `run_model.log` and shown at the top of
  the Output pane. The Output pane also prints "saved <path>" whenever the program saves a
  file (settings, pak lists, Save as .bsp / .map...; not temp files, caches or logs), and
  the RUN window prints "wrote <package> into <libs>" after each install.

Rule gaps closed:

- New `bin/mohaa_common.py`, imported by every script: rotating logs in `output/logs/`
  (one per program part), `swallowed()` to log a deliberately handled exception (first five
  tracebacks per call site, then a count), crash hooks for the main thread and worker
  threads, atomic writes (temp file, fsync, read-back SHA-256, `os.replace`, optional
  `.bak`), damage-tolerant settings, the Pillow floor, HTTP with retries and backoff, and
  the child-process environment.
- Every broad `except` that doesn't re-raise (about 380 handlers, mostly
  `except Exception: pass`) now calls `MC.swallowed()` first, so its traceback reaches the
  log; behaviour is otherwise unchanged. A pak that fails to open, and a failed
  `mohaa_textures` import, are logged as warnings / errors instead of being skipped silently.
- Every file the programs write goes through the atomic writers (pages, `.obj`, sidecar
  `.js`, decompiled `.map`, caches, manifests, catalogues, settings, the shared pak list).
- Pillow 10.3 is enforced at run time on every platform (`mohaa_common.pil_image()`), not
  only by the Windows installer, and images over 8192 x 8192 pixels are refused.
- Vendored packages: a per-OS libs folder beside the scripts (`bin/libs`, `bin/libs-linux`,
  `bin/libs-mac`) is put first on `sys.path` by every script. The RUN files install into it
  with `python -m pip install --target`, through the new `bin/mohaa_envcheck.py`, which
  verifies each package by importing it in a fresh process (and reinstalls one that no
  longer imports, e.g. after a Python update).
- Importing `mohaa_launcher` no longer creates `output/`, sets environment variables or
  copies files; that moved to `init_runtime()`. `globals().update(...)` for the theme was
  replaced by an explicit `set_palette()`. The silent `hasattr(MTX, "build_shader_props")`
  fallback is gone.
- Options menu: **Open log folder** and **Reset settings...** (both viewers). The console
  log keeps the previous launch's copy (`.prev`).
- Child builds (`mohaa_view.py`, `mohaa_map_view.py`, `mohaa_bsp.py`) log their command line,
  exit code and any crash to their own log; `mohaa_bsp.py`'s command line prints errors to
  stderr.
- Privacy notice dated 4 November 2026 (`PRIVACY_TEXT`, `docs/PRIVACY.md`): six stored
  things, adding the program logs and the previous-versions folder, the settings `.bak`, and
  the `.sh` scripts. `docs/PRIVACY.md` had drifted from the program's text (it carried a
  map-grid phrase the program didn't show); it is now generated from `PRIVACY_TEXT`, and the
  grid moved into the Map Viewer's own wording, where it belongs (`mohaaMapViewerGrid`).
- `tests/`: `test_hardening.py` (27 regression tests), `check_batch_files.py`,
  `check_privacy_sync.py`, `check_init_attrs.py`, `fuzz_parsers.py`.

Windows scripts (.bat) and new Linux / macOS scripts (.sh):

- `RUN -- Medal of Honor Map Viewer.bat` and `python_installer_updater.bat` were LF-only;
  all three `.bat` files are now CRLF, byte-checked by `tests/check_batch_files.py`.
- One `pause`, at the very end, in every `.bat` (there were three or five, plus a
  `timeout /t 3`); every failure sets `EXIT_CODE` and jumps to `:end`. The RUN files run the
  launcher with `python.exe` and wait, so the window shows how it finished, instead of
  starting `pythonw.exe` and closing.
- Package checks and installs moved from batch into `mohaa_envcheck.py` (no more
  `"Pillow>=10.3.0"` or `v>=(10,3)` inside quoted batch strings); packages go into `bin\libs`
  instead of Python's own folders or `--user`.
- Scratch files are unique per run (`%RANDOM%`), so two launchers started together can't
  read each other's answer.
- `python_installer_updater.bat`: TLS 1.2 is added to PowerShell's protocols instead of
  being the only one allowed, the Python download is tried three times with a growing wait,
  and the packages go into `bin\libs` (refreshed with `--upgrade` when run on its own).
- New `RUN -- Medal of Honor Model Viewer.sh` / `... Map Viewer.sh` for Linux and macOS:
  find Python 3.8+ with tkinter, vendor Pillow into `bin/libs-linux` (`bin/libs-mac`), start
  the launcher, pause once when run in a terminal. `--target` works where pip refuses
  system-wide installs (Ubuntu / Kubuntu 23.04+, PEP 668).
- All four RUN files are generated from one template, so the Model and Map twins can't
  drift apart.

## 1.0.002 Modify performance (November 2026)

Adding or changing many entities in the Map Viewer's Modify section made the page lag. The
entities were never kept in HTML (`MOD.ents` is a JS array; the list is only a view of it);
the cost was in redrawing everything on every change. Only `bin/mohaa_map_page.py` changed.
`MAP_VIEWER_REV` / `MAP_VIEWER_REV_REQUIRED` go to 107, so cached map pages rebuild.

- **List drawn by window.** `modRender` used to rebuild every row with `innerHTML` on every
  change, each row carrying the entity's whole text in its tooltip. The list is now a
  scrolling box (22 px rows, newest first) that draws only the rows in view; its tooltip is
  built on mouse-over. A newly selected row is scrolled into view.
- **Heavy checks deferred.** `modLimits`, `paIssues` and the status line moved out of
  `modRender` into `modStatNow`, run at most once per animation frame.
- **`modEdited` without strings.** It compared two `JSON.stringify` results on every call
  (it is called for each entity from the list, the links and the hide sync); it now compares
  the key/value pairs directly, with the same answer.
- **Undo / Redo as JSON, uncapped.** Each step is kept as a compact JSON string instead of a
  deep copy of every entity, and the old 1000-step limit (`MOD_UNDO_MAX`) is gone: no step is
  ever dropped. `modRestore` takes a string or an object.
- **Backup stringifies once.** `modBackupNow` built the entities' JSON twice per backup; the
  string made for the change check is reused in the file's text. The file is unchanged.

Known limits: the undo steps are held in the page's memory as strings (smaller than before,
not on disk), so a very long session still grows them; the launcher's recovery file holds
the current state only, not the undo history. Checked with a JS engine on 3000 entities
(rows drawn, tooltip on hover, scroll window, selection scroll, 3000 undo steps round-trip,
`modEdited` cases) and the repo's tests; not yet timed in a real browser or WebView2.

## 1.0.003 Simulate on path nodes (November 2026)

The Map Viewer's SIMULATE section now also shows for an `info_pathnode` (a map's own or one
Modify placed). It stands a human with a weapon on the node and plays the animation the game
plays there, so a wall, a crate that is too high or a node too near a wall shows in the
animation itself. `MAP_VIEWER_REV` / `MAP_VIEWER_REV_REQUIRED` go to 108; the version to
1.0.003. The spline Simulate is unchanged.

- **The panel.** A **Human** drop-down (every `models/human/*.tik` whose own text says
  `classname Actor`) and a **Weapon** drop-down (`models/weapons/*.tik` with `classname
  Weapon` and a `weapongroup`, which leaves the grenades and `static_kar98` out; the group
  is shown in brackets), then **Spawn**, **Simulate**, **Reset** and **Remove**. The
  choices are remembered in the browser. **Spawn** (**Respawn** once he is there) stands
  him on the node, dropped to the floor (`pgDrop`, droptofloor) and facing the node's
  yaw, idling (`<weapongroup>_stand_alert01` over `<weapongroup>_stand_alert_legs`, as
  stand.scr). Changing a drop-down with him there builds the new one. Selecting anything
  else removes him; moving the node in Modify moves him.
- **What Simulate plays**, by the node's spawnflags, in the order the game's scripts play
  them (`PathNode::GetSpecialAttack` tests CORNER_LEFT, CORNER_RIGHT, then CRATE):
  CORNER_LEFT `_wall_alert_left`, `_wall_left_shoot_intro`, `_wall_left_shoot`,
  `_wall_left_shoot_outro` (cornerleft.scr); CORNER_RIGHT the same with `right`; CRATE
  `_crate_standtocrouch`, `_crate_alert`, `_crate_crouchtostand`, `_crate_shoot`,
  `_crate_standtocrouch` (overattack.scr); SNIPER `_aim` then `_shoot` over the alert
  legs; DUCK `_crouch_alert`. A name the group lacks falls back to `name01`, then the
  lowest `nameNN` (mp40 and bar have `crate_shoot01`). No flags, DONT_LINK, COVER or
  CONCEALMENT: he only stands there and Simulate is greyed out with the reason. A flag
  combination the AI refuses (`IsValidPathnode`, the page's `nodeFlagsBad`) has no
  animation either. A group with no clips for a role (bazooka has none for the walls or
  the crate) greys it out with the missing clip's name. A corner or crate node with no
  `angle` says it faces east. Each clip plays at its own frame rate, a short one held to
  0.35 s, and the last frame stays until **Reset**. Nothing stops him going through a
  wall: that is what it shows.
- **Built on demand.** The human and weapon are built by the launcher only when chosen
  (`mohaa-sim-actor`: `ModelBuilder` with `skin_wanted`, which records each drawn vertex's
  bone weights in the order the mesh is written, plus the skeleton's names, parents and
  base pose, as `build_payload` makes them). The animation of the node's role is built when
  **Simulate** is first pressed (`mohaa-sim-actor-anim`), solved in-process against the
  skeleton the mesh came from with the Model Viewer's `solve_anim`, and kept: **Reset** then
  **Simulate** replays it without a rebuild. Clip records go to the page as JSON
  (`MOHAA_SIMACT_ANIM`), the actor as a packet (`MOHAA_SIMACTOR`); the launcher keeps the
  last four actors' skeletons.
- **Posing.** The page does what the Model Viewer's does (`worldFromPose`, `skin`, ported
  as `actWorld`, `actSkin` with the conjugating quaternion kept), without the entity-angle
  root and the Y-up swap, and uploads the skinned vertices with `bufferSubData` each
  frame. The weapon is a rigid instance on `tag_weapon_right` (`Weapon::attachToTag_main`),
  placed as the Model Viewer's attachmodel is (its `ATT_BASE_ANG` is the identity). Some
  clips move it to `tag_weapon_left` (`Weapon::attachToTag_offhand`) with their server
  commands, `weaponcommand mainhand attachtohand offhand`: the right-corner clips hold it
  there from their first frame, and a few switch mid-clip. The launcher reads these from the
  catalogue entry (`hand_events`) into each clip's `hand`; the page carries the hand from one
  clip to the next, and starts every role with the weapon in the main hand.
- **New file `bin/mohaa_map_actor.py`**: the model lists, the flag to role rules, the clip
  resolver, the solver call and the skin recorder, apart from Tk so they can be tested. It
  is in the RUN files' file lists (`tools/make_launchers.py`, both launchers regenerated).
- **Hardening.** The page's requests are checked in the launcher: keys match `[A-Za-z0-9_-]`
  (64 at most), the model paths must be a `.tik` directly in `models/human/` or
  `models/weapons/` without `..`, roles come from a fixed set (never a clip name), a clip
  over 600 frames is refused, and every failure goes to the Output pane and back to the
  page (`MOHAA_SIMACT_FAIL`), which shows it in the panel.
- **Tests.** `tests/test_map_actor.py` (20: flag rules checked against the page's
  `nodeFlagsBad` for all 256 flag values, clip-name fallbacks, request checks, list
  filters; with `MOHAA_GAMEFOLDER` set, the real catalogue of a human against every weapon
  group and a solved clip). Checked by hand with a JS engine: the page's skin of the base
  pose equals `ModelBuilder`'s own mesh (0.000 difference), and an animated frame equals
  `compute_world`'s pose of the same `.skc` frame (0.002 at most), for three humans and
  roles; the panel's whole flow (spawn, build reply, simulate, clip reply, finish, reset,
  remove) was driven with stubbed GL and DOM, and the launcher's workers against the real
  paks' data.

Checked numerically for the weapon's placement: for the rifle, MP40, Thompson, BAR and MP44 in
every clip of the left, right and crate roles, the barrel (`tag_barrel`) points along the
line to the supporting hand (cosine 0.91 to 0.99) when the hand events are applied. Without
them the right-corner clips had the rifle pointing back through him, which is how the hand
events were found. The exception is `_wall_alert_right`, which has no hand command and keeps
the weapon in the main hand as the scripts do (cornerright.scr sets nothing before it); the
barrel then lies away from the other hand in that clip, as it does in the game's data.

Known limits: not looked at in a real browser or WebView2 (no display here), so the
weapon's look in the hand should be confirmed by eye. The gear a human gets for a `case weapon "..."` in his `.tik`
(helmet, belts) is not applied: the case values don't match the weapon names, so he is
built with the `.tik`'s first branch, as map-placed actors are. Clips are played one after
another without the game's blend between them. He doesn't take part in the pick pass or
the collision of Simulate's spline model: clicks go through him.

## 1.0.003, continued: actors that move, Modify deletes, path node errors (November 2026)

Work done after the Simulate entry above and before 1.0.003 was released, so the version
stays 1.0.003 and `MAP_VIEWER_REV` / `MAP_VIEWER_REV_REQUIRED` stay at 108 (a public 1.0.001
install has page rev 106, so its cached pages are rebuilt anyway; a page built during
development is rebuilt because its scripts are newer).

**Simulate's actor**

- **New controls.** Reset and Remove are gone. The section now has the Human and Weapon
  drop-downs, then **Spawn** (**Respawn** once he is there: back on the node, idling),
  **Pause** / **Resume** (freezes him mid-animation; every clock moves on by the pause),
  **Fly to** (the camera 120 units from his chest, keeping its heading), **Follow**, then
  **Simulate**, **Move** and **Trace path**. Deselecting the node takes him away.
- **Follow** is the game's third-person camera (`CG_OffsetThirdPersonView`): the eye at his
  head (82 up) plus `cg_cameraheight` 18, back `cg_cameradist` 120 along the view, 2 down
  (`cg_cameraverticaldisplacement`), a 10-unit box traced from his head so a wall keeps it
  out, and the pitch raised 2 degrees at a time while that leaves it under 40 units from
  his head. Moving the camera by hand turns it off.
- **Move** (a menu): **Run path** / **Walk path** follow the node's `"target"` chain (its
  target, that one's target, and so on; Modify's entities first, then the map's), **Run
  to** / **Walk to** go to whatever is clicked next: a node, any entity, or a spot (Esc
  cancels). Each leg is reached as the game sends a man to a goal
  (`Actor::MoveToPatrolCurrentNode`): an `info_waypoint` is walked to in a straight line
  (`SetDest`); anything else is routed by `PathSearch::FindPath` (the nearest path node he
  can see, else the nearest; the nearest the goal can see; an A* over the paths in use,
  leaving out drops past `ai_fallheight`). When that finds nothing the panel says "Path not
  found" and he stays put, as in game. The clips are `<weapongroup>_run_forward` and
  `_walk_forward` (new `run` and `walk` roles), and his pace is the clip's own movement
  (250 / 100 units a second for a clip that carries none). Once he has moved, Run path /
  Walk path wait for Respawn: from where he stands they would send him back through walls.
- **Steering as the server does it** (`actSimRoute`, from actor.cpp, actorpath.cpp,
  g_mmove.cpp), planned in 50 ms frames before he starts: `ActorPath::UpdatePos` aims him at
  a look-ahead point along the path (`PathLookAhead`: a swept area that grows 1024 a frame
  to 256², while a 30 x 30 x 60 box trace to it is clear), so he rounds corners;
  `FaceMotion` / `UpdateAngles` turn him toward his velocity (or his last 375-500 ms of
  movement) at 360 degrees a second; a path ends within 16 units of its end. Walls and steps
  (`MmoveSingle`) aren't tested, so nothing stops him in a wall.
- **Doors open for him** as for an AI in game (`Door::SpawnTriggerField`, `FieldTouched`,
  `TryOpen`, `DoorFire`, doors.cpp): each door group's bounds grown by 60 units in x and y
  and 8 in z are a trigger field (none for a door with `health`, TARGETED, or one that
  answers only players, NOT_MONSTERS); walking into it opens the door. Doors are solid to
  him, he is held to the door's `speed` * 64 units a second while it opens, and his
  look-ahead is cut short (`ForceShortLookahead`). The walk is planned on copies of the doors
  (`actDoorSim`; `doorsAdvance` takes a set of its own and draws nothing for a copy) and the
  door events are then played on the map's doors at their time (`actDoorFire`). A door that
  never opens for him stops him there, with a message naming it.
- **Trace path** draws his path as `PathSearch::ShowNodes` does for `ai_showpath`: start to
  end in blue, the part still to go in red (32 units up), and a yellow line to his next
  point. It turns on and off with AI routes and can be turned off on its own.
- **The clip moves him.** `parse_skc` (mohaa_view.py) now returns each frame's movement
  delta (`skelAnimFileFrame_t.delta`, `fdelta`), and `solve_clip` sends the running sum
  (`dl`). The corner clips step him about 28 units to the side to lean out and back again,
  so the clearance a CORNER node needs shows in the animation.
- **More nodes and roles.** He can stand on an `info_waypoint` (no animation; he can run or
  walk from it). LOW_WALL_ARC (256, Spearhead and Breakthrough only) plays the new
  `highwall` role (aim, then shoot, standing; anim/highwall.scr) or `lowwall` with DUCK
  (crouching; anim/lowwall.scr), and the panel gives the node's `low_wall_arc`. A CORNER,
  CRATE or LOW_WALL_ARC node with no angle faces its target, else the way the camera faced
  when he spawned. With several nodes selected that form one unbroken `target` chain, the
  first of them along the chain is the one he uses; any other multiple selection shows no
  Simulate (the spline Simulate needs a single selection too).

**Modify**

- **Deleting the map's own entities.** Delete on one of the map's point entities flags it
  DEL (its row reads `#N DEL` in red, its label DEL) instead of doing nothing: it is drawn
  nowhere, a path node among them loses its links, Save as .bsp leaves it out of the entity
  lump (`write_bsp_entities` takes `del` entries; the worldspawn can't be deleted) and Save as
  .map drops its block. Copy leaves it out. The button then reads **Restore**, which (like
  Undo) puts it back. The Delete key does the same for Modify's selected rows; what has no
  row (a brush entity, a static prop) can't be deleted.
- **Spawnflags** (a new button): a list of the selected entity's spawnflag bits, each with
  its value and name (the class's own from the QUAKED headers, then the editor's `!Easy`,
  `!Medium` ... that every class has; for a path node DONT_LINK to CRATE and LOW_WALL_ARC).
  A click sets or clears a bit, Clear takes them all off; each change is one Undo step.
  Hotkey Alt+S (again, or Esc, closes it), listed in the keyboard map with Alt+M / T / E.
- **Yaw** (Modify, after Trim origin; Alt+R): each press turns the selected entities to the
  next of 0, 90, 180 and 270 degrees, as `"angle"` on an `info_` class and `"angles" "0 yaw 0"`
  on anything else (taking out the other key); one Undo step a press.
- **X-ray off hides labels behind walls.** With X-ray (9) off, entity labels and the AI path
  tags show only where the camera can see their spot (`lblSeen`), at any distance and for
  selected entities too; with it on they show through walls within 512 / 350 units as before.
  The button's tooltip says so.
- **Why an entity can't be modified.** Selecting a `.bsp`'s static model (`static_*`,
  from the static model lump, not the entity lump) or a brush entity now says so in yellow
  in Modify, as an entity the level script spawns already did; the static model's info card
  adds that it isn't in the `.bsp`'s entity lump and can't be modified here.
- **Pinched pants cuffs on MOHAA Reborn's allied_pilot** (Model Viewer, and the Map Viewer's
  actors). The ankle helper was always posed as the retail rigs' `HOSEROTBOTH`, the calf's
  frame flipped 180 degrees about its Y. `parse_skd` now reads each HoseRot bone's variant
  (`hoseType`, as `LoadBoneFromBuffer2` does), and an ankle helper that is plain `HOSEROT` (or
  `HOSEROTPARENT`) is posed by the HoseRot port instead. Only `zzzzzzzz_Reborn_pak8.pk3`'s
  `allied_pilot.skd` has such ankles among the paks checked (Pak0, pak6, pak7 and the
  `zzz` paks: 48 retail ankle helpers, all BOTH), so every other model draws as before.
- **Changes on the info card.** A map entity changed in Modify gets a "Changed in Modify
  (not saved yet)" section on its info card (N): each changed key with the map's value
  struck through and the new one (spawnflags named), or DEL for a deleted one, before the
  map's own keys (`modChangesHtml`, `sfNamesOf`).
- **48-path relinking.** A map node that already has its 48 paths may have been cut short;
  when a node within 640 units of it is added, moved or deleted, it is linked again in the
  game's order, as the game would on the next build.
- An entity with a model gets thin white axes at its origin, turned with its angles, in
  place of the facing arrow, so its new origin can be placed exactly.
- Selecting an entity the level script spawns says that it can only be changed in the
  script (with its file and line).

**Selection and AI paths**

- **Same spawnflags** selects every shown entity of the same class with the same
  spawnflags (every CRATE node, say). **Same error** selects every path node with any of the
  selected nodes' errors: no paths, one-way, duplicate, no angle, in the wall, 48 paths
  full, and Modify's own. Hide and Clear moved up beside Fly to.
- **The 48-path limit on the map's own nodes** (`paOver`): worked out from the paths in use
  by going through each full node's candidates in the game's order. A node that had more to
  link gets a "48 paths: full" tag (always shown, like Modify's own) and a card line with
  the game's `^~^~^ 48 paths per node at (...) exceeded`; one with exactly 48 gets an
  information line. Paths worked out for a map with no `.pth` report how many nodes hit it.
- **Links on terrain.** A move from a node on a terrain grid line (x or y a multiple of 64
  from the terrain's corner) started stuck in the capsule trace, though the game walks it.
  It is now tried again 1 unit up (`pgCheckMove`): on m3l1b this finds 65 of the 93 links
  the game's `.pth` has that were missed, and adds none.

**Build and launcher**

- A `.pth` beside the map on disk now comes before the one in the paks, since the game reads
  loose files before any `.pk3`: the `.pth` the game wrote when it built a map's paths beats
  a stock one made for another version of the map.
- A model the level script spawns is shown and counted as the editor class of its `.tik`
  (its QUAKED header; a German soldier is `ai_german_wehrmact_soldier`), as a map entity with
  that model is, else `script_model`, instead of a class named after the model's path
  (`LevelScript` takes `tik_class`). In game it is spawned as the class the `.tik`'s init
  `classname` names (`SpawnArgs::getClassDef`: `Actor` for a human).
- Legend: the path node rows say where each kind of node belongs (with the 28-unit lean of
  the CORNER clips, and DUCK or CRATE heights), and DONT_LINK, DUCK and LOW_WALL_ARC have
  rows of their own. The CRATE description in mohaa_entdefs.py says not to add DUCK (the AI
  refuses the combination).
- Build lines starting with `!` show in the launcher's Output in yellow, as notes: the build
  carries on and they aren't errors.
- The RUN files' menu takes Space as Enter.
- **Map Viewer sliders saved in the settings.** Camera speed, FOV, cubic clip distance, grid
  size, Modify's trim step and Simulate's camera zoom are kept in
  `mohaa_map_viewer_config.json` (`sliders`) and come back the next time a map opens; until
  now speed, FOV, clip and grid were only in the page's local storage, which the embedded
  pane (private mode) forgets when the launcher closes, and trim step and camera zoom
  weren't kept at all. The page posts them (`mohaa-sliders`) a moment after a slider
  moves and asks for them when it opens (`mohaa-sliders-get`); the launcher keeps only the
  six known keys, as numbers. In a plain browser they stay in local storage.
- **Launcher tooltips stay inside the window** (both programs): `_tip_window` narrows a
  tooltip's wrap to fit the launcher window and then moves it so every edge is at least
  8 px inside (the top-right buttons' tooltips used to run off the right edge). The drop
  shadow is added after the move. A tooltip pushed up by the bottom edge can cover the
  widget it belongs to.
- `tests/test_map_actor.py`: 23 tests (2 need `MOHAA_GAMEFOLDER`).

Known limits: the walk doesn't test walls, steps or falls (only doors stop him), a door
closing on him (`DoorBlocked`) isn't simulated, and the run and walk clips play without the
game's blending between them. Checked with the repository's tests and `node --check`; the
look of the walk and the doors should be confirmed by eye in the launcher.

## Documentation (November 2026)

- Code comments reviewed again for the Map Viewer's newest parts: notes that described
  how the code used to be ("the old note stands", "actSimRoute replaced it") now say what
  it does. Unused code removed from mohaa_map_page.py: `actAlong`, `actTurn`, `ACT_TURN`,
  `actReset` and `actRemove` (left over from the Reset and Remove buttons). The unused
  spawnflag constants in mohaa_map_actor.py had the wrong values for DUCK, COVER,
  CONCEALMENT and SNIPER; they now match the game (1 to 128, and LOW_WALL_ARC 256).
- Python files use LF line endings throughout, as the repository stores them (some had
  been saved with CRLF). The `.bat` files stay CRLF.
- `.gitignore` leaves out `.claude/`, a local editor-assistant settings folder.
- Privacy notice dated 12 November 2026 (`PRIVACY_TEXT`, `docs/PRIVACY.md`): the Map
  Viewer's display choices now include Simulate's human and weapon (`_PRIVACY_SWAPS`).
- SECURITY lists the requests a map page sends its launcher, and how each is checked.
- README, map-viewer.md, doors-notes.md, engine-notes.md, game-cvars-candidates.md,
  project-overview.md and development-workflow.md describe the changes above.

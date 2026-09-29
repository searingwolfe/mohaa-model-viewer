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

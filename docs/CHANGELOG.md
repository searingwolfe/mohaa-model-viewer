# Changelog

Revision history and notable fixes for the viewer, launcher and installer. The source
comments describe current behaviour only; the history behind it lives here. Entries are in
ascending order, so add new ones at the end of their section.

## Source comments

- Comments and docstrings across `bin/*.py` and the `.bat` files were rewritten to describe
  current behaviour, with OpenMOHAA source references kept. Per-revision notes were moved
  into this file. No code changed.

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
- rev 62 (launcher): saved placement angles are no longer snapped to the four quarter turns; the dial pencil editor accepts any angle and the typed value is kept.
- Launcher: the self-contained `--app=` standalone-window mode was removed; drag-out and "Open in browser" always use the default browser.

## Notable fixes (mohaa_view.py)

- Removed the ankle-ring vertex Z-negate workaround; the ankle helper's skinning frame is now built up-limb in `_solve_helper_world`, which made the negate unnecessary (and harmful on top of the fix).
- `mat_to_localquat` added: baking IK-solved frames with plain `mat_to_quat` stored the transpose of the intended rotation, which twisted/stretched the legs in the JS viewer while isolated renders looked correct.
- SKD morph blocks (`skeletorMorph_t`) are now read instead of skipped; they drive facial blend shapes.
- Emitter `avelocity` / `angles` accept `crandom` / `random` / `range` per component; previously `avelocity crandom ...` failed to parse and debris never rotated.
- Leg IK now runs on demand during bone resolution (engine order) instead of after a full FK pass, fixing leg-garment spikes on animations that take their legs from a movement-slot donor.
- TikiScript comment stripping removes `//` lines before `/* */` blocks; the old order let banner lines swallow whole animations{} blocks (fx_oceanspray, fx_leaves_blowing).
- Retired the load-time emitter schedule built from the `start` anim (e.g. adamspark's emitters pulsed in bursts instead of streaming like the idle in-game entity); emitteron/off windows now apply only when the anim is played.

## python_installer_updater.bat

- The user's PATH is no longer hand-edited. The old script read the user PATH with `[Environment]::GetEnvironmentVariable` (which expands `%VAR%` references) and wrote the expanded text back, permanently flattening `REG_EXPAND_SZ` entries such as `%USERPROFILE%\...` with no backup. It also stripped any entry ending in `\PythonNN`, including unrelated toolchains. Python's own installer now sets PATH (`PrependPath=1`).
- Every `if <cond> cmd1 & cmd2` is parenthesised. `&` is a command separator, so `if X endlocal & exit /b 1` ran the `exit` unconditionally; this made the old `:compare_versions` always report "older" and re-download Python on every run.
- Paths are passed to PowerShell as arguments instead of being pasted into single-quoted strings. A path containing an apostrophe (`C:\Users\O'Brien\...`) used to end the string early and have the rest parsed as code.
- The download is pinned to TLS 1.2 and the installer's Authenticode signature is verified before it runs.
- The Python version is chosen for the running Windows release. Python 3.9+ refuses to install on Windows 7 and 3.12+ requires Windows 10, so the old "always fetch latest" failed there. The viewer only needs Python 3.7.
- CPU architecture is detected (x64 / ARM64 / x86) instead of assuming amd64, and Pillow is version-checked (>= 10.3) rather than merely imported.
- Microsoft Store execution aliases are no longer deleted (a system-wide change outside the program's remit); the interpreter search skips them instead.

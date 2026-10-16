# Map Viewer

MOHAA Map Viewer opens a compiled `.bsp` or a `.map` source and shows the whole map:
textured brushes, curved patches, LOD terrain, placed and static models, and every
entity, with MOHRadiant's filters and camera keys. It is a viewer only; nothing is ever
written back to a map. Its purpose is finding things: any entity, trigger, node or brush,
with its targetname, origin and `setsize`.

It shares the Model Viewer's launcher window, pak handling, themes and embedded pane,
and keeps its own settings, log, temp folders and output folders, so both programs can
run at once.

## Files

| Path | Role |
|---|---|
| `RUN -- Medal of Honor Map Viewer.bat` | Windows entry point. Same checks as the Model Viewer's `.bat` (Python 3.8+ with tkinter, Pillow, the embedded-pane packages, WebView2) and the same installer, plus the map viewer's own scripts. A `.bsp` / `.map` dropped on it is opened directly. |
| `bin/mohaa_map_launcher.py` | The launcher. `MapApp` subclasses `mohaa_launcher.App` and changes only what differs for maps: the `maps/` tree, opening and building, the map details panel, the map options in the menus, the privacy notice's wording (`_PRIVACY_SWAPS`), and its config / log / output names. What both programs share (the updater, the WebView2 folder, `PRIVACY_TEXT`, `VERSION`) stays in `mohaa_launcher.py`. |
| `bin/mohaa_map_view.py` | Map builder. Decompiles a `.bsp`, scans the `.map`, resolves textures through the shaders, builds the placed models, collects the entity definitions and writes `<stem>_bsp_view.html` / `<stem>_map_view.html`. |
| `bin/mohaa_map_page.py` | The viewer page template (`HTML_TEMPLATE`): HTML, CSS and the WebGL2 viewer. |
| `bin/mohaa_bsp.py` | `.bsp` reader and decompiler. It also runs on its own, `python mohaa_bsp.py <map.bsp> [out.map]`, but without the paks it can't read texture sizes and assumes 256 x 256, so textures of other sizes get the wrong scale; the launcher's decompile uses the real sizes. |
| `bin/mohaa_entdefs.py` | Entity definitions: editor colour, box, spawnflag names and description per class, read from the `/*QUAKED*/` headers in the paks, with a built-in table generated from OpenMoHAA's game code as the fallback. |

## How a map gets built

1. **Paks.** As in the Model Viewer, the chosen `.pk3` files merge into one `Vfs`. The
   launcher then indexes the shaders and entity definitions once into
   `%TEMP%/mohaamap_*/cache`, so each build reads them from there.
2. **Open.** A pak map is extracted to the temp workspace and built into
   `output/maps/<subfolder>/` (`maps/DM/x.bsp` and `maps/dm/x.bsp` share `dm/`). A
   file opened from disk goes to `output/maps_standalone/`.
3. **Decompile** (`.bsp` only). `mohaa_bsp.py` writes `<stem>.map` beside the page.
   A `.map` of that name that the program didn't write (the mapper's own source next to
   the `.bsp`) is never replaced: the decompile goes to `<stem>_decompiled.map` instead.
   Decompiled files start with `// MOHAA map source rebuilt from`, which is how the
   program tells them apart, also for **File -> Clear built maps**.
4. **Build.** The `.map` text itself goes into the page and is parsed there. The builder
   adds what the page can't read for itself: every texture (the picture the game draws,
   or the editor picture for caulk, clips, triggers, sky and other tool textures, scaled
   to Options -> Texture size, 256 by default), the placed models as meshes, the sky
   boxes, the entity definitions of the classes used, and for a `.bsp` the exact bounds
   of every brush entity and the game's lighting (below).
5. **Show.** Same as the Model Viewer: the embedded pane with `#embed&theme=...`, or the
   default browser. The page sends `mohaa-close` when Esc closes the map.

## The decompiler

- **Brushes** are rebuilt from their planes (a large square on each plane, cut down by
  the brush's other planes, as `polylib.c` does). Brushes of an entity with an origin
  are stored around (0,0,0) and are moved back; an origin brush is added back where the
  entity's pivot isn't the centre of its brushes (a door's hinge).
- **Texture alignment.** A compiled brush side keeps only its shader, so each visible
  face is matched to the draw surface the game renders on that plane, and the
  shift / rotation / scale are fitted to that surface's texture coordinates
  (`QuakeTextureVecs` in reverse). Texture coordinates are computed in world space, also
  for brush entities. The texture size used is the one the map compiler used: the
  shader's light image, else its `qer_editorimage`, else the image named after the
  shader, else 64x64. Faces the game never draws (caulk, hidden sides) keep a default
  alignment; side equations (lump 10) fill in where no surface matches. Sky faces get
  `0 0 0 1 1`, as in EA's own sources: a sky polygon's texture coordinates are laid out
  on their own, not projected from the face, so there is nothing to fit.
- **Patches** come back from their control-point grids, **terrain** from the terrain lump
  (heights, per-triangle holes, texture shift / scale per block), **static models** as
  entities with their `.tik` class name.
- **Checked on** all 54 retail Allied Assault `.bsp` files, plus Spearhead and
  Breakthrough ones. On `mohdm6` and `m6l1a`, 98-99% of the visible surfaces get the same
  texture coordinates back as the `.bsp` holds.
- **Damaged files.** Every lump must lie inside the file; counts come from lump sizes; a
  brush with more than 300 sides (q3map's `MAX_BUILD_SIDES`) is skipped; a plane, polygon
  or fit with NaN or infinite numbers is skipped, and such a number is written as 0. A
  file that still trips the reader stops the build with "looks damaged" (exit code 5;
  `mohaa_bsp.py` on its own exits with 3), and nothing is written for it. Randomly
  corrupted copies of retail maps either build or stop with that message.

## The page

- **Data.** One `MMV1` container: a JSON header followed by binary blobs (the `.map`
  text, textures, model meshes), gzip-compressed, base64 in a
  `<script type="application/octet-stream">` block. The page unpacks it with
  `DecompressionStream` and serves textures as blob URLs. The CSP is the Model Viewer's.
- **Reading the `.map`.** A texture name is one word, as q3map and MOHRadiant read it,
  whatever it starts with: a brush in Spearhead's `t1l1` (`script_object`, entity 1072)
  has the shader `textures/(0`, which the compiler took from EA's source as it was. A
  block the reader can't make sense of (a brush, patch or terrain block) is skipped and
  the rest of the map is drawn. The red "unreadable blocks skipped" line under the map's
  stats opens a card that lists each one: its entity (a link, unless it is part of the
  world), the primitive, its line in the `.map` and the reason, with the line itself. In
  the launcher's pane the same list goes to the Output console, in red. After a bad
  block the reader carries on past the `}` that closes it, so a damaged patch or terrain
  block doesn't cut its entity short.
- **Drawing.** WebGL2. One index buffer holds every face, grouped per material and
  rebuilt when the filters change. Models are instanced; point entities without a model
  are boxes coloured as MOHRadiant colours them (below). With Full Brightness on (and
  always for a `.map`), Radiant-style shading darkens faces by their facing (0.9 x^2 +
  0.8 y^2 + 1.0 z^2 on the normal); with it off, a `.bsp` is drawn with the game's
  lighting. Alpha-tested, blended, additive and editor-translucent kinds, worldspawn
  `farplane` fog, and cubic clipping work in both.
- **See-through editor brushes** (hint, clip, trigger, nodraw and the like) are drawn
  one-sided, as MOHRadiant draws them, so a hint brush doesn't show the letters of its
  far side through its near side. When the camera is inside one, its inner sides are
  drawn instead (culling flipped), as MOHRadiant shows them.
- **Caulk** is pushed half a unit back along each vertex's line of sight, so it loses
  every depth tie against the walls it touches (no sparkles along corners).
- **Nodraw.** A texture the game never draws that is in no other editor group (caulk,
  clips, triggers, hints...) goes with the Nodraw button and the In-game look: rain (the
  volume of a `func_rain` entity), patharea, ladders, and the flat tree pictures some
  maps stand beside their trees (`misc_outside/commontreeshadow`), which only give the
  tree its shadow when the map is lit. Those are world brushes, not part of the tree, so
  hiding a tree leaves them.
- **Trees.** A tree model carries a sprite version: a card of the whole tree
  (`deformVertexes autoSprite2`, `alphaGen oneMinusDistFade`) that the game fades in far
  away as the tree's own surfaces fade out (`alphaGen distFade`; `R_AddStaticModelSurfaces`
  skips a surface outside its fade range). The page draws the whole tree without the card.
  Simple models (`M`) draws the card alone instead, as the game shows a tree far away,
  turned in the vertex shader the way `Autosprite2Deform` turns it: each quad about its
  long axis, to face the camera's forward direction, so the tree stays upright. The build
  marks those shaders `TF_LOD`. Bushes and other models without a card don't change.
- **Lines** (setsize boxes, target links and their arrowheads, facing arrows) are
  hidden behind walls like everything else. With X-ray on, only the selection's own
  outline, box, links and arrow show faintly through walls. Labels are always drawn on
  top.
- **Sky.** With Simple Sky off (the default) the sky is drawn as the game draws it: the
  shader's far box (`skyParms env/<name>`, the six `_rt _bk _lf _ft _up _dn` pictures),
  looked up per pixel as `vec_to_st` in `tr_sky.c`, at the far end of the depth range
  (`RB_StageIteratorSky` draws it with `qglDepthRange(1, 1)`). So the sky is behind
  everything, and whatever is behind a sky brush shows through it, as in game. It looks
  the same with Full Brightness on and on a `.map` page. With Fog on, the sky and
  everything beyond the fog's far end are the fog colour. Simple Sky (`K`) draws sky
  brushes as MOHRadiant does: solid, with the shader's editor picture tiled
  (`qer_editorimage`, else the image named after the shader). Editor look turns it on
  together with Full Brightness (MOHRadiant is always full bright), In-game look turns
  both off. The Sky filter (`Ctrl+K`) hides sky brushes altogether.
- **Clouds.** A sky shader's stages are its cloud layers (the drifting clouds of
  `textures/sky/africanight`, on m1l1, m1l2a/b, m6l3b and mohdm7), drawn over the far
  box as `R_BuildCloudData` draws them: each pixel's direction is followed out to a
  sphere 4096 units in radius whose top is the `skyParms` cloud height above the eye,
  and the arc cosines of that point's x and y are the texture coordinates
  (`R_InitSkyTexCoords`); the bottom of the box gets none. Each stage keeps its
  blendFunc, alphaFunc, rgbGen (`const`, `wave`, `colorWave`), alphaGen (`const`,
  `wave`, `skyAlpha` from the worldspawn's `skyalpha`) and tcMods (`scroll`, `scale`,
  `rotate`, `transform`, `stretch`, `offset`, `wavetrans` / `wavetrant`), worked out each
  frame from the time since the page opened and folded into one affine map; up to four
  layers. Moving clouds redraw the view up to 30 times a second while some sky is in
  view: an occlusion query on each frame's sky says whether any of it showed, and the
  redrawing stops when none did until the view changes. They aren't drawn with Simple Sky
  or Fog on, as the game's fog covers its sky.
- **Picking** renders face / entity ids into a 1-pixel target around the cursor, then
  finds the exact point on the plane or triangle under it. What the mouse is over gets an
  outline in the accent colour: a brush's edges (all of a brush entity's brushes), or
  for a model or marker its box, as the selection draws it in red. The game's sky is
  picked only where nothing else is under the cursor, as it is seen; a second pass then
  finds the nearest sky brush there.
- **Clicks.** Click selects, Shift+click adds or removes, Ctrl+click also opens the info
  card, Alt+click selects everything of the same kind. Ctrl+Shift+click (or a
  middle-click) shows the clicked face's texture; in Radiant, Ctrl+Shift+click selects a
  single face. Ctrl+Alt+click selects every entity on a path through the clicked one: it
  follows `"target"` to the entities with that `"targetname"`, again and again, and back
  the other way to every entity whose target leads to it, so a node in the middle of a
  chain selects the whole chain, a fork or a loop included (with Shift, the path is added
  to the selection). The Links section of an entity's info card has the same as a link,
  and the Selection panel's **Same kind** and **Same path** buttons do what Alt+click and
  Ctrl+Alt+click do (Same path shows when the selected entity has a path: its target leads
  somewhere or something targets it).
- **Entity boxes** (the `setsize` on the info card): for a `.bsp`, the brush model's
  exact bounds around its origin; for a `.map`, the bounds of the entity's brushes around
  its origin brush, `origin` key, or brush centre. Point entities use a `setsize` key,
  else the model's `.tik` setsize, else the model's own bounds, else the class box (a
  game-code class: MOHRadiant's 16-unit stand-in cube).
- **Point-entity boxes** are coloured the way MOHRadiant's camera colours them (its
  brush drawing in `mohradiant.exe`): the class colour, each side shaded by its facing
  (`SetShadeForPlane`: 0.6 facing x, 0.8 facing y, 1.0 up and down); a `"_color"` key
  paints the box flat in that colour; an `info_path...` class with a `"targetname"` gets
  its colour turned inside out (1 - colour). MOHRadiant reads class definitions from the
  .tik files and from its entity folder (`code/`) on disk; the game code's ship inside
  entdefs.pk3, so there every game-code class (player starts, path nodes, script
  origins, spline paths, grenade hints...) is its "Not found in source." stand-in: a dark
  green 16-unit cube on the origin. The viewer draws them the same way. Classes defined
  in a .tik keep their definition's colour and box. Path nodes are therefore
  dark green, pink with a targetname, flat cyan for the friendlynodes' `_color`. A path
  node with AI flags also gets MOHRadiant's thick outline by its spawnflags, first match:
  COVER green, CORNER_LEFT yellow, CORNER_RIGHT yellow-green, SNIPER red, CRATE dark
  red, CONCEALMENT blue, DUCK cyan; black for flags that don't go together
  (`IsValidPathnode` in navigate.cpp; its `ai_editmode` colours are the same). A node's
  info card lists its colours and why. Lights stay diamonds in their light colour.
- **Facing arrows** are MOHRadiant's (`Brush_DrawFacingAngle`): white, 4 pixels wide,
  from the middle of the box out to 2.5 times its half-width, the head opening up and
  down; drawn as camera-facing bands each frame.
- **The legend** (`L`, the "L legend" chip, or the Legend button in a node's card; Help >
  Legend / `F2` in the launcher) explains the node colours and borders, the entity
  markers (setsize boxes included) and every editor surface the retail maps use, rain
  and caulksky included, plus the flat grey of a texture missing from the paks. The page
  and the launcher both read `LEGEND` in mohaa_map_view.py; the build puts the editor
  pictures of its textures in the page (48 px PNGs, cached with the textures), and the
  launcher reads them from the loaded paks. Each of its sections (AI path nodes,
  entities, brushes and editor surfaces) is a column that scrolls on its own, so both
  windows stay about 640 px tall (the launcher's never taller than the launcher window);
  the mouse wheel scrolls the column under the pointer.
- **Remembered** per browser: theme, backdrop, display / filter choices, camera
  settings, and the camera position for each map (keyed by the map's path inside the
  paks, or its file name). The embedded pane runs WebView2 in private mode, so there
  they last only while the launcher is open.

## The game's lighting

With Show > Full Brightness off (the default), a `.bsp` is drawn the way the game lights
it. Everything comes from the `.bsp`; the light is never recomputed.

- **Planar faces** are the compiled polygons themselves (draw surfaces, lump 3), each
  tied to the `.map` face it came from, so the filters, Hide and selection still work on
  them. Picking always uses the `.map` faces. Editor textures (caulk, clips, triggers,
  hints...) keep their `.map` faces.
- **Lightmaps** (lump 2, 128x128 pages) are brightened as `R_ColorShiftLightingBytes`
  does with `r_mapOverBrightBits 1` (shift by one, scaled back if a channel overflows)
  and packed into one PNG; the page loads them into a texture array.
- **How each surface is lit** follows `R_FindShader` / `ParseStage` (renderergl1
  `tr_shader.c`): no shader script = texture x lightmap; a `$lightmap` stage = texture x
  lightmap (white without one); `rgbGen vertex` / `exactVertex` = texture x vertex
  colour; anything else = the texture as it is. A lightmap number past the file's
  pages, and triangle soups, are vertex lit (`ParseFace`, `ParseTriSurf`).
- **The picture and its stage.** Each shader shows one picture: the texture a stage
  multiplies by the lightmap, else the stage drawing the `qer_editorimage` (unless it
  is a glow added on top), else the last solid stage (floors draw a reflection first and
  paint over it), else the first picture; `tcGen environment` reflections only when
  nothing else is left. With the game's lighting that stage's `tcMod scale`, its
  `alphaGen` (`const`, `sCoord` / `tCoord` fades, vertex alpha) and a `depthWrite` on a
  blended stage are applied; Full Brightness keeps MOHRadiant's unscaled picture.
- **See-through surfaces** are drawn in layers: the game's own (water, glass, glows;
  the ones that write depth in game first), then the models', then the editor's volumes
  (triggers, clips, hints, nodraw), so water never paints over a trigger above it.
- **Patches** are tessellated from the `.map` patch with the `.bsp`'s lightmap
  coordinates and vertex colours carried through the same curve.
- **Terrain** gets its lightmap coordinates from each patch's corner texel and scale,
  64 units per step (`R_PreTessellateTerrain` in `tr_terrain.c`).
- **Static props** (`static_*`) use the vertex light baked for them (lump 24), in the
  engine's vertex order (every surface of every mesh, hidden ones included), brightened
  like `R_InitStaticModels`; it applies to surfaces whose shader uses `rgbGen vertex`,
  `lightingSpherical` or similar. Other models take the light grid colour at their
  origin (lumps 16-18, `R_GetLightingGridValue`).
- **Water, slime and lava** use the shader's own picture (MOHRadiant's editor picture
  at Full Brightness) and are solid unless the shader blends.
- **Sky** polygons are the `.bsp`'s own, drawn with the sky box as described under The
  page.

## Cameras

- **Free-look** is the Model Viewer's: drag to look, WASD / arrows, Space / C, Q / E
  tilt. With the camera tilted, looking and turning follow the tilted screen, as in the
  Model Viewer: a mouse movement (or arrow key) is rotated by the roll before it becomes
  yaw and pitch (`lookBy`), so dragging down still looks toward the bottom of the screen.
  A / D strafe along the tilted screen's right, and Space / C rise along its up (world
  up turned about the view line by the roll; straight up and down with no tilt). End
  levels the view and clears the tilt.
- **Radiant-look** follows MOHRadiant: right-drag flies (push up = forward, sideways =
  turn, like `Cam_MouseControl`), arrows move and turn, `,` / `.` strafe, D / C rise and
  fall, A / Z look up and down, End levels the view, PgUp / PgDn hop to the floor above /
  below (UpFloor / DownFloor), Ctrl+arrows and Ctrl+`,` / `.` move one 64-unit grid step,
  `[` / `]` move the cubic clip.
- `V` switches cameras, `R` returns to the player start, `B` toggles Full Brightness,
  `K` Simple Sky, `M` Simple models, `L` opens the legend and `T` switches the theme. The
  FOV slider runs from 60 to 150. Press `H` in the viewer for the full list.

## Versions

- `MAP_VIEWER_REV` (mohaa_map_view.py) is baked into each page as
  `<!--mohaa-map-viewer-rev:N-->`; `MAP_VIEWER_REV_REQUIRED` (mohaa_map_launcher.py) is
  the oldest one the launcher reuses. Raise both together when cached pages must be
  rebuilt. A page is also rebuilt when any script that builds it is newer.
- `INDEX_VERSION` (mohaa_map_view.py) invalidates the shader / entity-definition cache.

## Known limits and open work

- Each shader shows one picture (above), sky clouds aside; its other stages (a second
  texture bundle, an added glow or highlight layer), `tcMod scroll` / `rotate` / `turb`,
  animated maps and `deformVertexes` don't play.
- Lighting: dynamic lights (lamps switched by script, muzzle flashes) and the
  `alphaGen distFade` fade-out aren't drawn. Portal skies (`textures/common/skyportal`
  with a `script_skyorigin`) show the plain sky box; no retail Allied Assault map uses one.
- Trees don't change with distance: they are drawn whole, or as their sprite version
  with Simple models on (above), never faded from one to the other as in game.
- A `.map` has no compiled light, so it is always drawn full bright.
- Clouds: `tcMod turb` and the entity-driven tcMods, `animMap` frames after the first,
  and a second texture bundle aren't drawn; the noise waveform is a smooth stand-in for
  the engine's.
- `.pth`, `.min`, `.dcl` and `.vis` files are listed in the tree but not opened yet;
  `.scr` scripts open in the text editor.
- Triangle soups in a `.bsp` (rare in MOHAA maps) are counted but not decompiled.
- **Planned:** reading a map's other files: its `.pth` path data, its `.min` file, and
  its `.scr` level scripts, to show the models and changes a script adds at run time.

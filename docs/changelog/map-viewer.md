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
| `bin/mohaa_bsp.py` | `.bsp` reader and decompiler; also reads the BSP tree and vis data, tessellates curved patches as the renderer does, and reads the game's `.pth` AI path files (for the game cvars). It also runs on its own, `python mohaa_bsp.py <map.bsp> [out.map]`, but without the paks it can't read texture sizes and assumes 256 x 256, so textures of other sizes get the wrong scale; the launcher's decompile uses the real sizes. |
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
   boxes, the entity definitions of the classes used, for a `.bsp` the exact bounds of
   every brush entity, the game's lighting (below) and what `r_showtris` needs (the BSP
   tree, leafs, vis lump and the lines of every surface the game draws), and the map's
   `.pth` path file when there is one (Game cvars, below).
5. **Show.** Same as the Model Viewer: the embedded pane with `#embed&theme=...`, or the
   default browser. The page sends `mohaa-close` when Esc closes the map.

## The decompiler

- **Brushes** are rebuilt from their planes (a large square on each plane, cut down by
  the brush's other planes, as `polylib.c` does). Brushes of an entity with an origin
  are stored around (0,0,0) and are moved back; an origin brush is added back where the
  entity's pivot isn't the centre of its brushes (a door's hinge). It takes the shape
  EA's own sources give it (`ORIGIN_COLUMNS`): for a `func_ladder` (always) and a
  `func_rotatingdoor`, a thin column from the bottom of the entity up through the origin
  and as far again above it, 4 or 8 units across (the climbing line, the hinge); for
  anything else, a 16-unit cube. Either way it is centred on the origin, so a recompile
  gives the same origin.
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
  clips, triggers, hints...) goes with the Nodraw button (`Ctrl+O`) and the In-game look:
  patharea, ladders, and the flat tree pictures some maps stand beside their trees
  (`misc_outside/commontreeshadow`), which only give the tree its shadow when the map is
  lit. Those are world brushes, not part of the tree, so hiding a tree leaves them.
- **Rain and foliage clips** have Show buttons of their own: Rain (`Ctrl+I`,
  `common/rain`, the volumes of `func_rain` entities, which fill some winter maps like
  hint brushes) starts hidden, in the Editor look too; Foliage clips (`Ctrl+G`,
  `common/foliageclip`) are apart from the other Clips. The In-game look hides both.
  Options saved before Rain had its button start with it hidden.
- **The Entities button** (`Alt+2`) covers brush entities, point entities, lights, AI
  nodes, paths, models and static props. With only some of those hidden by their own
  buttons, it stays on, dashed, and its tooltip names the hidden kinds; a click hides the
  rest, a second shows all.
- **All, In-game look, Editor look** (under the Show buttons; `Ctrl+A`, `G`, `Shift+G`):
  All shows every group. In-game look hides what the game never draws (caulk, clips,
  triggers, hints, origin brushes, areaportals, nodraw, rain, foliage clips) and the
  entity markers, with the game's lighting and sky (Full Brightness and Simple Sky off).
  Editor look is MOHRadiant's view: everything but hints, areaportals and rain, at Full
  Brightness with Simple Sky.
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
- **Hide** (Backspace or the Hide button) and **Show all** (Shift+H) go on a stack that
  `Ctrl+Z` (or the Undo button beside Show all) unwinds one step at a time: a Hide shows
  those things again, a Show all hides again what it showed.
- **Find, Classes, Textures** (the list under Find): each tab's counts and hints sit above
  a line, and the list is a section of its own under it. A class row selects the class and
  opens (or closes) the list of its entities; a double-click leaves it open and flies there
  (a second click on the same row within half a second counts as one, since the first
  click rebuilds the list and the browser may not see a double-click). Hidden entities
  (Hide, or a Show button off) are red, a class with some of them hidden yellow with the
  hidden count. Shift+click a row's coloured square to hide that entity or the whole class
  (again: show them; on the Hide stack, so Ctrl+Z undoes it); a Show button's hiding stays,
  and the message names the button.
- **Entity counts.** Under the map's stats: how many entities are real (the game spawns
  them as entities, each with an entity number; MOHAA has 1024 slots), simple (path
  nodes, player starts, waypoints, vehicle points, grenade hints, AI spawn points, which
  derive from `SimpleEntity`, and the lights, info_nulls, misc_models and compiler-only
  entities that don't last as entities), and static props. The class lists are
  `SIMPLE_CLASSES` / `DROPPED_CLASSES` in mohaa_entdefs.py, from OpenMoHAA's game code;
  an unknown class (most come from `.tik` files) counts as real. Static props are the
  `static_*` classes of a `.map`, or the entities from a `.bsp`'s static model lump
  (`firstStatic`; some take a `.tik` class name without the prefix). The launcher's map
  details and the build log show the same counts, the log in red past 1024.
- **Open** beside Copy on an info card's `.map source`: in the launcher's pane, the
  launcher opens the `.map` in the Text Editor at that entity's or brush's line (for
  Notepad++, VS Code, Sublime Text, Notepad2/3, EmEditor, gedit, Kate and gVim; other
  editors open it at the top); in a browser, the whole `.map` opens as text in a new tab.
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
  somewhere or something targets it). **Same targetname** (`$`, Shift+4) selects every
  entity with the selected one's targetname, the group a script reaches as `$name`; it
  shows when another entity shares the name. **Open door** (`O`) shows when a door is
  selected (Doors, below).
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
- **Doors** (`func_rotatingdoor`, `func_door`): **Open door** in Selection, or `O`, does
  what the use key does in game (`doors.cpp`, `mover.cpp`); while the door is open or
  opening it reads Close door. Each door keeps the game's states (closed, opening, open,
  closing). A rotating door turns `openangle` degrees (90) about its origin, away from the
  camera with `alwaysaway` 1 (the default) or always the same way with 0
  (`RotatingDoor::DoOpen`); a `func_door` slides along `angle` by its size that way less
  `lip` (8). A whole move takes `time` seconds or `doortype` wood 1 / metal 1.5 (the last
  of those keys wins; a `func_door`'s `speed` overrides both), at an even speed from
  wherever the door is (`Mover::MoveTo`), and the door closes itself `wait` seconds after
  it has opened (3; never with TOGGLE, or `wait` -1 or 0). Doors of one class whose boxes
  touch move together, led by the first of them in the .map (`Door::LinkDoors`). The
  `.map` faces, the game's polygons and r_showtris's points, planes and lines are put
  where the door is now from copies of where the `.map` has them (`doorPose`), and the
  selection, setsize box, label and links follow. The master's area portal is open from
  the moment it starts to open until it is shut again (`doorPortal`, counted as
  `CM_AdjustAreaPortalState` counts). The doors run on the page's clock
  (`doorsAdvance`), so a page left in the background catches up in order. The info card
  has a Door section. A `script_door` moves only for its map script, so its button is
  greyed out.
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
- **Keyboard shortcuts** (`H` or `?`, or the "H hotkeys" chip; Help > Keyboard shortcuts /
  `F1` in the launcher, which has the launcher's own keys on a second tab) are a keyboard
  map, as in Adobe Audition: a keyboard and a mouse with every key the viewer uses
  coloured by kind (camera, selecting, show / hide, display, window) and its short name on
  it, and the same shortcuts as a list underneath, three columns that each scroll on their
  own with a line between rows. Hovering a key, or pressing it, lists everything it does
  with every modifier and in which camera; Shift, Ctrl and Alt (clicked, or held) show
  their layer of the keyboard; Free-look / Radiant-look switch the camera keys, and the
  page's window opens on the camera in use. Hovering a row rings its keys, clicking a key
  finds its rows, and a search box and the category chips narrow it all down. While the
  window is open, keys are only looked up; Esc, H or `?` closes it (Esc or F1 in the
  launcher). Both windows read `MAP_VIEWER_KEYS` in mohaa_map_view.py. The page's window
  is the Model Viewer's (`KEYS_JS` / `KEYS_CSS` in mohaa_view.py), the launcher's is
  `KeyMapWindow` in mohaa_launcher.py.
- **Game cvars** (Display > "game cvars", below backdrop, or `` ` ``): a few of the game's
  debugging cvars, doing in the page what they do in game. A click on a row sets it (again:
  back to the game's default); the filter box is also the console (`r_showtris 2` then
  Enter; a name alone tells its value and default). The list's foot shows the camera's
  cluster and area, what is drawn from there (counted in every direction: the game also
  drops what is outside the view), and the path file's source; the cvars set are named
  beside the button and remembered. `CVAR_DEFAULTS` / `CVAR_ROWS` in the page hold them.
  - `r_showtris 1 / 2 / 3` (`.bsp` only) outlines what the renderer draws from the camera
    (`DrawTris`, `tr_shade.c`): 1 behind walls, 2 through them with axis crosses, 3 the
    crosses alone. The page walks the `.bsp`'s tree the way `tr_world.c` does: the
    camera's cluster (`R_PointInLeaf`), its row of the vis lump and the areas joined to
    its own (`R_MarkLeaves`), the farplane (`farplane`, `farplane_cull`), faces turned
    away dropped with 8 units of slack (`R_CullSurface`), curved patches at the rows and
    columns their distance allows (`RB_SurfaceGrid` with `r_lodCurveError` 250, on the
    grid `R_SubdividePatchToGrid` makes from the patch's own subdivisions x
    `r_subdivisions` / 10, else `r_subdivisions` 3; ported as `subdivide_patch` in
    mohaa_bsp.py), terrain blocks
    and static props from the kept leafs, and the brush entities and models the server
    sends (`sv_snapshot.c`). A leaf with no cluster (outside the map) keeps everything; a
    `.bsp` without vis data sees every cluster. The overlay ignores the Show buttons: it is
    the game's view.
  - `cm_noAreas 1` opens every area portal. Without it the level is as it starts: doors
    shut, except a `func_door`, `func_rotatingdoor` or `script_door` with spawnflags 1
    (START_OPEN) that leads its group, whose portal is open (flooded as
    `CM_FloodAreaConnections` does); Open door opens and shuts them (Doors, above).
  - `ai_showroutes 1` (with `ai_showroutes_distance` and `ai_fallheight`) draws the
    connections in the map's `.pth` as `DrawAllConnections` (`navigate.cpp`) draws them:
    green both ways, a red arrowhead one way, a red X on a node with none, a blue circle on
    a DONT_LINK node. The `.pth` is `maps/<map>.pth` in the paks (else beside the file),
    unpacked (`CSVG` + LZ77, `lz77.cpp`) and read as `PathSearch::ArchiveLoadNodes` reads
    it, typed (the game's own files) or untyped (OpenMoHAA's); node i is the map's i-th
    `info_pathnode`, and a count mismatch is flagged. A path node's info card lists its
    connections.
  - The cvars' lines are cut at the near plane in the vertex shader (`clipEnd`), since
    SwiftShader drops a line with one end behind the camera.
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
- **Stopping.** `X` stops the camera (held keys, a drag, Radiant-look's flight, a fly-to).
  It also stops by itself when the page loses the keyboard or the window, while the page
  doesn't have the focus, when a drag's mouse button turns out to have been let go
  outside the page, and, in the launcher's pane, on any click on the launcher: a key or
  button let go outside the page never reaches it, and the camera used to keep moving.
- `V` switches cameras, `R` returns to the player start, `B` toggles Full Brightness,
  `K` Simple Sky, `M` Simple models, `L` opens the legend, `` ` `` the game cvars list and
  `T` switches the theme. The
  FOV slider runs from 60 to 150. Press `H` in the viewer for all of them (Keyboard
  shortcuts, above).

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
- `.min`, `.dcl` and `.vis` files are listed in the tree but not opened yet; `.scr`
  scripts open in the text editor. A map's `.pth` is read by its page (ai_showroutes),
  not opened from the tree on its own.
- Triangle soups in a `.bsp` (rare in MOHAA maps) are counted but not decompiled.
- `r_showtris` draws terrain at full detail (the game thins it out with distance,
  `ter_error` / `ter_maxlod`) and models at full detail (no model LOD). Patches aren't
  stitched where two meet (`R_StitchAllPatches`, `R_FixSharedVertexLodError`), so a seam
  between patches of different detail can differ from the game's. The sky's cloud dome
  isn't outlined. Doors are as the level starts unless opened with Open door (no scripts
  run), and other entities stand where the `.map` puts them. The overlay and its counts
  cover every direction around the camera.
- Doors: a fully open door doesn't cut the AI paths it blocks. In game `Door::SetState`
  disconnects every path connection an actor's box can't sweep past the open door
  (`Entity::DisconnectPaths`, a cylinder trace), and `ai_showroutes` stops drawing those
  until the door starts closing. Locks, a door's `message` and its sounds aren't
  simulated, and a door that is blocked doesn't stop.
- **Planned:** reading a map's other files: its `.min` file, and its `.scr` level
  scripts, to show the models and changes a script adds at run time. More of the game's
  debugging cvars, once checked in game.

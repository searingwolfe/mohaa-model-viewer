# Map Viewer

MOHAA Map Viewer opens a compiled `.bsp`, a `.map` source or MOHRadiant's `.bak` backup
and shows the whole map:
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
| `MOH Model-Map Viewer (Windows x86-x64).bat` (`.sh`) | The entry point both programs share: press 1 (or Enter) in its menu for the Map Viewer. Same checks as for the Model Viewer (Python 3.8+ with tkinter, Pillow, the embedded-pane packages, WebView2) and the same installer, plus the map viewer's own scripts. A `.bsp` / `.map` / `.bak` dropped on it skips the menu and opens directly. |
| `bin/mohaa_map_launcher.py` | The launcher. `MapApp` subclasses `mohaa_launcher.App` and changes only what differs for maps: the `maps/` tree, opening and building, the map details panel (one scrolling column, shared with the Model Viewer as `make_info_pane`, with Rebuild / Browser / .map buttons: `info_button`), the map options in the menus, the privacy notice's wording (`_PRIVACY_SWAPS`), and its config / log / output names. What both programs share (the updater, the WebView2 folder, `PRIVACY_TEXT`, `VERSION`) stays in `mohaa_launcher.py`. |
| `bin/mohaa_map_view.py` | Map builder. Decompiles a `.bsp`, scans the `.map`, resolves textures through the shaders, builds the placed models, collects the entity definitions and writes `<stem>_bsp_view.html` / `<stem>_map_view.html` (`<stem>_bak_view.html` for a `.bak`). |
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
   every brush entity, the game's lighting (below) and what `r_showtris` and
   `r_shownormals` need (the BSP tree, leafs, vis lump, the lines of every surface the
   game draws and the normal at each of its points, and each model's vertex normals), and
   the map's `.pth` path file when there is one (Game cvars, below), its `.dcl`
   decals, its `.lin` leak trail (Decals and leak trail, below) and what its level
   script spawns and sets (Level script, below).
   - The page lists the loose files it was built from with their times (`deps` in its
     summary block: the map opened from disk, the `.scr`, `.dcl`, `.lin` and `.pth` beside
     it, the loose scripts read and where the map's script could appear in the paks'
     folder). The launcher rebuilds it instead of reusing it when one of them changed,
     appeared or went.
   - A `.bak` (MOHRadiant's previous save of the `.map`, or a backed-up `.bsp`) opens
     as what its first bytes say it holds. What it writes has `_bak` in its name:
     `<stem>_bak_view.html`, and for a `.bsp` backup `<stem>_bak.map`, so it never
     takes the place of the real map's page or decompile. Its side files (`.dcl`,
     `.lin`, `.pth`) are the map's own: `maps/<stem>.*` in the paks, else beside it.
5. **Show.** Same as the Model Viewer: the embedded pane with `#embed&theme=...`, or the
   default browser. The page sends `mohaa-close` when Esc closes the map.

## The decompiler

- **Entities** are written one key a line. A key or value with a line break or a brace
  in it (a damaged lump: the game reads a quoted string across lines) is written on one
  line, braces as ( ), with an Output line naming the entity (`_map_safe`), so the .map
  has the lump's entities one for one; otherwise every entity after it would be one place
  out (static props with their neighbour's model, script entities without theirs).
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

- **Drawing.** The frame loop (`loop`, once per screen refresh) draws at most once a
  frame. Anything that needs the view redrawn (a mouse look, a key move, the clouds, the
  hover outline, a cvar) only asks for it (`requestDraw`).
  - **What is sent to the card is culled to the view** (`frustumOf`, `drawRuns`,
    `cullModels`). Each texture's run of world faces, and of the game's polygons, is
    sorted by the 1024-unit cell it lies in (`cullPrepFaces`, `cullPrepLit`). A cell's part
    is skipped when its box is outside the view's six planes or outside the cubic clip.
    The far plane is the fog's or r_farplane's far end, or 1.8 times the cubic clip, so
    Fog and Cubic clip now cut what is drawn and not only what is seen.
  - Parts next to each other, and small hidden gaps between them, are drawn as one.
  - Brush entities' faces (doors and exploder chunks move) are never culled.
  - Model instances are culled by their bounding sphere, and the shown ones are packed into
    the instance buffer, in new storage each time it changes.
  - On m5l1a from one spot, the four ways round average 78k triangles a frame instead of
    280k (20k with Cubic clip at 2048). The picture is the same.
  - The overlay canvas is cleared only when it has something on it. The text read-outs (the
    camera line, the game cvars list's foot) change at most about 8 times a second while
    the view moves, and once more when it stops (`textSoon`).
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
- **Keys with `$` or `#` in front** (`"$targetname" "mg42guy"`, used some 3600 times in the
  retail maps) set the key of that name when the game has a setter for it
  (`SpawnArgs::SpawnInternal`, g_spawn.cpp; `#` gives it as a whole number), and the page
  reads them that way everywhere (`spawnKeys`, after the .map is read): names, labels,
  links, Same targetname and Same path, the lists and the info card. The setters' names
  (`SETTER_KEYS`, from the game's `EV_SETTER` events) are in mohaa_bsp.py and come with
  the page (`D.sk`); the build reads entities the same way (`MB.kv_dict`). The first
  written of `name`, `$name` and `#name` wins, since the game runs an entity's keys last
  to first, except that `$model` outlasts a plain `model` (due earlier); on an actor the
  plain key wins (Engine notes, Map entities). Without such a
  setter (`#set`, `#group`, `$type`) the game only makes a script variable of it
  (`self.set`), so it stays a key of its own. The info card shows the keys as written, and
  MOHRadiant's look goes by them as written too (`edKey`); so does the decompiler, which
  reads what the map compiler wrote.
- **Drawing.** WebGL2. One index buffer holds every face, grouped per material and
  rebuilt when the filters change. Models are instanced, each posed at frame 0 of its
  `idle` animation (else its first), found in any of the `.tik`'s animations sections,
  the ones its `$include`s bring too (a character's idle is in new_generic_human.tik);
  heads and hands are drawn as the game draws them (MOHRadiant draws only the body).
  Point entities without a model
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
  entity markers, with the game's lighting, sky and sun flare (Full Brightness and Simple
  Sky off, Sun flare on). Editor look is MOHRadiant's view: everything but hints,
  areaportals and rain, at Full Brightness with Simple Sky and no sun flare. The two looks
  are a row of two wide buttons at the bottom of Show, like the cameras' Free-look and
  Radiant-look. Each is on while the Show buttons, the light, the sky and the sun flare
  are still as it set them (`GAME_LOOK`, `EDIT_LOOK`; the flare only on a map that has
  one). Where the panel is too narrow for a name and its key on one line, the key goes
  under the name.
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
  top: nearest first, never overlapping, named entities out to 2048 units and unnamed
  ones to 700 (brush entities too, doors and ladders, labelled at the middle of their
  box; not func_group / detail, nor unnamed lights and static props). Behind a wall they reach 512 / 350: past that a label shows only when the
  camera can see its spot (checked from 60% of that on, so it can fade): a sight line against the world's shown, solid, opaque brushes (`lblSeen`,
  `lblBlocked`; detail brushes count, clip and see-through ones don't, nor patches,
  terrain or brush entities), through a box tree over them and kept until the camera
  moves 4 units. Each label fades out over the last 40% of its own range (in sight or
  behind a wall) to nothing at its end. Selected entities are always labelled, fully. A path node with spawnflags
  names its highest one after its class, `info_pathnode [CORNER_RIGHT]` for COVER +
  CORNER_RIGHT (`nodeFlagTag`; one name, the more particular kind, so labels stay short),
  since its outline colour is otherwise the only sign. Modify's entities are labelled the
  same way, with a filled tab in front: **NEW** (amber) on an added one, **EDIT** (blue)
  on one of the map's that Modify has changed and draws instead of the map's marker.
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
- **Sun flare** (`J`, on at first): the game draws its sun only as a lens flare
  (`RB_DrawSun` is compiled out), and the page draws it the same way (`drawSunFlare`).
  - The flare shows while the view faces within the flare's `dot_min` of the sun and the
    sun is seen (`sunSeen`). Its brightness is `(dot - dot_min) / (1 - dot_min)`. The screen
    whitens by that brightness to the 4th power times `fullscale`. When the sun goes out
    of sight, both fade over `fullfade` ms.
  - Each flare is a square of ±`size` screen units, so it stretches with the window. It
    sits on the sun's place on the screen (`SunScreenCalc` of the point 128 units toward
    it), and its picture is added. The flare and the glare are drawn after the scene and
    `r_showsky`, unfogged, under the selection, lines and labels.
  - The sun is seen when the line from the camera 16384 units toward it first meets a sky
    face (`sunTrace`). The line meets the world's solid brushes, solid patches and the
    terrain, but not brush entities, models, static props or fences, and the Show buttons
    don't change it. In a .bsp it is looked for only from a leaf whose light list starts
    with the sun (`D.vis.sun`), from outside the map, or from anywhere when the map has no
    vis or no leaf lists the sun.
  - The direction comes from the worldspawn's `sunflaredirection`, else `sundirection`.
    The flare is the `global/lensflaredefs.txt` section that `sunflarename` names, `sun`
    when there is none. The build sends all of it as `D.sun`, or the reason there is no
    flare, which the greyed-out button shows.
  - The page draws only when something changes, so a fade starts when the sun was in view
    in the last frame drawn, and the view keeps redrawing until the fade ends.
- **Picking** renders face / entity ids into a 1-pixel target around the cursor, then
  finds the exact point on the plane or triangle under it. What the mouse is over gets an
  outline in the accent colour: a brush's edges (all of a brush entity's brushes), or
  for a model or marker its box, as the selection draws it in red; both are drawn after
  the Wire edges, so with Wire on the hovered edges show green. The game's sky is
  picked only where nothing else is under the cursor, as it is seen; a second pass then
  finds the nearest sky brush there.
- **Hide** (Backspace or the Hide button) and **Show all** (Shift+H) go on a stack that
  `Ctrl+Z` (or the Undo button beside Show all) unwinds one step at a time: a Hide shows
  those things again, a Show all hides again what it showed. Backspace hides an entity
  added in Modify too (selected in the view or its list), as its square does, and
  Ctrl+Z shows it again; **Delete** removes one, as Modify's Delete button does (map
  entities stay: Delete never takes anything out of the map).
- **The search box** (Find, `Ctrl+F`) matches entities and textures (`runFind`,
  `findTerms`). Its terms all have to match, and a term with `-` in front leaves out what
  it matches instead.

  | You type | It matches |
  |---|---|
  | `word` | any key or value containing it (or a texture name) |
  | `"exact"` | a key's value that is exactly that (or a texture name, whole or its last part) |
  | `$name` | targetname exactly `name` |
  | `key: value` | that key exactly that value, with `*` for any letters: `classname: info_*`, `#set: 2`, `texture: caulk`, `entity: 25` (the viewer's number), `entnum: 104` (the game's) |
  | `key:` | an entity that has that key at all |
  | `entity 25` | the viewer's entity 25 |
  | `( x y z )` or `origin: x y z` | an entity whose origin is exactly there |

  Textures are listed only when every term can apply to one (words, `"exact"`,
  `texture:`). An entity row in Results shows its targetname before its class, and its
  tooltip has the whole row (targetname, class, entity number, origin, hidden). A texture
  row's tooltip has its name, its uses and how many of them are hidden.
- **Results, Classes, Textures, Entities** (the tabs under Find): each tab's counts and
  hints sit above a line, and the list is a section of its own under it. A class row
  selects the class and opens (or closes) the list of its entities; a double-click leaves
  it open and flies there (a second click on the same row within half a second counts as
  one, since the first click rebuilds the list and the browser may not see a
  double-click). What is selected is green (an entity; a class or a texture once
  everything shown that it covers is), however it was selected: a click in the view, Enter
  in the search box, a row. Hidden entities (Hide, or a Show button off) are red, a class
  or texture with some of its users hidden yellow with the hidden count. Shift+click a
  row's coloured square to hide that entity or the whole class (again: show them; on the
  Hide stack, so Ctrl+Z undoes it); a Show button's hiding stays, and the message names
  the button. Shift+click a green row (in any of the four tabs) to deselect just that
  entity, class or texture and keep the rest selected (`deselectRow`); Shift+click a row
  that isn't green adds it to the selection.
  - **Textures**: a click selects everything shown that uses the texture (`texUse`): each
    world brush with a face in it, each brush entity, and each entity whose model draws it,
    such as a static prop's (`armchairposh` on mohdm1 is only on its nine armchairs).
    Shift+click a texture's square hides all of those, as Hide does (again: shows them).
    The count is the faces and model surfaces using it, as before.
  - **Entities**: the entities the game gives an entity number to, in that order, as
    `sv_showentnums` numbers them (`gameEnts`, so they follow the game cvars' g_gametype,
    skill, developer and sv_maxclients): "N real entities with entnums", each row its
    targetname, else `entity` and its number, with the number on the right when the name
    doesn't give it. The world (1022) isn't listed, nor an entity that removes itself as it
    spawns (misc_model, func_remove), whose number stays unused. A click selects the entity
    and flies there; the tooltip has its class, numbers and origin. Above them, greyed and
    not clickable, are the client slots `entity 0` to `sv_maxclients - 1`: entity 0's
    tooltip says "reserved for $player, or $player[1] in multiplayer", the others
    "reserved for $player[N] in multiplayer".
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
  shows when another entity shares the name. **Eye view** (after Same kind) shows for an
  entity with angles, a target to look at, or a player start: the camera flies to where it
  sees from, facing its angles (pitch, yaw, roll), else its target, else yaw 0. Player
  starts put the eye 82 units above the start (DEFAULT_VIEWHEIGHT); path nodes,
  waypoints, vehicle points and actors drop to the floor first (droptofloor, as the game
  stands them there) and put it 82 above that; spline paths, cameras and everything else
  see from their exact origin, as the game's cameras do. **Open door** (`O`) shows when a door is
  selected (Doors, below).
- **Entity boxes** (the `setsize` on the info card): for a `.bsp`, the brush model's
  exact bounds around its origin; for a `.map`, the bounds of the entity's brushes around
  its origin brush, `origin` key, or brush centre. Point entities use a `setsize` key,
  else the model's `.tik` setsize, else the model's own bounds, else the class box (a
  game-code class: MOHRadiant's 16-unit stand-in cube). A model entity's box turns with
  its angles where the game turns it (`boxTurns`): `EF_LINKANGLES` makes
  `CM_TransformedBoxTrace` rotate even a `setsize` box by `r.currentAngles`, and
  ScriptSlave sets it (script_model, script_object, script_origin and the rest), as do
  Vehicle and VehicleCollisionEntity; a `rotatedbbox` key or script line sets or clears
  it (`Entity::EventSetRotatedBbox`; the level script's `rotatedbbox` lines are read).
  Other classes (an Actor, an Animate) keep an unturned box, and the info card's "From"
  line says so when the entity is turned. A model's own bounds (no setsize anywhere)
  always turn with it. The card's `absmin` / `absmax`, Fly to, and the area / PVS links
  use the turned box's world bounds, as `SV_LinkEntity` does (`CalculateRotatedBounds2`).
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
  dark green, pink with a `targetname` key as written (MOHRadiant reads `$targetname` as
  any other key, so such a node stays green), flat cyan for the friendlynodes' `_color`. A path
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
- **Exploders** (`global/exploder.scr`): with an `exploder`, `explodersmashed`,
  `exploderchunk`, `exploderfire` or `explodertrigger` selected, Selection shows **Run
  exploder** and **Reset exploder**. Run plays the script's `explode` for the selection's
  `#set` (every set selected): each `$exploder` hides after its `#pause`, each
  `$explodersmashed` turns solid, and each `$exploderchunk` is thrown toward the
  script_origin it targets (`explodechunk`). Run greys out until Reset puts the set back
  as the level starts.
  - **Nothing is hidden at the start.** In game exploder.scr hides the smashed brushes and
    the chunks as the level loads; the viewer draws the map as the `.bsp` has it, so
    obj_team2's chunks are seen. The smashed brushes usually sit inside their exploder.
    Only the `$exploder` (a brush or a model, such as obj_team2's radio) and the chunks
    once they are done are hidden, apart from Hide (`EXP.hid`).
  - **A chunk** gets the way from its origin to its target as its velocity, the up part
    times 1.5. For 0.2 s it moves through anything (`MOVETYPE_PUSH`). Then `physics_on`
    makes it bounce (`G_Physics_Toss`): gravity 800, a box trace from its origin with its
    `mins` / `maxs` (`expTrace`, `CM_TraceThroughBrush`), overbounce 1.4, its sideways speed
    cut on each bounce, stopped on a floor below 40 units a second. It spins on its own
    axes: by random amounts, with its biggest spin about the way it is thrown, dying away
    over 10 to 24 frames from 0.5 s on. The first touch starts `moveitout`, which lowers
    it by its fall speed / 15 a frame for 48 frames, so it sinks into the ground and,
    below the floor brush, falls on through the void, as in game. It hides 10 s after its
    spin stops (the game deletes it), and Reset shows it again even if Hide had hidden it.
  - **What a chunk can hit:** the world's solid brushes (`CONTENTS_SOLID` and
    `CONTENTS_FENCE`, no clips), patches and terrain (thin prisms of their triangles), the
    `func_` brush entities, every `$exploder` still standing and each `$explodersmashed`
    its set has shown. Other `script_object`s are left out, because their scripts often
    make them notsolid. Doors are where the `.map` has them.
  - **Keys:** `#set` and `#pause` are script variables and the game reads them as whole
    numbers (`SpawnArgs::SpawnInternal` uses atoi), so m5l2a's `#pause .1` is 0. A plain
    `anglex` / `angley` key isn't a variable, so the spin stays random.
  - **Not shown:** the emitters (`$exploderfire`), sounds, `radiusdamage`, and a set going
    off again (`level.exploderrepeat`).
  - A chunk moves through `entPose` (shared with the doors), and `doorXf` / `movObj` give
    its current place to the selection, setsize box, label and r_showtris. The info card
    has an Exploder section.
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
- **Game cvars** (Display > "game cvars", below backdrop, or `` ` ``): the game's
  debugging cvars that a map can show, doing in the page what they do in game, in groups
  (Render distance: farplane fog and culling, What the renderer draws, Lighting,
  Entities, AI paths, The game the entities spawn for). A click on a row sets it (again: back to the game's default); the filter box is
  also the console (`r_showtris 2` then Enter, `r_farplane_color 1 .5 0` for a colour; a
  name alone tells its value and default). A row the map can't use is greyed out with the
  reason. The list's foot shows the camera's cluster and area, what is drawn from there
  (counted in every direction: the game also drops what is outside the view), and what
  each cvar that is set found; the cvars set are named beside the button and remembered
  (`r_lockpvs` aside: it locks where the camera is). The list's head counts them ("N set",
  or "all at default") beside a Reset button that sets every one back to its default
  (`resetCvars`, cg_weather first; the Model Viewer's list has the same button).
  `CVAR_DEFAULTS` / `CVAR_ROWS` in the page hold them.
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
  - `r_shownormals 1` (`.bsp` only) draws a white line 2 units long along the normal of
    each point r_showtris would draw, over everything (`DrawNormals`, `tr_shade.c`, which
    `RB_EndSurface` runs on every batch as it runs `DrawTris`). A face's points take its
    plane (`lightmapVecs[2]` as `ParseFace` copies it), a triangle soup's its vertex
    normals, a patch's the rows and columns `RB_SurfaceGrid` keeps, with the grid's normals
    (`MakeMeshNormals` on the finished grid, ported as `grid_normals` in mohaa_bsp.py); the
    build sends them for every point (`vn`, signed bytes) and each face's and soup's run of
    points (`si` 5 and 6). A model's vertices take their normal turned by their first
    weight's bone (`SkelVertGetNormal`, a static model's `pStaticNormal`; the model's `n`):
    an entity's lines are 2 world units (`RB_SkelMesh` scales the points, not the
    normals), a static prop's 2 of its own units, so its scale stretches them
    (`R_RotateForStaticModel` scales the matrix). Terrain has none: `tr_terrain.c` never
    fills them in. In game a face or patch fills its normals in only when its shader uses
    them (`needsNormal`: an environment map, `deformVertexes`, a dot `alphaGen` or `rgbGen`,
    `tcMod macro`), `needsLSpherical`, or there is a dynamic light in the scene
    (`RB_SurfaceFace`, `RB_SurfaceGrid`); otherwise its lines show whatever the batch before
    left in the tessellator. The page always shows each surface's own. The lines are made
    the first time the cvar is on, from where the doors are then, and a door that moves
    turns its normals with it.
  - `cm_noAreas 1` opens every area portal. Without it the level is as it starts: doors
    shut, except a `func_door`, `func_rotatingdoor` or `script_door` with spawnflags 1
    (START_OPEN) that leads its group, whose portal is open (flooded as
    `CM_FloodAreaConnections` does); Open door opens and shuts them (Doors, above).
  - `ai_showroutes 1` (also the **AI routes** button in Show, greyed on a map with no
    path nodes; with `ai_showroutes_distance` and `ai_fallheight`; the viewer starts
    the distance at 8200, where the game's default is 1000, since it draws that many
    without slowing down) draws the connections in the map's `.pth` as
    `DrawAllConnections` (`navigate.cpp`) draws them:
    green both ways, a red arrowhead one way, a red X on a node with none, a blue circle on
    a DONT_LINK node. Each node with a mark gets a tag saying what it means, the map's
    and Modify's new ones alike (`drawPathIssues2D`, from the same pass that draws them):
    "⚠ no paths" (orange, the X), "⚠ N one-way" (red, the arrowheads: the AI can go
    that way but not come back, a climb past `ai_fallheight`), and for the blue circle
    either "⊘ DONT_LINK" (blue: the node's own spawnflag 1, unlinked on purpose) or
    "⚠ duplicate of entity N: not linked" (orange: no such spawnflag, the game set it
    while loading because the node, dropped to the floor, lands on the very spot of an
    earlier one, `^~^~^ Duplicate node at (...) not linked` in `PathSearch::LoadNodes`;
    the earlier one is linked, so routes still end there; m1l1 has two `$friendlynode`s
    at one origin, entities 111 and 705). A node's tag sits under its class label (a new
    node's under its NEW label); within `ai_showroutes_distance`, past 350 units only in sight.
    Modify's own problems (48 paths, cut off, cell full) join the same tag. **AI errors**
    (SHOW, after AI routes; `AIERR`) shows or hides the tags that report a problem: no
    paths, one-way, own group of N, in the wall, and no angle (a CORNER_LEFT,
    CORNER_RIGHT, CRATE or LOW_WALL_ARC node with no "angle" / "angles": its special
    attack faces the node's yaw, `PathNode::GetSpecialAttack`, so it faces east; `nodeNoAngle`). It turns on and off with AI routes and
    can be turned off while AI routes stays on; DONT_LINK, duplicate, 48 paths and cell
    full always show. The `.pth` is `maps/<map>.pth` in the paks (else beside the file),
    unpacked (`CSVG` + LZ77, `lz77.cpp`) and read as `PathSearch::ArchiveLoadNodes` reads
    it (and, as the game, used only when the map_time in it is the .bsp's; else the paths
    are worked out here, `pathsStale`; turning AI routes on says in Output which), typed (the game's own files) or untyped (OpenMoHAA's); node i is the map's i-th
    `info_pathnode`, and a count mismatch is flagged. A path node's info card lists its
    connections.
    A map with path nodes but no `.pth` gets its paths worked out by the page the first
    time they are drawn, as the game does when it loads it (Modify, below).
  - `r_lockpvs 1` keeps the leafs marked from where the camera was (`R_MarkLeaves` stops);
    `r_novis 1` keeps every leaf. The server's marks (what it sends) and the renderer's
    are kept apart, so with the lock the entities still follow the camera.
  - `r_showsky 1` draws the sky box parts the game draws from here, in front of
    everything: the sky polygons in view projected onto a box round the eye and rounded
    out to quarters of a side (`ClipSkyPolygon`, `tr_sky.c`).
  - `r_farplane N` (with `r_farplane_color`, `r_farplane_nocull` and `r_farplane_nofog`)
    replaces the map's farplane distance, fog colour and culling.
  - `r_lightmap 1` shows the lightmap in place of the texture where the game does (a
    stage joined with the texture by `CollapseMultitexture`; `lmr` in the shader index),
    `r_lightmap 2` the lightmaps coloured by brightness, with the brightest value. The
    lightmaps are sent raw and brightened in the page (`R_ColorShiftLightingBytes`).
  - `r_light_showgrid 1`: the light grid points within 256 units, in their colour.
  - `r_showstaticbboxes 1`: a magenta box round each static model drawn from here (its
    .tik's bounds times its scale, turned with it).
  - `sv_showentnums 1`, `sv_showbboxes 1` to `8` and `g_entinfo 1` to `4` (with
    `g_entinfo_max`) number and box the entities within 1000 units as the game does
    (`Entity::DrawBoundingBox`, `Actor::ShowInfo`), counted in the order the game spawns
    them for `g_gametype`, `skill`, `developer` and `sv_maxclients` (the last group of
    rows); the world is 1022. An info card gives the entity number and radnum. An
    entity's box (`gameBox`) is its `setsize` key, else its .tik's setsize, else its .tik's
    bounds times its scale; an AI's is a standing player's, ( -15 -15 0 ) ( 15 15 94 ),
    which `Actor::EventStart` sets after the spawn args (rev 23).
  - `sv_showcameras 1` and `g_showflypath 1` draw the spline paths (`CreatePath`) of the
    cameras and of `info_splinepath` chains; `func_camera.tik` isn't in the game's files,
    so a camera is a wire stand-in.
  - `cg_rain_drawcoverage 1`: where each `func_rain`'s drops land, cut to the map
    script's `rain_min_dist` (512).
  - `ai_shownodenums 1`, `ai_shownode N` (with `ai_showallnode 1`) and `g_nodecheck 1`:
    node numbers, the nodes the game finds where you stand (a player box traced against
    the world's brushes, as `DebugNearestNodeList` / `DebugNearestNodeList2` do), and the
    `.pth`'s node check.
  - The cvars' lines are cut at the near plane in the vertex shader (`clipEnd`), since
    SwiftShader drops a line with one end behind the camera.
- **Remembered** per browser: theme, backdrop, display / filter choices, camera
  settings, and the camera position for each map (keyed by the map's path inside the
  paks, or its file name). The embedded pane runs WebView2 in private mode, so there
  they last only while the launcher is open.

## The game's lighting

With Show > Full Brightness off (the default), a `.bsp` is drawn the way the game lights
it. Everything comes from the `.bsp`; the light is never recomputed, only scaled down
while lights are turned off (Lights off, below).

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
- **Lights off** (Display, `0`) turns every light entity off, and Selection's **Turn
  off** / **Turn on** the selected ones; the map then looks as if those lights had never
  been in it.
  - It works on the light the game draws with: lightmaps (polygons, patches, terrain,
    brush entities), vertex-lit polygons, the static props' baked vertex light and the
    light grid colour of models lit by it. Coronas, flares and bright textures stay.
  - The `.bsp` keeps only the sum of every light's light, so the page works out each
    light's share of every lightmap texel and probe (`ltWeigh`), using the compiler's
    formula and its shadows (engine-notes, Baked light). On a map with sky faces, it
    works out the sun's and the sky's share too (`ltSun`).
  - A texel then keeps its ambient floor plus the rest of its light times the share
    still on (`FS_LTREL`), losing no more than twice what the lights turned off could
    have given there without shadows. With every light off, rooms go dark and only what
    the sun, the sky and `ambientlight` gave stays.
  - Probes are the props' vertices, the vertex-lit polygons' vertices and one per
    grid-lit model at its origin, relit the same way (`FS_LTPREL`).
  - The first time, every light's share is worked out once, with a progress line (and in
    the launcher a line in Output as it starts and one with the time when ready); after
    that a light turned off or on is one light's work, added or taken out (`ltApply`).
  - All of it runs on the graphics card in float textures (`EXT_color_buffer_float`), a
    few steps per frame. Each batch starts only when the card has finished the last (a
    fence).
  - The steps the card is working on are noted in the browser's storage. If the graphics
    driver resets, the message names them. The next press on that map only warns; another
    within 6 s tries again, one step at a time.
  - Not kept: a page always opens with every light on.
  - Greyed out on a `.map` page, which has no baked light (the tooltip says why), and on
    a `.bsp` without lightmaps or light entities.
- **Sun light** (Display, `-`, on at first) takes the sun's and the sky's light out of the
  same baked light when turned off, so open ground falls to what the lights and
  `ambientlight` give it; rooms the sun doesn't reach stay as they are.
  - The share left at a texel is the lights' still on, over all lights and the sun.
  - What none of the traced light explains (sky light under eaves, in deep trenches) goes
    with the sun. A texel keeps no more than twice what the lights still on could give
    there without shadows.
  - With every light off as well, only the ambient floor is left.
  - It works with Lights off and Turn off / Turn on in any order. The first time costs
    what the first Lights off does; after that it is only the relight.
  - The sun flare (`J`) is separate. Not kept: a page always opens with the sun on.
  - Greyed out where Lights off is, and on a map without sky faces or a sun colour in its
    worldspawn (m6l3c, m6l3d).
- **Sky** polygons are the `.bsp`'s own, drawn with the sky box as described under The
  page.

## Decals and leak trail

- **Decals** (Display, `=`, on at first) draws the map's permanent decals: signs,
  cracks and numbers placed in MOHRadiant and saved in `maps/<stem>.dcl`, which the game
  loads with the map (`R_LoadPermanentMarks`, renderergl1/tr_marks_permanent.c).
  - The file is `dclHeader_t` ("DCL ", version 1 or 2, checksum, decal and fragment
    counts; version 2 then the `.bsp`'s 32-byte map time), the decals (124 bytes each:
    shader, origin, projection, radius, scales, rotation, colour, lighting), then the
    fragments they were cut into (76 bytes: shader, fog number, decal, vertex count; then
    24-byte `polyVert_t`s: xyz, st and the lit colour). The per-model and per-leaf
    fragment lists after them aren't read.
  - Each fragment is drawn as the game draws it: a fan of its vertices, its shader's
    picture times the colour the file keeps (the decal shaders use `rgbGen vertex` and
    `alphaGen vertex`), blended, pushed toward the camera (`polygonOffset`) and without
    writing depth. With Full Brightness, or on a `.map` page, the colour is white and
    only the alpha is kept. Lights off and Sun light don't change them.
  - Not pickable: a click goes to the wall under the decal.
  - The game skips a version 2 file whose map time isn't the `.bsp`'s (outside edit
    mode); the viewer draws them anyway, as retail maps (version 1, no map time) have
    them.
  - Greyed out, with the reason in the tooltip, when there is no `.dcl` in the paks or
    beside the file. m2l1: 22 decals in 25 fragments.
- **Leak** (Display, `P`, on at first) draws the leak trail the compiler writes when the
  map isn't sealed: `<stem>.lin`, one point a line. q3map's `LeakFile` starts at the
  outside node and writes the middle of each portal on the shortest way in, then the
  origin of the entity it reached. So the first point is at the opening the void comes
  in through, and the last one is the entity.
  - Drawn on the 2D overlay, so it shows through walls: a red line with a dark edge,
    yellow dots at its points, a red ring at its start ("leak: starts in the void"), a
    yellow one at the entity ("leak: reaches <class> (entity N)") and a light blue one
    where the void gets in ("leak: gets in here, fix this", with the gap's width when it
    is under 64 units). A click on a point or a ring opens the card at that point (on the
    entity's it selects the entity too); the stats under the map's name have a "leak
    trail: the map isn't sealed" line that opens it as well.
  - **Where it gets in** (`leakFix`): the first point is only just outside the map, so
    the gap is found from the brushes. The ones that seal a map for the compiler are the
    world's (and func_group's) structural brushes that are solid and not see-through
    (`surfaceparm trans` / CONTENTS_TRANSLUCENT): detail brushes, patches, terrain,
    clips, water don't. Along the trail from its start, every 32 units, rays go 26 ways
    (`leakRay`, against those brushes only); the last sample from which one of them
    leaves the map's box is where the trail gets in. From there, along that way out, the
    gap is the place it passes closest to those brushes (the free width across it, the
    two other axes). When the void is in sight from most ways (18 of 26) at the entity
    itself, the entity is out in the void.
  - From there toward the void: if the game collides with something first that the
    compiler doesn't take as a seal (terrain, a patch, a detail / clip / see-through
    brush, a brush entity: `leakWhatAt`), the void comes in through that, and the card
    names it with Select it and says to put caulk under or behind it. Else the opening is
    the last place along that way still between sealing brushes (across one of the two
    other axes, within 1024 units): past it is the void. The gap is measured at its
    narrowest within 64 units of there; under 2 units, or with sides at fractions of a
    unit, it is a hairline crack off the grid.
  - A `.bsp` with vis data didn't leak when it was compiled, so its `.lin` is left over
    from an earlier one (found in another pak, or shipped by mistake): the card says so.
  - Checked: on sealed maps no player start or path node sees the void through the
    sealing brushes (1,270 in obj_team2, mohdm7, m1l1, m3l1a, m5l1a, m6l3e and
    Tirtagen-Kechtat). Leaking: BSunrise3-3 (0.39-unit crack), BSunrise3-3a (1.33-unit
    crack), pleviathan (8-unit slit at its -x edge), SiDvFinal (8-unit gap), V2revamped
    (an opening toward +y), NormandyBridge_V1 and abydos (under terrain with no caulk).
  - The card, in sections: **Found** (what a leak is and does; where the trail starts,
    gets in and ends, each with Go and Copy), **Where it gets in** (the gap's width along
    each axis it is shut on and between which coordinates, which way the void is, the
    brushes either side with Select them, how far along the trail the void stays in
    sight, and anything the game collides with there that the compiler doesn't take as a
    seal), **Recommended fix** (under 1 unit: a hairline crack, brushes off the grid,
    snap them, Ctrl+G in MOHRadiant, or overlap them; under 16: stretch one to meet the
    other; else a missing wall, floor or sky to close with a structural brush; caulk
    behind terrain and patches; the entity out in the void: move it in), **Reading the
    trail** (q3map's BSP cells: the trail is the fewest cells from outside, through the
    middle of each opening between two, hence its straight runs on the 1024-unit lines
    and its turns; the entity at its end is only the first, by number, the void reaches)
    and every point (up to 200 listed; Copy all has them all; the start, the gap and the
    entity named). Go flies to a point looking along the trail from the next point's
    side, so the camera isn't put inside a wall.
  - Beside a `.map`, a `.lin` older than the `.map` is flagged: the map was saved after
    the compile that leaked, so the hole may be sealed already. (Beside a `.bsp` the
    dates say nothing: a leaking compile writes the `.bsp` after the `.lin`.)
  - A leaking `.bsp` has no vis data, which the card notes when it applies.
  - Greyed out when there is no `.lin`. NormandyBridge_V1: 3 points, from below the
    terrain up to a `light`. BSunrise3-3: 32 points, in through a 0.39-unit crack along x
    between two caulk floor slabs (one ends at x 318, the next starts at 318.39), open to
    the void below, then 2,272 units along it before the trail turns in.
- `.min` (the loading bar's resource list, written by `UI_EndLoad`) and `.vis` aren't
  used.

## Weather

**Weather** (Display, `Y`; the game's `cg_rain`) makes the map's rain or snow as the
client makes it (cgame/cg_nature.cpp `CG_Rain`, cg_beam.cpp), with the settings in the game
cvars' Weather group (`drawWeather`, `wxRain`, `wxFrame` in the page).

- **Where.** Only in the map's `func_rain` boxes (the editor's Rain brushes), and only those
  the client has: a box in a cluster the camera's PVS sees (`gvSent`; every box on a `.map`
  page). The box is its brush model's bounds. `cg_rain_wholemap 1` (not a game cvar) adds
  the whole map's box, so a map without rain can be tried.
- **From the sky** (the viewer's own addition): a map with no `func_rain`, or with every
  one hidden with Hide, gets its weather from the sky instead (`wxSkyMode`). The drops
  start in the same square round the viewer, each under the highest sky brush whose
  footprint covers its spot, and fall to the first solid thing under that (a roof, the
  ground or a lower sky brush). The test is a point trace through the chunks' solids
  (`wxCol`, kept per 16-unit column). A spot with no sky brush above it (a tunnel, or
  mohdm7's covered streets) gets none, and the drops never fall through a roof. The
  Rain display filter doesn't count: only Hide does.
- **A map that sets no weather** (no rain density from its script, as on every map
  without func_rain) starts at `cg_weather rain` and the rain preset's values, so Weather
  shows something. `cg_weather map` still gives the map's own, which is nothing; Reset
  goes back to rain.
- **Each client frame** (`com_maxfps` a second, the game's default 85, run on the page's
  clock), each box cut to the square `rain_min_dist` round the viewer starts
  `sqrt(width x depth) x density / 200` drops (at most 4096), at random places in that
  square (those outside the circle skipped).
  - Allied Assault 1.11 (`com_target_game 0`, the default): at the top of the box, living
    as long as they take to fall to its bottom.
  - Spearhead / Breakthrough 2.0 and OpenMoHAA (`com_target_game 1` / `2`): anywhere in the
    box's height, at most 10 s.
- **A drop** is a beam from its start to a point at the bottom of the box a random 0 to
  `slant` over in x and in y (the same way, so the rain leans toward +x +y) plus the wind
  (`vss_wind_x` 8, `vss_wind_y` 4), at `speed` plus a random 0 to `speed_vary`. It is drawn
  as a streak `length` long and `2 x width` wide facing the camera sideways
  (`CG_BuildRendererBeam_Fast`); the snow shaders turn it into a square facing the camera
  (`deformVertexes autoSprite`). Drops go through roofs: nothing stops one before the
  bottom of its box, as in game.
- **MAX_BEAMS.** All of them share the client's 4096 beams; with none free a drop isn't
  started. Slow snow from a high box fills them before the first flakes land, which gives
  the clumps and gaps of the game. The list's foot counts the beams falling, the drops
  started in the last second and those not started for want of a beam.
- **Random numbers** are the game's: `rand()` (MSVC's) once a box a frame, then the
  client's own `214013 x + 2531011` step on the 15-bit value, so the patterns it makes
  are the game's too.
- **Shaders.** One per box per frame: `cg_rain_shader`, or with `cg_rain_numshaders` N its
  name (a digit it ends with dropped, as OpenMoHAA does) with a random 0 to N - 1 after it.
  The game has `textures/rain` (a streak, added at .2) and `textures/snow0` to `snow11`
  (flakes, added at .5; scripts/effects.shader); the build puts all of them in every page,
  with each shader's `rgbGen constant`. An added shader fades to black in the fog.
- **The map's settings** are the defaults of the cvars: what its script sets as
  `level.rain_*` or with `setcvar "cg_rain_*"` (`LevelScript`: m6l1a's snow, m6l2a's), else
  the client's (density 0, speed 2048, speed_vary 512, slant 50, length 90, min_dist 512,
  width 1, textures/rain). A map that runs global/weather.scr (m5l1a, m5l1b) changes its
  density as it plays (a storm cycle): the viewer starts at that script's middle setting
  (width .4, min_dist 512, density 3, slant 50). They aren't kept for next time.
- **cg_weather** sets all of them at once from weather.scr's presets: snow, snow_fast,
  blizzard, hail, snow_original (the game's m6l1a snow), rain, drizzle, monsoon,
  rain_original (the client's defaults), off, and `map` for the map's own. The game's own
  console has no `cg_rain_*` cvars (OpenMoHAA reads only the level's settings); in the
  viewer they stand for those settings, as weather.scr's cvars of these names do.
  Drops already falling keep the shader, length and width they started with (as the
  game's beams do); a change to those cvars or to cg_weather only shows on new drops.
- `cg_rain_drawcoverage` draws the same boxes, cut to `cg_rain_min_dist`.
- **Thunder** (`cg_thunder`, a game cvars row under `cg_rain`; not a game cvar, off at
  first) is global/weather.scr's lightning without its sound (`thTick`): every
  `level.thundertime` + `randomint(level.thundertime x 1.5)` seconds one of its three
  flickers at the script's timings (flash 0.2 s, off 1 s, flash 0.1 s ...), then
  1 + `randomfloat(2)` seconds. A flash is `r_fastsky 1`: no sky, the screen cleared to the
  fog colour where the map has a farplane, else to 0.5 0.5 1 (`RB_BeginDrawingView`), with
  the farplane colour 0.9 0.9 0.9; the map's `$weatherF` entities (m5l1a's 15 lit windows)
  are hidden while thunder runs and shown in a flash. `level.thundertime` is 20 at first and
  follows the storm (20, 8, 6, 4): the viewer takes the map script's, else 6 on a map that
  runs global/weather.scr (its middle storm), else 20.
- **Moving leaves.** A model surface whose shader has `deformVertexes wave` or `flap` (the
  trees' leaves: `flap t 24 sin 0 3.5 0 0.2 1 0`) moves in the model shader by the game's
  time, along its vertex normals (`RB_CalcDeformVertexes`, `RB_CalcFlapVertexes`, with the
  engine's wave tables; a flap moves every vertex in step, as the engine does). A static
  model has no entity, so its wave's base, amplitude, phase and frequency are scaled by
  `r_static_shadermultiplier0` .. `3` (Weather group of the game cvars; the game's default
  1); a model with an entity keeps its shader's. global/weather.scr sets
  `r_static_shadermultiplier1` each second to `(raindensity + 1.5) / 2.5`: the viewer starts
  it at 1.8 (its middle storm) on those maps. While a moving model is drawn the view is
  redrawn 30 times a second. The build reads the deform into the texture entry (`dv`;
  `INDEX_VERSION` 9). `r_static_shaderdata0` .. `3` only stand in for `fromEntity` values,
  which no deform here uses.
- No sounds and no splashes (the client's `RainTouch` is for temp models, not these
  beams).

## Level script

The game runs `maps/<map>.scr` when the level loads. The viewer doesn't run it as the game
does (no waits, no threads side by side, no events): the build walks it once, top to
bottom (`LevelScript` in mohaa_map_view.py), keeping what it can work out without the
game, and the page adds what it spawns.

- **Which files.** As the game finds them: a loose file in the folder the paks are in
  (`main/maps/<map>.scr`) before the paks. The file beside the one opened comes first
  (`NormandyBridge_V1.bak` reads `NormandyBridge_V1.scr`). The map scripts it runs
  (`exec`, `waitexec`, `thread`, `waitthread` with a `.scr` path, not `global/`) are read
  too, up to 40 files.
- **Spawned entities.** `spawn <class or model> [key value ...]` (ScriptThread's
  `SpawnEntity`), with or without `local.x =` / `level.x =` in front. A model path
  (`models/human/...`, `.tik`) gives the entity that model and the `.tik`'s path as its
  class. The lines that follow give the same entity its `origin`, `angles`, `angle`,
  `targetname`, `target`, `model`, `scale`, `setsize` or `spawnflags`, as
  `<var>.origin = ( x y z )`, as the command form `<var> origin ( x y z )`, or through
  its `$targetname` or `$( expression )` (`$("fhe" + local.q).target = ...`).
- **The map's own entities**: a line setting the `target` of one of them (a map node
  joined to the script's) changes that key in the page; its info card has a "Changed by
  the level script" section. Other changes to the map's entities aren't followed.
- **Control flow.** The script is read as a tree (`_parse`): `{ }` blocks, `for`,
  `while`, `if` / `else`, `switch` (its cases read once), statements ending at a line
  break, a `;` or a brace.
  - A `for` or `while` runs as long as its condition can be worked out, up to 4096 turns
    (`for (local.q = 1700; local.q <= 1715; local.q++)` runs 16 times with `local.q`
    set), else once with its counter unknown, and what it changes is unknown after it. A
    `while` whose condition nothing in it changes (`while (1)`, a wait loop) runs once.
  - An `if` takes its branch when the condition is known; else both are read, and a
    variable the two leave different is unknown after it. A condition with a call in it
    (`getcvar(x)`) is unknown.
  - Lines read inside a loop note the counters in the card (`// local.q = 1703`).
  - A `while` with a `wait`, `waitframe` or `waittill` in it (respawn waves, watcher
    threads) runs once: it goes by the game's clock.
  - `break` and `continue` end the loop they are in, or go on to its next turn. Inside a
    `switch` a `break` only ends the case. Under an `if` the viewer can't decide, a
    `break` may or may not happen, so the loop goes no further and its counter is unknown
    afterwards. Before rev 54 these were read as plain statements, so a path walk such as
    `for (local.n = 1; local.n <= 1025; local.n++) { ... if (local.tent == NULL) { break } }`
    ran all 1025 turns every time.
  - A label run again and again (every actor's AI threads: path walks, sight checks,
    dialogue) is skipped once it has run 8 times without spawning anything new, or setting
    a target, cvar or `$world` line (`LABEL_IDLE`). A label that keeps spawning new things
    (a waypoint thread called hundreds of times) keeps running.
  - At most 400,000 statements are run in all, and one line spawns at most 1024
    entities; the build log says so if a script hits the first.
  - The m3l1b remaster script (1.36 MB) used to stop at the limit after 14 s with 130
    entities placed. It now finishes in 1.6 s with 4228 placed (3740 of them
    info_waypoints). The retail maps place the same as before.
- **Threads.** Each file is split at its labels (`bipod local.exists local.origin
  local.angles:`). A label run by name (`thread x`, `waitthread x`, `exec file.scr::x`,
  with or without an entity in front: `$mg42 thread bipod 1`, `local.gun thread bipod`)
  is read when it is run, with that entity as `self` (else the caller's own) and the
  arguments in its parameters (`NIL` for those not given), so `self.origin`,
  `self.angles`, `self != NULL`, `self.origin += ( 0 10 0 )` and `local.entity.origin`
  work. A label run several times is read each time (a bipod under each gun). Labels
  nothing runs by name are read once on their own, with `self` and their parameters
  unknown. A thread doesn't run itself again (recursion), and calls nest at most 24 deep.
  What a `thread` or `exec` (not `waitthread` / `waitexec`) does to `level.` variables
  doesn't reach its caller: in game it runs beside it, later (a death thread lowering a
  wave's counter would otherwise make the wave loop run on).
- Entities a thread run several times spawns the same, in the same place, are drawn
  once.
- **Values** are worked out where they are plain: strings, numbers, vectors, arithmetic
  (`+ - * / %`), comparisons, `&&`, `||`, `!`, `++`, `--`, `+=` and the like
  (`"wp" + 1`, `$org.origin + ( 0 0 64 )`), `local.` / `level.` variables (a thread's own
  `local.`s end at its label; `level.`s carry over), `$name` and `$(...)` as entities
  (`NULL` when the map and the script have none of that name), and `$name.origin` /
  `.angles` of a map or script entity. What only the running game knows (a thread's
  parameters, `self`, `getcvar`, a random number) stays unknown.
- **In the page** (`scriptEnts`): the entities with an origin are added after the map's
  own (`MAP.nMap` is where the map's end), marked `C_SCRIPT` on top of their own kind, so
  they are drawn, labelled, linked (a waypoint's `target` chain), found, listed and
  selected like the map's. **Show → Script ents** (`Ctrl+E`) hides them all. A trigger
  among them with a `setsize` keeps a marker of its class's size (`X.mbox`, `markerBoxOf`),
  and **Show → Script trigs** (`C_SCRTRIG`, on by default, off in the In-game look)
  draws its volume as a see-through box in the trigger green with its edges
  (`drawScriptTrigs`, tinted with the selection's colour when selected). Its sides are
  clickable, as a trigger brush's are (`pickScriptTrigs`, in the pick pass), and select the
  whole trigger; its selection box and info card give the whole setsize. The reader keeps the script's own fields of an entity
  (`local.t.setsize1 = ( ... )`, `LevelScript.fields`), so a later
  `local.t setsize local.t.setsize1 local.t.setsize2` gets its values. Their info
  card has a Level script section with the spawn line and the lines that placed it, and
  any key it couldn't follow. They have no entity number (the game gives one as the
  script runs), aren't counted in the map's real / simple / static counts, and aren't
  `.pth` nodes or static props.
- **The script card**: the map's stats line ("level script: N entities placed, R real
  placed, M not, K setcvar", under the map's title; real ones are those the game gives an
  entity number, not waypoints and other simple classes) opens it: the files read and
  where, the placed entities by class (links), the ones not placed with their line and
  why, the map entities whose target it sets, every `setcvar` (name, value, line; Copy
  gives them as lines) and the `$world` lines (farplane and the like, listed once per
  line, not applied). **Open .scr** (between Copy and X) and each file's **Open** open the
  script in the launcher's text editor (a pak's copy is extracted first); in a browser
  they copy its path.
- Checked on retail m3l1a (70 of its 76 spawns placed, by `$name.origin` of the map's
  spawn points; its fog lines in `if (getcvar(...) == "1") ... else ...` all listed), on
  the waypoint chain `$("fhe" + local.q).target = $("fhe" + (local.q + 1))` in a `for`
  loop (each waypoint gets its target, the last none), on 4000 waypoints in 250 such loops
  (0.4 s), and a test script with an `info_waypoint` loop, script models, a
  `script_origin` placed from another one, an actor and a spawn inside a `for` loop
  (listed as not placed).

## Modify

The **Modify** section, above Find, adds entities to the map and saves a copy of it. Its
main use is adding AI path nodes and seeing the AI's routes change as they are placed.

- **Adding.** Pick a class from the class list (`info_pathnode` first, then every point
  class the entity definitions know and every class in the map, each with how many the
  map has; it opens beside its button with a search box, as the Model Viewer's attach-to-
  bone list: every typed word must appear, the arrows move, Enter or a click takes one) and press Add, then click anywhere on the
  map: the entity goes where the click meets it (a path node 16 units over the spot, as
  the game drops it to the floor from 36 units up; anything else with its box's bottom
  on it). While placing, a white outline follows the cursor; Esc or Add again cancels.
  **Move** makes the selected new entity follow the mouse again until a click puts it
  down (Esc or Move again cancels); Move and Trim origin each grey the other out while on.
  New entities look like the map's own markers of the same keys (a path node:
  MOHRadiant's 16-unit dark green stand-in, inside out with a targetname, its
  spawnflags outline, drawn by the markers' own shader, which follows "spawnflags" as it
  is typed; a selected one gets a yellow box round it), but see-through until the saved `.bsp` is opened, and fainter
  while edited, moved or trimmed; with an angle, a white line along their yaw. They stay out of the map's own lists and cvars
  (entity numbers, Find), and a click in the 3D view on one, nearer than the map under
  the cursor, selects it in Modify's list. As in the Find lists, Shift+click the selected
  (green) name deselects it and Shift+click a row's square hides / shows it (its name in
  red while hidden; hidden is only how it is drawn, its AI routes stay). Ctrl+Z undoes a hide or
  show. In the 3D view Shift+click on the selected new entity deselects it, as Esc does
  (before it closes the map), and so does a plain click on anything else (a brush, a
  static prop, the sky), unless it is being edited, trimmed or moved; Ctrl+click opens its card. N (More info) on a new entity
  opens a card of its own: not saved (no entity number until the saved map loads), its
  origin, box and spawnflag names, for a path node the number the saved map gives it
  (after the map's nodes) and its links both ways, its class's description, and its
  parameters in a box that applies what is typed (its routes follow). Eye view puts the
  camera where it sees from, by the rules Eye view has for the map's entities
  (`eyeViewFrom`: a node, a player start or an AI 82 units above the floor under it,
  facing its angles, else its target, else yaw 0); Fly to (also a click on its row once
  it is selected, so a double-click on the row), Delete. Hotkeys: Alt+M Move, Alt+T Trim
  origin, Alt+E Edit parameters, Delete; each button's tooltip names its own.
- **The map's own entities.** Selecting one of the map's point entities (a path node, a
  player start, a script origin...; not brush entities, static props or what the level
  script spawns) gives it a row too, with a hollow square and its entity number ("#251
  map"); new ones have a filled square and "new". Edit parameters, Move, Trim origin and
  Eye view work on it the same way. Once its keys differ from the map's the row says
  "changed" (and stays when something else is selected), the map's own marker is hidden
  and it is drawn see-through where it now is; Restore puts back the map's keys. A
  changed `info_pathnode` (node k of the `.pth`, the map's k-th) has its links worked out
  again, both ways, as a new node's are, and the `.pth`'s links to and from it are left
  out; a node whose classname is changed away from `info_pathnode` loses its links (and
  gets them again if changed back), once Edit parameters is closed.
- **Putting one down** (Add, Copy, Move) selects it: a new one lets go of the map's
  selection, and an open More info card (N) turns to it (`modPlacedSel`).
- **Edit parameters** (Alt+E) opens a box, which moves by its title bar
  and stays where it was left, with the entity as
  the `.bsp`'s entity lump holds it, `"key" "value"` lines in `{ }`. What is typed applies
  a moment later when it reads (an error says why it doesn't, with its line: one
  `"key" "value"` pair a line, every quote closed on its line, no { or } in a key or
  value; the game would read a quote left open on across the lines that follow): origin, angles, spawnflags,
  setsize, a model the page has (its size), classname. Undo and Redo step
  through the changes made since the box opened (Ctrl+Z, Ctrl+Y; greyed when there is
  none), each pause in typing one step; Done (Esc), at the bottom right, keeps it. Light isn't worked out for new entities.
- **Trim origin** stops the camera (keys, drag and wheel); W A S D or the arrows move the
  entity along the map axis nearest the way the camera faces, Space / C up and down, one
  **trim step** (1 to 50 units) a press. Arrows round it show the ways, white, red while
  it moves that way. Esc or T stops.
- **Limits.** The game stops a map past 1024 entity slots (maxentities; the world and
  "none" keep two and the client slots come first: 1 in single player, sv_maxclients in
  multiplayer; "Level::AllocEdict: no free edicts") or 4096 path nodes (MAX_PATHNODES,
  "Exceeded MAX_PATHNODES!"). Modify counts real entities (the map's, the real ones its
  level script spawns, and its own new ones and changed classes; `modLimits`) and path
  nodes: Add and placing are refused past 1021 real entities (one player) or 4096 path
  nodes, a flash warns within 64 (96 in multiplayer) or 200 of them, and the status line
  gives both counts, yellow near and red past. The stats' real and simple tooltips say
  the same with the map's own counts. Other simple entities have no fixed limit.
- **Path problems** (`paIssues`), for Modify's new and changed path nodes, as the game
  meets them when it builds and walks the paths: 48 paths to check (NUM_PATHSPERNODE:
  "^~^~^ 48 paths per node at (...) exceeded", the node linked no further, and
  g_nodecheck 1 stops the level with "Node check failed"), a full 256-unit cell
  (PATHMAP_NODES 128: "^~^~^ PathSearch::AddToGrid: Node overflow at ( x, y )", the node
  left out of it), no path (nothing within 384 units it can walk to, or only drops deeper
  than ai_fallheight, 96: ai_showroutes's red X) and nodes cut off from the map's others
  (an AI sent across gets "^~^~^ Path not found", which g_patherror 1, the default,
  prints). The map's own nodes the new ones push past 48 are named too. Each is an
  orange tag over the node in the view, a line on its card (with the rules: 384 units,
  48 a node, 128 a cell, drops past ai_fallheight not taken and shallower ones one way),
  a line in the launcher's Output, a flash when it first appears, and a count in the
  status line (yellow; its tooltip lists them). Changing ai_fallheight works them out
  again, as the game's drawn routes and its path search follow it.
- **Make path** sets the selected entity's `"target"`: a note in green says to click the
  entity it should point at (a new one or one of the map's), which must have a
  targetname: the target is set to it. One without is refused, with why (give it a
  `targetname` in Edit parameters first); the selected entity needs none.
  The link is drawn as the map's are (Links, 7), with its arrowhead, and the clicked
  entity is selected after, so Make path again goes on along the path: `info_waypoint`,
  `info_splinepath`, `script_origin` chains. Esc or Make path again cancels.
- **Facing.** A new entity of a class that faces a way (most of the map's own of that
  class carry an angle; with none in the map, player starts, actors, turrets, vehicles)
  is placed with an `"angle"`: the camera's yaw to the nearest 45 degrees. Its facing
  arrow is drawn as the map's (Arrows, 5).
- **Grid** (+; Display's buttons, after Decals): on, a see-through grid of MOHRadiant's
  grid sizes is drawn round Modify's moving or selected entity, else round the first
  surface the camera looks at (a trace straight ahead, a little this side of it). Under
  the backdrop: a button picking its planes, in turn **Grid XY** (one flat plane, the
  default), **Grid XZ** and **Grid YZ** (one upright plane) and **Grid all** (the whole 3D
  lattice), then a slider of the sizes (1, 2, 4 ... 512; { and } step it); beside the
  backdrop, its colour (cyan by default; Default resets both). A single plane is laid on
  the grid line nearest the point on the camera's side of it (so on a floor it is just
  above it), 8 to 24 cells each way; the lattice 6 to 12. It fades with the distance from
  its centre and is drawn only in front of the map's surfaces, so nothing shows through
  floors and walls. Lines on multiples of 64 (or 8 grid sizes) are brighter, those through
  ( 0 0 0 ) brightest; the centre's coordinates and every few lines' values along the
  plane's axes are written beside them, unless a floor or wall is in the way. Add and Move
  snap the origin to the nearest corner, a grid size higher when the nearest would put
  the entity's box into the floor. Trim origin keeps its own trim step. On / off, planes,
  size and colour are remembered (`mohaaMapViewerGrid`).
- **AI routes.** A new `info_pathnode` joins the paths whenever it isn't being edited or
  trimmed. Its links are worked out as `PathSearch::CreatePaths` makes them
  (`navigate.cpp`): dropped to the floor (`droptofloor`, a 31 x 31 box 36 up and 2048
  down); a node at the same spot as an earlier one is a duplicate and gets DONT_LINK (a
  blue circle); otherwise it is filed in the four 256-unit cells round it and linked
  with every node of the 3 x 3 cells about each end (at most 48 links a node, 128 nodes a
  cell) that is less than 384 units away across the ground and that `CheckMove` reaches:
  a 31 x 31 x 94 box walking at 150 units a second in 0.1 s steps (at most 200) through
  the AI's movement code (`MmoveSingle`, `g_mmove.cpp`: sliding along walls, stepping up
  18 units, falling at gravity 800), stopped by a wall it can't pass, a fall over 1024
  units, or arriving more than 94 units above or below the other node. The fall on the
  way is the link's fall height (`ai_fallheight` hides it). The map's own links come from
  its `.pth`, and each new node gets its links to its neighbours and theirs to it, the new
  nodes numbered after the map's, as they will be in game.
  - **Collision**, as the game's traces: brushes whose own contents (from the `.bsp`'s
    brush, `D.bsp.bcont` where it differs from the first face's) are in `MASK_PATHSOLID`
    (solid, monsterclip, fence, not playerclip); movement traces see the box as a
    capsule on brushes (`CM_TraceThroughBrush` with `sphere.use`) and as a sphere on the
    terrain (`CM_TraceCylinderThroughTerrainCollide`), `droptofloor` sees the terrain by
    the box's four bottom corners (`CM_TracePointThroughTerrainCollide`); the terrain's
    collision squares are built as `CM_GenerateTerrainCollide` builds them. Patches are
    facets seen from the front. Brush entities count except doors (`CreatePaths` unlinks
    them), triggers, `func_rain` and `func_ladder`, exploder chunks and smashed pieces
    (`global/exploder.scr` makes them notsolid as the level loads), script objects made
    only of `common/trigger`, and the map's entities the level script makes `notsolid`
    before `level waittill prespawn` (`$x solid` / `notsolid` lines, read by the level
    script reader).
  - **Checked against the game's own `.pth` files**, every node pair worked out again:
    m3l1a 850 of 850 links, m2l2b 889 of 893 (1 extra), m6l3e 760 of 768, m5l1a 3085
    of 3114 (16 extra), m6l2a 7532 of 7544 (48 extra), m5l2a 11668 of 11836, m1l1 6396
    of 6517, m3l2 23759 of 24053 (14 extra); fall heights agree on 94 % (m5l2a) to 99 % of the links found.
    The whole map takes 0.3 to 11 s in the page; a new node, a few dozen pairs.
- **Saving** writes the changed map entities too. Save as .bsp asks the launcher where to write a copy of the `.bsp` (never
  over the file the map came from, nor over a file Save as didn't write): every lump but
  the entities is copied byte for byte, the entity lump with the new entities after the
  map's goes at the end of the file (with changed entities, the whole lump written again
  from its entities: each one found by its entity number, checked by its class and old
  origin, else the only entity with them), and worldspawn gets a new `"map_time"`, so the game
  rebuilds the `.pth` instead of loading the old one (`PathSearch::ArchiveLoadNodes`
  compares it). The new file is read back and checked; more than 4096 path nodes is
  refused. A map from a pak is copied out of the pak. A new file name is a new map: the
  game runs `maps/<newname>.scr` with it, so the map's script needs copying or renaming
  (the launcher's Output says so). Save as .map writes the `.map` with the new entities
  added. Copy puts the new entities on the clipboard as entity-lump text. **Unsaved
  changes**: when Esc gets past its last layer and would close the viewer while Modify has
  new or changed entities that no Save as wrote (`modUnsaved`: what Save would write,
  compared with what the last successful save wrote, `MOD.savedKey`), the page sends
  `mohaa-close-ask` instead of `mohaa-close`, and the launcher asks (`MapApp._close_ask`,
  `_unsaved_dialog`, in the launcher's dark / light look or the system's with "Use old
  popup windows"): **Save as .bsp** (greyed out for a map opened from a .map), **Save as
  .map**, **Discard changes**, or **Cancel** (Esc, the window's X; Cancel has the focus).
  A Save as closes the viewer once the file is written (`modSaveThenClose`); cancelling
  its file box keeps the viewer open (`modSaveCancelled`). In a browser the page asks with
  the browser's own box. Outside the launcher, Save as .map downloads the file and
  Save as .bsp isn't available.

## Simulate

Phase 1 flies a model along an `info_splinepath` path the way a script's `followpath`
moves a `script_model` (`ScriptSlave::FollowPath`, `CreatePath` and `FollowingPath` in
fgame/scriptslave.cpp; `BSpline` and `SplinePath` in fgame/bspline.cpp). Later phases are
to run actors along `info_pathnode` / waypoint / `script_origin` chains and play an actor's
cover and corner animations at a node.

- **Where.** Selecting an `info_splinepath` (the map's, or one Modify added) shows the
  SIMULATE section between SELECTION and CAMERA (`simSect`), with **Simulate** and
  **Reset** at its top, then the path's first and last node, how many, what
  ends it, how long it takes in game time, the model and the playback speed. The section
  stays while a simulation runs, whatever is selected (`simPanel`, called from
  `updateSelPanel` and `modRender`).
- **The path.** The entities are taken as the game would spawn them: the map's in order
  with Modify's changes, then Modify's new ones (`simWorld`; Modify's `$` / `#` keys read
  as `spawnKeys` reads the map's, `simKvl`). A node's next is the first entity with the
  targetname its `target` names (`G_FindTarget`); one that isn't an `info_splinepath` ends
  the path (`SplinePath::CreatePath`'s ScriptError), as does a missing one. The path starts
  at its first node: the selected node's chain followed back through the node that targets
  it, the last one in spawn order where several do (the engine's `owner`); a closed loop
  starts at the selected node. `CreatePath` stops when the chain comes back to its start;
  one that runs into a loop further on stops there (the game would hang).
- **The flight** (`simChain`, `simFrames`, `simEval`). Each node is a control point: its
  origin, its angles as the forward vector `AngleVectors` gives plus the roll in -180..180,
  and its `speed` (1 when it has none) (`BSplineControlPoint::Set`). `splineTime` starts at
  -2 (followpath's default); each 0.05 s server frame the model goes to the position and
  angles `EvalClamp` gives (cubic B-spline weights over four points, clamped at the ends;
  the forward vectors are blended and turned back into angles by `Vector::toAngles`, the
  roll blended apart), and `splineTime` moves on by 0.05 times the blended speed, so a
  speed is in nodes per second. It stops once `splineTime` passes the number of nodes
  less 2, short of the last node. The frames are worked out when it starts (at most 10
  minutes of them, for a path whose speed never gets it there) and drawn between, angles
  the short way round, as the client does. A Python copy of `EvalClamp` gives the same
  frames for m3l2's `$bomberpath`.
- **Drawing** (`drawSim`). While the section shows, the curve the model flies (a point
  every tenth of a node) in orange, faintly through walls, and a short line from each node
  along its facing. While it flies, the model: an extra instance drawn with the map's
  models (`modelsDrawn`, its matrix every frame, `simInst`), lit by the light grid where it
  is (`lgFast`, brightened and clamped as `RB_GetEntityGridLighting`), without its
  emitters or sprites, and left out of the pick pass so clicks go through it. Until a
  model is there, or when it can't be drawn, a box with a nose flies instead.
- **Buttons.** Simulate is greyed out while it flies, Reset while it doesn't; Reset stops
  it and takes the model away, and the end does the same by itself. Speed plays it at
  0.25x to 4x without a jump. The camera (`simFollow`, `simEyeStart`): **Follow** alone
  keeps it behind the model's heading and a little above it, looking at it, catching up
  smoothly; **Eye view** alone puts it on the path's first node at the node's angles when
  the simulation starts, and leaves it there; both put it behind the model along its own
  facing at its exact angles (the page's roll is the game's turned the other way). The
  **camera zoom** slider sets how far behind it follows (24 to 4096 units, log scale), and
  the mouse wheel over the view changes it while the camera follows. Moving the camera by
  hand turns Follow off.
- **The model** (`simOpen`, `simUseModel`). **Choose...** opens a picker with a search box
  (every word must match): the models the map places, from the page's own data, and in the
  launcher's pane every `models/**.tik` in the loaded paks (`mohaa-sim-models` →
  `MOHAA_SIM_MODELS`). A pak model is built by the launcher in a thread
  (`MapApp._sim_build`: the path must be a `.tik` under `models/` in the loaded paks), as
  the map build builds a map's models (`ModelBuilder`, `TextureTable`, `pack_payload`),
  and handed to the page as page data (`MOHAA_SIMMODEL`, or `MOHAA_SIMMODEL_FAIL`). The
  page decodes it like its own (`decodePacket`), uses the map's picture where the shader
  is the same and adds the rest after the map's textures (kept out of the Textures list
  and Find), and makes its mesh as the map's models' (`modelR`). The choice is remembered
  in the browser (`mohaaMapViewerSimModel`); "Placeholder box" goes back to the box.

## Cameras

- **Free-look** is the Model Viewer's: drag to look, WASD, Space / C, Q / E tilt, Left /
  Right turn, and Up / Down forward and back level with the ground (the way the camera
  faces with its pitch taken out, so looking down doesn't dive), where W / S follow the
  view. Q / E (Q the head to the left shoulder, E to the right, as in the Model Viewer). With
  the camera tilted, looking and turning follow the tilted screen, as in the Model
  Viewer: a mouse movement (or arrow key) is rotated by the roll before it becomes yaw
  and pitch (`lookBy`), so dragging down still looks toward the bottom of the screen.
  A / D strafe along the tilted screen's right, and Space / C rise along its up (world
  up turned about the view line by the roll; straight up and down with no tilt). U
  levels the view and clears the tilt (it was End, which a browser also uses to scroll
  the side panel to its bottom).
- **Radiant-look** follows MOHRadiant: right-drag flies (push up = forward, sideways =
  turn, like `Cam_MouseControl`), arrows move and turn, `,` / `.` strafe, D / C rise and
  fall, A / Z look up and down, U levels the view (MOHRadiant's End), PgUp / PgDn hop to
  the floor above / below (UpFloor / DownFloor), Ctrl+arrows and Ctrl+`,` / `.` move one
  64-unit grid step, `[` / `]` move the cubic clip.
- **Stopping.** `X` stops the camera (held keys, a drag, Radiant-look's flight, a fly-to).
  It also stops by itself when the page loses the keyboard or the window, while the page
  doesn't have the focus, when a drag's mouse button turns out to have been let go
  outside the page, and, in the launcher's pane, on a click with any mouse button on the
  launcher: a key or button let go outside the page never reaches it, and the camera used
  to keep moving. A key pressed or let go in the launcher makes the page let go of its
  keys (`releaseCameraKeys`; a drag or a fly-to goes on), and on Windows the launcher reads
  the keyboard itself, so letting go of the last camera key lets go of them wherever its
  key-up went (`App._watch_camera_stop`). Once stopped, a key still held stays let go: its
  auto-repeats don't take it up again, only a new press does. A right-click that opens the
  browser's own menu (anywhere in the page but the 3D view) stops it too, since that menu
  takes the keyboard while it is open.
- **Go to and angles** (under the sliders): `go to: x y z` flies the camera to a position
  typed or pasted (Enter; brackets and commas are fine), and **Copy pos** copies where it
  is as `( x y z )`. **Ctrl+C** with the mouse over the 3D view copies the point under the
  cursor instead (on the face it is over, or a marker's origin), the same way, rounded to
  hundredths; with text picked out on the page, Ctrl+C copies that as usual. The note
  under the view says which was copied: "Camera's origin", "Camera's angles" or "Mouse
  cursor's origin", with the value. `angles: pitch yaw roll` turns it where it stands to angles as the
  game takes them (`AngleVectors`: looking down is a positive pitch), and **Copy ang**
  copies its own the same way, `( pitch yaw roll )`, pitch and roll in -180..180 and yaw
  in 0..360. The page's own roll turns the other way to the game's (`camAxes` tilts the
  right axis up for a positive roll, `AngleVectors` down), so both swap its sign
  (`camAngles`, `turnTo`). The camera line at the bottom of the view shows `roll` after
  pitch only while the camera is tilted.
- A page always opens at the player start. `V` switches cameras, `R` returns to the player start, `B` toggles Full Brightness,
  `K` Simple Sky, `M` Simple models, `J` Sun flare, `0` Lights off, `-` Sun light, `=`
  Decals, `Y` Weather, `P` Leak trail, `I` AI routes, `Ctrl+E` Script ents,
  `Ctrl+B` Script trigs, `L`
  opens the legend, `` ` `` the game cvars list and `T` switches the theme. The FOV
  slider runs from 60 to 150. Press `H` in the viewer for all of them (Keyboard
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
  animated maps and `deformVertexes` (but a model's `wave` and `flap`, below) don't play.
- Lighting: dynamic lights (lamps switched by script, muzzle flashes) and the
  `alphaGen distFade` fade-out aren't drawn. Portal skies (`textures/common/skyportal`
  with a `script_skyorigin`) show the plain sky box; no retail Allied Assault map uses one.
- Trees don't change with distance: they are drawn whole, or as their sprite version
  with Simple models on (above), never faded from one to the other as in game.
- Sun flare: the line toward the sun meets patches and the terrain by their drawn
  triangles, not the game's collision shapes, and meets a patch from either side (the
  game's facets stop it only from the front). The glare is always white, as `whitefade`
  is. A `fullscreen` shader the paks don't have would draw the game's default picture
  instead. The flares of entities and dynamic lights (`begin entity`, `begin dlight`)
  aren't drawn.
- A `.map` has no compiled light, so it is always drawn full bright.
- After a graphics driver reset, opening the same page again in the launcher showed the
  reset message again; Rebuild in viewer brought it back.
- Lights off is worked out, not read: the compiler's own lighting code for MOHAA isn't
  public, so each light's share comes from q3map's formula (measured to match the
  lightmaps' bytes on m6l3d and m4l3), and the sun's and sky's strength from
  `suncolor` and `sundiffuse` as the retail maps' lightmaps show them. Each light also
  gets a small share by distance, without shadows, so a texel it reached only by the
  compiler's sampling (through a gap, around an edge) still goes dark with it; how much
  that share can take away is capped, so light the page doesn't trace (the sky under
  eaves and in shaded corners) stays. Texels whose light was clipped at full
  brightness (most sunlit ones) can't tell how much each light added, so near a light
  outdoors turning it off takes away its share of the clipped value. The same goes for
  Sun light: near a lamp outdoors, the lamp keeps only its share of a clipped texel.
- Clouds: `tcMod turb` and the entity-driven tcMods, `animMap` frames after the first,
  and a second texture bundle aren't drawn; the noise waveform is a smooth stand-in for
  the engine's.
- `.min` and `.vis` files are listed in the tree but not used; `.scr` scripts open in the
  text editor. A map's `.pth`, `.dcl` and `.lin` are read by its page (ai_showroutes,
  Decals, Leak), not opened from the tree on their own.
- Triangle soups in a `.bsp` (rare in MOHAA maps) are counted but not decompiled.
- `r_showtris` and `r_shownormals` draw terrain at full detail (the game thins it out with
  distance, `ter_error` / `ter_maxlod`; it has no normals anyway) and models at full
  detail (no model LOD), and every face and patch with its own normals (see above).
  Patches aren't stitched where two meet (`R_StitchAllPatches`,
  `R_FixSharedVertexLodError`; the stitching adds rows and columns and makes those grids'
  normals again), so a seam between patches of different detail can differ from the
  game's. The sky's cloud dome isn't outlined. Doors are as the level starts unless
  opened with Open door (no scripts
  run), and other entities stand where the `.map` puts them. The overlay and its counts
  cover every direction around the camera.
- Doors: a fully open door doesn't cut the AI paths it blocks. In game `Door::SetState`
  disconnects every path connection an actor's box can't sweep past the open door
  (`Entity::DisconnectPaths`, a cylinder trace), and `ai_showroutes` stops drawing those
  until the door starts closing. Locks, a door's `message` and its sounds aren't
  simulated, and a door that is blocked doesn't stop.
- Level script: entities are placed from its lines, not by running it, so a spawn whose
  place comes from the running game (a thread's parameter, a loop, `self`) isn't drawn,
  and what a script does to the map's own entities (moving them, removing them, `hide`)
  isn't shown. `$world` settings are listed, not applied.
- Weather: the drops are made at the page's frame rate when it can't keep up with
  `com_maxfps` (at most a fifth of a second of client frames at once), and from the
  camera's place rather than the player's feet (1.11 took the player's origin; across, it
  is the same). Script-spawned `func_rain`s have no brush to give them a box.
- Modify: a changed map entity drawn with a model shows as a box while changed. New
  entities are boxes (a model isn't drawn), get no light, and don't take
  part in what the page simulates (doors, exploders, cvars that list entities). Only
  point entities can be added. The routes on the `.pth`'s own nodes are the file's;
  only links to and from new nodes are worked out, so a new node that fills a cell or a
  node's 48 links isn't followed by the game's re-ordering of the rest.
- **Planned:** following more of what a level script does as it runs. More of the game's
  debugging cvars, once checked in game.

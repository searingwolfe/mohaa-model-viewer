# Doors: how the Map Viewer opens them

What the game does, from OpenMoHAA's `fgame/doors.cpp` and `fgame/mover.cpp`, and how the
page copies it. **Open door** (Selection panel, or `O`) shipped in Map Viewer page rev 21;
the code is the Doors section of the page script (`doorsInit` ... `doorInfo` in
`mohaa_map_page.py`).

## Classes and spawnflags

- `func_rotatingdoor` (`RotatingDoor`) swings about its origin, the hinge column the
  decompiler writes since rev 19. `func_door` (`SlidingDoor`) slides. `script_door` moves
  only when the map's script tells it to (`initthread` / `openthread` / `closethread`), so
  the page greys its button out.
- Spawnflags (`Door`): 1 START_OPEN, 2 OPEN_DIRECTION, 4 DOOR_DONT_LINK, 8 NOT_PLAYERS,
  16 NOT_MONSTERS, 32 TOGGLE, 64 AUTO_OPEN, 128 TARGETED (only triggers or script open it).
- What opens it in game (`Door::DoorUse`): the use key, unless it has health (it must be
  shot), AUTO_OPEN (a player walking up to it) or TARGETED. The page's button opens any of
  them; the info card's Door section says which it is.

## Keys, in the order the game reads them

- The constructor runs first (`newInstance` in `g_spawn.cpp`), then every key is posted as an
  event in the entity's key order, so the last of `time` / `doortype` wins.
- Events with the same name share one event number, and a class's own handler wins over
  its base class's (`ClassDef::BuildResponseList`). So `time` is `Door::SetTime`
  (traveltime, at least one frame; speed = 1 / traveltime), `wait` is `Door::SetWait`, and
  `speed` is `SlidingDoor::SetSpeed` on a `func_door` but `ScriptSlave::SetSpeed` (the rate
  itself) on a `func_rotatingdoor`.
- Defaults: `doortype` wood (1 s; metal 1.5 s; anything else is a script error and changes
  nothing), `wait` 3 (0 with TOGGLE), `openangle` 90, `alwaysaway` 1, `lip` 8.
- `angle` is `Door::SetDir` / `SlidingDoor::SetMoveDir`: a direction, not a turn of the door
  (so the info card's Script lines don't give a door `.angles` from it). `startangle` is
  taken in the constructor, before any key, so it is ( 0 0 0 ).

## Rotating doors

- `RotatingDoor::DoOpen`, only when the door was shut: with `m` the `angle` direction
  (`G_GetMovedir`) and `dir = (-m.y, m.x)`,
  - `diropened = dot(flat direction from the door's origin to the opener, m)`, negated when
    `dot(dir, normalised middle of its box) > 0`;
  - with `alwaysaway 0`: `diropened = dot(dir, normalised middle of its box)`, the same way
    every time;
  - the door turns to yaw `+openangle` when `diropened < 0`, else `-openangle`.
- In the retail maps `angle` lies across the door (perpendicular to its face), and the
  flip makes it swing away from the opener whichever side `angle` points to. (The QUAKED
  text, "point toward the middle of the door", is Quake's.)
- A door that is closing keeps its side when it is opened again (`previous_state` isn't
  closed).

## Sliding doors

- Along `angle` (-1 up, -2 down) by `|movedir . size| - lip` (`SlidingDoor::Setup`, after
  the keys). With a `speed` key the rate is `speed / totalmove`, so it overrides `time`.

## Moving and closing

- `Mover::MoveTo`: an even speed from wherever the door is (angles by `angledist`); a move
  shorter than a server frame (0.05 s) jumps at the frame's end; no move at all ends after
  one frame.
- `Door::Open` on an opening door does nothing; on an open one it restarts the wait. It
  opens the linked doors with the same opener, and the master opens its area portal if it
  was shut.
- `Door::OpenEnd`: open; TOGGLE stays open; otherwise the master posts Close after `wait`
  seconds when `wait > 0` (`-1` and `0` never close by themselves).
- `Door::Close` cancels a pending close and closes the linked doors; `Door::CloseEnd` (the
  master) closes its area portal.
- START_OPEN: the constructor marks the door open and posts Open with no opener, which
  throws a script error at once (`ScriptError` is `throw ScriptException`), so the door
  never moves and no close is scheduled. Its master opens its portal in `LinkDoors`
  (unless it is DOOR_DONT_LINK or left unlinked). Using it closes it (in place), then it
  opens normally. OPEN_DIRECTION only counts for a DoOpen with no opener.

## Linked doors

- `Door::LinkDoors`, door by door in entity order, per class: a door already linked is
  skipped; DOOR_DONT_LINK stands alone; a door that no later door touches but an earlier
  one does is left unlinked; otherwise it walks the later doors, linking each that touches
  the last one linked, and becomes their master. Boxes touch with a unit of slack on both
  (`SV_LinkEntity`'s absmin / absmax).

## Areas (r_showtris)

- `CM_AdjustAreaPortalState` counts per area pair (a count can go below zero); a pair is
  open while its count is above zero. The door's pair is the areas its box touches where
  the .map has it (`GV.doorArea`), which is where the door is at Open and at CloseEnd.
- While a door moves, the server links it again each frame: a turned door's box is the
  bounds of its turned setsize (`CalculateRotatedBounds2`), so its clusters and areas
  follow it (`gvLink`).

## In the page

- `doorPose` puts the door where it is now from copies of where the .map has it: the .map
  faces (one run of vertices), their planes and the brushes' boxes (picking, the see-through
  test), the game's lit polygons (runs of `LIT.pos`), r_showtris's points, plane / box /
  patch-centre records and its uploaded lines. Selection and hover outlines index the same
  vertex buffer, so they follow; the setsize box turns with it and the label and links use
  its moved anchor.
- `doorsAdvance(now)` runs the moves and closes each at its own time, so a page left in the
  background catches up in order. A test can stop the frame loop, set `performance.now`
  and call it.

## Not done

- A fully open door cuts the AI path connections an actor can't sweep past it
  (`Door::SetState` -> `Entity::DisconnectPaths`, a cylinder trace against the door), and
  `ai_showroutes` stops drawing them until the door starts closing. The page doesn't.
- Locks (script only), a door's `message`, its sounds, and being blocked.
- A door the level script spawns or moves: script entities are point entities here
  (Level script, map-viewer.md).

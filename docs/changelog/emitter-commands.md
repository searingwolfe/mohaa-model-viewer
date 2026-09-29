# Emitter commands

What the viewer does with each keyword inside a `.tik` emitter block. The parser is
`_em_body()` / `parse_tik_emitters()` in `bin/mohaa_view.py`; the simulation is
`spawnParticle()` / `stepParts()` / `drawParticles()` in the page template. Engine references
are OpenMOHAA `code/cgame` (`cg_commands.cpp` parses the commands, `cg_tempmodels.cpp`
runs them, `cg_volumetricsmoke.cpp` handles volumetric smoke). Anything not listed here
is ignored.

## Where emitters come from

| Form | Where | Behaviour |
|---|---|---|
| `originemitter <name> ( ... )` | `init { client { } }` | continuous emitter at the model origin |
| `tagemitter <tag> <name> ( ... )` | same | continuous emitter at a tag; the tag may be quoted and contain spaces |
| `commanddelay <t> originemitter ...` | same | the emitter starts `t` seconds after load or Reset |
| `sfx` / `delayedsfx <t>` + `originspawn` / `tagspawn` / `tagspawnlinked ( ... )` | `init { client { } }` | one-shot burst at load or Reset (after `t` seconds) |
| `originspawn` / `tagspawn` / `tagspawnlinked ( ... )` | animation frame commands | one-shot burst of `count` when the frame plays |
| `emitteron <name>` / `emitteroff <name>` | animation frame commands | switch an init emitter on or off (optionally behind `commanddelay`) |

Server-side frame commands also handled: `attachmodel <model> <tag> [scale]`,
`surface <name> +nodraw / -nodraw` and `explosioneffect <type>` (plays the matching
`*exp_base.tik`). `removeattachedmodel` is ignored on purpose: attachments are removed
when their animation ends.

## Spawning

| Command | Viewer behaviour |
|---|---|
| `spawnrate <n>` | one particle every `1/n` s (`SetSpawnRate`, `UpdateEmitter`); capped at 300/s |
| `count <n>` | burst size for spawn commands (default 1); for a volumetric burst the puff count is `count` x `life` (capped) |
| `life <base> [amp]` | lifetime = base + random x amp |
| `model <ref>` / `emittermodel <ref>` | `.spr` = shader-name sprite; `.tik` = mesh debris or a nested effect; volumetric names (`greasefire`, ...) = VSS puff types |
| `startoff` | the emitter starts silent until an `emitteron` |

## Placement and shape

| Command | Viewer behaviour |
|---|---|
| `offset x y z` | world-space offset; each component may be `crandom a`, `random a` or `range a b` |
| `offsetalongaxis x y z` | offset along the entity axis (rotates with the placement angles); same random forms |
| `radius r` | spawn on a shell of radius `r`, moving outward (default 0) |
| `sphere` | direction sampled inside the unit ball, so speeds spread from 0 to `velocity` |
| `inwardsphere` | spawn on the `radius` shell and fly toward the centre |
| `circle` | ring of `radius` in the ground plane; bursts are evenly spaced |
| `cone <height> <radius>` | spawn inside a cone around the up axis; also sets the ring radius used by `circle` |

Effect entities are placed facing up (`angles 270 0 0`), so "forward" means up unless a
placement angle is set with the Display dial.

## Motion

| Command | Viewer behaviour |
|---|---|
| `velocity v` | speed along the spawn direction (up by default) |
| `randvel x y z` | random velocity added after everything else; `crandom` / `random` / `range` per component |
| `randvelaxis x y z` | treated like `randvel` (not rotated onto the entity axis) |
| `radialvelocity a b c` | replaces `velocity`: outward speed uniform in `[b, c]` plus `a` x distance |
| `accel x y z` | constant acceleration; for volumetric emitters the slot means `[type, fadeMult, scaleMult]` |
| `smokeparms a b c` | writes the same slot as `accel` (the last one wins) |
| `friction f` | velocity x (1 - f/10) per 10 Hz physics step; negative values accelerate |
| `clampvel minX maxX minY maxY minZ maxZ` | clamps velocity every physics step |
| `collision` + `bouncefactor b` | bounce off an invisible floor at the grid (default b = 0.3) |
| `swarm freq maxspeed delta` | `T_SWARM`: random velocity re-rolls and a pull toward the target, on a fixed tick |

## Orientation

| Command | Viewer behaviour |
|---|---|
| `angles p y r` | initial angles (random forms allowed); without it, the tempmodel inherits the tag or entity axis |
| `avelocity p y r` | angular velocity per component (random forms allowed) |
| `randomroll` | new random roll every 10 Hz physics tick, interpolated; see [sprite-roll-rules.md](sprite-roll-rules.md) |
| `align` / `alignonce` | face along the velocity |
| `alignstretch s` | stretch mesh tempmodels along their travel (implies `align`); flat sprites aren't stretched |

## Appearance

| Command | Viewer behaviour |
|---|---|
| `color r g b [a]` | tint via the engine's byte conversion (wraps above 1.0, not clamped); the optional 4th value sets alpha; only affects shaders with `rgbGen vertex` |
| `alpha a` | base opacity |
| `varycolor` | darkens each particle by a random 0-20% (the engine varies each channel) |
| `flickeralpha` | random alpha each frame |
| `scale s [amp]` | base scale, plus random x amp |
| `scalemin` / `scalemax` | random base scale range (a spawn range, not a runtime cap) |
| `scalerate r` | scale = base x (1 + r x age), unbounded |
| `fade` | fade out over the life |
| `fadedelay t` | fading starts after `t` seconds (implies `fade`) |
| `fadein t` | fade in over the first `t` seconds |
| `volumetric` | volumetric smoke (VSS): density ramp and decay, radius growth, wind and repulsion |

Sprites whose shader blend doesn't read source alpha (`blendfunc add`) ignore the
emitter's alpha, fade and flicker, as in the engine.

## Parsed but not used

`alwaysdraw`, `spritegridlighting`, `parallel`, `scaleupdown`, `spin`, `tracer`,
`spawnrange` and `randaxis` are recognised so they aren't mistaken for stray tokens, but
have no effect in the viewer.

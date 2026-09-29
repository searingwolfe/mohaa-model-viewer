# Sprite roll and `randomroll`

Engine rules behind the sprite-roll handling, worked out while matching electric_arc,
electric_panelmelt and the mg42 / jeep muzzle flash to in-game footage. Line numbers are
OpenMOHAA `code/renderergl1` and `code/cgame`.

## 1. Roll only shows on `spritegen parallel_oriented` sprites

`RB_DrawSprite` (tr_sprite.c:82-150) switches on the sprite shader's `sprite.type`:

| Type | Uses the sprite's axis? | Roll visible? |
|---|---|---|
| `SPRITE_PARALLEL` (default, 0) | no: view axes, right negated (:123-130) | no |
| `SPRITE_PARALLEL_ORIENTED` | yes: roll from `axis[1]` (:105-121) | yes |
| `SPRITE_ORIENTED` | yes: full `axis[1]` / `axis[2]` (:131-133) | yes |
| `SPRITE_PARALLEL_UPRIGHT` | no: world up + horizontal right (:135-149) | no |

A shader with no `spritegen` line is `SPRITE_PARALLEL`: `ParseShader` only sets
`sprite.type` in the `spritegen` branch (tr_shader.c:2402-2418), the shader is zeroed
first (:3424), and `SPRITE_PARALLEL` is 0 (tr_local.h:530-535). An unresolved sprite name
falls back to the default shader, zeroed the same way. So "no spritegen" means no roll,
not "unknown, assume it rolls".

Retail sprite shaders with no `spritegen` (never roll): `corona_reg`, `corona_red`,
`corona_util`, `corona_orange`, `fire_front`, `fire_middle`, `fire_back`, `lampflame`,
`greensmoke2`, `fire4`, `fire4d`, `watersplash`, `explosed`, `flame_pj`.

Relevant declared ones: `electric` is `spriteGen parallel_oriented`; `vsssource` /
`vsssource2` are `spritegen parallel` (their `parallel_oriented` line is commented out);
`muzsprite` is `spriteGen parallel_oriented` with `spriteScale .3`.

This only applies to the sprite renderer, i.e. `RT_SPRITE` tempmodels: `.spr` models and
volumetric puffs (drawn through `VSSSource.spr`). A `.tik` sub-model tempmodel is an
`RT_MODEL` rendered on its full axis, so `randomroll` does turn it.

## 2. `randomroll` holds for the first 100 ms

`T_RANDOMROLL` sets `angles[ROLL] = random() * 360` in `TempModelPhysics`
(cg_tempmodels.cpp:601-602), which runs at the 10 Hz effect physics rate (:237,
:959-968). Between ticks the render lerps the axis matrix (:854-859) along the shortest
arc, so a long-lived particle turns smoothly from one random roll to the next.

On a tempmodel's first frame, physics runs because `lastEntValid` is still false
(:1000-1012), and that call ends by copying `lastEnt = ent` (:796-802). Both ends of the
lerp are then the same rolled axis until the next tick at 100 ms.

So a `randomroll` particle with `life < 0.1` never turns. electric_arc's `lightning2`
(`life .09`) is rolled once at spawn and held, which matches the game.

## 3. Additive sub-model textures need real alpha in a canvas

`muzflash.tik` uses shader `muzmodel`: `blendFunc GL_SRC_ALPHA GL_ONE` with
`alphagen vertex`. Its texture (`models/fx/muzflash/flashnode1.tga`) is a 24-bit TGA with
no alpha. In GL that's fine: alpha comes from the vertex colour and the black surround
adds nothing.

Canvas `'lighter'` adds onto a transparent canvas, so an opaque black texel still adds
alpha and paints a black rectangle around the flash. Additive sub-model surfaces are
therefore encoded like additive sprites (`texture_to_dataurl(..., emitter_clean=True)`:
lossless PNG with near-black floored to alpha 0).

## 4. Where this lives

- `bin/mohaa_view.py`: the `p.rroll` block in `stepParts` (tick timer and lerp) and the
  camera-facing sprite branch in `drawParticles` (`_noRoll`).
- `bin/mohaa_launcher.py`: `_submodel_mesh` and the `surface ... shader ...` texture export
  for sub-models.

## 5. How it was verified

Built pages are self-contained, so they can be driven headlessly with Playwright
(particles are always drawn on the 2D canvas, whichever renderer draws the mesh). Useful
probes:

- sample `parts[].roll` every frame and sum the shortest-arc change per particle to get
  its total turn over its life;
- wrap `CanvasRenderingContext2D.prototype.rotate` / `.scale` to count rolled versus
  unrolled draws;
- on frames where `parts.some(p => p.mrot)`, read the canvas with `getImageData` and count
  opaque near-black pixels to detect the muzzle-flash black card.

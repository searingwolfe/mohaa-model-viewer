# Engine notes

Findings about MOHAA's formats and renderer that were expensive to learn. Engine
references are to [OpenMOHAA](https://github.com/openmoh/openmohaa) (`code/cgame`,
`code/renderergl1`, `code/skeletor`, `code/tiki`). The source comments cite exact files
and line numbers next to the code that depends on them.

## Verifying against the real pipeline

- A Python or `.obj` render of a pose can look right while the JS viewer is wrong. The
  only reliable check is to replay the page's own math: take the real `DATA` payload
  from a built page, run the same quaternion/skinning code, and compare with numeric
  metrics (vertex distances, angles), not by eye.
- Python's `round()` rounds half to even; JavaScript's `Math.round` rounds half up. Any
  value computed on both sides (quantised angles, indices) must use the same rule, e.g.
  floor division with an explicit offset.
- Back faces: for front-sided shaders the engine keeps OpenGL's default CCW front face and
  culls `GL_FRONT` (`GL_Cull`, tr_backend.c:137-175), so visible faces run clockwise on
  screen. On the 2D path's y-down screen that's positive area (`_a2 > 0`); the WebGL path
  uses `cullFace(FRONT)`. A synthetic `.skd` with one clockwise and one counter-clockwise
  quad checks both renderers without game assets.

## Skeleton, animation and IK

- Leg IK must resolve on first demand, before any bone that depends on it (helper, Toe0,
  tags) is composed, matching the engine's lazy evaluation in `skeletorbones.cpp`. An
  FK-then-IK batch pass displaces helper origins on upper-body animations that borrow
  their legs from a movement-slot donor.
- `HoseRot` / `AvRot` helper bones must be solved, not folded into their ancestors, or
  ankles, knees and shoulders deform. The ankle helper also needs a 180-degree flip about
  its target's local Y, so its X axis points up the shin.
- Thigh and calf share one bend-plane frame (a port of `skelBone_IKshoulder` / `IKelbow` /
  `IKwrist`); a shortest-arc swing per bone twists the shin.
- When baking IK-solved world matrices into local quaternions, use the local-space
  conversion (`mat_to_localquat`); plain `mat_to_quat` stores the transpose.
- SKD vertices can carry `skeletorMorph_t` blocks (16 bytes each, after the 28-byte vertex
  and before the weights). They are the facial blend shapes; skipping them loses all face
  animation.
- Validate every count and offset in `.skc` / `.skd` headers against the file size before
  looping. The older ProtoAnimations v11 `.skc` format inserts a 64-byte name after the
  version field, shifting every offset.
- Humanoid `.skd` files have no usable rest pose (identity lays the rig along +X), and
  shared idle `.skc` frames are posed actions. A neutral A-pose template (allied_pilot)
  gives a clean default.

## TikiScript (.tik) parsing

- Expand `$include` before any parsing (grenade models keep `setup{}` in an included
  `_base.txt`), and write the expanded text back to disk before the builder subprocess
  reads the file.
- Strip `//` line comments before `/* */` blocks. Banner lines like `//******` contain a
  `/*` that otherwise pairs with a later `*/` and swallows whole `animations{}` blocks.
- `case <key> <values> { ... }` is a switch (`TIKI_LoadSetupCase`): only the matching
  branch's `skelmodel`s load.
- `tagemitter` takes a tag that may be a quoted string with spaces
  (`tagemitter "smoke emitter" heavysmoke`).
- Emitter parameters that go through `SetBaseAndAmplitude` accept `crandom` / `random` /
  `range` per component, including `avelocity` and `angles`.
- `life` on a volumetric emitter doesn't time out puffs; it scales the spawn count.
  `accel` / `smokeparms` share one slot, which for volumetric smoke means
  `[typeInfo, fadeMult, scaleMult]`, not an acceleration.
- A stale `skelmodel foo.skb` resolves to the shipped `foo.skd`, as the engine's loader
  does.
- The full list of emitter commands the viewer understands is in
  [emitter-commands.md](emitter-commands.md).

## Shaders and sprites

- `model <name>.spr` in an emitter is a shader name, not a file: the shader named by the
  path minus the extension (e.g. `mortar_dirthit` in `effects.shader`), whose first stage
  `map` / `clampmap` is the actual `.tga`. The `.spr` files themselves are not needed.
- Shader name lines can carry a trailing `//` comment; the block scanner must allow it or
  the whole index fails.
- `greasefire` and similar volumetric model names are VSS types (`VST_GREASEFIRE`) drawn
  through `VSSSource.spr`, not sprite or `.tik` references.
- A shader with no `spritegen` is `SPRITE_PARALLEL`, which ignores roll. See
  [sprite-roll-rules.md](sprite-roll-rules.md).
- Emitter `color` is converted to a byte with wrap-around (`(int)(c*255)` stored in a
  byte), not clamped: `color 4.5 0.2 0` becomes (123, 51, 0).
- `blendFunc GL_ONE GL_ONE` in a canvas needs premultiply compensation (alpha = max(R,G,B),
  RGB divided by it). Keeping the texture's own alpha under-lights it, and forcing alpha
  to 255 punches opaque black squares through the backdrop with canvas `'lighter'`.

## Browser, WebView2 and file URLs

- A WebGL2 context doesn't offer `OES_standard_derivatives` to GLSL ES 1.00 shaders, so
  `dFdx` / `dFdy` fail to compile there. The renderer compiles its shaders as GLSL ES 3.00
  on WebGL2 and as 1.00 with the extension on WebGL1.

- Navigating WebView2 to the same `file:` URL with only the `#hash` changed is an in-page
  hash change, not a reload. To force a reload, close and recreate the pane.
- Don't cache-bust `file:` URLs with a query string (`?v=<mtime>`): `System.Uri` treats it
  as part of the file name and the load fails with `ERR_FILE_NOT_FOUND`.
- Build `file:` URLs with `pathlib.Path.as_uri()`. Hand-built `"file://" + path` breaks on
  Windows drive letters and on `#`, `%` or non-ASCII characters.

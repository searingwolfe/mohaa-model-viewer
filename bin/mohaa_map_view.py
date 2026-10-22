#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
#  mohaa_map_view.py  --  build a MOHAA map (.bsp or .map) into a 3D viewer page
#
#  A .bsp is first turned back into .map source by mohaa_bsp.py (written next to the
#  page, so it can be opened in MOHRadiant or a text editor). The .map text itself
#  goes into the page, which rebuilds every brush, patch and terrain block in the
#  browser. This script adds what the page can't work out on its own:
#
#    - each shader's picture, size and render hints (sky, alpha test, blending, the
#      surfaceparms that make a brush a clip, trigger, caulk, hint ...), from the
#      loaded paks' scripts/*.shader files and textures
#    - the meshes of the models placed in the map (static_* props, script_models,
#      turrets ...), posed and textured from their .tik files
#    - the entity definitions (colours, boxes, spawnflag names, notes) that
#      MOHRadiant reads from /*QUAKED*/ headers
#    - the six pictures of each sky shader's sky box and its cloud layers, and the
#      editor pictures the legend shows
#    - for a .bsp, the exact bounding box the game uses for each brush entity, and
#      the game's lighting: lightmaps, vertex light, static-prop light, light grid
#
#  Everything is packed into one self-contained .html file (see mohaa_map_page.py
#  for the page itself).
#
#  Command line:
#    python mohaa_map_view.py <map.bsp|map.map> [--pak=<file.pk3> ...] [--paks=<list.txt>]
#           [--vfs=<path inside the paks>] [--outdir=<folder>] [--cache=<folder>]
#           [--texsize=256] [--theme=light|dark] [--no-models] [--decompile-only] [--no-open]
# ==============================================================================
import base64, gzip, hashlib, io, json, math, os, re, struct, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mohaa_bsp as MB
import mohaa_entdefs as ME
try:
    import mohaa_textures as MTX         # pak file system (Vfs) and .tik $include expansion
except Exception:                         # pragma: no cover - shipped together
    MTX = None
try:
    import mohaa_view as MV               # .skd / .skc / .tik readers shared with the model viewer
except Exception:                         # pragma: no cover
    MV = None

# Page format revision, baked into each page as <!--mohaa-map-viewer-rev:N-->. Raise it
# (and MAP_VIEWER_REV_REQUIRED in mohaa_map_launcher.py) when the page changes in a way
# that a cached page must pick up.
MAP_VIEWER_REV = 21

# Bumped when the cached shader / entity index format changes, so old caches are ignored.
INDEX_VERSION = 7

# Default longest side of the textures embedded in the page. 256 keeps a large map's
# page around 10-20 MB; the launcher can ask for 128 or 512.
TEX_MAX_DIM = 256

# Limits for the placed models, so a map full of characters can't stall the build.
MODEL_MAX_UNIQUE = 400
MODEL_MAX_VERTS = 60000            # per model
MODELS_MAX_TOTAL_VERTS = 2500000   # all models together

# Part of every texture cache key; raise it when encode_image's output changes.
TEX_CACHE_FORMAT = 2

USAGE = ("usage: python mohaa_map_view.py <map.bsp|map.map> [--pak=<file.pk3> ...] [--paks=<list.txt>]\n"
         "         [--vfs=<path inside the paks>] [--outdir=<folder>] [--cache=<folder>]\n"
         "         [--texsize=256] [--theme=light|dark] [--no-models] [--decompile-only] [--no-open]")


def log(*a):
    """Progress line for the launcher's Output pane (it reads our stdout as we go)."""
    print(*a)
    try:
        sys.stdout.flush()
    except Exception:
        pass


# ==============================================================================
#  Shaders
# ==============================================================================
# surfaceparm names -> (contents bits, surface bits), from OpenMoHAA's
# renderergl1/tr_shader.c infoParms[] (MOHAA's own list, a superset of Quake 3's).
SURFACEPARMS = {
    "water": (0x20, 0), "slime": (0x10, 0), "lava": (0x8, 0),
    "playerclip": (0x10000, 0), "monsterclip": (0x20000, 0), "fence": (0x2000, 0),
    "weaponclip": (0x40000, 0), "vehicleclip": (0x80000, 0), "nodrop": (0x80000000, 0),
    "nonsolid": (0, 0x800), "origin": (0x1000000, 0), "trans": (0x20000000, 0),
    "detail": (0x8000000, 0), "structural": (0x10000000, 0), "areaportal": (0x8000, 0),
    "fog": (0x40, 0), "sky": (0, 0x4), "alphashadow": (0, 0x200), "slick": (0, 0x2),
    "noimpact": (0, 0x10), "nomarks": (0, 0x20), "ladder": (0, 0x8), "nodamage": (0, 0x1),
    "nosteps": (0, 0x400), "paper": (0, 0x2000), "wood": (0, 0x4000), "metal": (0, 0x8000),
    "rock": (0, 0x10000), "dirt": (0, 0x20000), "grill": (0, 0x40000), "grass": (0, 0x80000),
    "mud": (0, 0x100000), "puddle": (0, 0x200000), "glass": (0, 0x400000),
    "gravel": (0, 0x800000), "sand": (0, 0x1000000), "foliage": (0, 0x2000000),
    "snow": (0, 0x4000000), "carpet": (0, 0x8000000), "nodraw": (0, 0x80),
    "castshadow": (0, 0x40), "nolightmap": (0, 0x100), "nodlight": (0, 0x20000000),
    "hint": (0, 0x40000000),
}

# Render-hint bits for a texture, read by the page (keep in step with TF_* there):
# sky, nodraw, alpha-tested, alpha-blended, additive, two-sided, missing from the paks,
# camera-facing sprite, multiplied over what's behind (decals, "filter" blends), and a
# tree's long-range stand-in sprite (see parse_shaders' "lod").
TF_SKY, TF_NODRAW, TF_ALPHATEST, TF_BLEND, TF_ADD, TF_TWOSIDED, TF_MISSING, TF_SPRITE, TF_FILTER, TF_LOD = (
    1, 2, 4, 8, 16, 32, 64, 128, 256, 512)

# Editor-only "utility" textures sorted into the groups the page filters by.
_UTIL_NAMES = (
    ("caulk", ("caulk", "caulkshadow", "foliagecaulk", "sunblock")),
    ("trigger", ("trigger",)),
    ("origin", ("origin",)),
    ("hint", ("hint", "vis")),
    ("skip", ("skip", "waterskip")),
    ("portal", ("areaportal", "portal", "skyportal")),
    ("nodraw", ("nodraw", "rain", "patharea", "static_visible")),
    ("ladder", ("ladder",)),
)


def _strip_comments(txt):
    """Shader text without // and /* */ comments."""
    txt = re.sub(r"/\*.*?\*/", " ", txt, flags=re.S)
    return re.sub(r"//[^\n]*", "", txt)


_SHADER_NAME = re.compile(r"[ \t\r\n]*([^\s{}]+)[ \t\r\n]*\{")

# Stage pictures that are reflections or helpers, never the surface's own picture.
_HELPER_PIC = re.compile(r"(?i)reflection|/env/|cubemap|_spec\.|specular")
_ADD_BLENDS = ("add", "gl_one gl_one", "alphaadd", "gl_src_alpha gl_one")
_FILTER_BLENDS = ("filter", "gl_dst_color gl_zero", "gl_zero gl_src_color")


def _parse_stage(text):
    """One { stage } of a shader, as tr_shader.c ParseStage reads it: the picture of
    each texture bundle ("nextBundle" starts the second), the blend, alpha test,
    rgbGen / alphaGen, depthWrite, and the tcMods of the first bundle."""
    st = {"map0": None, "b": [None, None], "env": False, "blend": None, "cut": False,
          "afunc": None, "rgb": None, "rgbx": None, "agen": None, "tcmod": [], "dw": False,
          "lm": False, "anim": None}
    bundle = 0
    for line in text.splitlines():
        tok = line.split()
        if not tok:
            continue
        kw = tok[0].lower()
        if kw == "nextbundle":
            bundle = 1
        elif kw in ("map", "clampmap", "clampmapx", "clampmapy") and len(tok) > 1:
            if tok[1].lower() == "$lightmap":
                st["lm"] = True
            if st["map0"] is None:
                st["map0"] = tok[1]
            if st["b"][bundle] is None:
                st["b"][bundle] = tok[1]
        elif kw in ("animmap", "animmapphase", "animmaponce") and len(tok) > 2:
            frames = [x for x in tok[2:] if not x.startswith(("$", "*"))]
            if kw == "animmapphase" and frames:
                frames = frames[1:]
            if frames:
                if st["map0"] is None:
                    st["map0"] = frames[0]
                    st["anim"] = frames
                if st["b"][bundle] is None:
                    st["b"][bundle] = frames[0]
        elif kw == "blendfunc" and len(tok) > 1:
            st["blend"] = " ".join(x.lower() for x in tok[1:3])
        elif kw in ("alphafunc", "alphatest") and len(tok) > 1:
            st["cut"] = True
            if st["afunc"] is None:
                st["afunc"] = tok[1].lower()
        elif kw == "rgbgen" and len(tok) > 1:
            if st["rgb"] is None:
                st["rgb"] = tok[1].lower()
            st["rgbx"] = [tok[1].lower()] + tok[2:]        # the whole rgbGen; the last one wins
        elif kw == "alphagen" and len(tok) > 1:
            st["agen"] = [tok[1].lower()] + tok[2:]
        elif kw in ("tcgen", "texgen") and len(tok) > 1 and bundle == 0:
            st["env"] = tok[1].lower().startswith(("environment", "sunreflection"))
        elif kw == "tcmod" and len(tok) > 1 and bundle == 0:
            st["tcmod"].append([tok[1].lower()] + tok[2:])
        elif kw in ("depthwrite", "depthmask"):
            st["dw"] = True
    pic = st["b"][0]
    st["pic"] = pic if pic and not pic.startswith(("$", "*")) and not _HELPER_PIC.search(pic) else None
    return st


def _img_key(path):
    """An image path without its extension, for comparing stage pictures."""
    return re.sub(r"\.(tga|jpg|png|dds)$", "", (path or "").lower().replace("\\", "/"))


def _picture_stage(stages, editor):
    """The stage whose picture the surface shows in game, or None:
    1. the one that multiplies its picture by the lightmap (map X / nextBundle / map
       $lightmap): that is the surface's own lit texture, whatever is drawn under it
       (snow shaders draw a sparkle layer first);
    2. the one drawing the editor picture, unless it is a glow added on top;
    3. the last stage drawn solid, which covers every stage before it (floors draw a
       reflection first and paint over it); an alpha-tested one only covers part;
    4. the texture a lightmap-first shader multiplies in (blendFunc filter);
    5. the first picture. Reflections (tcGen environment) only when nothing else is left."""
    cand = [i for i, st in enumerate(stages) if st["pic"] and not st["env"]]
    lit = [i for i in cand if (stages[i]["b"][1] or "").lower() == "$lightmap"]
    if lit:
        return lit[-1]
    if editor:
        ed = _img_key(editor)
        for i in cand:
            b = stages[i]["blend"] or ""
            if _img_key(stages[i]["pic"]) == ed and not b.startswith(_ADD_BLENDS):
                return i
    solid = None
    for i in cand:
        b = stages[i]["blend"]
        if (b is None or b == "gl_one gl_zero") and not (stages[i]["cut"] and solid is not None):
            solid = i
    if solid is not None:
        return solid
    for i in cand:
        if (stages[i]["blend"] or "") in _FILTER_BLENDS:
            return i
    if cand:
        return cand[0]
    for i, st in enumerate(stages):
        if st["pic"]:
            return i
    return None


def _tcmod_scale(tcmods):
    """The texture scale a stage's tcMods give at time zero (scroll, rotate, turb and
    the other moving ones start at no change): RB_CalcScaleTexCoords multiplies."""
    ss = st = 1.0
    for m in tcmods:
        if m[0] == "scale" and len(m) >= 3:
            try:
                ss *= float(m[1])
                st *= float(m[2])
            except ValueError:
                pass
    return None if (ss == 1.0 and st == 1.0) else [ss, st]


def _alpha_gen(agen):
    """A stage's alphaGen as the page can use it (tr_shade.c ComputeColors):
    ["c", a] constant, ["s"|"t", min, max, low, high] from the base texture coordinate
    (RB_CalcAlphaFromTexCoords), ["v"] / ["1v"] vertex alpha; None for anything else."""
    if not agen:
        return None
    kind, args = agen[0], agen[1:]
    nums = []
    for a in args:
        try:
            nums.append(float(a.rstrip(".")))
        except ValueError:
            break
    if kind in ("const", "constant") and nums:
        return ["c", max(0.0, min(1.0, nums[0]))]
    if kind in ("scoord", "tcoord"):
        lo, hi = (nums + [0.0, 1.0])[:2]
        cap_lo = nums[2] if len(nums) > 2 else 0.0
        cap_hi = nums[3] if len(nums) > 3 else 1.0
        return [kind[0], lo, hi, cap_lo, cap_hi]
    if kind == "vertex":
        return ["v"]
    if kind == "oneminusvertex":
        return ["1v"]
    return None


def _atof(word):
    """C's atof: the number at the start of a word, else 0 ("-" and "fromEntity" give 0)."""
    m = re.match(r"\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", word or "")
    return float(m.group(0)) if m else 0.0


def parse_shaders(txt, out):
    """Every shader block in one .shader script, as the map viewer needs it:
    {name_lower: {"name", "editor", "light", "map", "parms", "trans", "keywords",
                  "blend0", "alphafunc", "cull", "sky", "sprite", "lod", "anim",
                  "lmstage", "nst", "rgb0", "ptm", "pag", "pdw"}}, and for a sky shader
    "skyh" (its cloud height) and "clouds" (its stages).
    "map" is the picture the game shows ("ptm", "pag", "pdw": its stage's texture
    scale, alphaGen and depthWrite). Later definitions of the same name replace
    earlier ones, as in the engine."""
    t = _strip_comments(txt)
    i, n = 0, len(t)
    while i < n:
        m = _SHADER_NAME.match(t, i)
        if not m:
            nl = t.find("\n", i)
            if nl < 0:
                break
            i = nl + 1
            continue
        name = m.group(1)
        j = m.end() - 1
        depth = 0
        k = j
        while k < n:
            c = t[k]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        body = t[j + 1:k]
        i = k + 1
        info = {"name": name, "editor": None, "light": None, "map": None, "parms": [],
                "trans": None, "keywords": [], "blend0": None, "alphafunc": None,
                "cull": None, "sky": None, "sprite": False, "lod": False, "anim": None,
                "stage0map": None,
                # how the game lights it: a $lightmap stage, the number of stages and the
                # first stage's rgbGen (tr_shader.c ParseStage / R_FindShader)
                "lmstage": False, "nst": 0, "rgb0": ""}
        # Split the body into its top-level lines and its { stage } blocks.
        stages = []
        top = []
        d = 0
        cur = []
        for ch_line in re.split(r"(\{|\})", body):
            if ch_line == "{":
                d += 1
                if d == 1:
                    cur = []
                    continue
            elif ch_line == "}":
                d -= 1
                if d == 0:
                    stages.append("".join(cur))
                    continue
            if d >= 1:
                cur.append(ch_line)
            else:
                top.append(ch_line)
        for line in "".join(top).splitlines():
            tok = line.split()
            if not tok:
                continue
            kw = tok[0].lower()
            if kw == "qer_editorimage" and len(tok) > 1:
                info["editor"] = tok[1]
            elif kw == "q3map_lightimage" and len(tok) > 1:
                info["light"] = tok[1]
            elif kw == "surfaceparm" and len(tok) > 1:
                info["parms"].append(tok[1].lower())
            elif kw == "qer_trans" and len(tok) > 1:
                try:
                    info["trans"] = float(tok[1])
                except ValueError:
                    pass
            elif kw == "qer_keyword" and len(tok) > 1:
                info["keywords"].append(tok[1].lower())
            elif kw == "cull" and len(tok) > 1:
                info["cull"] = tok[1].lower()
            elif kw == "nocull":
                info["cull"] = "none"
            elif kw == "skyparms" and len(tok) > 1:
                info["sky"] = tok[1]
                # the cloud height (ParseSkyParms): atof of the word, 0 or "-" meaning 512;
                # with no word at all the shader has no cloud layers
                info["skyh"] = (_atof(tok[2]) or 512.0) if len(tok) > 2 else 0.0
            elif (kw == "deformvertexes" and len(tok) > 1 and tok[1].lower().startswith("autosprite")) \
                    or kw == "spritegen":
                info["sprite"] = True
        info["nst"] = len(stages)
        sts = [_parse_stage(st) for st in stages]
        # A sky shader's stages are its cloud layers, drawn over the far box
        # (tr_sky.c R_BuildCloudData). Kept as written; sky_clouds() turns them into what
        # the page draws.
        if info["sky"] is not None and info.get("skyh"):
            info["clouds"] = [{"pic": st["map0"], "blend": st["blend"], "afunc": st["afunc"],
                               "rgb": st["rgbx"], "agen": st["agen"], "tcmod": st["tcmod"]}
                              for st in sts if st["map0"] and not st["map0"].startswith(("$", "*"))]
        # A tree's long-range stand-in: an autoSprite2 card that fades in with distance
        # (alphaGen oneMinusDistFade) as the tree's own leaf cards fade out (plain distFade).
        # The Model Viewer's isLodSprite uses the same pairing.
        info["lod"] = bool(re.search(r"(?im)^\s*deformvertexes\s+autosprite2\b", "".join(top))) and any(
            (st["agen"] or [""])[0] in ("oneminusdistfade", "oneminustikidistfade") for st in sts)
        for si, st in enumerate(sts):
            if st["lm"]:
                info["lmstage"] = True
            if st["afunc"] and info["alphafunc"] is None:
                info["alphafunc"] = st["afunc"]
            if st["anim"] and info["anim"] is None:
                info["anim"] = st["anim"]
        if sts:
            info["stage0map"] = sts[0]["map0"]
            info["blend0"] = sts[0]["blend"]
            info["rgb0"] = sts[0]["rgb"] or ""
        # The picture the game shows, and how its stage draws it (the game's lighting
        # uses these: the stage's texture scale, alphaGen and depthWrite).
        pi = _picture_stage(sts, info["editor"])
        if pi is not None:
            ps = sts[pi]
            info["map"] = ps["pic"]
            info["ptm"] = _tcmod_scale(ps["tcmod"])
            info["pag"] = _alpha_gen(ps["agen"])
            info["pdw"] = ps["dw"]
        out[name.lower()] = info
    return out


def shader_render_bits(info):
    """(TF_* bits, contents bits, surface bits) for a shader."""
    bits = 0
    cont = 0
    surf = 0
    for p in info["parms"]:
        c, s = SURFACEPARMS.get(p, (0, 0))
        cont |= c
        surf |= s
    if surf & 0x4 or info["sky"]:
        bits |= TF_SKY
    if surf & 0x80:
        bits |= TF_NODRAW
    if info["alphafunc"] in ("gt0", "lt128", "ge128"):
        bits |= TF_ALPHATEST
    # The first stage's blendFunc decides whether the surface is solid or see-through in
    # game (tr_shader.c FinishShader); a lightmap stage first means solid.
    b0 = info["blend0"] or ""
    s0 = info.get("stage0map") or ""
    if b0 and not s0.startswith("$"):
        if b0 in ("add", "gl_one gl_one", "alphaadd") or (
                b0.startswith("gl_src_alpha gl_one") and not b0.startswith("gl_src_alpha gl_one_minus")):
            bits |= TF_ADD
        elif b0.startswith(("blend", "gl_src_alpha gl_one_minus_src_alpha",
                            "gl_one_minus_src_alpha", "gl_one gl_one_minus_src_alpha")):
            bits |= TF_BLEND
        elif b0.startswith(("filter", "gl_dst_color gl_zero", "gl_zero gl_src_color")):
            bits |= TF_FILTER
    if info["cull"] in ("none", "disable", "twosided"):
        bits |= TF_TWOSIDED
    if info["sprite"]:
        bits |= TF_SPRITE
    if info.get("lod"):
        bits |= TF_LOD
    return bits, cont, surf


def util_group(name, cont, surf):
    """Which editor-only group a texture belongs to ('' for ordinary textures):
    caulk, clip, trigger, origin, hint, skip, portal, nodraw, ladder, liquid, fog, sky."""
    nl = name.lower()
    base = nl.rsplit("/", 1)[-1]
    if nl.startswith("textures/common/") or nl.startswith("common/"):
        for grp, names in _UTIL_NAMES:
            if base in names:
                return grp
        if base.endswith("clip") or base in ("monster", "weapon", "clipall"):
            return "clip"
    if cont & (0x10000 | 0x20000 | 0x40000 | 0x80000) and surf & 0x80:
        return "clip"
    if cont & 0x1000000:
        return "origin"
    if cont & 0x8000:
        return "portal"
    if surf & 0x40000000:
        return "hint"
    if cont & (0x8 | 0x10 | 0x20):
        return "liquid"
    if cont & 0x40:
        return "fog"
    return ""


# ==============================================================================
#  The legend: what the viewer's colours, markers and editor surfaces mean
# ==============================================================================
# One table for the page's legend (L) and the launcher's Help > Legend (F2). A row's
# "sw" says how its swatch is drawn: "node" (a path node: "fill", and "line" for its
# border), "box" (a filled square), "diamond" (a light), "wire" (a setsize box: a wire
# cube in "fill"), "arrow" (a facing arrow), "link" (a target link), "label", "sel" (the
# selection tint), "hover" (the outline of what is under the mouse) or "tex" (the editor
# picture of the shader "tex"; "fill" stands in when the paks don't have it). "key" is
# the viewer's toggle for that group. {"sub": text} is a small heading inside a section.
# Each section is one column in both legends. The path-node colours follow radiantLook /
# NODE_OUTLINES in the page, which draw them.
# Line swatches for the game cvars' rows: [x0, y0, x1, y1, colour] on a 24 x 24 dark square
_LEG_ROUTE = [[3, 20, 21, 5, [0, 1, 0]]]
_LEG_ONEWAY = [[10, 14, 9, 20, [1, 0, 0]], [10, 14, 4, 13, [1, 0, 0]]]
_LEG_X = [[5, 5, 19, 19, [1, 0, 0]], [19, 5, 5, 19, [1, 0, 0]]]
_LEG_CIRCLE = [[round(12 + 8 * math.sin(k * math.pi / 6), 2), round(12 + 8 * math.cos(k * math.pi / 6), 2),
                round(12 + 8 * math.sin((k + 1) * math.pi / 6), 2), round(12 + 8 * math.cos((k + 1) * math.pi / 6), 2),
                [0, 0, 1]] for k in range(12)]
_LEG_TRIS = [[3, 20, 12, 4, [1, 1, 1]], [12, 4, 21, 20, [1, 1, 1]], [21, 20, 3, 20, [1, 1, 1]], [12, 4, 12, 20, [1, 1, 1]]]
_LEG_CROSS = [[12, 3, 12, 21, [1, 0, 0]], [3, 12, 21, 12, [0, 1, 0]], [6, 18, 18, 6, [0, 0, 1]]]

LEGEND = [
    {"title": "AI path nodes (info_pathnode)",
     "note": "Coloured the way MOHRadiant colours them. Select a node and press N to see which of these "
             "apply to it.",
     "rows": [
         {"sw": "node", "fill": [0, 0.5, 0], "name": "Plain node",
          "desc": "Dark green 16-unit cube. MOHRadiant has no definition for info_pathnode, so it draws "
                  "its stand-in class."},
         {"sw": "node", "fill": [1, 0.5, 1], "name": "Has a targetname",
          "desc": "Pink: MOHRadiant turns a path node's colour inside out when it has a \"targetname\" "
                  "(\"target\" and \"$targetname\" don't count)."},
         {"sw": "node", "fill": [0.408, 0.976, 0.906], "name": "Has a _color key",
          "desc": "Flat in that colour, like the cyan friendlynodes."},
         {"sub": "Border, by spawnflags (the first that applies wins)"},
         {"sw": "node", "fill": [0, 0.5, 0], "line": [0, 1, 0], "name": "COVER (4)",
          "desc": "A good place to hide during weapon fire. Also the border of COVER together with DUCK, "
                  "a CORNER or CRATE."},
         {"sw": "node", "fill": [0, 0.5, 0], "line": [1, 1, 0], "name": "CORNER_LEFT (16)",
          "desc": "A place to fire around a corner to the left."},
         {"sw": "node", "fill": [0, 0.5, 0], "line": [0.7, 1, 0], "name": "CORNER_RIGHT (32)",
          "desc": "A place to fire around a corner to the right."},
         {"sw": "node", "fill": [0, 0.5, 0], "line": [1, 0, 0], "name": "SNIPER (64)",
          "desc": "A sniper spot: the AI goes there to target the enemy when running at it is awkward."},
         {"sw": "node", "fill": [0, 0.5, 0], "line": [0.5, 0, 0], "name": "CRATE (128)",
          "desc": "A place to stand up and fire over."},
         {"sw": "node", "fill": [0, 0.5, 0], "line": [0, 0, 1], "name": "CONCEALMENT (8)",
          "desc": "Cover that isn't sight-checked: foliage and combat spots."},
         {"sw": "node", "fill": [0, 0.5, 0], "line": [0, 1, 1], "name": "DUCK (2)",
          "desc": "A good place to crouch during weapon fire."},
         {"sw": "node", "fill": [0, 0.5, 0], "line": [0, 0, 0], "name": "Black",
          "desc": "Flags that don't go together, such as 130 (CRATE + DUCK) or 10 (DUCK + CONCEALMENT). "
                  "The game's ai_editmode marks the same nodes."},
         {"sw": "node", "fill": [0, 0.5, 0], "name": "No border",
          "desc": "No node type: spawnflags 0, or only DONT_LINK (1) or LOW_WALL_ARC (256)."},
         {"sub": "ai_showroutes (the game cvars list, `)"},
         {"sw": "lines", "lines": _LEG_ROUTE, "name": "Path both ways",
          "desc": "A path the AI can walk between two nodes, 36 units up, as the game worked it out (the "
                  "map's .pth). Only the nodes within ai_showroutes_distance of the camera draw theirs."},
         {"sw": "lines", "lines": _LEG_ROUTE + _LEG_ONEWAY, "name": "One way",
          "desc": "The AI can only go one way: the way back drops further than ai_fallheight. The red "
                  "arrowhead, 16 units along it, points the way it goes."},
         {"sw": "lines", "lines": _LEG_X, "name": "No paths",
          "desc": "A red X on the floor: a node the game found no path from."},
         {"sw": "lines", "lines": _LEG_CIRCLE, "name": "Not linked",
          "desc": "A blue circle: a node marked DONT_LINK (spawnflags 1), which the game never connects."},
     ]},
    {"title": "Entities",
     "rows": [
         {"sw": "box", "fill": [0, 0.5, 0], "name": "Small dark green cube",
          "desc": "A class MOHRadiant shows as \"Not found in source.\": the classes defined in the game "
                  "code (player starts, script origins, spline paths, grenade hints...). It draws its "
                  "stand-in, a 16-unit cube on the origin."},
         {"sw": "box", "fill": [0.5, 0, 0.5], "name": "Class colour",
          "desc": "A class defined in a .tik: the colour and box of its definition."},
         {"sw": "box", "fill": [0.957, 0.592, 0.043], "name": "_color key",
          "desc": "A point entity with a \"_color\" key is painted flat in that colour."},
         {"sw": "diamond", "fill": [1, 0.92, 0.6], "name": "Light", "key": "Alt+0",
          "desc": "A light entity, in its light colour."},
         {"sw": "wire", "fill": [0.8, 0.55, 1], "name": "Setsize box", "key": "4",
          "desc": "An entity's bounding box (its origin plus setsize), in the entity's colour. The "
                  "selection always shows its own, in red."},
         {"sw": "arrow", "name": "Facing arrow", "key": "5",
          "desc": "Which way an entity with an angle faces, drawn as MOHRadiant draws it."},
         {"sw": "link", "fill": [0.6, 0.75, 1], "name": "Target link", "key": "7",
          "desc": "From an entity to the ones its \"target\" names, in that entity's colour; the "
                  "arrowhead points at the target."},
         {"sw": "label", "name": "Label", "key": "6",
          "desc": "Class and $targetname over nearby entities; in the accent colour when the entity has "
                  "a targetname."},
         {"sw": "sel", "name": "Selection",
          "desc": "Tinted red, as in MOHRadiant. With X-ray (9) its outline, box and links show faintly "
                  "through walls."},
         {"sw": "hover", "name": "Under the mouse",
          "desc": "Outlined in the accent colour: a brush's edges, or a model's or marker's box."},
         {"sub": "r_showtris (the game cvars list, `)"},
         {"sw": "lines", "lines": _LEG_TRIS, "name": "Triangle outlines",
          "desc": "Every triangle the game draws from where the camera is: only what is in its PVS and "
                  "in an area joined to its own. 1 hides them behind walls, 2 shows them through walls."},
         {"sw": "lines", "lines": _LEG_CROSS, "name": "Axis cross",
          "desc": "r_showtris 2 or 3: the origin of the world and of each brush entity and model drawn. "
                  "Red up, green along y, blue a diagonal (the engine's own slip)."},
     ]},
    {"title": "Brushes and editor surfaces",
     "note": "Editor-only textures are drawn see-through with their editor picture, as MOHRadiant shows "
             "them; the game never draws them. The Show buttons hide each group.",
     "rows": [
         {"sw": "tex", "tex": "textures/common/caulk", "name": "caulk", "key": "Alt+6",
          "desc": "Never drawn, but solid. Goes on faces nobody can see, so the game skips them."},
         {"sw": "tex", "tex": "textures/common/caulkshadow", "name": "caulkshadow",
          "desc": "Caulk that still casts shadows when the map is lit."},
         {"sw": "tex", "tex": "textures/common/sunblock", "name": "sunblock",
          "desc": "Not drawn; blocks sunlight when the map is lit."},
         {"sw": "tex", "tex": "textures/common/clip", "name": "clip", "key": "Alt+7",
          "desc": "Blocks players and AI. Bullets, grenades and vehicles pass."},
         {"sw": "tex", "tex": "textures/common/playerclip", "name": "playerclip",
          "desc": "Blocks players (and the camera) only."},
         {"sw": "tex", "tex": "textures/common/monster", "name": "monster",
          "desc": "Blocks AI only: their movement and their paths."},
         {"sw": "tex", "tex": "textures/common/weapon", "name": "weapon",
          "desc": "Blocks bullets, grenades and explosions only (and AI sight)."},
         {"sw": "tex", "tex": "textures/common/vehicleclip", "name": "vehicleclip",
          "desc": "Blocks vehicles only."},
         {"sw": "tex", "tex": "textures/common/clipall", "name": "clipall",
          "desc": "Blocks players, AI, vehicles and bullets."},
         {"sw": "tex", "tex": "textures/common/tankclip", "name": "tankclip, grillclip",
          "desc": "Block everything, with metal or metal-grate hits."},
         {"sw": "tex", "tex": "textures/common/hedgehogclip", "name": "hedgehogclip, bplaneclip, bspindleclip",
          "desc": "Block players, AI and vehicles; bullets hit only the solid parts of the picture "
                  "(a fence mask)."},
         {"sw": "tex", "tex": "textures/common/woodclip", "name": "Material clips",
          "desc": "metalclip, woodclip, stoneclip, dirtclip, grassclip, gravelclip, mudclip, sandclip, "
                  "snowclip, glassclip, carpetclip, paperclip, puddleclip: invisible but solid, with that "
                  "material's footsteps and bullet hits."},
         {"sw": "tex", "tex": "textures/common/foliageclip", "name": "foliageclip", "key": "Ctrl+G",
          "desc": "Walk-through; bullets hitting it make foliage effects. Shown and hidden apart from "
                  "the other clips."},
         {"sw": "tex", "tex": "textures/common/trigger", "name": "trigger", "key": "Ctrl+T",
          "desc": "The volume of a trigger_* entity: walking into it (or using it) fires the trigger."},
         {"sw": "tex", "tex": "textures/common/hint", "name": "hint", "key": "Ctrl+H",
          "desc": "Tells the compiler where to split the map for visibility. Not drawn, not solid."},
         {"sw": "tex", "tex": "textures/common/vis", "name": "vis",
          "desc": "MOHAA's other hint texture; the same job as hint."},
         {"sw": "tex", "tex": "textures/common/skip", "name": "skip",
          "desc": "The sides of a hint brush that shouldn't split anything."},
         {"sw": "tex", "tex": "textures/common/waterskip", "name": "waterskip",
          "desc": "Water with no surface drawn."},
         {"sw": "tex", "tex": "textures/common/areaportal", "name": "areaportal", "key": "Ctrl+P",
          "desc": "Splits the map into areas that a closed door shuts off from view."},
         {"sw": "tex", "tex": "textures/common/origin", "name": "origin",
          "desc": "The pivot of a door or other moving brush entity."},
         {"sw": "tex", "tex": "textures/common/nodraw", "name": "nodraw", "key": "Ctrl+O",
          "desc": "Not drawn and not solid. The Nodraw button hides it, with ladder, patharea and "
                  "commontreeshadow."},
         {"sw": "tex", "tex": "textures/common/rain", "name": "rain", "key": "Ctrl+I",
          "desc": "The volume of a func_rain entity: the game makes it rain (or snow) inside it. Not "
                  "drawn, not solid. Hidden until you show it."},
         {"sw": "tex", "tex": "textures/misc_outside/commontreeshadow", "name": "commontreeshadow",
          "desc": "A flat picture of a tree, put beside a tree model so the tree casts a shadow when the "
                  "map is lit. It's a world brush, not part of the tree: the game never draws it, and the "
                  "Nodraw button hides it."},
         {"sw": "tex", "tex": "textures/common/ladder", "name": "ladder",
          "desc": "A climbable surface."},
         {"sw": "box", "fill": [0.45, 0.62, 0.86], "name": "Sky", "key": "Ctrl+K",
          "desc": "The game draws its sky box, and the sky's cloud layers, behind everything there, "
                  "so whatever is behind a sky brush shows through it. Simple Sky (K) draws them "
                  "solid and tiled, as MOHRadiant does."},
         {"sw": "tex", "tex": "textures/common/caulksky", "name": "caulksky", "key": "Ctrl+K",
          "desc": "Sky with no sky box. The game clears it to the fog colour (worldspawn "
                  "farplane_color), or leaves the last frame's picture there on a map without fog. "
                  "The viewer draws it in farplane_color, or the backdrop when there is none."},
         {"sw": "box", "fill": [0.18, 0.38, 0.62], "name": "Water, slime, lava, fog", "key": "Alt+5",
          "desc": "Liquid and fog volumes."},
         {"sw": "box", "fill": [0.68, 0.83, 0.88], "name": "Translucent", "key": "Alt+4",
          "desc": "Glass, decals, light beams and other see-through surfaces."},
         {"sw": "box", "fill": [0.55, 0.52, 0.48], "name": "Detail brushes", "key": "Ctrl+D",
          "desc": "Brushes left out of the visibility tree (trim, props)."},
         {"sw": "box", "fill": [0.5, 0.5, 0.5], "name": "Not in the paks",
          "desc": "A texture the loaded paks don't have, drawn flat grey. The Textures list marks it "
                  "(missing)."},
     ]},
]


# The map viewer's keyboard shortcuts: the page's H window, and the launcher's F1 window
# on its "3D viewer" tab. The format is the Model Viewer's (VIEWER_KEYS and the notes
# above it in mohaa_view.py): a heading is _kx_sub(title, category, view) and a row is
# _kx(keys as shown, what they do, (chord, keycap label[, what this key does]) ...).
# Keep it in step with the page's key handlers (keydown and the mouse in
# mohaa_map_page.py) and the FILTERS / DISPLAY buttons.
def _kx_sub(title, cat, view=None):
    d = {"sub": title, "c": cat}
    if view:
        d["v"] = view
    return d


def _kx(keys, text, *binds):
    return {"k": keys, "d": text, "b": [list(b) for b in binds]}


MAP_VIEWER_KEYS = {
    "title": "Map viewer keyboard shortcuts",
    "views": [{"id": "free", "name": "Free-look"}, {"id": "rad", "name": "Radiant-look"}],
    "cols": [
        {"title": "Camera", "rows": [
            _kx_sub("Free-look camera", "cam", "free"),
            _kx("W|S", "move forward / back", ("W", "forward", "move forward"), ("S", "back", "move back")),
            _kx("Up|Down", "move forward / back", ("Up", "forward", "move forward"), ("Down", "back", "move back")),
            _kx("A|D", "strafe left / right", ("A", "left", "strafe left"), ("D", "right", "strafe right")),
            _kx("Space|C", "move up / down", ("Space", "up", "move up"), ("C", "down", "move down")),
            _kx("Q|E", "tilt (roll) left / right", ("Q", "tilt L", "tilt (roll) left"),
                ("E", "tilt R", "tilt (roll) right")),
            _kx("Left|Right", "turn left / right", ("Left", "turn L", "turn left"), ("Right", "turn R", "turn right")),
            _kx("right-drag", "look around, as drag does", ("RDrag", "look", "look around")),
            _kx_sub("Radiant-look camera (MOHRadiant's keys)", "cam", "rad"),
            _kx("right-drag", "fly: push the mouse up to go forward, left / right to turn", ("RDrag", "fly")),
            _kx("Up|Down", "move forward / back", ("Up", "forward", "move forward"), ("Down", "back", "move back")),
            _kx("Left|Right", "turn left / right", ("Left", "turn L", "turn left"), ("Right", "turn R", "turn right")),
            _kx(",|.", "strafe left / right", (",", "left", "strafe left"), (".", "right", "strafe right")),
            _kx("D|C", "move up / down", ("D", "up", "move up"), ("C", "down", "move down")),
            _kx("A|Z", "look up / down", ("A", "look up", "look up"), ("Z", "look dn", "look down")),
            _kx("Ctrl+Up|Down|,|.", "one grid step (64 units) forward / back / left / right",
                ("Ctrl+Up", "step", "one grid step forward"), ("Ctrl+Down", "step", "one grid step back"),
                ("Ctrl+,", "step", "one grid step left"), ("Ctrl+.", "step", "one grid step right")),
            _kx_sub("Both cameras", "cam"),
            _kx("drag", "look around", ("Drag", "look")),
            _kx("wheel", "move forward / back (with Shift, 4x as far)", ("Wheel", "move", "move forward / back"),
                ("Shift+Wheel", "move x4", "move forward / back, 4x as far")),
            _kx("middle-drag", "slide (strafe / rise)", ("MDrag", "slide")),
            _kx("Shift", "hold to move and turn faster (4x)", ("Shift", "faster", "hold: move and turn 4x faster")),
            _kx("V", "switch Free-look / Radiant-look", ("V", "camera")),
            _kx("R", "back to the player start", ("R", "start")),
            _kx("F|double-click", "fly to the selection", ("F", "fly to"), ("DblClick", "fly to")),
            _kx("End", "level the view", ("End", "level")),
            _kx("PgUp|PgDn", "up / down one floor", ("PgUp", "floor up", "up one floor"),
                ("PgDn", "floor dn", "down one floor")),
            _kx("[|]", "cubic clip nearer / further", ("[", "clip -", "cubic clip nearer"),
                ("]", "clip +", "cubic clip further")),
            _kx("Ctrl+\\", "cubic clipping on / off", ("Ctrl+\\", "clip")),
            _kx("X", "stop the camera (if it keeps moving after a click outside the map)", ("X", "stop", "stop the camera")),
        ]},
        {"title": "Selecting and window", "rows": [
            _kx_sub("Selecting", "sel"),
            _kx("click", "select a brush or entity (empty space clears the selection)", ("Click", "select")),
            _kx("Shift+click", "add to / remove from the selection", ("Shift+Click", "add")),
            _kx("Ctrl+click", "select it and show more info", ("Ctrl+Click", "info")),
            _kx("Alt+click", "select everything of the same kind: the same class, or the same texture (Same "
                "kind); with Shift, add them",
                ("Alt+Click", "same", "select everything of the same kind: the same class, or the same texture"),
                ("Alt+Shift+Click", "+ same", "add everything of the same kind to the selection")),
            _kx("Ctrl+Alt+click", "select the whole path through an entity: its \"target\" chain, before and "
                "after it (Same path); with Shift, add it",
                ("Ctrl+Alt+Click", "path", "select the whole path through an entity: its \"target\" chain"),
                ("Ctrl+Alt+Shift+Click", "+ path", "add the whole path through an entity to the selection")),
            _kx("$", "select every entity with the selected one's targetname (Same targetname)",
                ("Shift+4", "$name", "select every entity with the same targetname")),
            _kx("O", "open / close the selected door, as in game (Open door)",
                ("O", "door", "open / close the selected door")),
            _kx("Shift+click", "on a coloured square in the Find lists: hide / show that entity, or every entity "
                "of that class",
                ("Shift+Click", "hide", "on a Find list's coloured square: hide / show that entity or class")),
            _kx("Ctrl+Shift+click|middle-click", "the clicked face's texture",
                ("Ctrl+Shift+Click", "texture"), ("MClick", "texture")),
            _kx("N", "more info on the selection", ("N", "info")),
            _kx("Backspace", "hide the selection", ("Backspace", "hide")),
            _kx("Shift+H", "show everything hidden", ("Shift+H", "show all")),
            _kx("Ctrl+Z", "undo the last hide or show-all (again for the one before)", ("Ctrl+Z", "undo")),
            _kx("Ctrl+F or /", "find: class, targetname, key, texture", ("Ctrl+F", "find"), ("/", "find")),
            _kx_sub("Window", "win"),
            _kx("H or ?", "show / hide this window", ("H", "keys", "show / hide the keyboard shortcuts"),
                ("Shift+/", "keys", "show / hide the keyboard shortcuts")),
            _kx("L", "the legend: what the colours, markers and editor surfaces mean", ("L", "legend")),
            _kx("T", "light / dark theme", ("T", "theme")),
            _kx("\\", "collapse / expand the control panel", ("\\", "panel")),
            _kx("Esc", "close a card / clear the selection / close the map (one a press)", ("Esc", "back")),
        ]},
        {"title": "Show / hide and display", "rows": [
            _kx_sub("Show / hide (as in MOHRadiant)", "show"),
            _kx("Alt+1 … Alt+0", "World · Entities · Patches · Translucent · Liquids · Caulk · Clips · Paths · "
                "AI nodes · Lights",
                ("Alt+1", "World", "show / hide the world brushes"),
                ("Alt+2", "Entities", "show / hide every entity"),
                ("Alt+3", "Patches", "show / hide the curved patches"),
                ("Alt+4", "Transl.", "show / hide see-through surfaces: glass, decals, effects"),
                ("Alt+5", "Liquids", "show / hide water, slime, lava and fog volumes"),
                ("Alt+6", "Caulk", "show / hide caulk"),
                ("Alt+7", "Clips", "show / hide the clips (player, monster, weapon, vehicle ...)"),
                ("Alt+8", "Paths", "show / hide spline paths and waypoints"),
                ("Alt+9", "AI nodes", "show / hide the AI path nodes (info_pathnode)"),
                ("Alt+0", "Lights", "show / hide the light entities")),
            _kx("Ctrl+D|H|M", "Details · Hints and skips · Models",
                ("Ctrl+D", "Details", "show / hide the detail brushes"),
                ("Ctrl+H", "Hints", "show / hide hint and skip brushes"),
                ("Ctrl+M", "Models", "show / hide every entity drawn with a model")),
            _kx("Ctrl+R|T|P|K", "Terrain · Triggers · Areaportals · Sky",
                ("Ctrl+R", "Terrain", "show / hide the LOD terrain"),
                ("Ctrl+T", "Triggers", "show / hide triggers"),
                ("Ctrl+P", "Portals", "show / hide areaportals"),
                ("Ctrl+K", "Sky", "show / hide the sky brushes")),
            _kx("Ctrl+O|I|G", "Nodraw · Rain (hidden at first) · Foliage clips",
                ("Ctrl+O", "Nodraw", "show / hide nodraw, ladders, patharea and tree-shadow cards"),
                ("Ctrl+I", "Rain", "show / hide the rain volumes (hidden at first)"),
                ("Ctrl+G", "Foliage", "show / hide the foliage clips")),
            _kx("Ctrl+A", "show every group (All)", ("Ctrl+A", "All")),
            _kx("G", "In-game look: hide what the game never draws, with the game's light and sky",
                ("G", "in-game")),
            _kx("Shift+G", "Editor look: MOHRadiant's view, at full brightness with Simple Sky",
                ("Shift+G", "editor")),
            _kx("B", "Full Brightness on / off (off: the game's own lighting)", ("B", "bright")),
            _kx("K", "Simple Sky on / off (off: the game's sky)", ("K", "sky")),
            _kx("M", "Simple models on / off: trees drawn as the sprite the game shows far away",
                ("M", "simple")),
            _kx_sub("Display", "disp"),
            _kx("1 … 9", "Texture · Shade · Wire · Setsizes · Arrows · Labels · Links · Fog · X-ray",
                ("1", "Texture", "Texture on / off (off: each texture's average colour)"),
                ("2", "Shade", "Shade: MOHRadiant's face shading on / off"),
                ("3", "Wire", "Wire: outline every brush face, patch and terrain block"),
                ("4", "Setsizes", "Setsizes: every entity's bounding box"),
                ("5", "Arrows", "Arrows: which way entities with an angle face"),
                ("6", "Labels", "Labels: class and $targetname over nearby entities"),
                ("7", "Links", "Links: a line from each entity to its targets"),
                ("8", "Fog", "Fog: the map's distance fog"),
                ("9", "X-ray", "X-ray: the selection's outline through walls")),
            _kx("`", "the game cvars list: r_showtris, ai_showroutes ... (type a cvar and its value, then "
                "Enter, as in the game's console)", ("`", "cvars", "open / close the game cvars list")),
        ]},
    ]}


def _legend_thumb(data, size):
    """A size x size PNG of an editor picture for the legend, in the cache's
    (mime, bytes, average colour, has alpha) form. A cut-out picture (an alpha channel
    with both see-through and solid parts, such as the tree in commontreeshadow) is laid
    on grey, so its shape shows."""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        rgba = im.convert("RGBA")
        lo, hi = rgba.getchannel("A").getextrema()
        if lo < 128 <= hi:
            im = Image.new("RGBA", rgba.size, (110, 110, 110, 255))
            im.alpha_composite(rgba)
    im = im.convert("RGB").resize((size, size), Image.BILINEAR)
    avg = tuple(round(c / 255.0, 3) for c in im.resize((1, 1), Image.BOX).getpixel((0, 0)))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "image/png", buf.getvalue(), avg, False


def legend_thumbs(vfs, shaders, cache=None, size=48):
    """{shader: (mime, bytes, average colour, False)}: the editor picture of every
    texture in LEGEND, found the way the page finds a utility texture's picture (its
    qer_editorimage, else the image named after the shader, else its first map)."""
    out = {}
    if vfs is None or not _have_pil():
        return out
    for sec in LEGEND:
        for row in sec["rows"]:
            name = row.get("tex")
            if not name or name in out:
                continue
            info = (shaders or {}).get(name) or {}
            img = None
            for ref in (info.get("editor"), name, info.get("map")):
                img = vfs.find_texture(ref) if ref else None
                if img:
                    break
            if not img:
                continue
            ckey = "legend2|%s|%s|%d" % (vfs.pak_of(img), img, size)
            val = cache.get(ckey) if cache else None
            if val is None:
                data = vfs.read(img)
                try:
                    val = _legend_thumb(data, size) if data else None
                except Exception:
                    val = None
                if val and cache:
                    cache.put(ckey, val)
            if val:
                out[name] = val
    return out


# ==============================================================================
#  Images
# ==============================================================================
def image_dims(data):
    """(width, height) from an image file's header (TGA, JPEG, PNG, DDS), or None."""
    try:
        return _image_dims(data)
    except struct.error:                      # a truncated header
        return None


def _image_dims(data):
    if not data or len(data) < 18:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i, n = 2, len(data)
        while i + 9 < n:
            if data[i] != 0xFF:
                i += 1
                continue
            mk = data[i + 1]
            if 0xC0 <= mk <= 0xCF and mk not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return (w, h)
            if mk in (0xD8, 0xD9) or 0xD0 <= mk <= 0xD7:
                i += 2
                continue
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
        return None
    if data[:4] == b"DDS ":
        h, w = struct.unpack("<II", data[12:20])
        return (w, h)
    w, h = struct.unpack("<HH", data[12:16])          # TGA
    if 0 < w <= 8192 and 0 < h <= 8192:
        return (w, h)
    return None


def _have_pil():
    """Is Pillow installed? (Without it the map draws untextured.)"""
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


def encode_image(data, max_dim, keep_alpha):
    """Decode a texture file, shrink it to max_dim and re-encode it for the page.
    Returns (mime, bytes, (avg r, g, b) in 0..1, has_alpha) or None. Opaque pictures
    become JPEG; ones whose alpha matters (fences, foliage, windows) stay PNG."""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    if max(im.size) > max_dim:
        r = max_dim / float(max(im.size))
        im = im.resize((max(1, int(round(im.size[0] * r))), max(1, int(round(im.size[1] * r)))),
                       Image.BILINEAR)
    alpha = keep_alpha and ("A" in im.getbands() or im.mode == "P")
    if alpha:
        im = im.convert("RGBA")
        lo, _hi = im.getchannel("A").getextrema()
        alpha = lo < 250
    small = im.convert("RGB").resize((1, 1), Image.BOX)
    avg = tuple(round(c / 255.0, 3) for c in small.getpixel((0, 0)))
    buf = io.BytesIO()
    if alpha:
        im.save(buf, "PNG", optimize=False)
        return "image/png", buf.getvalue(), avg, True
    im.convert("RGB").save(buf, "JPEG", quality=82)
    return "image/jpeg", buf.getvalue(), avg, False


class TextureCache:
    """Encoded textures kept on disk between builds (maps share most of their
    textures), keyed by pak, file, size and mode."""

    def __init__(self, folder):
        self.folder = folder
        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                self.folder = None

    def _path(self, key):
        """The cache file for a key (a hash of it, so any key makes a safe file name)."""
        h = hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:24]
        return os.path.join(self.folder, h + ".tex")

    def get(self, key):
        """(mime, bytes, average colour, has alpha) for a key, or None."""
        if not self.folder:
            return None
        p = self._path(key)
        try:
            with open(p, "rb") as f:
                raw = f.read()
            hl = struct.unpack("<I", raw[:4])[0]
            meta = json.loads(raw[4:4 + hl].decode("utf-8"))
            return meta["mime"], raw[4 + hl:], tuple(meta["avg"]), meta["alpha"]
        except Exception:
            return None

    def put(self, key, val):
        """Store a value: a 4-byte header length, a JSON header, then the image bytes."""
        if not self.folder:
            return
        mime, data, avg, alpha = val
        meta = json.dumps({"mime": mime, "avg": list(avg), "alpha": alpha}).encode("utf-8")
        try:
            tmp = self._path(key) + ".part"
            with open(tmp, "wb") as f:
                f.write(struct.pack("<I", len(meta)) + meta + data)
            os.replace(tmp, self._path(key))
        except OSError:
            pass


# ==============================================================================
#  Pak-wide indexes (shaders + entity definitions), cached per set of paks
# ==============================================================================
def pak_signature(paks):
    """Short id for a list of paks, changing when any of them changes."""
    h = hashlib.sha1()
    for p in paks:
        try:
            st = os.stat(p)
            h.update(("%s|%d|%d;" % (os.path.abspath(p).lower(), st.st_size, int(st.st_mtime))).encode("utf-8"))
        except OSError:
            h.update(("%s|missing;" % p).encode("utf-8"))
    h.update(b"mapidx-v%d" % INDEX_VERSION)
    return h.hexdigest()[:16]


def build_indexes(vfs, paks, cache_dir=None, say=log):
    """(shaders, entity definitions) for the loaded paks, from the cache when it
    matches. The launcher calls this once after the paks load so builds start fast."""
    sig = pak_signature(paks)
    path = os.path.join(cache_dir, "mapindex_%s.json" % sig) if cache_dir else None
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                blob = json.load(f)
            ed = ME.EntityDefs()
            for k, d in blob["defs"].items():
                d["color"] = tuple(d["color"])
                if d.get("box"):
                    d["box"] = (tuple(d["box"][0]), tuple(d["box"][1]))
                d["flags"] = tuple(d.get("flags") or ())
                ed.defs[k] = d
            ed.tik_for_class = blob["tik_for_class"]
            ed.class_for_tik = blob["class_for_tik"]
            return blob["shaders"], ed
        except Exception:
            pass
    t0 = time.time()
    shaders = {}
    names = sorted(k for k in vfs.names() if k.endswith(".shader"))
    for k in names:
        data = vfs.read(k)
        if data:
            try:
                parse_shaders(data.decode("latin-1", "replace"), shaders)
            except Exception as e:
                say("(shader file %s skipped: %s)" % (k, e))
    ed = ME.EntityDefs()
    ed.scan_vfs(vfs)
    say("indexed %d shaders and %d entity classes in %.1f s" % (len(shaders), len(ed.defs), time.time() - t0))
    if path:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            blob = {"shaders": shaders, "defs": ed.defs, "tik_for_class": ed.tik_for_class,
                    "class_for_tik": ed.class_for_tik}
            tmp = path + ".part"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(blob, f)
            os.replace(tmp, path)
        except Exception:
            pass
    return shaders, ed


# ==============================================================================
#  Textures for the map's shaders
# ==============================================================================
class TextureTable:
    """Every shader the page draws, in one list the page indexes by number. Each
    entry carries the picture (as a blob in the page's data block), the size the
    map compiler used for texture coordinates and the render hints."""

    def __init__(self, vfs, shaders, blobs, max_dim, cache):
        self.vfs = vfs
        self.shaders = shaders or {}
        self.blobs = blobs
        self.max_dim = max_dim
        self.cache = cache
        self.entries = []
        self.index = {}
        self.missing = []
        self.decoded = 0
        self.cached = 0

    def _find(self, ref):
        """The pak path of a texture reference (any extension), or None."""
        if not ref or self.vfs is None:
            return None
        return self.vfs.find_texture(ref)

    def _size_for(self, info, name):
        """The texture size q3map used for this shader's coordinates (LoadShaderImage in
        the map compiler, tools/ommap/shaders.c): q3map_lightimage, else qer_editorimage,
        else the image named after the shader, else 64 x 64."""
        for ref in ((info or {}).get("light"), (info or {}).get("editor"), name):
            p = self._find(ref)
            if p:
                d = self.vfs.read(p)
                wh = image_dims(d) if d else None
                if wh:
                    return wh
        return (64, 64)

    def _encode(self, img, want_alpha):
        """(mime, bytes, average colour, has alpha) for a pak image, through the cache."""
        mode = "a" if want_alpha else "o"
        ckey = "%s|%s|%d|%s|%d" % (self.vfs.pak_of(img), img, self.max_dim, mode, TEX_CACHE_FORMAT)
        val = self.cache.get(ckey) if self.cache else None
        if val is not None:
            self.cached += 1
            return val
        data = self.vfs.read(img)
        try:
            val = encode_image(data, self.max_dim, want_alpha) if data else None
            self.decoded += 1
        except Exception:
            val = None
        if val and self.cache:
            self.cache.put(ckey, val)
        return val

    @staticmethod
    def _key(name, model):
        """The entry name for a shader name: brush textures always under textures/, model
        shaders as the .tik names them."""
        key = name.lower().replace("\\", "/")
        if not model and not key.startswith("textures/"):
            key = "textures/" + key
        return key

    def info(self, name, model=False):
        """The parsed shader for a name (with or without textures/), or None."""
        key = self._key(name, model)
        info = self.shaders.get(key)
        if info is None and model and not key.startswith("textures/"):
            info = self.shaders.get("textures/" + key)
        return info

    def add(self, name, model=False):
        """Index of the entry for a shader name (with or without textures/)."""
        key = self._key(name, model)
        if key in self.index:
            return self.index[key]
        info = self.info(name, model)
        ent = {"n": key}
        bits, cont, surf = shader_render_bits(info) if info else (0, 0, 0)
        grp = util_group(key, cont, surf)
        # Utility textures are shown with their editor picture (as MOHRadiant does), real
        # ones with the picture the game draws. A sky shows its editor picture too: the
        # game draws its sky box there instead (the page's game sky), MOHRadiant and
        # Simple Sky the editor picture, tiled.
        refs = []
        if info:
            if grp or bits & (TF_NODRAW | TF_SKY):
                refs += [info.get("editor"), key, info.get("map")]
            else:
                refs += [info.get("map"), info.get("editor"), key]
        else:
            refs.append(key)
        img = None
        for r in refs:
            img = self._find(r)
            if img:
                break
        if img is None and info and info.get("map") and self.vfs is not None:
            img = self.vfs.find_texture_by_name(info["map"])
        if not model:
            w, h = self._size_for(info, key)
            ent["w"], ent["h"] = int(w), int(h)
        ent["f"] = bits
        if cont:
            ent["cf"] = cont
        if surf:
            ent["sf"] = surf
        if grp:
            ent["g"] = grp
        if info:
            if info.get("trans") is not None:
                ent["a"] = max(0.05, min(1.0, info["trans"]))
            if info.get("alphafunc"):
                ent["at"] = info["alphafunc"]
            if info.get("parms"):
                ent["p"] = info["parms"]
            if info.get("keywords"):
                ent["k"] = info["keywords"]
            if info.get("sky"):
                ent["sky"] = info["sky"]
            if info.get("lmstage"):
                ent["lm"] = 1
            if info.get("rgb0"):
                ent["rg"] = info["rgb0"]
            # how the game draws its picture: texture scale, alphaGen, depthWrite
            if info.get("ptm"):
                ent["tm"] = info["ptm"]
            if info.get("pag"):
                ent["ag"] = info["pag"]
            if info.get("pdw"):
                ent["dw"] = 1
        else:
            ent["noshader"] = 1
        want_alpha = bool(bits & (TF_ALPHATEST | TF_BLEND | TF_ADD))
        if img:
            ent["img"] = img
            val = self._encode(img, want_alpha)
            if val:
                mime, data, avg, alpha = val
                ent["b"] = self.blobs.add(data)
                ent["m"] = mime
                ent["c"] = list(avg)
                if alpha:
                    ent["al"] = 1
        # Water, slime and lava show their editor picture at Full Brightness (as MOHRadiant
        # does), but the game draws the shader's own picture: that one goes along for the
        # game's lighting.
        if img and info and grp == "liquid" and not bits & TF_NODRAW:
            gimg = self._find(info.get("map"))
            if gimg and gimg != img:
                val = self._encode(gimg, want_alpha)
                if val:
                    ent["gb"] = self.blobs.add(val[1])
                    ent["gm"] = val[0]
        if "b" not in ent:
            ent["f"] |= TF_MISSING
            self.missing.append(key)
        self.index[key] = len(self.entries)
        self.entries.append(ent)
        return self.index[key]


# ==============================================================================
#  The page's data block: one JSON header plus binary blobs, gzipped
# ==============================================================================
class Blobs:
    """Binary pieces of the page data (pictures, mesh arrays, the .map text). Each is
    stored 4-byte aligned so the page can view it as a typed array; the header lists
    them as [offset, length] pairs and the rest of the data refers to them by number."""

    def __init__(self):
        self.chunks = []
        self.table = []
        self.size = 0

    def add(self, data):
        """Append a blob (bytes, or text as Latin-1) and return its number."""
        if isinstance(data, str):
            data = data.encode("latin-1", "replace")
        pad = (-self.size) % 4
        if pad:
            self.chunks.append(b"\0" * pad)
            self.size += pad
        self.table.append([self.size, len(data)])
        self.chunks.append(bytes(data))
        self.size += len(data)
        return len(self.table) - 1


def pack_payload(header, blobs):
    """The page data: "MMV1", the header's length, the JSON header, padding to 4
    bytes, then the blobs; gzipped and base64-encoded for the page."""
    header = dict(header)
    header["blobs"] = blobs.table
    hj = json.dumps(header, separators=(",", ":")).encode("utf-8")
    pad = (-(8 + len(hj))) % 4
    raw = b"".join([b"MMV1", struct.pack("<I", len(hj)), hj, b"\0" * pad] + blobs.chunks)
    gz = gzip.compress(raw, compresslevel=6)
    return base64.b64encode(gz).decode("ascii"), len(raw), len(gz)


# ==============================================================================
#  A quick read of the .map text (the page does the full parse)
# ==============================================================================
_KV = re.compile(r'^\s*"([^"]*)"\s+"([^"]*)"')


_BPFACE_TEX = re.compile(r"\)\s*\)\s*([^\s()]+)")


def scan_map(text):
    """Entities (as lists of (key, value)) with how many brushes, patches and terrain
    blocks each has, and every texture name the map uses (with a use count). The
    page parses the geometry itself; this is only what the build needs up front."""
    ents = []
    textures = {}

    def use(t):
        t = t.lower()
        textures[t] = textures.get(t, 0) + 1

    cur = None
    depth = 0
    kind = None          # what the current depth-2 block is: brush / patch / terrain / brushdef
    sub = 0              # terrainDef: which { } sub-block we are in (1 = textures)
    want_shader = False  # patchDef: the next plain line is its shader
    for raw in text.split("\n"):
        s = raw.strip()
        if not s or s.startswith("//"):
            continue
        if s == "{":
            depth += 1
            if depth == 1:
                cur = {"kv": [], "brushes": 0, "patches": 0, "terrain": 0}
                ents.append(cur)
            elif depth == 2:
                kind = "brush"
            elif depth == 3 and kind == "patch":
                want_shader = True
            elif depth == 4 and kind == "terrain":
                sub += 1
            continue
        if s == "}":
            if depth == 2 and cur is not None:
                if kind == "patch":
                    cur["patches"] += 1
                elif kind == "terrain":
                    cur["terrain"] += 1
                else:
                    cur["brushes"] += 1
                kind = None
                sub = 0
            depth = max(0, depth - 1)
            continue
        if depth == 1:
            m = _KV.match(s)
            if m and cur is not None:
                cur["kv"].append((m.group(1), m.group(2)))
            continue
        if depth == 2:
            low = s.lower()
            if low.startswith("patchdef"):
                kind = "patch"
            elif low.startswith("terraindef"):
                kind = "terrain"
            elif low.startswith("brushdef"):
                kind = "brushdef"
            elif s.startswith("("):
                tok = _face_texture(s)
                if tok:
                    use(tok)
            continue
        if depth == 3:
            if kind == "patch" and want_shader and not s.startswith("("):
                use(s.split()[0])
                want_shader = False
            elif kind == "brushdef" and s.startswith("("):
                m = _BPFACE_TEX.search(s)
                if m:
                    use(m.group(1))
            continue
        if depth == 4 and kind == "terrain" and sub == 1:
            m = re.search(r"\(\s*([^\s()]+)", s)
            if m:
                use(m.group(1))
    for e in ents:
        e["kvd"] = {}
        for k, v in e["kv"]:
            e["kvd"].setdefault(k.lower(), v)
    return ents, textures


def _face_texture(line):
    """The texture name of a brush face line: the word after the third ')'."""
    n = 0
    for i, ch in enumerate(line):
        if ch == ")":
            n += 1
            if n == 3:
                tok = line[i + 1:].split()
                return tok[0] if tok else None
    return None


# ==============================================================================
#  Placed models (static props, script models, turrets ...)
# ==============================================================================
def _norm_model_path(p):
    p = (p or "").replace("\\", "/").strip().strip('"').lower()
    while "//" in p:
        p = p.replace("//", "/")
    p = p.lstrip("/")
    if not p:
        return ""
    if not p.startswith("models/"):
        p = "models/" + p
    return p


def entity_model_path(kvd, entdefs):
    """The .tik (or .skd) an entity draws, or ''. A "model" key wins (script models,
    turrets, the static props of a compiled map); otherwise the class may come from
    a .tik's /*QUAKED*/ header (static_* props, animate_* objects, items)."""
    m = kvd.get("model", "")
    if m and not m.startswith("*"):
        mp = _norm_model_path(m)
        if mp.endswith((".tik", ".skd", ".skb")):
            return mp
    cls = kvd.get("classname", "").lower()
    if cls and entdefs is not None:
        tik = entdefs.tik_for_class.get(cls)
        if tik:
            return _norm_model_path(tik)
    return ""


def _bytes_skd(data, name):
    """A skeletal mesh from .skb ("SKL ") or .skd ("SKMD") file data."""
    ident = data[:4]
    if ident == b"SKL ":
        return MV._parse_skb(data, name)
    if ident == b"SKMD":
        return MV._parse_skmd(data, name)
    raise ValueError("not a .skd/.skb model")


def _resolve_in_vfs(vfs, ref, base_dirs):
    """A file a .tik refers to: as given, then in each base folder, then anywhere by
    name (some retail .tiks carry stale paths)."""
    ref = (ref or "").replace("\\", "/").strip().strip('"')
    if not ref:
        return None
    cands = [ref]
    for d in base_dirs:
        if d:
            cands.append(d.rstrip("/") + "/" + ref)
            cands.append(d.rstrip("/") + "/" + os.path.basename(ref))
    for c in cands:
        if vfs.exists(c):
            return vfs._k(c)
    bn = "/" + os.path.basename(ref).lower()
    for k in vfs.names():
        if k.endswith(bn):
            return k
    return None


class ModelBuilder:
    """Loads, poses and textures each model the map places, once per model."""

    def __init__(self, vfs, texs, blobs, say=log):
        self.vfs = vfs
        self.texs = texs
        self.blobs = blobs
        self.say = say
        self.models = []
        self.index = {}
        self.total_verts = 0
        self.failed = {}
        self.lod_models = 0         # models with a long-range stand-in sprite (see _build)

    def get(self, path):
        """The model's number in the page, building it the first time; -1 if it can't be
        drawn (the reason is kept in self.failed)."""
        if path in self.index:
            return self.index[path]
        idx = -1
        if len(self.models) < MODEL_MAX_UNIQUE and self.total_verts < MODELS_MAX_TOTAL_VERTS:
            try:
                m = self._build(path)
            except Exception as e:
                m = None
                self.failed[path] = str(e)[:160]
            if m:
                idx = len(self.models)
                self.models.append(m)
        else:
            self.failed[path] = "model limit reached"
        self.index[path] = idx
        return idx

    def _tik_text(self, path):
        """A .tik's text with its $include files expanded."""
        data = self.vfs.read(path)
        if data is None:
            raise ValueError("not found in the paks")
        txt = data.decode("latin-1", "replace")
        if MTX is not None:
            txt = MTX.expand_tik_includes(txt, self.vfs)
        return txt

    def _pose_channels(self, txt, tik_dir, setup_path):
        """Frame 0 of the model's idle (or first) animation, the way static models
        are drawn (renderergl1/tr_staticmodels.cpp poses them at frame 0)."""
        try:
            anims = MV.parse_tik_animations(txt)
        except Exception:
            anims = []
        if not anims:
            return {}
        pick = None
        for a in anims:
            if a["name"].lower() == "idle":
                pick = a
                break
        if pick is None:
            pick = anims[0]
        ref = _resolve_in_vfs(self.vfs, pick["file"], [setup_path, tik_dir])
        if not ref or not ref.endswith(".skc"):
            return {}
        data = self.vfs.read(ref)
        if not data:
            return {}
        fd, tmp = tempfile.mkstemp(suffix=".skc")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            skc = MV.parse_skc(tmp)
        except Exception:
            return {}
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return skc["frames"][0] if skc.get("frames") else {}

    def _build(self, path):
        """Load a .tik (or a bare .skd/.skb), pose it at frame 0 of its idle animation,
        and pack its vertices, texture coordinates, triangles and surfaces as blobs."""
        if MV is None:
            raise ValueError("mohaa_view.py is missing")
        low = path.lower()
        tik_dir = os.path.dirname(low)
        shader_map = {}
        scale = 1.0
        setsize = None
        if low.endswith(".tik"):
            txt = self._tik_text(low)
            parts = MV.parse_tik_skelmodels(txt)
            if not parts:
                raise ValueError("the .tik names no skelmodel")
            scale = MV.parse_tik_scale(txt) or 1.0
            setsize = MV.parse_tik_setsize(txt)
            try:
                for skd, pairs in MTX.parse_tik_setup(txt).items():
                    for sname, sh in pairs:
                        shader_map.setdefault(sname.lower(), sh)
            except Exception:
                pass
            # Surfaces the .tik switches off at spawn (LOD stand-ins, broken variants).
            try:
                nodraw_ops = MV.parse_tik_static_nodraw(txt)
            except Exception:
                nodraw_ops = []
            setup_path = parts[0][0] or tik_dir
            skds = []
            for p, sk in parts:
                ref = _resolve_in_vfs(self.vfs, sk, [p, tik_dir])
                if ref is None and sk.lower().endswith((".skd", ".skb")):
                    twin = sk[:-4] + (".skb" if sk.lower().endswith(".skd") else ".skd")
                    ref = _resolve_in_vfs(self.vfs, twin, [p, tik_dir])
                if ref is None:
                    continue
                data = self.vfs.read(ref)
                if data:
                    skds.append(_bytes_skd(data, ref))
            if not skds:
                raise ValueError("its skelmodel isn't in the paks")
            skd = MV.merge_skds(skds) if len(skds) > 1 else skds[0]
            channels = self._pose_channels(txt, tik_dir, setup_path)
        else:
            data = self.vfs.read(low)
            if data is None:
                raise ValueError("not found in the paks")
            skd = _bytes_skd(data, low)
            channels = {}
            nodraw_ops = []

        def hidden(sname):
            # the last matching "surface <name> +/-nodraw" line wins
            hide = False
            for op in nodraw_ops:
                pat = op["name"].lower()
                if pat == sname or (pat.endswith("*") and sname.startswith(pat[:-1])):
                    hide = op["nodraw"]
            return hide
        try:
            wR, wT = MV.compute_world(skd["bones"], channels)
        except Exception:
            wR, wT = MV.compute_world(skd["bones"], {})
        pos = []
        uvs = []
        idx = []
        surfs = []
        nverts = 0
        # Where each surface starts in the engine's own vertex numbering (every surface of
        # every mesh in order, hidden ones included): a static model's baked vertex light
        # is stored in that order (tr_staticmodels.cpp R_AddStaticModelSurfaces).
        eng = 0
        for s in skd["surfaces"]:
            sname = s["name"].lower()
            eo = eng
            eng += len(s["verts"])
            if hidden(sname):
                continue
            shader = shader_map.get(sname)
            if shader is None:
                for pat, sh in shader_map.items():
                    if pat == "all" or (pat.endswith("*") and sname.startswith(pat[:-1])):
                        shader = sh
                        break
            first = len(idx)
            base = nverts
            for weights, (u, v) in zip(s["verts"], s["uvs"]):
                X = Y = Z = 0.0
                for bi, wv, off in weights:
                    if not (0 <= bi < len(wR)):
                        continue
                    R = wR[bi]
                    T = wT[bi]
                    X += wv * (R[0][0] * off[0] + R[0][1] * off[1] + R[0][2] * off[2] + T[0])
                    Y += wv * (R[1][0] * off[0] + R[1][1] * off[1] + R[1][2] * off[2] + T[1])
                    Z += wv * (R[2][0] * off[0] + R[2][1] * off[1] + R[2][2] * off[2] + T[2])
                pos += (X * scale, Y * scale, Z * scale)
                uvs += (u, v)
                nverts += 1
            for a, b, c in s["tris"]:
                idx += (base + a, base + b, base + c)
            if nverts > MODEL_MAX_VERTS:
                raise ValueError("too many vertices (%d)" % nverts)
            ti = self.texs.add(shader or sname, model=True)
            # [first index, index count, texture, name, first vertex, vertex count, engine offset]
            surfs.append([first, len(idx) - first, ti, sname, base, nverts - base, eo])
        if not idx:
            raise ValueError("no triangles")
        # A tree's long-range stand-in (TF_LOD): the game fades it in far away as the tree's
        # own surfaces fade out. The page leaves it out, or with Simple models on draws it
        # alone, in place of the tree.
        if any(self.texs.entries[sf[2]]["f"] & TF_LOD for sf in surfs):
            self.lod_models += 1
        mins = [min(pos[k::3]) for k in range(3)]
        maxs = [max(pos[k::3]) for k in range(3)]
        self.total_verts += nverts
        return {"p": path,
                "v": self.blobs.add(struct.pack("<%df" % len(pos), *pos)),
                "t": self.blobs.add(struct.pack("<%df" % len(uvs), *uvs)),
                "i": self.blobs.add(struct.pack("<%dI" % len(idx), *idx)),
                "s": surfs, "b": [mins, maxs], "ss": setsize, "sc": scale, "nv": nverts, "env": eng}


# ==============================================================================
#  Sky boxes and cloud layers (.bsp and .map)
# ==============================================================================
SKY_SUFFIXES = ("rt", "bk", "lf", "ft", "up", "dn")    # tr_shader.c ParseSkyParms
SKY_MAX_DIM = 512
SKY_MAX_CLOUDS = 4          # cloud layers the page draws per sky (retail skies have one)

# blendFunc factors, numbered as the page's sky shader takes them (tr_shader.c
# NameToSrcBlendMode / NameToDstBlendMode: a name that side doesn't take counts as GL_ONE)
_SRC_BLEND = {"gl_zero": 0, "gl_one": 1, "gl_dst_color": 4, "gl_one_minus_dst_color": 5,
              "gl_src_alpha": 6, "gl_one_minus_src_alpha": 7, "gl_dst_alpha": 8,
              "gl_one_minus_dst_alpha": 9, "gl_src_alpha_saturate": 10}
_DST_BLEND = {"gl_zero": 0, "gl_one": 1, "gl_src_color": 2, "gl_one_minus_src_color": 3,
              "gl_src_alpha": 6, "gl_one_minus_src_alpha": 7, "gl_dst_alpha": 8,
              "gl_one_minus_dst_alpha": 9}
_SIMPLE_BLENDS = {"add": [1, 1], "filter": [4, 0], "blend": [6, 7], "alphaadd": [6, 1]}
_WAVE_FUNCS = ("sin", "square", "triangle", "sawtooth", "inversesawtooth", "noise")


def _blend_factors(blend):
    """[source, destination] factors of a stage's blendFunc; [1, 0] (drawn solid) when it
    has none, or only one word that isn't a shorthand (ParseStage then sets no blend)."""
    words = (blend or "").split()
    if not words:
        return [1, 0]
    if words[0] in _SIMPLE_BLENDS:
        return list(_SIMPLE_BLENDS[words[0]])
    if len(words) < 2:
        return [1, 0]
    return [_SRC_BLEND.get(words[0], 1), _DST_BLEND.get(words[1], 1)]


def _wave(words):
    """A waveform as ParseWaveForm reads it: [function, base, amplitude, phase, frequency]."""
    func = words[0].lower() if words else "sin"
    nums = [_atof(w) for w in words[1:5]]
    return [func if func in _WAVE_FUNCS else "sin"] + nums + [0.0] * (4 - len(nums))


def _cloud_rgb(rg):
    """A cloud stage's rgbGen as the page works it out each frame: ["c", r, g, b] for a
    constant (identity, identityLighting and the kinds a sky has nothing for are white;
    r_overBrightBits is 0 in MOHAA, so identityLight is 1), ["w", wave] or
    ["cw", r, g, b, wave] (colorWave)."""
    kind, args = (rg[0], rg[1:]) if rg else ("", [])
    if kind in ("const", "constant", "colorwave"):
        v = [max(0.0, min(1.0, _atof(w))) for w in args[:3]]
        v += [0.0] * (3 - len(v))
        return ["c"] + v if kind != "colorwave" else ["cw"] + v + _wave(args[3:])
    if kind == "wave":
        return ["w"] + _wave(args)
    return ["c", 1.0, 1.0, 1.0]


def _cloud_alpha(ag):
    """alphaGen: ["c", a] for a constant (none at all is 1), ["w", wave], or ["sky"] /
    ["1sky"] for the worldspawn's "skyalpha" (or one minus it)."""
    kind, args = (ag[0], ag[1:]) if ag else ("", [])
    if kind in ("const", "constant"):
        return ["c", max(0.0, min(1.0, _atof(args[0]) if args else 0.0))]
    if kind == "wave":
        return ["w"] + _wave(args)
    if kind == "skyalpha":
        return ["sky"]
    if kind == "oneminusskyalpha":
        return ["1sky"]
    return ["c", 1.0]


def _cloud_tcmods(mods):
    """A stage's tcMods, in order, with their numbers (tr_shader.c ParseTexMod). The
    random part of scroll and offset is left out; turb (it wobbles by world position),
    bulge (it changes nothing in the engine) and the entity-driven kinds are dropped."""
    out = []
    for m in mods:
        kind, args = m[0], [_atof(w) for w in m[1:]]
        if kind in ("scroll", "offset", "scale") and len(args) >= 2:
            out.append([kind, args[0], args[1]])
        elif kind == "rotate" and args:
            out.append(["rotate", args[0], args[1] if len(args) > 1 else 0.0,
                        args[2] if len(args) > 2 else 1.0])
        elif kind == "transform" and len(args) >= 6:
            out.append(["transform"] + args[:6])
        elif kind in ("stretch", "wavetrans", "wavetrant") and len(m) > 1:
            out.append([kind] + _wave(m[1:]))
    return out


def sky_clouds(info, texs, blobs):
    """A sky shader's cloud layers for the page, or None: {"h": cloud height, "s":
    [{"b": picture, "m": its type, "f": [source factor, destination factor, alphaFunc
    (1 GT0, 2 GE128, 3 LT128)], "rg": rgbGen, "ag": alphaGen, "tm": tcMods}, ...]}.
    A stage whose picture isn't in the paks is left out."""
    layers = []
    for cs in (info or {}).get("clouds") or ():
        img = texs._find(cs["pic"])
        if img is None and texs.vfs is not None:
            img = texs.vfs.find_texture_by_name(cs["pic"])
        if img is None:
            continue
        src, dst = _blend_factors(cs["blend"])
        af = {"gt0": 1, "ge128": 2, "lt128": 3}.get(cs["afunc"] or "", 0)
        val = texs._encode(img, bool(af) or src in (6, 7, 10) or dst in (6, 7))
        if not val:
            continue
        layers.append({"b": blobs.add(val[1]), "m": val[0], "f": [src, dst, af],
                       "rg": _cloud_rgb(cs["rgb"]), "ag": _cloud_alpha(cs["agen"]),
                       "tm": _cloud_tcmods(cs["tcmod"])})
        if len(layers) == SKY_MAX_CLOUDS:
            break
    return {"h": info["skyh"], "s": layers} if layers else None


def sky_boxes(texs, blobs, vfs):
    """The game's sky for the page (.bsp and .map alike): the six pictures of each sky
    shader's far box (skyParms <env> ...) and its cloud layers. A sky texture entry with a
    box gets its index as "sb", one with cloud layers its index as "cl"."""
    skies, clouds = [], []
    if vfs is None:
        return skies, clouds
    for te in texs.entries:
        if not (te.get("f", 0) & TF_SKY) or not te.get("sky"):
            continue
        if te["sky"] != "-":
            faces = []
            for suf in SKY_SUFFIXES:
                p = vfs.find_texture("%s_%s" % (te["sky"], suf))
                data = vfs.read(p) if p else None
                try:
                    enc = encode_image(data, SKY_MAX_DIM, False) if data else None
                except Exception:
                    enc = None
                if not enc:
                    faces = None
                    break
                faces.append(blobs.add(enc[1]))
            if faces:
                te["sb"] = len(skies)
                skies.append(faces)
        layers = sky_clouds(texs.info(te["n"]), texs, blobs)
        if layers:
            te["cl"] = len(clouds)
            clouds.append(layers)
    return skies, clouds


# ==============================================================================
#  In-game lighting (.bsp only)
# ==============================================================================
# With Full Brightness off the page shows what the game draws: the compiled polygons
# (planar faces straight from the .bsp; patches and terrain from the .map with the .bsp's
# lightmap coordinates), each lit the way the engine lights it.
# Everything here comes from the .bsp; a .map has no compiled light.


def _light_mode(info, lightmap_num, nlm):
    """How the game lights a surface, as R_FindShader / ParseStage set it up
    (renderergl1/tr_shader.c): 'lm' texture x lightmap, 'v' texture x vertex light,
    'f' the texture as it is (full bright)."""
    if lightmap_num >= nlm:
        return "v"                   # lightmap number past the file's pages: lit by vertex
    lit = lightmap_num >= 0
    if info is None:                 # no shader script: two-pass lightmap x texture
        return "lm" if lit else "f"
    if info.get("lmstage"):          # an explicit $lightmap stage (white without a lightmap)
        return "lm" if lit else "f"
    if info.get("rgb0") in ("vertex", "exactvertex", "oneminusvertex"):
        return "v"
    return "f"


def _layer(mode, lightmap_num):
    """The page's per-vertex lighting code: the lightmap page, -1 vertex light, -2 none."""
    return lightmap_num if mode == "lm" else (-1 if mode == "v" else -2)


def lit_payload(bsp, stats, texs, blobs, shaders, vfs, ents, model_of, models, say=log):
    """Everything the page needs to draw the map with the game's lighting, or None when
    the .bsp has no lightmaps (the game then draws it full bright too)."""
    from array import array
    nlm = bsp.lightmap_count()
    if not nlm or not _have_pil():
        return None
    from PIL import Image
    page = MB.LIGHTMAP_SIZE * MB.LIGHTMAP_SIZE * 3

    def shader_info(name):
        # (texture number in the page, the shader's index entry)
        ti = texs.add(name)
        return ti, shaders.get(texs.entries[ti]["n"])

    # ---- lightmaps: brightened like the game, packed 8 pages across in one PNG -------
    shifted = MB.color_shift(bsp.lump(MB.LUMP_LIGHTMAPS)[:nlm * page], 3)
    cols = min(8, nlm)
    rows = (nlm + cols - 1) // cols
    atlas = Image.new("RGB", (cols * MB.LIGHTMAP_SIZE, rows * MB.LIGHTMAP_SIZE))
    for k in range(nlm):
        pg = Image.frombytes("RGB", (MB.LIGHTMAP_SIZE, MB.LIGHTMAP_SIZE), shifted[k * page:(k + 1) * page])
        atlas.paste(pg, ((k % cols) * MB.LIGHTMAP_SIZE, (k // cols) * MB.LIGHTMAP_SIZE))
    buf = io.BytesIO()
    atlas.save(buf, "PNG", compress_level=9)
    out = {"lm": blobs.add(buf.getvalue()), "nlm": nlm, "cols": cols}

    # ---- the planar polygons of every brush model the map places ------------------------
    P, UV, LM = array("f"), array("f"), array("f")
    COL = bytearray()
    IDX, SURF = array("I"), array("i")
    verts = bsp._verts
    owners = stats["owners"]
    for mi, (ei, org) in sorted(stats["models"].items()):
        mdl = bsp.models[mi]
        for si in range(mdl["firstSurface"], mdl["firstSurface"] + mdl["numSurfaces"]):
            s = bsp.surfaces[si]
            if s["type"] not in (MB.MST_PLANAR, MB.MST_TRIANGLE_SOUP) or s["numVerts"] < 3:
                continue
            sh = bsp.shaders[s["shader"]] if 0 <= s["shader"] < len(bsp.shaders) else None
            if sh is None or sh["surface"] & MB.SURF_NODRAW:
                continue              # never drawn (ParseFace skips nodraw surfaces)
            ti, info = shader_info(sh["name"])
            # triangle soups are always lit by vertex (ParseTriSurf)
            lmn = s["lightmapNum"] if s["type"] == MB.MST_PLANAR else nlm
            layer = _layer(_light_mode(info, lmn, nlm), lmn)
            fv, nv = s["firstVert"], s["numVerts"]
            if fv < 0 or (fv + nv) * 44 > len(verts):
                continue
            base = len(P) // 3
            for x, y, z, su, sv, ls, lt, _nx, _ny, _nz, r, g, b, a in struct.iter_unpack(
                    "<10f4B", verts[fv * 44:(fv + nv) * 44]):
                P.extend((x + org[0], y + org[1], z + org[2]))
                UV.extend((su, sv))
                LM.extend((ls, lt, layer))
                COL.extend((r, g, b, a))
            i0 = len(IDX)
            for v in bsp.indexes[s["firstIndex"]:s["firstIndex"] + s["numIndexes"]]:
                if 0 <= v < nv:
                    IDX.append(base + v)
            n_idx = (len(IDX) - i0) // 3 * 3
            del IDX[i0 + n_idx:]
            own = owners.get(si, (ei, -1, -1))
            SURF.extend((i0, n_idx, ti, own[0], own[1], own[2]))
    out.update({"v": blobs.add(P.tobytes()), "uv": blobs.add(UV.tobytes()), "l": blobs.add(LM.tobytes()),
                "c": blobs.add(MB.color_shift(bytes(COL), 4)), "i": blobs.add(IDX.tobytes()),
                "s": blobs.add(SURF.tobytes()), "ns": len(SURF) // 6})

    # ---- patches: lightmap coordinates and vertex light per control point ---------------
    # in the .map's control point order (row j holds the .bsp's column j)
    PL = array("f")
    PCOL = bytearray()
    patches = []
    for si, (ei, bn) in sorted(stats["patch_owner"].items()):
        s = bsp.surfaces[si]
        sh = bsp.shaders[s["shader"]] if 0 <= s["shader"] < len(bsp.shaders) else None
        w, h = s["patchWidth"], s["patchHeight"]
        if sh is None or w * h != s["numVerts"]:
            continue
        if sh["surface"] & MB.SURF_NODRAW:
            patches.append([ei, bn, -3, 0, 0])        # never drawn in game
            continue
        _ti, info = shader_info(sh["name"])
        layer = _layer(_light_mode(info, s["lightmapNum"], nlm), s["lightmapNum"])
        off = len(PL) // 2
        for j in range(w):
            for i in range(h):
                (ls, lt), rgba = bsp.vert_light(s["firstVert"] + i * w + j)
                PL.extend((ls, lt))
                PCOL.extend(rgba)
        patches.append([ei, bn, layer, off, w * h])
    out.update({"p": patches, "pl": blobs.add(PL.tobytes()), "pc": blobs.add(MB.color_shift(bytes(PCOL), 4))})

    # ---- terrain: each patch's lightmap page, corner texel and texels per 64 units -----
    # (tr_bsp.c R_UnpackTerraPatch, tr_terrain.c R_PreTessellateTerrain)
    terr = []
    for k, tp in enumerate(bsp.terrain):
        if k >= len(stats["terrain_owner"]):
            break
        sh = bsp.shaders[tp["shader"]] if 0 <= tp["shader"] < len(bsp.shaders) else None
        info = shader_info(sh["name"])[1] if sh else None
        mode = _light_mode(info, tp["lightmap"], nlm)
        layer = tp["lightmap"] if mode == "lm" else -2
        terr.append([stats["terrain_owner"][k], layer, (tp["ls"] + 0.5) / MB.LIGHTMAP_SIZE,
                     (tp["lt"] + 0.5) / MB.LIGHTMAP_SIZE, tp["lmscale"] / float(MB.LIGHTMAP_SIZE)])
    out["t"] = terr

    # ---- models: baked vertex light for static props, the light grid for the rest -------
    grid = MB.LightGrid(bsp)
    smlight = MB.static_model_light(bsp)
    statics = {}
    first = stats["first_static"]
    for k, smd in enumerate(bsp.static_models):
        ei = first + k
        mi = model_of.get(str(ei))
        if mi is None:
            continue
        nvd, base = smd["numVertexData"], smd["firstVertexData"] // 3
        # only when the model's vertices line up one to one with the stored light
        if nvd == models[mi].get("env") and base >= 0 and (base + nvd) * 3 <= len(smlight):
            statics[str(ei)] = base
    elight = {}
    for ei_s in model_of:
        o = MB.parse_vec(ents[int(ei_s)]["kvd"].get("origin", "")) if int(ei_s) < len(ents) else None
        if o:
            elight[ei_s] = grid.entity_light(o)
    if smlight and statics:
        out["sm"] = blobs.add(smlight)
        out["smn"] = len(smlight) // 3
        out["st"] = statics
    out["el"] = elight
    say("lighting: %d lightmaps, %d polygons, %d patches, %d terrain blocks, %d of %d static models with baked light"
        % (nlm, out["ns"], len(patches), len(terr), len(statics), len(bsp.static_models)))
    return out


# ==============================================================================
#  What the game draws from where the camera is (the page's r_showtris)
# ==============================================================================
# The renderer only draws the leafs in the camera's PVS (its cluster's bit row in the
# vis lump) and in an area the camera's area is connected to (doors split a map into
# areas), then drops the planar faces that face away (R_CullSurface) and, with a
# farplane, everything past it. The page walks the same tree each frame; this packs it:
#   np / nc / nb   each node's plane (normal, dist), children and box
#   lf             each leaf: cluster, area, mins, maxs, first and count of its
#                  surfaces, terrain patches and static models (14 ints)
#   ls / lt / lm   the surface, terrain patch and static model numbers the leafs list
#   pvs, ncl, cb   the vis rows (null without vis), clusters, bytes per row
#   si / sf        per .bsp surface, 8 ints: kind (0 not drawn, 1 planar, 2 triangle
#                  soup, 3 patch), cull (0 front, 1 back, 2 none), entity, then for 1 / 2
#                  its lines (first, count) and for 3 its grid (first point, width,
#                  height, first lod error); and 10 floats: plane (1) or lod centre and
#                  radius (3), then mins, maxs
#   v / l / ge     points, line pairs into them, patch columns' and rows' lod errors
#   bm             each brush entity's surfaces: [entity, first, count]
#   to             each terrain patch's block number in the .map's world entity
_CULL_TWO = ("none", "twosided", "disable")
_CULL_BACK = ("back", "backside", "backsided")


def _surface_cull(info):
    """The shader's cullType (tr_shader.c ParseShader): 0 front-sided (the default),
    1 back-sided, 2 two-sided; a fence is never two-sided."""
    c = (info or {}).get("cull")
    if c in _CULL_BACK:
        return 1
    if c in _CULL_TWO:
        return 0 if shader_render_bits(info)[1] & 0x2000 else 2
    return 0


def vis_payload(bsp, stats, texs, blobs, say=log):
    """The page's data for r_showtris, or None when the .bsp has no tree to walk."""
    from array import array
    tree = bsp.vis_tree()
    if not tree["nodes"] and not tree["leafs"]:
        return None
    planes = bsp.planes
    NP, NC, NB = array("f"), array("i"), array("i")
    for pn, c0, c1, x0, y0, z0, x1, y1, z1 in tree["nodes"]:
        p = planes[pn] if 0 <= pn < len(planes) else (0.0, 0.0, 1.0, 0.0)
        NP.extend(p)
        NC.extend((c0, c1))
        NB.extend((x0, y0, z0, x1, y1, z1))
    LF = array("i")
    for t in tree["leafs"]:
        LF.extend(t)
    # every drawn surface, placed where its entity puts it
    owner = {}
    for mi, (ei, org) in stats["models"].items():
        if 0 <= mi < len(bsp.models):
            m = bsp.models[mi]
            for si in range(m["firstSurface"], m["firstSurface"] + m["numSurfaces"]):
                owner[si] = (ei, org)
    V, L, GE = array("f"), array("I"), array("f")
    SI, SF = array("i"), array("f")
    verts = bsp._verts
    counts = [0, 0, 0, 0]
    kinds = {MB.MST_PLANAR: 1, MB.MST_TRIANGLE_SOUP: 2, MB.MST_PATCH: 3}
    for si, s in enumerate(bsp.surfaces):
        rec, flo = [0] * 8, [0.0] * 10
        own = owner.get(si)
        sh = bsp.shaders[s["shader"]] if 0 <= s["shader"] < len(bsp.shaders) else None
        kind = kinds.get(s["type"], 0) if own and sh else 0
        info = texs.info(sh["name"]) if kind else None
        if kind and (sh["surface"] & (MB.SURF_NODRAW | MB.SURF_SKY)
                     or (info and shader_render_bits(info)[0] & (TF_NODRAW | TF_SKY))):
            kind = 0                  # never drawn, or drawn as the sky box (no triangles of its own)
        fv, nv = s["firstVert"], s["numVerts"]
        if kind and (fv < 0 or nv < 3 or (fv + nv) * 44 > len(verts)):
            kind = 0
        if kind:
            ei, org = own
            pts = [(x + org[0], y + org[1], z + org[2])
                   for x, y, z in struct.iter_unpack("<3f8x8x12x4x", verts[fv * 44:(fv + nv) * 44])]
            mn = [min(p[k] for p in pts) for k in range(3)]
            mx = [max(p[k] for p in pts) for k in range(3)]
            rec[0], rec[1], rec[2] = kind, _surface_cull(info), ei
            if kind == 3:
                w, h = s["patchWidth"], s["patchHeight"]
                if w * h != nv or w < 3 or h < 3:
                    kind = rec[0] = 0
                else:
                    gw, gh, grid, ew, eh = MB.subdivide_patch(w, h, pts, MB.patch_subdivide_value(s))
                    rec[3:7] = [len(V) // 3, gw, gh, len(GE)]
                    for p in grid:
                        V.extend(p)
                    GE.extend(ew)
                    GE.extend(eh)
                    # the lod group's centre and radius (ParseMesh: lightmapVecs 0 and 1)
                    a, b = s["vecs"][0:3], s["vecs"][3:6]
                    c = [(a[k] + b[k]) * 0.5 for k in range(3)]
                    flo[0:4] = [c[0] + org[0], c[1] + org[1], c[2] + org[2],
                                math.sqrt(sum((a[k] - c[k]) ** 2 for k in range(3)))]
                    mn = [min(p[k] for p in grid) for k in range(3)]
                    mx = [max(p[k] for p in grid) for k in range(3)]
            else:
                base = len(V) // 3
                for p in pts:
                    V.extend(p)
                edges = set()
                idx = bsp.indexes[s["firstIndex"]:s["firstIndex"] + s["numIndexes"]]
                for t in range(0, len(idx) - 2, 3):
                    a, b, c = idx[t], idx[t + 1], idx[t + 2]
                    if 0 <= a < nv and 0 <= b < nv and 0 <= c < nv:
                        for u, v in ((a, b), (b, c), (c, a)):
                            edges.add((u, v) if u < v else (v, u))
                rec[3] = len(L)
                for u, v in sorted(edges):
                    L.extend((base + u, base + v))
                rec[4] = len(L) - rec[3]
                if kind == 1:
                    # the plane from the lightmap vectors' third row (ParseFace)
                    n = s["vecs"][6:9]
                    if abs(n[0]) + abs(n[1]) + abs(n[2]) < 0.5:
                        n = MB._norm(MB._cross(MB._sub(pts[2], pts[0]), MB._sub(pts[1], pts[0]))) or (0.0, 0.0, 0.0)
                        if n == (0.0, 0.0, 0.0):
                            rec[1] = 2
                    flo[0:4] = [n[0], n[1], n[2], pts[0][0] * n[0] + pts[0][1] * n[1] + pts[0][2] * n[2]]
            if kind:
                flo[4:10] = mn + mx
                counts[kind] += 1
        SI.extend(rec)
        SF.extend(flo)
    bm = [[ei, bsp.models[mi]["firstSurface"], bsp.models[mi]["numSurfaces"]]
          for mi, (ei, org) in sorted(stats["models"].items()) if mi > 0 and mi < len(bsp.models)]
    vis = tree["vis"]
    out = {"np": blobs.add(NP.tobytes()), "nc": blobs.add(NC.tobytes()), "nb": blobs.add(NB.tobytes()),
           "lf": blobs.add(LF.tobytes()), "ls": blobs.add(array("i", tree["leafsurfaces"]).tobytes()),
           "lt": blobs.add(array("i", tree["terrain"]).tobytes()), "lm": blobs.add(array("i", tree["statics"]).tobytes()),
           "pvs": blobs.add(vis[2]) if vis else None, "ncl": vis[0] if vis else 0, "cb": vis[1] if vis else 0,
           "si": blobs.add(SI.tobytes()), "sf": blobs.add(SF.tobytes()),
           "v": blobs.add(V.tobytes()), "l": blobs.add(L.tobytes()), "ge": blobs.add(GE.tobytes()),
           "bm": bm, "to": list(stats["terrain_owner"]),
           "nn": len(tree["nodes"]), "nl": len(tree["leafs"]), "ns": len(bsp.surfaces)}
    areas = {t[1] for t in tree["leafs"] if t[1] >= 0}
    say("visibility: %d leafs in %d clusters%s, %d area%s; %d faces, %d triangle soups and %d patches drawn in game"
        % (len(tree["leafs"]), vis[0] if vis else 0, "" if vis else " (no vis data: every leaf sees every other)",
           len(areas), "" if len(areas) == 1 else "s", counts[1], counts[2], counts[3]))
    return out


# AI path files: maps/<map>.pth in the paks (the game's own), else beside the map
def paths_payload(vfs, vpath, src, blobs, say=log):
    """The path nodes and connections the game built for this map (what ai_showroutes
    draws), from maps/<map>.pth: {"src": where it was found, "n": nodes, "o": their
    origins, "f": their flags, "c": per connection [from, to, fallheight, pos1, pos2]
    (9 floats), "time"}, or {"src", "err"} when it can't be read, or None when the map
    has no path file."""
    from array import array
    stem = os.path.splitext(vpath.replace("\\", "/"))[0]
    if not stem.lower().startswith("maps/"):
        stem = "maps/" + os.path.basename(stem)
    data = where = None
    if vfs is not None:
        k = (stem + ".pth").lower()
        if k in vfs.index:
            data = vfs.read(k)
            zi, real = vfs.index[k]
            where = "%s (%s)" % (real, os.path.basename(vfs.zips[zi].filename))
    if data is None:
        side = os.path.splitext(src)[0] + ".pth"
        if os.path.isfile(side):
            with open(side, "rb") as f:
                data = f.read()
            where = side
    if data is None:
        return None
    try:
        pf = MB.read_path_file(data)
    except ValueError as e:
        say("! path file %s can't be read: %s" % (where, e))
        return {"src": where, "err": str(e)}
    O, F, C = array("f"), array("i"), array("f")
    for i, nd in enumerate(pf["nodes"]):
        O.extend(nd["origin"])
        F.append(nd["flags"])
        for to, fall, p1, p2 in nd["children"]:
            C.extend((i, to, fall))
            C.extend(p1)
            C.extend(p2)
    say("AI paths: %d nodes, %d connections (%s)" % (len(pf["nodes"]), len(C) // 9, where))
    return {"src": where, "n": len(pf["nodes"]), "time": pf["maptime"],
            "o": blobs.add(O.tobytes()), "f": blobs.add(F.tobytes()), "c": blobs.add(C.tobytes())}


# ==============================================================================
#  HTML
# ==============================================================================
def _html_esc(s):
    """Text for HTML element content or a quoted attribute value."""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def _js_lit(s):
    """A JS string literal that is safe inside an inline <script>."""
    return (json.dumps(str(s)).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _json_script(obj):
    """JSON for a <script type="application/json"> block: '<' is escaped so the text
    can never close the block early."""
    return (json.dumps(obj, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026"))


# Stand-in for the keyboard map when mohaa_view.py can't be loaded: the same table as a
# plain list (the page's Esc, H and a click outside still close it).
_KEYS_CSS_PLAIN = (".kx-ov{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;"
                   "justify-content:center;z-index:40}.kx-card{background:var(--panel);border:1px solid var(--line);"
                   "border-radius:10px;padding:14px 18px;width:min(900px,94vw);height:min(800px,92vh);overflow:auto}")
_KEYS_JS_PLAIN = r"""function kxBuild(host,P){const e=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');
 let h='<b>'+e(P.t.title)+'</b>';
 P.t.cols.forEach(c=>{h+='<h4>'+e(c.title)+'</h4>';c.rows.forEach(r=>{h+=r.sub!=null?'<div style="color:var(--dim);margin-top:6px">'+
   e(r.sub)+'</div>':'<div><kbd>'+e(r.k.replace(/\|/g,' / '))+'</kbd> '+e(r.d)+'</div>';});});
 host.innerHTML=h;return{show:function(){},hide:function(){}};}"""


def _keys_parts():
    """The keyboard shortcuts window for the page: its style, its code and its data
    (KEYS_CSS, KEYS_JS and kx_payload in mohaa_view.py, with this viewer's table)."""
    if MV is not None and hasattr(MV, "KEYS_JS"):
        return MV.KEYS_CSS, MV.KEYS_JS, MV.kx_payload(MAP_VIEWER_KEYS)
    return _KEYS_CSS_PLAIN, _KEYS_JS_PLAIN, {"cats": [], "layout": [], "t": MAP_VIEWER_KEYS}


def write_html(path, title, b64, info, theme=None):
    """Fill the page template (mohaa_map_page.py) and write it, via a temporary file so
    a half-written page is never left behind."""
    from mohaa_map_page import HTML_TEMPLATE
    kcss, kjs, kdata = _keys_parts()
    repl = {"__TITLE__": _html_esc(title), "__TITLE_JS__": _js_lit(title),
            "__DATA__": b64, "__REV__": str(MAP_VIEWER_REV),
            "__INFO__": _json_script(info),
            "__THEME__": theme if theme in ("light", "dark") else "",
            "__KEYS_CSS__": kcss, "__KEYS_JS__": kjs, "__KEYS__": _json_script(kdata)}
    # One pass, so a substituted value is never scanned again for another token.
    html = re.sub(r"__(?:TITLE_JS|TITLE|DATA|REV|INFO|THEME|KEYS_CSS|KEYS_JS|KEYS)__",
                  lambda m: repl[m.group(0)], HTML_TEMPLATE)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    os.replace(tmp, path)


def page_name(src_name):
    """mohdm6.bsp -> mohdm6_bsp_view.html, obj_team2.map -> obj_team2_map_view.html."""
    stem, ext = os.path.splitext(os.path.basename(src_name))
    return "%s_%s_view.html" % (stem, (ext[1:] or "map").lower())


# ==============================================================================
#  Build
# ==============================================================================
def _read_pak_list(args):
    """The paks from --pak= options and --paks= list files (one path per line)."""
    paks = list(args["pak"])
    for lf in args["paks"]:
        try:
            with open(lf, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if ln and not ln.startswith("#"):
                        paks.append(ln)
        except OSError as e:
            log("! could not read pak list %s: %s" % (lf, e))
    return [p for p in paks if os.path.isfile(p)]


def build(src, args):
    """Build the viewer page for one .bsp or .map (args from parse_args). A .bsp is
    decompiled first and its .map written to the output folder. Returns
    {"html": page path, "map": decompiled .map or None}; with decompile_only, just
    {"map": ...}."""
    t_start = time.time()
    paks = _read_pak_list(args)
    vfs = None
    if paks and MTX is not None:
        vfs = MTX.Vfs(paks)
        log("paks: %d loaded (%d files)" % (len(paks), len(vfs.index)))
    elif not paks:
        log("no paks given: the map will draw without textures or models")
    cache_dir = args.get("cache")
    shaders, entdefs = ({}, ME.EntityDefs())
    if vfs is not None:
        shaders, entdefs = build_indexes(vfs, paks, cache_dir)
    vpath = (args.get("vfs") or os.path.basename(src)).replace("\\", "/")
    name = os.path.basename(vpath)
    stem, ext = os.path.splitext(name)
    kind = "bsp" if src.lower().endswith(".bsp") else "map"
    outdir = args.get("outdir") or os.path.dirname(os.path.abspath(src))
    os.makedirs(outdir, exist_ok=True)
    blobs = Blobs()
    bspinfo = None
    bsp = stats = None
    with open(src, "rb") as f:
        raw = f.read()
    if kind == "bsp":
        bsp = MB.Bsp(raw, name)
        log("decompiling %s (.bsp version %d) ..." % (name, bsp.version))
        tex_sizes = {}

        def tex_size(shader):
            # the texture size q3map used for this shader's coordinates (TextureTable._size_for)
            k = shader.lower()
            if k not in tex_sizes:
                info = shaders.get(k)
                wh = None
                if vfs is not None:
                    for ref in ((info or {}).get("light"), (info or {}).get("editor"), k):
                        p = vfs.find_texture(ref) if ref else None
                        if p:
                            wh = image_dims(vfs.read(p))
                            if wh:
                                break
                tex_sizes[k] = wh or (64, 64)
            return tex_sizes[k]
        t0 = time.time()
        text, stats = MB.decompile(bsp, tex_size=tex_size, static_classname=entdefs.static_classname, log=log)
        log("decompiled in %.1f s" % (time.time() - t0))
        map_out = MB.output_map_path(outdir, stem)
        if os.path.basename(map_out) != stem + ".map":
            log("(%s.map in that folder isn't one this program wrote, so it's left alone)" % stem)
        with open(map_out, "w", encoding="latin-1", errors="replace", newline="\n") as f:
            f.write(text)
        log("wrote %s" % map_out)
        bspinfo = {"version": bsp.version, "bounds": {str(k): [list(v[0]), list(v[1])] for k, v in stats["bounds"].items()},
                   "firstStatic": stats["first_static"], "aligned": stats["aligned"], "faces": stats["faces"],
                   "mapFile": map_out}
        if args.get("decompile_only"):
            return {"map": map_out}
    else:
        text = raw.decode("latin-1", "replace")
    ents, used = scan_map(text)
    nbrush = sum(e["brushes"] for e in ents)
    npatch = sum(e["patches"] for e in ents)
    nterr = sum(e["terrain"] for e in ents)
    # real entities (an entity number in game, 1024 slots), simple ones, static props (for a
    # .bsp, every entity from its static model lump, which the decompiler writes last)
    kinds = {"real": 0, "simple": 0, "static": 0}
    first_static = bspinfo["firstStatic"] if bspinfo else None
    for i, e in enumerate(ents):
        kinds[ME.entity_kind(e["kvd"].get("classname"), first_static is not None and i >= first_static)] += 1
    log("map: %d entities (%d real, %d simple, %d static props), %d brushes, %d patches, %d terrain blocks, %d textures"
        % (len(ents), kinds["real"], kinds["simple"], kinds["static"], nbrush, npatch, nterr, len(used)))
    if kinds["real"] > 1024:
        log("! %d real entities: more than the game's 1024 entity slots" % kinds["real"])
    # ---- textures -------------------------------------------------------------
    t0 = time.time()
    tcache = TextureCache(os.path.join(cache_dir, "tex") if cache_dir else None)
    texs = TextureTable(vfs, shaders, blobs, args.get("texsize") or TEX_MAX_DIM, tcache)
    for tname in sorted(used):
        texs.add(tname)
    log("textures: %d resolved (%d decoded, %d from cache) in %.1f s"
        % (len(texs.entries) - len(texs.missing), texs.decoded, texs.cached, time.time() - t0))
    if texs.missing:
        shown = ", ".join(texs.missing[:12]) + (" ..." if len(texs.missing) > 12 else "")
        log("textures not found in the paks (%d): %s" % (len(texs.missing), shown))
    # the legend (L in the page) with the editor pictures of its textures
    legend = {"s": LEGEND, "t": {}}
    for tname, val in legend_thumbs(vfs, shaders, tcache).items():
        legend["t"][tname] = [blobs.add(val[1]), val[0]]
    # ---- models ---------------------------------------------------------------
    model_of = {}
    mb = ModelBuilder(vfs, texs, blobs) if vfs is not None else None
    if mb is not None and not args.get("no_models"):
        t0 = time.time()
        for ei, e in enumerate(ents):
            if ei == 0:
                continue
            mp = entity_model_path(e["kvd"], entdefs)
            if not mp:
                continue
            mi = mb.get(mp)
            if mi >= 0:
                model_of[str(ei)] = mi
        log("models: %d placed, %d different (%d vertices) in %.1f s"
            % (len(model_of), len(mb.models), mb.total_verts, time.time() - t0)
            + (", %d with a sprite version (Simple models)" % mb.lod_models if mb.lod_models else ""))
        if mb.failed:
            items = sorted(mb.failed.items())
            for p, why in items[:15]:
                log("  model not drawn: %s - %s" % (p, why))
            if len(items) > 15:
                log("  ... and %d more" % (len(items) - 15))
    # ---- entity definitions for the classes in this map --------------------------
    defs = {}
    counts = {}
    for e in ents:
        cls = e["kvd"].get("classname", "")
        cl = cls.lower()
        counts[cls] = counts.get(cls, 0) + 1
        if cl and cl not in defs:
            d = entdefs.get(cl)
            if d:
                defs[cl] = {"n": d["name"], "c": list(d.get("color") or (0.5, 0.5, 0.5)),
                            "b": [list(d["box"][0]), list(d["box"][1])] if d.get("box") else None,
                            "br": bool(d.get("brush")), "f": list(d.get("flags") or ()),
                            "d": (d.get("desc") or "")[:6000], "s": d.get("source", ""),
                            "t": d.get("tik", "")}
    # ---- the game's sky: sky boxes and cloud layers (.bsp and .map) -------------------------
    skies, clouds = sky_boxes(texs, blobs, vfs)
    if clouds:
        ncl = sum(len(c["s"]) for c in clouds)
        log("sky: %d cloud layer%s" % (ncl, "" if ncl == 1 else "s"))
    # ---- in-game lighting (a .bsp only) ------------------------------------------------
    lit = None
    if bsp is not None:
        t0 = time.time()
        try:
            lit = lit_payload(bsp, stats, texs, blobs, shaders, vfs, ents, model_of, mb.models if mb else [])
        except Exception as e:           # a damaged lighting lump only costs the lit view
            log("! in-game lighting left out: %s" % e)
        if lit:
            log("lighting packed in %.1f s" % (time.time() - t0))
    # ---- what the game draws from the camera (r_showtris) and the AI paths -------------
    vis = None
    if bsp is not None:
        try:
            vis = vis_payload(bsp, stats, texs, blobs)
        except Exception as e:           # a damaged tree only costs r_showtris
            log("! r_showtris left out: %s" % e)
    try:
        paths = paths_payload(vfs, vpath, src, blobs)
    except Exception as e:
        log("! AI paths left out: %s" % e)
        paths = None
    world = ents[0]["kvd"] if ents else {}
    title = vpath
    header = {"v": 1, "name": stem, "path": vpath, "kind": kind, "built": time.strftime("%Y-%m-%d %H:%M"),
              "src": blobs.add(text.encode("latin-1", "replace")),
              "tex": texs.entries, "models": mb.models if mb else [], "modelOf": model_of,
              "defs": defs, "editorFlags": {str(k): v for k, v in ME.EDITOR_FLAGS.items()},
              "bsp": bspinfo, "lit": lit, "sky": skies, "clouds": clouds, "legend": legend,
              "vis": vis, "paths": paths,
              "ek": {"simple": sorted(ME.SIMPLE_CLASSES), "dropped": sorted(ME.DROPPED_CLASSES)}}
    t0 = time.time()
    b64, raw_len, gz_len = pack_payload(header, blobs)
    info = {"name": stem, "path": vpath, "kind": kind, "entities": len(ents), "brushes": nbrush,
            "real": kinds["real"], "simple": kinds["simple"], "static": kinds["static"],
            "patches": npatch, "terrain": nterr, "textures": len(used), "models": len(model_of),
            "message": world.get("message", ""), "classes": sorted(counts.items(), key=lambda kv: kv[0].lower()),
            "missing": texs.missing[:200], "bsp": bool(bspinfo), "bspVersion": bspinfo["version"] if bspinfo else None,
            "mapFile": bspinfo["mapFile"] if bspinfo else None,
            "netBrushes": ents[0]["brushes"] if ents else 0}
    out_html = os.path.join(outdir, page_name(name))
    write_html(out_html, title, b64, info, args.get("theme"))
    log("page data: %.1f MB (%.1f MB before compression) packed in %.1f s"
        % (gz_len / 1048576.0, raw_len / 1048576.0, time.time() - t0))
    log("wrote %s" % out_html)
    log("built in %.1f s" % (time.time() - t_start))
    return {"html": out_html, "map": bspinfo["mapFile"] if bspinfo else None}


def parse_args(argv):
    """(input files, options) from the command line (see USAGE)."""
    a = {"pak": [], "paks": [], "vfs": None, "outdir": None, "cache": None, "texsize": None,
         "theme": None, "no_models": False, "decompile_only": False, "no_open": False}
    files = []
    for x in argv:
        if x.startswith("--pak="):
            a["pak"].append(x[6:])
        elif x.startswith("--paks="):
            a["paks"].append(x[7:])
        elif x.startswith("--vfs="):
            a["vfs"] = x[6:]
        elif x.startswith("--outdir="):
            a["outdir"] = x[9:]
        elif x.startswith("--cache="):
            a["cache"] = x[8:]
        elif x.startswith("--texsize="):
            try:
                a["texsize"] = max(32, min(1024, int(x[10:])))
            except ValueError:
                pass
        elif x.startswith("--theme="):
            a["theme"] = x[8:].lower()
        elif x == "--no-models":
            a["no_models"] = True
        elif x == "--decompile-only":
            a["decompile_only"] = True
        elif x == "--no-open":
            a["no_open"] = True
        elif not x.startswith("--"):
            files.append(x)
    return files, a


def main(argv):
    files, args = parse_args(argv[1:])
    if not files:
        print(USAGE)
        return 1
    src = files[0]
    if not os.path.isfile(src):
        log("! file not found: %s" % src)
        return 2
    try:
        res = build(src, args)
    except MB.BspError as e:
        log("! %s" % e)
        return 3
    except MemoryError:
        log("! out of memory while building the page")
        return 4
    except (struct.error, IndexError) as e:
        # data that points outside its own file: a damaged .bsp (the details go to stderr)
        log("! %s looks damaged: %s" % (os.path.basename(src), e))
        import traceback
        traceback.print_exc()
        return 5
    if res.get("html") and not args["no_open"]:
        try:
            import webbrowser, pathlib
            webbrowser.open(pathlib.Path(os.path.abspath(res["html"])).as_uri())
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

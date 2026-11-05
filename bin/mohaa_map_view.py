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
#    - the map's permanent decals (.dcl) and the compiler's leak trail (.lin)
#
#  A .bak (MOHRadiant's previous save) opens as the .map or .bsp it holds; what it
#  writes has "_bak" in its name.
#
#  Everything is packed into one self-contained .html file (see mohaa_map_page.py
#  for the page itself).
#
#  Command line:
#    python mohaa_map_view.py <map.bsp|map.map|map.bak> [--pak=<file.pk3> ...] [--paks=<list.txt>]
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
MAP_VIEWER_REV = 73

# Bumped when the cached shader / entity index format changes, so old caches are ignored.
INDEX_VERSION = 10

# Default longest side of the textures embedded in the page. 256 keeps a large map's
# page around 10-20 MB; the launcher can ask for 128 or 512.
TEX_MAX_DIM = 256

# Limits for the placed models, so a map full of characters can't stall the build.
MODEL_MAX_UNIQUE = 400
MODEL_MAX_VERTS = 60000            # per model
MODELS_MAX_TOTAL_VERTS = 2500000   # all models together

# Part of every texture cache key; raise it when encode_image's output changes.
TEX_CACHE_FORMAT = 2

USAGE = ("usage: python mohaa_map_view.py <map.bsp|map.map|map.bak> [--pak=<file.pk3> ...] [--paks=<list.txt>]\n"
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


# ---- r_lightmap: what a lit surface shows with it on ----------------------------------------
# With r_lightmap set the game draws a surface's stages only as far as its first lightmap
# stage (tr_shade.c RB_IterateStagesGeneric), and a stage that carries the lightmap as its
# second picture replaces its colour with it (GL_REPLACE). So whether the texture still
# shows depends on how FinishShader joined the stages (tr_shader.c CollapseMultitexture),
# which these state bits and colour sources decide, as ParseStage sets them.
_GLS_SRC = {"gl_one": 0x2, "gl_zero": 0x1, "gl_dst_color": 0x3, "gl_one_minus_dst_color": 0x4,
            "gl_src_alpha": 0x5, "gl_one_minus_src_alpha": 0x6, "gl_dst_alpha": 0x7,
            "gl_one_minus_dst_alpha": 0x8, "gl_src_alpha_saturate": 0x9}
_GLS_DST = {"gl_one": 0x20, "gl_zero": 0x10, "gl_src_alpha": 0x50, "gl_one_minus_src_alpha": 0x60,
            "gl_dst_alpha": 0x70, "gl_one_minus_dst_alpha": 0x80, "gl_src_color": 0x30,
            "gl_one_minus_src_color": 0x40}
_GLS_SIMPLE = {"add": (0x2, 0x20), "filter": (0x3, 0x10), "blend": (0x5, 0x60), "alphaadd": (0x5, 0x20)}
_GLS_ATEST = {"gt0": 0x10000000, "lt128": 0x20000000, "ge128": 0x30000000, "lt_foliage1": 0x40000000,
              "ge_foliage1": 0x50000000, "lt_foliage2": 0x60000000, "ge_foliage2": 0x70000000}
_GLS_BLEND, _GLS_DEPTHMASK, _GLS_NODEPTH, _GLS_DEPTHEQUAL = 0xff, 0x100, 0x800, 0x1000
# CollapseMultitexture's table: (the first stage's blend, the second's) -> (texture
# environment, the blend of the joined stage)
_COLLAPSE = {(0, 0x31): ("mod", 0), (0, 0x13): ("mod", 0), (0x13, 0x13): ("mod", 0x13),
             (0x31, 0x13): ("mod", 0x13), (0x13, 0x31): ("mod", 0x13), (0x31, 0x31): ("mod", 0x13),
             (0, 0x22): ("add", 0), (0x22, 0x22): ("add", 0x22)}
_RGBGENS = {"identity": "identity", "identitylighting": "identitylighting", "global": "global",
            "entity": "entity", "fromentity": "entity", "oneminusentity": "oneminusentity",
            "vertex": "vertex", "fromclient": "vertex", "exactvertex": "exactvertex",
            "lightinggrid": "lightinggrid", "lightingspherical": "lightingspherical",
            "oneminusvertex": "oneminusvertex", "const": "const", "constant": "const",
            "static": "static", "scoord": "scoord", "tcoord": "tcoord", "dot": "dot",
            "oneminusdot": "oneminusdot", "wave": "wave", "colorwave": "colorwave"}


def _stage_state(text):
    """A stage's state bits, colour and alpha sources and which of its two pictures is the
    lightmap, as tr_shader.c ParseStage leaves them."""
    st = {"lm": [False, False], "mt": None, "rgb": None, "rgbw": None, "agen": "identity", "agenw": None}
    src = dst = atest = 0
    dmask, dmx, deq, nodepth, nocolor, nofog = True, False, False, False, False, False
    bundle = 0
    for line in text.splitlines():
        tok = line.split()
        if not tok:
            continue
        kw = tok[0].lower()
        arg = tok[1].lower() if len(tok) > 1 else ""
        if kw == "nextbundle":
            st["mt"] = "add" if arg == "add" else "mod"
            bundle = min(1, bundle + 1)
        elif kw in ("map", "clampmap", "clampmapx", "clampmapy") and arg == "$lightmap":
            st["lm"][bundle] = True
        elif kw == "blendfunc" and arg:
            if arg in _GLS_SIMPLE:
                src, dst = _GLS_SIMPLE[arg]
            else:
                src = _GLS_SRC.get(arg, 0x2)
                dst = _GLS_DST.get(tok[2].lower() if len(tok) > 2 else "", 0x20)
            if not dmx:
                dmask = False
        elif kw in ("alphafunc", "alphatest") and arg:
            atest = _GLS_ATEST.get(arg, 0)
        elif kw == "depthfunc":
            deq = arg == "equal"
        elif kw in ("depthwrite", "depthmask"):
            dmask, dmx = True, True
        elif kw in ("nodepthwrite", "nodepthmask"):
            dmask, dmx = False, True
        elif kw in ("nocolorwrite", "nocolormask"):
            nocolor = True
        elif kw == "nodepthtest":
            nodepth = True
        elif kw == "nofog":
            nofog = True
        elif kw == "rgbgen" and arg in _RGBGENS:
            st["rgb"] = _RGBGENS[arg]
            st["rgbw"] = tuple(x.lower() for x in tok[2:]) if arg == "wave" else None
            if arg in ("vertex", "fromclient", "static") and st["agen"] == "identity":
                st["agen"] = "vertex"
        elif kw == "alphagen" and arg:
            st["agen"] = arg
            st["agenw"] = tuple(x.lower() for x in tok[2:]) if arg == "wave" else None
    if st["rgb"] is None:                      # CGEN_BAD: identity or identityLighting
        st["rgb"] = "identity" if (st["mt"] or st["lm"][0]) else (
            "identitylighting" if src in (0, 0x2, 0x5) else "identity")
    if src == 0x2 and dst == 0x10:             # GL_ONE GL_ZERO: no blending
        src = dst = 0
        dmask = True
    if nodepth:
        dmask = False
    if st["agen"] == "identity" and st["rgb"] in ("identity", "lightinggrid", "lightingspherical"):
        st["agen"] = "skip"
    st["bits"] = ((_GLS_DEPTHMASK if dmask else 0) | src | dst | atest | (_GLS_NODEPTH if nodepth else 0) |
                  (_GLS_DEPTHEQUAL if deq else 0) | (0x100000 if nocolor else 0) | (0x10000 if nofog else 0))
    if st["mt"] and st["lm"][0]:               # FinishShader: the lightmap goes second
        st["lm"] = [st["lm"][1], True]
    return st


def _lightmap_replaces(stage_texts):
    """True when r_lightmap shows this lit surface's lightmap in place of its texture: its
    first lightmap stage gives the lightmap's colour (the texture's alpha still cuts or
    blends it) and isn't a multiply or add over what was drawn before; False when it
    multiplies the lightmap onto the texture drawn before it, as usual."""
    sts = [_stage_state(t) for t in stage_texts]
    if len(sts) > 1:                           # CollapseMultitexture
        keep = ~(_GLS_BLEND | _GLS_DEPTHMASK) & 0xffffffff
        i = 0
        while i < len(sts) - 1:
            a, b = sts[i], sts[i + 1]
            i += 1
            if a["mt"]:
                continue
            ar, br = a["bits"] & keep, b["bits"] & keep
            if ar != br and ((ar & br & ~_GLS_DEPTHEQUAL) or not a["bits"] & _GLS_DEPTHMASK
                             or not b["bits"] & _GLS_DEPTHEQUAL):
                continue
            env = _COLLAPSE.get((a["bits"] & _GLS_BLEND, b["bits"] & _GLS_BLEND))
            if env is None or a["rgb"] != b["rgb"] or a["agen"] != b["agen"]:
                continue
            if env[0] == "add" and a["rgb"] != "identity":
                continue
            if (a["rgb"] == "wave" and a["rgbw"] != b["rgbw"]) or (a["agen"] == "wave" and a["agenw"] != b["agenw"]):
                continue
            a["lm"] = [b["lm"][0], True] if a["lm"][0] else [False, b["lm"][0]]
            a["mt"] = env[0]
            a["bits"] = (a["bits"] & ~_GLS_BLEND) | env[1]
            del sts[i]
    for st in sts:
        if st["lm"][0] or st["lm"][1]:
            return (st["bits"] & _GLS_BLEND) not in (0x13, 0x31, 0x22)
    return False


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


# waveform names (tr_shader.c NameToGenFunc), numbered as the page's model shader takes them
_DEFORM_FUNCS = {"sin": 0, "triangle": 1, "square": 2, "sawtooth": 3, "inversesawtooth": 4}


def _deform(words):
    """A shader's deformVertexes wave or flap (tr_shader.c ParseDeform) as the page draws it:
    [kind (1 wave, 2 flap s, 3 flap t), 1 / spread, wave function, base, amplitude, phase,
    frequency, flap min, flap max], or None for the others (the page doesn't move them)."""
    w = [x.lower() for x in words]
    try:
        if w[0] == "wave" and len(w) >= 7:
            div = float(w[1])
            return [1, 1.0 / div if div else 100.0, _DEFORM_FUNCS.get(w[2], 0)] + [float(x) for x in w[3:7]] + [0.0, 1.0]
        if w[0] == "flap" and len(w) >= 8 and w[1][:1] in ("s", "t"):
            div = float(w[2])
            mn, mx = (float(w[8]), float(w[9])) if len(w) >= 10 else (0.0, 1.0)
            return [2 if w[1][0] == "s" else 3, 1.0 / div if div else 100.0, _DEFORM_FUNCS.get(w[3], 0)] + \
                [float(x) for x in w[4:8]] + [mn, mx]
    except (ValueError, IndexError):
        return None
    return None


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
            elif kw == "deformvertexes" and len(tok) > 1 and "dv" not in info:
                dv = _deform(tok[1:])
                if dv:
                    info["dv"] = dv
        info["nst"] = len(stages)
        sts = [_parse_stage(st) for st in stages]
        info["lmr"] = _lightmap_replaces(stages)
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
# a curve (grey) with its normals (white)
_LEG_NRM = [[3, 21, 8, 18.5, [0.45, 0.45, 0.45]], [8, 18.5, 16, 18.5, [0.45, 0.45, 0.45]],
            [16, 18.5, 21, 21, [0.45, 0.45, 0.45]], [5.5, 19.7, 3, 13.5, [1, 1, 1]],
            [12, 18.5, 12, 11.5, [1, 1, 1]], [18.5, 19.7, 21, 13.5, [1, 1, 1]]]

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
         {"sub": "r_showtris, r_shownormals (the game cvars list, `)"},
         {"sw": "lines", "lines": _LEG_TRIS, "name": "Triangle outlines",
          "desc": "Every triangle the game draws from where the camera is: only what is in its PVS and "
                  "in an area joined to its own. 1 hides them behind walls, 2 shows them through walls."},
         {"sw": "lines", "lines": _LEG_CROSS, "name": "Axis cross",
          "desc": "r_showtris 2 or 3: the origin of the world and of each brush entity and model drawn. "
                  "Red up, green along y, blue a diagonal (the engine's own slip)."},
         {"sw": "lines", "lines": _LEG_NRM, "name": "Vertex normals",
          "desc": "r_shownormals 1: a white line 2 units long along the normal of each point the game "
                  "draws from where the camera is, through walls (the curve itself isn't drawn). "
                  "Terrain has none."},
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
                  "solid and tiled, as MOHRadiant does. The sun is seen through the sky faces: the "
                  "game draws its flare (Sun flare, J) when the line toward the sun meets one first."},
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
            _kx("Up|Down", "move forward / back level with the ground", ("Up", "forward", "move forward, level"),
                ("Down", "back", "move back, level")),
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
            _kx("U", "level the view (no pitch, no tilt)", ("U", "level", "level the view")),
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
            _kx("Shift+click", "on a coloured square in the Find lists: hide / show that entity, every entity "
                "of that class, or every brush and entity using that texture",
                ("Shift+Click", "hide", "on a Find list's square: hide / show that entity, class or texture")),
            _kx("Ctrl+Shift+click|middle-click", "the clicked face's texture",
                ("Ctrl+Shift+Click", "texture"), ("MClick", "texture")),
            _kx("N", "more info on the selection", ("N", "info")),
            _kx("Backspace", "hide the selection", ("Backspace", "hide")),
            _kx("Shift+H", "show everything hidden", ("Shift+H", "show all")),
            _kx("Ctrl+Z", "undo the last hide or show-all (again for the one before)", ("Ctrl+Z", "undo")),
            _kx("Ctrl+F or /", "find: class, targetname, key, texture", ("Ctrl+F", "find"), ("/", "find")),
            _kx_sub("Modify: Trim origin (the camera stays put)", "sel"),
            _kx("W|S|A|D or arrows", "move the new entity forward / back / left / right along the map's axes "
                "nearest the way you face, one trim step a press"),
            _kx("Space|C", "move it up / down one trim step"),
            _kx("Esc or T", "stop trimming (Esc in Edit parameters: done)"),
            _kx("click", "with Make path on: the entity the selected one's target should point at "
                "(Esc cancels)"),
            _kx_sub("Window", "win"),
            _kx("H or ?", "show / hide this window", ("H", "keys", "show / hide the keyboard shortcuts"),
                ("Shift+/", "keys", "show / hide the keyboard shortcuts")),
            _kx("L", "the legend: what the colours, markers and editor surfaces mean", ("L", "legend")),
            _kx("T", "light / dark theme", ("T", "theme")),
            _kx("\\", "collapse / expand the control panel", ("\\", "panel")),
            _kx("Esc", "close a card / clear the selection (Modify's too) / close the map (one a press)", ("Esc", "back")),
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
            _kx("Ctrl+E", "Script ents: show / hide the entities the level script spawns (waypoints, script "
                "models, actors... placed where its lines say)", ("Ctrl+E", "Script", "show / hide the level script's entities")),
            _kx("Ctrl+A", "show every group (All)", ("Ctrl+A", "All")),
            _kx("G", "In-game look: hide what the game never draws, with the game's light, sky and sun flare",
                ("G", "in-game")),
            _kx("Shift+G", "Editor look: MOHRadiant's view, at full brightness with Simple Sky and no sun flare",
                ("Shift+G", "editor")),
            _kx("B", "Full Brightness on / off (off: the game's own lighting)", ("B", "bright")),
            _kx("K", "Simple Sky on / off (off: the game's sky)", ("K", "sky")),
            _kx("M", "Simple models on / off: trees drawn as the sprite the game shows far away",
                ("M", "simple")),
            _kx("J", "Sun flare on / off: the game's lens flare and glare when you look toward the sun",
                ("J", "flare", "Sun flare on / off")),
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
            _kx("0", "Lights off: every light of the map off / on, from the game's baked light (lightmaps, "
                "vertex light, props, models); single lights from Selection's Turn off / Turn on",
                ("0", "lights off", "Lights off: every light off / on")),
            _kx("-", "Sun light on / off: the sun's and the sky's light in the game's baked light (off: the "
                "map lit by its lights and the ambient light alone)",
                ("-", "sun light", "Sun light: the sun's and the sky's light on / off")),
            _kx("=", "Decals on / off: the map's permanent decals (its .dcl), as the game draws them",
                ("=", "decals", "Decals: the map's .dcl decals on / off")),
            _kx("Y", "Weather on / off (cg_rain): the map's rain or snow, made as the game makes it; every setting "
                "is in the game cvars (`)", ("Y", "weather", "Weather: the game's rain and snow on / off")),
            _kx("P", "Leak trail on / off: the line the compiler wrote (the map's .lin) from the void to "
                "the entity it reaches, seen through walls, and where it gets in; on, its card says how to fix it",
                ("P", "leak", "Leak: the compiler's leak trail (.lin) on / off")),
            _kx("+", "Grid on / off: a see-through 3D grid of the grid size round Modify's moving or selected "
                "entity (else ahead of the camera), its coordinates counted from ( 0 0 0 ); on, Modify's Add and "
                "Move snap to its corners", ("Shift+=", "grid", "Grid: the 3D grid on / off (Add and Move snap to it)")),
            _kx("{|}", "grid size down / up: 1, 2, 4 ... 512 units, as MOHRadiant's",
                ("Shift+[", "grid -", "a smaller grid size"), ("Shift+]", "grid +", "a larger grid size")),
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
                if info.get("lmr"):
                    ent["lmr"] = 1             # r_lightmap shows its lightmap alone
            if info.get("rgb0"):
                ent["rg"] = info["rgb0"]
            # how the game draws its picture: texture scale, alphaGen, depthWrite
            if info.get("ptm"):
                ent["tm"] = info["ptm"]
            if info.get("pag"):
                ent["ag"] = info["pag"]
            if info.get("pdw"):
                ent["dw"] = 1
            if info.get("dv"):
                ent["dv"] = info["dv"]         # deformVertexes wave / flap (a tree's leaves)
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
        # each key's first value, "$name" / "#name" counting as "name" where the game has a
        # setter of that name (MB.kv_dict, SETTER_KEYS)
        e["kvd"] = MB.kv_dict(e["kv"])
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


def _q8(n):
    """A normal as three signed bytes (x127), as the page takes normals."""
    return [max(-127, min(127, int(round(c * 127)))) if c == c else 0 for c in n[:3]]


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
        """(frame 0 of the model's idle (or first) animation, the way static models are
        drawn (renderergl1/tr_staticmodels.cpp poses them at frame 0), the model's own
        bounds): the idle animation's bounds, the union of its frames' (TIKI_InitTiki
        copies them into the .tik's mins / maxs, which TIKI_CalculateBounds and
        r_showstaticbboxes use), or None with no "idle" animation (the game then uses
        -4..4)."""
        try:
            anims = MV.parse_tik_animations(txt, every=True)
        except Exception:
            anims = []
        if not anims:
            return {}, None
        pick = None
        for a in anims:
            if a["name"].lower() == "idle":
                pick = a
                break
        idle = pick is not None
        if pick is None:
            pick = anims[0]
        ref = _resolve_in_vfs(self.vfs, pick["file"], [setup_path, tik_dir])
        if not ref or not ref.endswith(".skc"):
            return {}, None
        data = self.vfs.read(ref)
        if not data:
            return {}, None
        fd, tmp = tempfile.mkstemp(suffix=".skc")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            skc = MV.parse_skc(tmp)
        except Exception:
            return {}, None
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        bounds = None
        fb = skc.get("fbounds") or []
        if idle and fb:
            bounds = [[min(b[k] for b in fb) for k in range(3)], [max(b[3 + k] for b in fb) for k in range(3)]]
        return (skc["frames"][0] if skc.get("frames") else {}), bounds

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
        tbounds = None
        classname = None
        if low.endswith(".tik"):
            txt = self._tik_text(low)
            parts = MV.parse_tik_skelmodels(txt)
            if not parts:
                raise ValueError("the .tik names no skelmodel")
            scale = MV.parse_tik_scale(txt) or 1.0
            setsize = MV.parse_tik_setsize(txt)
            try:
                classname = MV.parse_tik_classname(txt)
            except Exception:
                classname = None
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
            channels, tbounds = self._pose_channels(txt, tik_dir, setup_path)
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
        # r_shownormals: each vertex's normal turned by its first weight's bone, as the
        # renderer turns it (SkelVertGetNormal for an entity, pStaticNormal for a static
        # model, tr_staticmodels.cpp), unscaled
        from array import array
        nrm = array("b")
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
            ns = s.get("normals") or []
            for vi, (weights, (u, v)) in enumerate(zip(s["verts"], s["uvs"])):
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
                b0 = weights[0][0] if weights else -1
                if vi < len(ns) and 0 <= b0 < len(wR):
                    R, n = wR[b0], ns[vi]
                    nrm.extend(_q8((R[0][0] * n[0] + R[0][1] * n[1] + R[0][2] * n[2],
                                    R[1][0] * n[0] + R[1][1] * n[1] + R[1][2] * n[2],
                                    R[2][0] * n[0] + R[2][1] * n[1] + R[2][2] * n[2])))
                else:
                    nrm.extend((0, 0, 0))
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
        # the .tik's own bounds as the game keeps them (the idle animation's, else -4..4;
        # TIKI_LoadTIKIfile), times its scale: sv_showbboxes 7 and r_showstaticbboxes
        if tbounds is None:
            tbounds = [[-4.0, -4.0, -4.0], [4.0, 4.0, 4.0]]
        tb = [[round(v * scale, 3) for v in tbounds[0]], [round(v * scale, 3) for v in tbounds[1]]]
        out = {"p": path,
               "v": self.blobs.add(struct.pack("<%df" % len(pos), *pos)),
               "t": self.blobs.add(struct.pack("<%df" % len(uvs), *uvs)),
               "i": self.blobs.add(struct.pack("<%dI" % len(idx), *idx)),
               "s": surfs, "b": [mins, maxs], "ss": setsize, "sc": scale, "nv": nverts, "env": eng,
               "tb": tb, "n": self.blobs.add(nrm.tobytes())}
        if classname:
            out["cn"] = classname          # the .tik's server "classname" (what it spawns as)
        return out


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
#  The sun flare (.bsp and .map)
# ==============================================================================
# The game draws its sun only as a lens flare (RB_DrawSun is compiled out). The
# worldspawn's sun keys give its direction and name the flare, a section of
# global/lensflaredefs.txt; the page draws it (drawSunFlare in mohaa_map_page.py) and,
# for a .bsp, learns from the vis payload which leafs see the sun.
LENSFLARE_DEFS = "global/lensflaredefs.txt"
SUN_FLARE_MAX_DIM = 256
_SCANF_FLOAT = re.compile(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")
_LF_TOKEN = re.compile(r'//[^\n]*|/\*.*?(?:\*/|$)|"([^"]*)"?|(\S+)', re.S)


def _scan_floats(text, n):
    """sscanf(text, "%f %f %f"): up to n numbers, each right after the one before it
    (blanks between). One that isn't there is 0 here; the engine leaves it unset."""
    out, pos = [], 0
    while len(out) < n:
        m = _SCANF_FLOAT.match(text or "", pos)
        if not m:
            break
        out.append(float(m.group(1)))
        pos = m.end()
    return out + [0.0] * (n - len(out))


def _forward(angles):
    """The forward vector of "pitch yaw roll" (AngleVectorsLeft, q_math.c)."""
    p, y = (math.radians(a) for a in _scan_floats(angles, 3)[:2])
    return [math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), -math.sin(p)]


def world_sun(entities):
    """The sun as R_Sphere_InitLights (renderergl1/tr_sphere_shade.cpp) reads it from the
    entities' keys (each entity a list of (key, value), in order), the key names compared
    as written: the keys up to the first entity whose classname isn't worldspawn count.
    "suncolor" or "sunlight" makes a sun, as does "sundirection", whose forward vector is
    the flare's too unless a "sunflaredirection" came first (that one always sets it);
    "sunflarename" names the flare, "sun" when a sun has none.
    Returns {"exists", "dir": the flare's direction or None, "name"}."""
    exists, flaredir, dir_set, name = False, None, False, ""
    for kv in entities:
        for k, v in kv:
            if k == "classname":
                if v != "worldspawn":
                    return {"exists": exists, "dir": flaredir, "name": name or ("sun" if exists else "")}
            elif k in ("suncolor", "sunlight"):
                exists = True
            elif k == "sundirection":
                exists = True
                if not dir_set:
                    flaredir = _forward(v)
            elif k == "sunflaredirection":
                flaredir, dir_set = _forward(v), True
            elif k == "sunflarename":
                name = v[:63]
    return {"exists": exists, "dir": flaredir, "name": name or ("sun" if exists else "")}


def lens_flare_def(text, which):
    """One section of lensflaredefs.txt as lens_flare::Init (tr_sun_flare.cpp) reads it,
    from "begin <which>" (any case) to "end": dot_min, fullscale, fullscreen (a shader
    name), fullfade (whole milliseconds) and the flares, each "flare <size> <where>
    <shader> [alphascale]" with its words on the directive's own line (COM_ParseExt
    without line breaks: a flare missing one is left out). The defaults are dot_min .8,
    fullscale .7, no fullscreen and fullfade 0. None when there is no such section."""
    toks, line, last = [], 0, 0
    for m in _LF_TOKEN.finditer(text):
        line += text.count("\n", last, m.start())
        last = m.start()
        if m.group(1) is not None or m.group(2) is not None:
            toks.append((m.group(1) if m.group(1) is not None else m.group(2), line))
    n, i = len(toks), 0

    def arg():
        # the next word if it is on the line of the last one read, else "" (none read)
        nonlocal i
        if i < n and toks[i][1] == toks[i - 1][1]:
            i += 1
            return toks[i - 1][0]
        return ""
    while i < n:
        i += 1
        if toks[i - 1][0].lower() == "begin" and arg().lower() == which.lower():
            break
    else:
        return None
    d = {"dot_min": 0.8, "fullscale": 0.7, "fullscreen": None, "fullfade": 0, "flares": []}
    while i < n:
        i += 1
        k = toks[i - 1][0].lower()
        if k == "end":
            break
        if k == "flare":
            a = [arg()]
            while a[-1] and len(a) < 4:
                a.append(arg())
            if len(a) < 4 or not a[2]:
                continue
            d["flares"].append([_atof(a[0]), _atof(a[1]), a[2], _atof(a[3]) if a[3] else 1.0])
        elif k in ("dot_min", "fullscale", "fullscreen", "fullfade"):
            a = arg()
            if a:
                d[k] = a if k == "fullscreen" else int(_atof(a)) if k == "fullfade" else _atof(a)
    return d


def _png_image(data, max_dim):
    """A picture re-encoded as PNG (a flare's smooth glow would show JPEG's blocks),
    no bigger than max_dim."""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    if max(im.size) > max_dim:
        r = max_dim / float(max(im.size))
        im = im.resize((max(1, int(round(im.size[0] * r))), max(1, int(round(im.size[1] * r)))),
                       Image.BILINEAR)
    im = im.convert("RGBA" if ("A" in im.getbands() or im.mode == "P") else "RGB")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "image/png", buf.getvalue()


def _flare_picture(name, vfs, shaders, blobs):
    """How a flare's shader draws (all the game's are one additive stage): the picture
    of its first stage (None for $whiteimage and the other built-in images: white) and
    that stage's blendFunc, as [blob, mime, source factor, destination factor]; or None
    when the picture isn't in the paks. A name with no shader is a picture of that
    name, added."""
    info = shaders.get(name.lower().replace("\\", "/"))
    pic = info.get("stage0map") if info else name
    src, dst = _blend_factors(info.get("blend0")) if info else (6, 1)
    if not pic:
        return None
    if pic.startswith(("$", "*")):
        return [None, None, src, dst]
    path = vfs.find_texture(pic)
    data = vfs.read(path) if path else None
    if not data:
        return None
    try:
        mime, raw = _png_image(data, SUN_FLARE_MAX_DIM)
    except Exception:
        return None
    return [blobs.add(raw), mime, src, dst]


def sun_payload(entities, vfs, shaders, blobs):
    """The page's sun flare (D.sun): {"d": its direction (a unit vector), "n": the flare's
    name, "dm": dot_min, "fs": fullscale, "ff": fullfade in milliseconds, "full": 1 when
    the screen brightens and fades (a fullscreen shader and a fullfade), "fl": the
    flares [[size, where, alphascale, picture], ...], "tx": their pictures
    (_flare_picture)}; or {"none": why the game draws no flare here}, which the page
    shows on its greyed-out Sun flare button."""
    sun = world_sun(entities)
    if not sun["exists"]:
        return {"none": "This map has no sun: its worldspawn has no suncolor, sunlight or sundirection."}
    name = sun["name"]
    if name.lower() == "none":
        return {"none": "This map turns the sun flare off: its worldspawn has \"sunflarename\" \"none\"."}
    if sun["dir"] is None:
        return {"none": "This map's sun has no sundirection (or sunflaredirection), so the game draws no flare."}
    if vfs is None:
        return {"none": "No paks were loaded, so the sun flare (%s) isn't known." % LENSFLARE_DEFS}
    data = vfs.read(LENSFLARE_DEFS)
    if not data:
        return {"none": "The paks have no %s, so the game draws no sun flare." % LENSFLARE_DEFS}
    d = lens_flare_def(data.decode("latin-1", "replace"), name)
    if d is None:
        return {"none": "%s has no \"%s\" flare (this map's sunflarename), so the game draws none."
                % (LENSFLARE_DEFS, name)}
    pics, index, flares = [], {}, []
    for size, where, shader, ascale in d["flares"]:
        key = shader.lower()
        if key not in index:
            pic = _flare_picture(shader, vfs, shaders, blobs)
            index[key] = len(pics) if pic else -1
            if pic:
                pics.append(pic)
        if index[key] >= 0:
            flares.append([size, where, ascale, index[key]])
    if not flares:
        return {"none": "The \"%s\" flare in %s has no flare picture in the paks." % (name, LENSFLARE_DEFS)}
    return {"d": [round(x, 6) for x in sun["dir"]], "n": name, "dm": d["dot_min"], "fs": d["fullscale"],
            "ff": d["fullfade"], "full": 1 if d["fullscreen"] and d["fullfade"] > 0 else 0,
            "fl": flares, "tx": pics}


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

    # ---- lightmaps: the .bsp's own bytes, packed 8 pages across in one PNG. The page
    # brightens them the way the game does (R_ColorShiftLightingBytes, as MB.color_shift)
    # and keeps them as they are for r_lightmap 2, which colours them by their raw
    # intensity (R_LoadLightmaps) ------------------------------------------------------
    raw = bsp.lump(MB.LUMP_LIGHTMAPS)[:nlm * page]
    cols = min(8, nlm)
    rows = (nlm + cols - 1) // cols
    atlas = Image.new("RGB", (cols * MB.LIGHTMAP_SIZE, rows * MB.LIGHTMAP_SIZE))
    for k in range(nlm):
        pg = Image.frombytes("RGB", (MB.LIGHTMAP_SIZE, MB.LIGHTMAP_SIZE), raw[k * page:(k + 1) * page])
        atlas.paste(pg, ((k % cols) * MB.LIGHTMAP_SIZE, (k // cols) * MB.LIGHTMAP_SIZE))
    buf = io.BytesIO()
    atlas.save(buf, "PNG", compress_level=9)
    out = {"lm": blobs.add(buf.getvalue()), "nlm": nlm, "cols": cols, "raw": 1,
           "shift": MB.OVERBRIGHT_SHIFT}

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

    # ---- patches: lightmap coordinates, vertex light and normal per control point ---------
    # in the .map's control point order (row j holds the .bsp's column j). The normals tell
    # which side the compiler lit (the page's Lights off weighs a patch's texels by them).
    PL, PN = array("f"), array("f")
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
                PN.extend(bsp.vert_normal(s["firstVert"] + i * w + j))
        patches.append([ei, bn, layer, off, w * h])
    out.update({"p": patches, "pl": blobs.add(PL.tobytes()), "pc": blobs.add(MB.color_shift(bytes(PCOL), 4)),
                "pn": blobs.add(PN.tobytes())})

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


def lightgrid_payload(bsp, blobs):
    """The light grid as the game keeps it, for r_light_showgrid (R_LoadLightGrid in
    tr_bsp.c): its corner, cell size and size in cells, and its palette, column offsets and
    run-length packed columns as they are in the .bsp. None when it can't be read."""
    g = MB.LightGrid(bsp)
    if not g.ok:
        return None
    return {"m": [float(v) for v in g.mins], "s": [float(v) for v in g.size], "b": list(g.bounds),
            "o": blobs.add(struct.pack("<%dH" % len(g.offsets), *g.offsets)),
            "p": blobs.add(bytes(g.pal)), "d": blobs.add(bytes(g.data))}


def rain_payload(vfs, vpath):
    """How far around the player a func_rain drops its rain (cg.rain.min_dist, 512 unless
    the map's script sets it), for cg_rain_drawcoverage: {"min": units, "src": where it was
    set} from the last uncommented "level.rain_min_dist = N" or "setcvar cg_rain_min_dist N"
    in maps/<map>.scr. None when the script can't be read."""
    if vfs is None:
        return None
    stem = os.path.splitext(vpath.replace("\\", "/"))[0]
    if not stem.lower().startswith("maps/"):
        stem = "maps/" + os.path.basename(stem)
    k = (stem + ".scr").lower()
    if k not in vfs.index:
        return None
    try:
        txt = vfs.read(k).decode("latin-1", "replace")
    except Exception:
        return None
    txt = re.sub(r"/\*.*?\*/", " ", txt, flags=re.S)
    found = None
    for line in txt.splitlines():
        line = line.split("//", 1)[0]
        m = re.search(r'(?i)\blevel\.rain_min_dist\s*=\s*"?\s*([-+]?\d*\.?\d+)', line) or \
            re.search(r'(?i)\bsetcvar\s+"?cg_rain_min_dist"?\s+"?\s*([-+]?\d*\.?\d+)', line)
        if m:
            found = float(m.group(1))
    return {"min": found if found is not None else 512.0, "src": k, "set": found is not None}


# The weather pictures the game has (scripts/effects.shader): the rain streak and twelve
# snowflakes, the shaders cg.rain names (cg_rain_shader, cg_rain_numshaders).
_WEATHER_SHADERS = ["textures/rain"] + ["textures/snow%d" % i for i in range(12)]


def _shader_rgb_consts(vfs, names):
    """{shader: [r, g, b]}: the "rgbGen constant" of each shader's first stage (the
    weather shaders are added with it: textures/rain .2, the snow .5), else white."""
    want = {n.lower() for n in names}
    out = {}
    if vfs is None:
        return out
    for k in sorted(vfs.index):
        if not (k.startswith("scripts/") and k.endswith(".shader")):
            continue
        try:
            txt = _strip_comments(vfs.read(k).decode("latin-1", "replace"))
        except Exception:
            continue
        for m in re.finditer(r"(?m)^\s*(\S+)\s*\{", txt):
            name = m.group(1).lower()
            if name not in want or name in out:
                continue
            body = txt[m.end():m.end() + 2000]
            st = re.search(r"\{(.*?)\}", body, re.S)
            c = re.search(r"(?i)\brgbgen\s+const(?:ant)?\s+\(?\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)", st.group(1)) if st else None
            out[name] = [float(c.group(1)), float(c.group(2)), float(c.group(3))] if c else [1.0, 1.0, 1.0]
    return out


def weather_shader_names(shader, num):
    """The shaders the client takes the rain from (cg_main.c, CS_RAIN_SHADER /
    CS_RAIN_NUMSHADERS): with numshaders, shader + 0 .. numshaders - 1 (a digit at the end
    of the name dropped first, as OpenMoHAA does: "textures/snow0" and 12 give snow0 to
    snow11), else the shader itself."""
    shader = (shader or "").strip()
    try:
        num = int(float(num or 0))
    except ValueError:
        num = 0
    if num > 0:
        if shader[-1:].isdigit():
            shader = shader[:-1]
        return ["%s%d" % (shader, i) for i in range(min(num, 32))]
    return [shader] if shader else []


def weather_payload(vfs, texs, scr, say=log):
    """The weather (cg_rain_* in the page): the pictures of the rain and snow shaders,
    and the rain settings the map's script makes (level.rain_* or setcvar cg_rain_*:
    LevelScript), so the page starts with the map's own. {"tex": {shader: [texture,
    [r, g, b]]}, "set": {setting: [value, file, line, text]}, "varies": [...],
    "wscr": the script runs global/weather.scr}."""
    rain = dict((scr or {}).get("rain") or {})
    names = list(_WEATHER_SHADERS)
    sh = (rain.get("shader") or [None])[0]
    if sh:
        for n in weather_shader_names(sh, (rain.get("numshaders") or [0])[0]):
            if n.lower() not in names:
                names.append(n.lower())
    rgb = _shader_rgb_consts(vfs, names)
    tex = {n: [texs.add(n, model=True), rgb.get(n.lower(), [1.0, 1.0, 1.0])] for n in names}
    wscr = "global/weather.scr" in ((scr or {}).get("glob") or ())
    if rain or wscr:
        say("weather: the script sets %s%s" % (", ".join("%s %s" % (k, v[0] if v[0] is not None else "(varies)")
                                                         for k, v in sorted(rain.items())) or "nothing",
                                               "; it runs global/weather.scr" if wscr else ""))
    return {"tex": tex, "set": rain, "varies": (scr or {}).get("rainv") or [], "wscr": int(wscr)}


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
    SK = array("I")                   # the sky polygons' triangles (r_showsky), as vertices of V
    # r_shownormals: the normal the renderer has for each vertex of V, as signed bytes x127.
    # A face takes its plane's (ParseFace copies lightmapVecs[2] as it is, RB_SurfaceFace
    # puts it on every point), a triangle soup its vertices' own (RB_SurfaceTriangles), a
    # patch its grid's (MakeMeshNormals); the sky's are never drawn.
    VN = array("b")
    q8 = _q8
    verts = bsp._verts
    counts = [0, 0, 0, 0, 0]
    kinds = {MB.MST_PLANAR: 1, MB.MST_TRIANGLE_SOUP: 2, MB.MST_PATCH: 3}
    for si, s in enumerate(bsp.surfaces):
        rec, flo = [0] * 8, [0.0] * 10
        own = owner.get(si)
        sh = bsp.shaders[s["shader"]] if 0 <= s["shader"] < len(bsp.shaders) else None
        kind = kinds.get(s["type"], 0) if own and sh else 0
        info = texs.info(sh["name"]) if kind else None
        bits = shader_render_bits(info)[0] if info else 0
        if kind and (sh["surface"] & MB.SURF_NODRAW or bits & TF_NODRAW):
            kind = 0                  # never drawn
        elif kind and (sh["surface"] & MB.SURF_SKY or bits & TF_SKY):
            # drawn as the sky box, which r_showtris doesn't outline; kind 4 keeps the
            # polygon's triangles for r_showsky (RB_ClipSkyPolygons)
            kind = 4 if kind in (1, 2) else 0
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
                    for n in MB.grid_normals(gw, gh, grid):
                        VN.extend(q8(n))
                    GE.extend(ew)
                    GE.extend(eh)
                    # the lod group's centre and radius (ParseMesh: lightmapVecs 0 and 1)
                    a, b = s["vecs"][0:3], s["vecs"][3:6]
                    c = [(a[k] + b[k]) * 0.5 for k in range(3)]
                    flo[0:4] = [c[0] + org[0], c[1] + org[1], c[2] + org[2],
                                math.sqrt(sum((a[k] - c[k]) ** 2 for k in range(3)))]
                    mn = [min(p[k] for p in grid) for k in range(3)]
                    mx = [max(p[k] for p in grid) for k in range(3)]
            elif kind == 4:
                base = len(V) // 3
                for p in pts:
                    V.extend(p)
                VN.extend([0] * (3 * nv))
                idx = bsp.indexes[s["firstIndex"]:s["firstIndex"] + s["numIndexes"]]
                rec[3] = len(SK)
                for t in range(0, len(idx) - 2, 3):
                    a, b, c = idx[t], idx[t + 1], idx[t + 2]
                    if 0 <= a < nv and 0 <= b < nv and 0 <= c < nv:
                        SK.extend((base + a, base + b, base + c))
                rec[4] = len(SK) - rec[3]
                rec[5] = texs.add(sh["name"])     # its texture entry: which sky box and clouds
                if s["type"] != MB.MST_PLANAR:
                    rec[1] = 2                # a triangle soup isn't culled by its plane
                else:
                    n = s["vecs"][6:9]
                    if abs(n[0]) + abs(n[1]) + abs(n[2]) < 0.5:
                        n = MB._norm(MB._cross(MB._sub(pts[2], pts[0]), MB._sub(pts[1], pts[0]))) or (0.0, 0.0, 0.0)
                        if n == (0.0, 0.0, 0.0):
                            rec[1] = 2
                    flo[0:4] = [n[0], n[1], n[2], pts[0][0] * n[0] + pts[0][1] * n[1] + pts[0][2] * n[2]]
                if not rec[4]:
                    kind = rec[0] = 0
            else:
                base = len(V) // 3
                for p in pts:
                    V.extend(p)
                if kind == 1:
                    VN.extend(q8(s["vecs"][6:9]) * nv)
                else:
                    for n in struct.iter_unpack("<12x8x8x3f4x", verts[fv * 44:(fv + nv) * 44]):
                        VN.extend(q8(n))
                rec[5], rec[6] = base, nv     # its points in V (r_shownormals)
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
           "sk": blobs.add(SK.tobytes()), "bm": bm, "to": list(stats["terrain_owner"]),
           "nn": len(tree["nodes"]), "nl": len(tree["leafs"]), "ns": len(bsp.surfaces)}
    if len(VN) == len(V):
        out["vn"] = blobs.add(VN.tobytes())
    else:                             # can't happen; r_shownormals is then greyed out
        say("! r_shownormals left out: %d normals for %d points" % (len(VN) // 3, len(V) // 3))
    areas = {t[1] for t in tree["leafs"] if t[1] >= 0}
    say("visibility: %d leafs in %d clusters%s, %d area%s; %d faces, %d triangle soups and %d patches drawn in game"
        ", %d sky polygons"
        % (len(tree["leafs"]), vis[0] if vis else 0, "" if vis else " (no vis data: every leaf sees every other)",
           len(areas), "" if len(areas) == 1 else "s", counts[1], counts[2], counts[3], counts[4]))
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
    # "fail": the file's node check failed flag (PathSearch::m_NodeCheckFailed), which
    # g_nodecheck 1 acts on when the map loads
    return {"src": where, "n": len(pf["nodes"]), "time": pf["maptime"], "fail": int(bool(pf["failed"])),
            "o": blobs.add(O.tobytes()), "f": blobs.add(F.tobytes()), "c": blobs.add(C.tobytes())}


def _map_side_file(vfs, vpath, src, ext):
    """(bytes, where it was found, its time or None) of maps/<map><ext> in the paks, else
    the file of that name beside the source on disk (NormandyBridge_V1.bak finds
    NormandyBridge_V1.lin), or (None, None, None)."""
    stem = os.path.splitext(vpath.replace("\\", "/"))[0]
    if not stem.lower().startswith("maps/"):
        stem = "maps/" + os.path.basename(stem)
    if vfs is not None:
        k = (stem + ext).lower()
        if k in vfs.index:
            zi, real = vfs.index[k]
            return vfs.read(k), "%s (%s)" % (real, os.path.basename(vfs.zips[zi].filename)), None
    side = os.path.splitext(src)[0] + ext
    if os.path.isfile(side):
        with open(side, "rb") as f:
            return f.read(), side, os.path.getmtime(side)
    return None, None, None


def read_dcl(data):
    """A .dcl, the permanent decals MOHRadiant places and the game loads with the map
    (renderergl1/tr_marks_permanent.c, R_LoadPermanentMarks): dclHeader_t ("DCL ",
    version 1 or 2, checksum, decal count, fragment count; version 2 then the 32-byte
    map_time of the .bsp they were made for), the decals (dclSavedMarkDef_t, 124 bytes:
    shader, origin, projection, radius, height / width scale, rotation, colour, lighting)
    and the fragments the decals were cut into (dclSavedMarkPoly_t, 76 bytes: shader, fog
    number, decal, vertex count; then that many polyVert_t of 24 bytes: xyz, st and the
    lit colour as 4 bytes). The lists of fragments per brush model and leaf after them
    aren't needed here. Returns {"ver", "time", "decals": [(shader, origin, radius)],
    "frags": [(shader, decal, [(x, y, z, s, t, r, g, b, a)])]}."""
    if len(data) < 20 or data[:4] != b"DCL ":
        raise ValueError("not a .dcl file")
    ver, _check, nd, nf = struct.unpack_from("<4i", data, 4)
    if ver not in (1, 2):
        raise ValueError("unknown .dcl version %d" % ver)
    if not (0 <= nd < 1 << 20 and 0 <= nf < 1 << 20):
        raise ValueError("bad decal counts")
    o = 20
    tm = ""
    if ver == 2:
        tm = data[o:o + 32].split(b"\0", 1)[0].decode("latin-1", "replace")
        o += 32
    decals, frags = [], []
    for _ in range(nd):
        if o + 124 > len(data):
            raise ValueError("the file ends inside its decals")
        sh = data[o:o + 64].split(b"\0", 1)[0].decode("latin-1", "replace")
        v = struct.unpack_from("<3f3f4f4fi", data, o + 64)
        decals.append((sh, v[0:3], v[6]))
        o += 124
    for _ in range(nf):
        if o + 76 > len(data):
            raise ValueError("the file ends inside its fragments")
        sh = data[o:o + 64].split(b"\0", 1)[0].decode("latin-1", "replace")
        _fog, di, nv = struct.unpack_from("<3i", data, o + 64)
        o += 76
        if nv < 0 or nv > 64 or o + 24 * nv > len(data):
            raise ValueError("a fragment with %d vertices" % nv)
        frags.append((sh, di, [struct.unpack_from("<5f4B", data, o + 24 * k) for k in range(nv)]))
        o += 24 * nv
    return {"ver": ver, "time": tm, "decals": decals, "frags": frags}


def dcl_payload(vfs, vpath, src, texs, blobs, say=log):
    """The map's permanent decals from maps/<map>.dcl (read_dcl), drawn as the game draws
    them: each fragment a fan of its vertices with its shader's picture times the lit
    colour the file keeps. {"src", "ver", "time", "n": decals, "nf": fragments,
    "d": per decal [texture, x, y, z, radius], "t": per fragment its texture, "k": its
    vertex count, "p" / "s" / "c": the vertices' xyz, st and colour bytes}, or {"src",
    "err"}, or None when there is no .dcl."""
    from array import array
    data, where, _mt = _map_side_file(vfs, vpath, src, ".dcl")
    if data is None:
        return None
    try:
        dc = read_dcl(data)
    except (ValueError, struct.error) as e:
        say("! decals %s can't be read: %s" % (where, e))
        return {"src": where, "err": str(e)}
    T, K, P, S = array("i"), array("i"), array("f"), array("f")
    Cb = bytearray()
    for sh, _di, verts in dc["frags"]:
        if len(verts) < 3:
            continue
        T.append(texs.add(sh, model=True))
        K.append(len(verts))
        for v in verts:
            P.extend(v[0:3])
            S.extend(v[3:5])
            Cb.extend(v[5:9])
    dl = [[texs.add(sh, model=True), round(o[0], 2), round(o[1], 2), round(o[2], 2), round(r, 2)]
          for sh, o, r in dc["decals"]]
    say("decals: %d (%d fragments) from %s%s" % (len(dc["decals"]), len(T), where,
                                                  ", made for the .bsp of %s" % dc["time"] if dc["time"] else ""))
    return {"src": where, "ver": dc["ver"], "time": dc["time"], "n": len(dc["decals"]), "nf": len(T), "d": dl,
            "t": blobs.add(T.tobytes()), "k": blobs.add(K.tobytes()), "p": blobs.add(P.tobytes()),
            "s": blobs.add(S.tobytes()), "c": blobs.add(bytes(Cb))}


def leak_payload(vfs, vpath, src, src_time, say=log):
    """The leak trail q3map writes when the map isn't sealed: maps/<map>.lin, one point a
    line (LeakFile: the middle of each portal on the shortest way from the void to the
    entity that reaches it, then that entity's origin, so the first point is at the hole).
    {"src", "p": [[x, y, z], ...], "old": the .lin is older than the map it is beside},
    or None."""
    data, where, mt = _map_side_file(vfs, vpath, src, ".lin")
    if data is None:
        return None
    pts = []
    for ln in data.decode("latin-1", "replace").splitlines():
        w = ln.replace(",", " ").split()
        if len(w) < 3:
            continue
        try:
            p = [float(w[0]), float(w[1]), float(w[2])]
        except ValueError:
            continue
        if all(abs(x) < 1e6 for x in p):
            pts.append([round(x, 3) for x in p])
        if len(pts) >= 20000:
            break
    if not pts:
        say("! leak trail %s has no points" % where)
        return {"src": where, "p": [], "err": "no points in the file"}
    old = bool(mt is not None and src_time is not None and mt + 1 < src_time)
    say("leak trail: %d points (%s)%s" % (len(pts), where, " - older than the map beside it" if old else ""))
    return {"src": where, "p": pts, "old": int(old)}


# ==============================================================================
#  Level scripts: what the map's .scr spawns and sets
# ==============================================================================
# The game runs maps/<map>.scr when the level loads (Level::SpawnEntities). The viewer
# doesn't run it as the game does (no waits, no threads in parallel, no events): it walks
# the script (and the map's own scripts it execs or threads into, not global/) once, top
# to bottom, keeping what it can work out without the game, for
#   - "spawn <class or model> [key value ...]" (ScriptThread::SpawnEntity), with the
#     properties the following lines give the same entity: "<ent>.origin = ( x y z )",
#     "<ent> origin ( x y z )", angles, angle, targetname, target, model, scale, setsize,
#     the entity named as "local.x", "level.x", "$targetname" or "$(expression)";
#   - "<map entity>.target = ..." on an entity of the map (a map node joined to the
#     script's own);
#   - "setcvar <name> <value>" and the "$world" lines (farplane and the like).
# Values are worked out where they are plain: strings, numbers, vectors, arithmetic,
# comparisons, local / level variables, "$name" and "$(expression)" as entities (NULL
# when there is none), and "$name.origin" / ".angles" of a map or script entity.
# Control flow: "for" and "while" loops run as long as their condition can be worked out
# (so "for (local.q = 1700; local.q <= 1715; local.q++)" runs 16 times with local.q set),
# else once with the counter unknown; "if" takes its branch when the condition is known,
# else both. What depends on the game running (a thread's parameters, self, a random
# number, waittill) stays unknown; an entity whose place is unknown is listed, not drawn.
_SCR_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|(-?(?:\d+\.?\d*|\.\d+)(?![\w.]))|([A-Za-z_$#@](?:[\w./\\$#:]|-(?=\w))*)'
                        r'|(==|!=|<=|>=|&&|\|\||\+\+|--|[-+*/=(){}\[\];,<>!%&|.])')
_SCR_LABEL = re.compile(r'^\s*([A-Za-z_][\w]*)((?:\s+(?:local|group)\.[\w]+)*)\s*:\s*$')
_SCR_PROPS = {"origin", "angles", "angle", "targetname", "target", "model", "scale", "setsize", "spawnflags",
              "classname"}
_SCR_NOT_SPAWN = {"waittill", "waittilltrigger", "thread", "waitthread", "exec", "waitexec", "goto", "end"}
_SCR_NULL = ("null",)
# the level's rain settings (Level::SetRain*: CS_RAIN_* configstrings, cg.rain in the client)
_RAIN_KEYS = ("density", "speed", "speed_vary", "slant", "length", "min_dist", "width", "shader", "numshaders",
              "thundertime")      # (level.thundertime: global/weather.scr's time between lightning)


def _scr_strip(text):
    """The script with its // and /* */ comments blanked (line breaks kept, so line
    numbers stay right); text in quotes is left alone."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"' and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * text.count("\n", i, j))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _scr_num(x):
    """A number as the game prints it in a string: whole numbers without a point."""
    return ("%d" % x) if float(x).is_integer() and abs(x) < 1e15 else ("%g" % x)


def _scr_str(v):
    """A value as a key's text: a vector as "x y z", an entity as its targetname."""
    if isinstance(v, list):
        return " ".join(_scr_num(x) for x in v)
    if isinstance(v, float):
        return _scr_num(v)
    if isinstance(v, tuple):
        return v[1] if v[0] == "$" else ""
    return v


class _ScrStop(Exception):
    """The walk took too many steps (a script that loops a very long way)."""


class _ScrBreak(Exception):
    """break: out of the loop it is in."""


class _ScrContinue(Exception):
    """continue: on to the loop's next turn."""


class _ScrMaybe(Exception):
    """A break or continue under a condition the viewer can't tell (an if read both ways):
    the loop may end there, so it goes no further and its counter is unknown."""
    def __init__(self, brk):
        Exception.__init__(self)
        self.brk = brk


class LevelScript:
    """Reads a map's level scripts (see above). find(path) returns (text, where) for a
    script path such as "maps/m3l1b.scr", or (None, None)."""

    MAX_FILES = 40
    MAX_LOOP = 4096               # turns of one loop
    MAX_STEPS = 400000            # statements run in all

    def __init__(self, find, ents):
        self.find = find
        self.files = []           # [path, where it was found]
        self.ents = []            # {"kv": [[k, v]], "f", "l", "s": the spawn line, "x": [[file, line, text]]}
        self.mods = []            # [map entity, key, value, file, line, text]: map entities the script changes
        self.cvars = []           # [name, value, file, line]
        self.world = []           # [text, file, line]
        self.missing = []         # script files named but not found
        self.level = {}           # level.x variables (shared by every file)
        self.local = {}           # local.x variables of the thread (label) being read
        self.vars = {}            # variable name -> index in self.ents
        self.tn = {}              # targetname -> index in self.ents (the last spawned)
        self.map_tn = {}          # targetname -> map entity index
        self.map_tn_all = {}      # targetname -> every map entity of it
        self.map_ents = ents
        for i, e in enumerate(ents):
            if i == 0:
                continue
            t = e["kvd"].get("targetname")
            if t:
                self.map_tn_all.setdefault(t, []).append(i)
            if t and t not in self.map_tn:
                self.map_tn[t] = i
        # "$x solid" / "$x notsolid" on the map's entities before "level waittill prespawn":
        # how they stand when the game makes the AI's paths (Level::PreSpawnSentient)
        self.prespawned = False
        self.presolid = {}        # map entity -> 1 solid / 0 notsolid
        self.fi = 0
        self.line = 0
        self.lines = []
        self.loops = []           # [name, value] of the loops being run, for the notes
        self.steps = 0
        self.stopped = False
        self._world_seen = set()
        self._cvar_seen = set()
        self._per_line = {}
        self.rain = {}            # rain setting -> [value, file, line, text] (level.rain_* / cg_rain_*)
        self.rain_varies = set()  # the settings the script changes in ways only the game knows
        self.globals = set()      # the global/ scripts it runs
        self.selfref = None       # the thread's self: ("ent", i) / ("map", i), NULL or None
        self.fdata = []
        self._brk = []            # the loops and switches the statement being run is in
        self._lab_runs = {}       # (file, label) -> [runs, did it spawn or set anything new]
        self._sigs = set()        # the spawns seen: (file, line, keys)

    # ---- tokens and structure ----------------------------------------------------------
    def _parse(self, text):
        """The script as trees of ("s", tokens, line), ("b", [nodes]), ("for", init, cond,
        step, body, line), ("if", cond, then, else, line), ("while", cond, body, line):
        (the nodes before its first label, {label: (parameters, nodes)}, the labels in
        order)."""
        raw = _scr_strip(text).split("\n")
        self.lines = raw
        toks = []
        for ln, s in enumerate(raw, 1):
            m = _SCR_LABEL.match(s)
            if m:
                toks.append(("L", (m.group(1).lower(), m.group(2).lower().split()), ln))
                continue
            for m in _SCR_TOKEN.finditer(s):
                q, num, word, op = m.groups()
                if q is not None:
                    toks.append(("s", q, ln))
                elif num is not None:
                    toks.append(("n", num, ln))
                elif word is not None:
                    toks.append(("w", word, ln))
                else:
                    toks.append(("o", op, ln))
            toks.append(("NL", "", ln))
        self._t = toks
        self._p = 0
        top = cur = []
        labels, order = {}, []
        while self._p < len(toks):
            n = self._node()
            if n is None:
                continue
            if n[0] == "label":
                cur = []
                if n[1] not in labels:           # the first of two labels of one name wins
                    labels[n[1]] = (n[2], cur)
                    order.append(n[1])
            else:
                cur.append(n)
        return top, labels, order

    def _skip_nl(self):
        while self._p < len(self._t) and self._t[self._p][0] == "NL":
            self._p += 1

    def _group(self):
        """The tokens inside a ( ... ) starting at the cursor (which is on the "(")."""
        t = self._t
        depth = 0
        out = []
        while self._p < len(t):
            k, s, _ln = t[self._p]
            self._p += 1
            if k == "NL":
                continue
            if k == "o" and s == "(":
                depth += 1
                if depth == 1:
                    continue
            elif k == "o" and s == ")":
                depth -= 1
                if depth == 0:
                    break
            out.append((k, s))
        return out

    def _body(self):
        self._skip_nl()
        if self._p >= len(self._t):
            return ("b", [])
        return self._node()

    def _node(self):
        t = self._t
        if self._p >= len(t):
            return None
        k, s, ln = t[self._p]
        if k == "NL":
            self._p += 1
            return None
        if k == "L":
            self._p += 1
            return ("label", s[0], s[1])
        if k == "o" and s == "{":
            self._p += 1
            nodes = []
            # (a label inside braces means they don't close: the block ends there)
            while self._p < len(t) and t[self._p][:2] != ("o", "}") and t[self._p][0] != "L":
                n = self._node()
                if n is not None:
                    nodes.append(n)
            if self._p < len(t) and t[self._p][0] != "L":
                self._p += 1
            return ("b", nodes)
        if k == "o" and s in ("}", ";"):
            self._p += 1
            return None
        low = s.lower() if k == "w" else ""
        nxt = t[self._p + 1] if self._p + 1 < len(t) else None
        if low in ("for", "while", "if", "switch") and nxt and nxt[:2] == ("o", "("):
            self._p += 1
            head = self._group()
            if low == "for":
                parts = [[]]
                for tk in head:
                    if tk == ("o", ";"):
                        parts.append([])
                    else:
                        parts[-1].append(tk)
                parts += [[]] * (3 - len(parts))
                return ("for", parts[0], parts[1], parts[2], self._body(), ln)
            body = self._body()
            if low == "if":
                save = self._p
                self._skip_nl()
                if self._p < len(t) and t[self._p][0] == "w" and t[self._p][1].lower() == "else":
                    self._p += 1
                    return ("if", head, body, self._body(), ln)
                self._p = save
                return ("if", head, body, None, ln)
            if low == "while":
                return ("while", head, body, ln)
            return ("sw", body)                # switch: its cases, read once
        if low == "else":                      # an else without its if: read its body
            self._p += 1
            return self._body()
        # a statement: to the end of the line, a ";" or a brace (outside brackets)
        out = []
        depth = 0
        while self._p < len(t):
            k2, s2, _l = t[self._p]
            if k2 in ("NL", "L") and depth == 0:
                break
            if k2 == "o" and depth == 0 and s2 in (";", "{", "}"):
                if s2 == ";":
                    self._p += 1
                break
            if k2 == "o" and s2 in ("(", "["):
                depth += 1
            elif k2 == "o" and s2 in (")", "]"):
                depth = max(0, depth - 1)
            if k2 != "NL":
                out.append((k2, s2))
            self._p += 1
        return ("s", out, ln) if out else None

    # ---- running it ------------------------------------------------------------------
    def _run(self, nodes, queue):
        for n in nodes:
            self._exec(n, queue)

    def _exec(self, n, queue):
        kind = n[0]
        if kind == "s":
            self.steps += 1
            if self.steps > self.MAX_STEPS:
                raise _ScrStop()
            self.line = n[2]
            self._statement(n[1], queue)
        elif kind == "b":
            self._run(n[1], queue)
        elif kind == "if":
            self.line = n[4]
            c = self._truth(self._eval(n[1]))
            if c is True:
                self._exec(n[2], queue)
            elif c is False:
                if n[3] is not None:
                    self._exec(n[3], queue)
            else:
                # either way: both branches read, and a variable they leave different unknown;
                # a break or continue in either may happen or not (_ScrMaybe)
                snap = self._snap()
                maybe = None
                try:
                    self._exec(n[2], queue)
                except (_ScrBreak, _ScrContinue, _ScrMaybe) as e:
                    maybe = e
                a = self._snap()
                self.level, self.local = dict(snap[0]), dict(snap[1])
                if n[3] is not None:
                    try:
                        self._exec(n[3], queue)
                    except (_ScrBreak, _ScrContinue, _ScrMaybe) as e:
                        maybe = maybe or e
                self._merge(a)
                if maybe is not None:
                    raise _ScrMaybe(maybe.brk if isinstance(maybe, _ScrMaybe) else isinstance(maybe, _ScrBreak))
        elif kind == "sw":
            self._brk.append("switch")
            try:
                self._exec(n[1], queue)
            finally:
                self._brk.pop()
        elif kind == "for":
            _k, init, cond, step, body, ln = n
            self.line = ln
            if init:
                self._statement(init, queue)
            var = init[0][1].lower() if init and init[0][0] == "w" else None
            turns = 0
            self._brk.append("loop")
            try:
                while True:
                    c = self._truth(self._eval(cond)) if cond else None
                    if c is None:
                        if turns == 0:
                            # a loop the viewer can't count: once, its counter unknown, and
                            # what it changes unknown after it
                            if var:
                                self._setvar(var, None)
                            snap = self._snap()
                            try:
                                self._exec(body, queue)
                            except (_ScrBreak, _ScrContinue, _ScrMaybe):
                                pass
                            self._merge(snap)
                        break
                    if not c or turns >= self.MAX_LOOP:
                        break
                    self.loops.append([var, self._getvar(var) if var else None])
                    try:
                        self._exec(body, queue)
                    except _ScrBreak:
                        break
                    except _ScrContinue:
                        pass
                    except _ScrMaybe as e:
                        if e.brk:
                            # it may end here: no further, the counter unknown
                            if var:
                                self._setvar(var, None)
                            break
                    finally:
                        self.loops.pop()
                    self.line = ln
                    if step:
                        self._statement(step, queue)
                    turns += 1
            finally:
                self._brk.pop()
        elif kind == "while":
            _k, cond, body, ln = n
            turns = 0
            # a loop that waits (respawning waves, a thread that watches something) runs
            # with the game's clock: once is all the viewer can tell
            timed = self._waits(body)
            self._brk.append("loop")
            try:
                while turns < self.MAX_LOOP:
                    self.line = ln
                    c = self._truth(self._eval(cond))
                    if c is False:
                        break
                    names = {s.lower() for k, s in cond if k == "w"}
                    before = [(x, self._getvar(x)) for x in sorted(names)]
                    snap = self._snap() if c is None else None
                    stop = False
                    try:
                        self._exec(body, queue)
                    except _ScrBreak:
                        stop = True
                    except _ScrContinue:
                        pass
                    except _ScrMaybe as e:
                        stop = e.brk
                    if snap is not None:
                        self._merge(snap)
                    turns += 1
                    if stop:
                        break
                    # a loop whose condition nothing in it changes (while (1), a wait loop):
                    # once is all the viewer can tell
                    if c is None or timed or before == [(x, self._getvar(x)) for x in sorted(names)]:
                        break
            finally:
                self._brk.pop()

    def _waits(self, n):
        """Does this node (or anything in it) wait for the game: wait, waitframe,
        waittill?"""
        k = n[0]
        if k == "s":
            return any(t[0] == "w" and t[1].lower() in ("wait", "waitframe", "waittill", "waittillframeend")
                       for t in n[1])
        if k == "b":
            return any(self._waits(x) for x in n[1])
        if k == "for":
            return self._waits(n[4])
        if k == "if":
            return self._waits(n[2]) or (n[3] is not None and self._waits(n[3]))
        if k == "while":
            return self._waits(n[2])
        if k == "sw":
            return self._waits(n[1])
        return False

    def _snap(self):
        return dict(self.level), dict(self.local)

    def _merge(self, other):
        """Keep a variable only where it is the same as in other (the state of the
        branch not taken, or before a loop run once); else it is unknown."""
        for cur, o in ((self.level, other[0]), (self.local, other[1])):
            for k in set(cur) | set(o):
                if cur.get(k) != o.get(k):
                    cur[k] = None

    def _getvar(self, name):
        name = name.lower()
        if name.startswith("level."):
            return self.level.get(name)
        if name.startswith("local."):
            return self.local.get(name)
        return None

    def _rainset(self, key, val):
        """A rain setting the script makes (level.rain_<key> or setcvar cg_rain_<key>):
        the last one read wins; one only the game knows marks the setting as varying."""
        if key not in _RAIN_KEYS:
            return
        if val is None or isinstance(val, tuple) or isinstance(val, list):
            if key not in self.rain:
                self.rain[key] = [None, self.fi, self.line, self._text()]
            self.rain_varies.add(key)
            return
        self.rain[key] = [_scr_str(val), self.fi, self.line, self._text()]

    def _setvar(self, name, val):
        name = name.lower()
        if name.startswith("level."):
            self.level[name] = val
            if name.startswith("level.rain_"):
                self._rainset(name[11:], val)
            elif name == "level.thundertime":
                self._rainset("thundertime", val)
        elif name.startswith("local."):
            self.local[name] = val
        self.vars.pop(name, None)

    # ---- values ---------------------------------------------------------------
    def _eval(self, T):
        if not T:
            return None
        try:
            v, i = self._or(T, 0)
        except (IndexError, ValueError, TypeError, OverflowError, ZeroDivisionError):
            return None
        # all of it, or it is something the viewer doesn't follow (a call: getcvar(x))
        return v if i >= len(T) else None

    @staticmethod
    def _truth(v):
        if v is None:
            return None
        if v == _SCR_NULL:
            return False
        if isinstance(v, tuple):
            return True
        if isinstance(v, float):
            return v != 0
        if isinstance(v, list):
            return True
        return v != ""

    def _or(self, T, i):
        v, i = self._and(T, i)
        while i < len(T) and T[i] == ("o", "||"):
            w, i = self._and(T, i + 1)
            a, b = self._truth(v), self._truth(w)
            v = 1.0 if (a or b) else (None if a is None or b is None else 0.0)
        return v, i

    def _and(self, T, i):
        v, i = self._eq(T, i)
        while i < len(T) and T[i] == ("o", "&&"):
            w, i = self._eq(T, i + 1)
            a, b = self._truth(v), self._truth(w)
            v = 0.0 if (a is False or b is False) else (None if a is None or b is None else 1.0)
        return v, i

    def _eq(self, T, i):
        v, i = self._rel(T, i)
        while i < len(T) and T[i][0] == "o" and T[i][1] in ("==", "!="):
            op = T[i][1]
            w, i = self._rel(T, i + 1)
            if v is None or w is None:
                v = None
                continue
            if _SCR_NULL in (v, w):
                o = w if v == _SCR_NULL else v
                same = (o == _SCR_NULL) or (isinstance(o, tuple) and o[0] == "$" and not self._exists(o[1]))
            elif isinstance(v, tuple) or isinstance(w, tuple):
                same = v == w
            elif isinstance(v, float) and isinstance(w, float):
                same = v == w
            else:
                same = _scr_str(v) == _scr_str(w)
            v = 1.0 if same == (op == "==") else 0.0
        return v, i

    def _rel(self, T, i):
        v, i = self._add(T, i)
        while i < len(T) and T[i][0] == "o" and T[i][1] in ("<", "<=", ">", ">="):
            op = T[i][1]
            w, i = self._add(T, i + 1)
            if isinstance(v, float) and isinstance(w, float):
                v = 1.0 if {"<": v < w, "<=": v <= w, ">": v > w, ">=": v >= w}[op] else 0.0
            else:
                v = None
        return v, i

    def _add(self, T, i):
        v, i = self._mul(T, i)
        while i < len(T) and T[i][0] == "o" and T[i][1] in ("+", "-") and i + 1 < len(T) and T[i + 1] != ("o", "="):
            op = T[i][1]
            w, i = self._mul(T, i + 1)
            v = self._binop(v, op, w)
        return v, i

    def _mul(self, T, i):
        v, i = self._unary(T, i)
        while i < len(T) and T[i][0] == "o" and T[i][1] in ("*", "/", "%") and i + 1 < len(T) and T[i + 1] != ("o", "="):
            op = T[i][1]
            w, i = self._unary(T, i + 1)
            if isinstance(v, float) and isinstance(w, float):
                v = v * w if op == "*" else (v / w if op == "/" else v % w)
            elif op == "*" and isinstance(v, list) and isinstance(w, float):
                v = [x * w for x in v]
            elif op == "*" and isinstance(w, list) and isinstance(v, float):
                v = [x * v for x in w]
            else:
                v = None
        return v, i

    def _unary(self, T, i):
        if i < len(T) and T[i] == ("o", "-"):
            v, i = self._unary(T, i + 1)
            return (-v if isinstance(v, float) else [-x for x in v] if isinstance(v, list) else None), i
        if i < len(T) and T[i] == ("o", "!"):
            v, i = self._unary(T, i + 1)
            t = self._truth(v)
            return (None if t is None else (0.0 if t else 1.0)), i
        return self._term(T, i)

    def _term(self, T, i):
        """(value, next index): a string, a float, a list of 3 floats, ("$", name) for an
        entity, NULL, or None (unknown)."""
        if i >= len(T):
            return None, i
        kind, s = T[i]
        if kind == "s":
            return s, i + 1
        if kind == "n":
            return float(s), i + 1
        if kind == "o" and s == "(":
            vals = []
            j = i + 1
            while j < len(T) and T[j] != ("o", ")"):
                v, j2 = self._or(T, j)
                if j2 == j:
                    j += 1
                    vals.append(None)
                else:
                    j = j2
                    vals.append(v)
            j += 1
            if len(vals) == 3:
                if all(isinstance(v, float) for v in vals):
                    return [vals[0], vals[1], vals[2]], j
                return None, j
            return (vals[0] if len(vals) == 1 else None), j
        if kind == "w":
            if s == "$" and i + 1 < len(T) and T[i + 1] == ("o", "("):
                # $( expression ): the entity of that targetname
                name, j = self._term(T, i + 1)
                ref = ("$", _scr_str(name)) if isinstance(name, (str, float)) else None
                if j + 1 < len(T) and T[j] == ("o", ".") and T[j + 1][0] == "w":
                    return (self._entprop(ref[1], T[j + 1][1].lower()) if ref else None), j + 2
                return ref, j
            return self._word(s), i + 1
        return None, i

    @staticmethod
    def _binop(a, op, b):
        if a is None or b is None or isinstance(a, tuple) or isinstance(b, tuple):
            return None
        if isinstance(a, float) and isinstance(b, float):
            return a + b if op == "+" else a - b
        if isinstance(a, list) and isinstance(b, list):
            return [x + (y if op == "+" else -y) for x, y in zip(a, b)]
        if op == "+" and not isinstance(a, list) and not isinstance(b, list):
            return _scr_str(a) + _scr_str(b)
        return None

    def _exists(self, name):
        return name in self.tn or name in self.map_tn

    def _entprop(self, name, prop):
        """A property of the entity of that targetname (the script's, else the map's)."""
        return self._refprop(self._named(name), prop)

    def _refprop(self, ref, prop):
        """A property of ("ent", script entity) or ("map", map entity)."""
        if ref is None:
            return None
        if ref[0] == "ent":
            return self._prop(self.ents[ref[1]], prop)
        if ref[0] == "map":
            k = self.map_ents[ref[1]]["kvd"]
            if prop == "origin":
                o = MB.parse_vec(k.get("origin", ""))
                return list(o) if o else None
            if prop == "angles":
                a = MB.parse_vec(k.get("angles", "")) or ([0.0, float(k["angle"]), 0.0] if k.get("angle") else None)
                return list(a) if a else [0.0, 0.0, 0.0]
            if prop in ("targetname", "target", "model"):
                return k.get(prop)
        return None

    def _refval(self, ref):
        """An entity as a value: ("@", script entity), ("$", targetname) for a map entity
        with one, ("m", map entity) for one without, NULL for none."""
        if ref is None:
            return None
        if ref == _SCR_NULL:
            return _SCR_NULL
        if ref[0] == "ent":
            return ("@", ref[1])
        t = self.map_ents[ref[1]]["kvd"].get("targetname")
        return ("$", t) if t else ("m", ref[1])

    def _valref(self, v):
        """The entity a value stands for (see _refval), or None."""
        if not isinstance(v, tuple):
            return None
        if v[0] == "@":
            return ("ent", v[1])
        if v[0] == "m":
            return ("map", v[1])
        if v[0] == "$":
            return self._named(v[1])
        return None

    def _var_ref(self, name):
        """The entity a variable (local.x, level.x, self) holds, or None."""
        if name == "self":
            return self.selfref if self.selfref != _SCR_NULL else None
        if name in self.vars:
            return ("ent", self.vars[name])
        return self._valref(self._getvar(name))

    def _word(self, w):
        lw = w.lower()
        if lw == "null" or lw == "nil":
            return _SCR_NULL
        if lw == "self":
            return self._refval(self.selfref)
        if lw.startswith(("local.", "level.", "game.", "self.", "group.", "parm.", "owner.")):
            if lw in self.vars:
                return ("@", self.vars[lw])
            base, _, prop = lw.rpartition(".")
            ref = self._var_ref(base)
            if ref is not None:
                return self._refprop(ref, prop)
            if lw.startswith(("level.", "local.")):
                return self._getvar(lw)
            return None
        if w.startswith("$"):
            name, _, prop = w[1:].partition(".")
            if not name:
                return None
            return self._entprop(name, prop.lower()) if prop else ("$", name)
        return w                  # a bare word is a string ("targetname foo")

    @staticmethod
    def _prop(E, prop):
        for k, v in E["kv"]:
            if k == prop:
                if prop in ("origin", "angles"):
                    p = MB.parse_vec(v)
                    return list(p) if p else None
                return v
        return [0.0, 0.0, 0.0] if prop == "angles" else None

    # ---- one entity's keys ---------------------------------------------------------
    @staticmethod
    def _set(E, key, val):
        key = key.lower()
        if key == "angle":
            E["kv"] = [kv for kv in E["kv"] if kv[0] not in ("angle", "angles")]
            E["kv"].append(["angles", "0 %s 0" % _scr_str(val)])
            return
        E["kv"] = [kv for kv in E["kv"] if kv[0] != key]
        E["kv"].append([key, val])

    def _text(self):
        """The line being read, with the loop counters it was read with."""
        s = self.lines[self.line - 1].strip() if 0 < self.line <= len(self.lines) else ""
        ctx = ", ".join("%s = %s" % (n, _scr_str(v) if v is not None else "?") for n, v in self.loops if n)
        return (s[:200] + ("   // " + ctx if ctx else ""))

    def _ref_of(self, T, i):
        """The entity a statement starts with: (("ent", index) / ("map", index) / None,
        property or None, next index)."""
        k, s = T[i]
        if k != "w":
            return None, None, i
        if s == "$" and i + 1 < len(T) and T[i + 1] == ("o", "("):
            name, j = self._term(T, i + 1)
            name = _scr_str(name) if isinstance(name, (str, float)) else None
            prop = None
            if j + 1 < len(T) and T[j] == ("o", ".") and T[j + 1][0] == "w":
                prop, j = T[j + 1][1], j + 2
            return self._named(name), prop, j
        if s.startswith("$"):
            name, _, prop = s[1:].partition(".")
            return self._named(name), (prop or None), i + 1
        ls = s.lower()
        ref = self._var_ref(ls)
        if ref is not None:
            return ref, None, i + 1
        base, _, prop = ls.rpartition(".")
        ref = self._var_ref(base) if base else None
        if ref is not None:
            return ref, prop, i + 1
        return None, None, i

    def _named(self, name):
        if not name:
            return None
        if name in self.tn:
            return ("ent", self.tn[name])
        if name in self.map_tn:
            return ("map", self.map_tn[name])
        return None

    def _apply(self, ref, prop, T, i, assign, op=None):
        """A property line for an entity: ".prop = value", ".prop += value" (op) or
        " prop value ..."."""
        prop = prop.lower()
        if prop not in _SCR_PROPS:
            return
        if prop == "setsize" and not assign:
            a, i = self._add(T, i)
            b, i = self._add(T, i)
            val = (_scr_str(a) + " " + _scr_str(b)) if isinstance(a, list) and isinstance(b, list) else None
        else:
            val, i = self._or(T, i)
            if op:
                val = self._binop(self._refprop(ref, prop), op, val)
            if isinstance(val, tuple) and val[0] in ("@", "m"):
                # an entity in a variable: by its targetname
                tn = self._refprop(self._valref(val), "targetname")
                val = ("$", tn) if tn else None
            if prop in ("origin", "angles") and not isinstance(val, list):
                val = None
            elif val == _SCR_NULL or (isinstance(val, tuple) and val[0] != "$"):
                val = None
            elif val is not None:
                val = _scr_str(val)
        text = self._text()
        if ref[0] == "map":
            # the map's own entity: only its target is followed (a map node joined to the
            # script's), as the last line sets it
            if prop == "target" and val is not None:
                self.mods.append([ref[1], "target", val, self.fi, self.line, text])
            return
        E = self.ents[ref[1]]
        if val is None:
            E.setdefault("unk", {})[prop] = text[:160]
            if prop in ("origin", "angles", "targetname"):
                E["kv"] = [kv for kv in E["kv"] if kv[0] != prop]
        else:
            self._set(E, prop, val)
            E.get("unk", {}).pop(prop, None)
            if prop == "targetname":
                self.tn[val] = ref[1]
        E["x"].append([self.fi, self.line, text])

    # ---- statements ------------------------------------------------------------
    def _spawn(self, T, i, var):
        """ "spawn <class> [key value ...]" from token i (the class)."""
        text = self._text()
        if i >= len(T):
            return
        # one line spawning thousands (a loop the viewer counted that the game runs with
        # waits in between): the first 1024 are enough
        key = (self.fi, self.line)
        self._per_line[key] = self._per_line.get(key, 0) + 1
        if self._per_line[key] > 1024:
            if var:
                self.vars.pop(var.lower(), None)
            return
        cls, i = self._term(T, i)
        if not isinstance(cls, str) or not cls:
            self.ents.append({"kv": [], "f": self.fi, "l": self.line, "s": text, "x": [],
                              "unk": {"class": text[:160]}})
            return
        kv = []
        low = cls.replace("\\", "/").lower()
        if "/" in low or low.endswith(".tik"):
            # a model: the game spawns the .tik's class with that model (G_SpawnEntity)
            m = low[7:] if low.startswith("models/") else low
            m = m if m.endswith(".tik") else m + ".tik"
            kv += [["classname", m[:-4]], ["model", m]]
        else:
            kv.append(["classname", cls])
        E = {"kv": kv, "f": self.fi, "l": self.line, "s": text, "x": []}
        idx = len(self.ents)
        self.ents.append(E)
        while i < len(T):
            k, i2 = self._term(T, i)
            if i2 == i:
                break
            v, i = self._add(T, i2)
            if not isinstance(k, str):
                continue
            kl = k.lower()
            if v is None or v == _SCR_NULL or (isinstance(v, tuple) and v[0] != "$"):
                E.setdefault("unk", {})[kl] = text[:160]
                continue
            if kl in ("origin", "angles") and isinstance(v, str):
                p = MB.parse_vec(v)
                v = list(p) if p else None
                if v is None:
                    continue
            self._set(E, kl, _scr_str(v))
            if kl == "targetname":
                self.tn[_scr_str(v)] = idx
        if var:
            self.vars[var.lower()] = idx

    def _statement(self, T, queue):
        if not T:
            return
        words = [s.lower() if k == "w" else None for k, s in T]
        # spawn, anywhere in the line ("local.x = spawn ...")
        for i, w in enumerate(words):
            if w == "spawn" and not (i > 0 and words[i - 1] in _SCR_NOT_SPAWN):
                var = None
                if i >= 2 and T[i - 1] == ("o", "=") and T[i - 2][0] == "w" and not T[i - 2][1].startswith("$"):
                    var = T[i - 2][1]
                    self._setvar(var, None)
                self._spawn(T, i + 1, var)
                return
        k0, s0 = T[0]
        l0 = s0.lower() if k0 == "w" else ""
        if not self.prespawned and len(words) >= 3 and words[0] == "level" and words[1] == "waittill" \
                and words[2] == "prespawn":
            self.prespawned = True
        if not self.prespawned and len(T) == 2 and k0 == "w" and s0.startswith("$") \
                and T[1][0] == "w" and T[1][1].lower() in ("solid", "notsolid"):
            for ei in self.map_tn_all.get(s0[1:], ()):
                self.presolid[ei] = 1 if T[1][1].lower() == "solid" else 0
        if l0 == "break" and len(T) == 1:
            if self._brk and self._brk[-1] == "loop":
                raise _ScrBreak()
            return                                 # a switch's case: its cases are read once anyway
        if l0 == "continue" and len(T) == 1:
            if "loop" in self._brk:
                raise _ScrContinue()
            return
        # a thread or script run: "[<ent>] thread label [args]", "local.r = waitthread
        # file.scr::label [args]", "exec file.scr"; the entity is the thread's self
        for i, w in enumerate(words):
            if w in ("exec", "waitexec", "thread", "waitthread") and i + 1 < len(T) and T[i + 1][0] == "w":
                if i == 0 or (i >= 2 and T[i - 1] == ("o", "=")):
                    who = self.selfref
                else:
                    ref, prop, j = self._ref_of(T, 0)
                    who = ref if (ref is not None and not prop and j == i) else None
                self._call(T[i + 1][1], who, T, i + 2, queue, w in ("thread", "exec"))
                return
        if l0 == "setcvar" and len(T) >= 2:
            name, i = self._term(T, 1)
            val, _ = self._add(T, i)
            if (self.fi, self.line) in self._cvar_seen:
                return
            self._cvar_seen.add((self.fi, self.line))
            if isinstance(name, str) and name.lower().startswith("cg_rain_"):
                self._rainset(name.lower()[8:], val if isinstance(val, (str, float)) else None)
            self.cvars.append([_scr_str(name) if isinstance(name, (str, float)) else self._text(),
                               _scr_str(val) if isinstance(val, (str, float, list)) else None, self.fi, self.line])
            return
        if l0 == "$world" and len(T) >= 2:
            # once per line (a loop that fades the fog runs it many times)
            if (self.fi, self.line) not in self._world_seen:
                self._world_seen.add((self.fi, self.line))
                self.world.append([self._text(), self.fi, self.line])
            return
        if k0 != "w":
            return
        # an entity's property: <ent>.<prop> = value, or <ent> <prop> value ...
        ref, prop, j = self._ref_of(T, 0)
        if ref is not None:
            if prop and j < len(T) and T[j] == ("o", "="):
                self._apply(ref, prop, T, j + 1, True)
            elif prop and j + 1 < len(T) and T[j][0] == "o" and T[j][1] in ("+", "-") and T[j + 1] == ("o", "="):
                self._apply(ref, prop, T, j + 2, True, T[j][1])
            elif not prop and j < len(T) and T[j][0] == "w":
                self._apply(ref, T[j][1], T, j + 1, False)
            return
        # a variable: local.x / level.x = value, ++, --, += and -=
        ls = s0.lower()
        if ls.startswith(("local.", "level.")) and len(T) >= 2:
            if T[1] == ("o", "="):
                v, j = self._or(T, 2)
                if j < len(T):
                    v = None
                if isinstance(v, tuple) and v[0] == "@":
                    self.vars[ls] = v[1]        # local.a = local.b: the same entity
                    return
                self._setvar(ls, v)
            elif T[1] in (("o", "++"), ("o", "--")):
                v = self._getvar(ls)
                self._setvar(ls, v + (1.0 if T[1][1] == "++" else -1.0) if isinstance(v, float) else None)
            elif len(T) >= 3 and T[1][0] == "o" and T[1][1] in ("+", "-", "*", "/") and T[2] == ("o", "="):
                w, _ = self._or(T, 3)
                v = self._getvar(ls)
                if T[1][1] in ("+", "-"):
                    r = self._binop(v, T[1][1], w)
                elif isinstance(v, float) and isinstance(w, float) and (T[1][1] == "*" or w):
                    r = v * w if T[1][1] == "*" else v / w
                else:
                    r = None
                self._setvar(ls, r)

    # ---- files and threads ----------------------------------------------------------
    def _load(self, path):
        """The index of a script file, read and parsed once, or None."""
        key = path.replace("\\", "/").lower().lstrip("/")
        if key in self._fkey:
            return self._fkey[key]
        if len(self.files) >= self.MAX_FILES:
            return None
        text, where = self.find(path)
        if text is None:
            self._fkey[key] = None
            if self.files:
                self.missing.append(path)
            return None
        fi = len(self.files)
        self._fkey[key] = fi
        self.files.append([path, where])
        save = self.lines
        top, labels, order = self._parse(text)
        self.fdata.append({"lines": self.lines, "top": top, "labels": labels, "order": order})
        self.lines = save
        # the labels something runs by name ("thread x", "file.scr::x"): they are read
        # when they are run, with their self and parameters, not on their own
        for m in re.finditer(r"\b(?:thread|waitthread|exec|waitexec)\s+([\w./\\:-]+)", _scr_strip(text), re.I):
            tgt = m.group(1).lower().replace("\\", "/")
            if "::" in tgt:
                f, _, lab = tgt.partition("::")
                self._called.add((f, lab))
            elif not tgt.endswith(".scr"):
                self._called.add((key, tgt))
        return fi

    def _scope(self, fi, selfref, params, args):
        """Enter a thread: its file, self and parameters (NIL where not given). Returns
        what to give _unscope."""
        save = (self.fi, self.lines, self.local, self.vars, self.selfref, self.line)
        self.fi = fi
        self.lines = self.fdata[fi]["lines"]
        self.selfref = selfref
        self.local = {}
        self.vars = {k: v for k, v in self.vars.items() if not k.startswith("local.")}
        for n, p in enumerate(params):
            v = args[n] if args is not None and n < len(args) else (_SCR_NULL if args is not None else None)
            if isinstance(v, tuple) and v[0] == "@":
                self.vars[p] = v[1]
            else:
                self.local[p] = v
        return save

    def _unscope(self, save):
        self.fi, self.lines, self.local, vars_, self.selfref, self.line = save
        # level variables set in the thread stay; the caller's locals come back
        self.vars = {k: v for k, v in self.vars.items() if not k.startswith("local.")}
        self.vars.update({k: v for k, v in vars_.items() if k.startswith("local.")})

    LABEL_IDLE = 8                # runs after which a label that never spawns or sets anything is skipped

    def _run_label(self, fi, label, selfref, args, queue):
        lab = self.fdata[fi]["labels"].get(label)
        if lab is None or (fi, label) in self._stack or len(self._stack) > 24:
            return
        # A thread every actor runs (its AI: path walking, sight checks, dialogue) is read
        # again for each one; once it has been read LABEL_IDLE times without spawning or
        # setting anything, the rest are skipped, so the steps go to the threads that place
        # things (a waypoint spawned by a thread called hundreds of times still runs)
        st = self._lab_runs.get((fi, label))
        if st is None:
            st = self._lab_runs[(fi, label)] = [0, False]
        if st[0] >= self.LABEL_IDLE and not st[1]:
            return
        st[0] += 1
        before = (len(self.ents), len(self.mods), len(self.cvars), len(self.world))
        self._ran.add((fi, label))
        self._stack.append((fi, label))
        save = self._scope(fi, selfref, lab[0], args)
        brk, self._brk = self._brk, []
        try:
            self._run(lab[1], queue)
        except (_ScrBreak, _ScrContinue, _ScrMaybe):
            pass
        finally:
            self._brk = brk
            self._unscope(save)
            self._stack.pop()
            # new: a spawn unlike any before it (a per-actor helper spawned at the actor's
            # unknown origin again is the same each time), or a target, cvar or $world line
            for E in self.ents[before[0]:]:
                sig = (E["f"], E["l"], tuple(sorted(tuple(kv) for kv in E["kv"])))
                if sig not in self._sigs:
                    self._sigs.add(sig)
                    st[1] = True
            if (len(self.mods), len(self.cvars), len(self.world)) != before[1:]:
                st[1] = True

    def _call(self, target, who, T, i, queue, side=False):
        """ "thread label", "waitthread file.scr::label", "exec file.scr" with the
        arguments from token i: the label is read with that self and those parameters.
        A thread started with thread or exec (side) runs beside its caller in game: what
        it does to level variables happens later (a death thread lowering a counter), so
        its caller doesn't see it."""
        target = target.replace("\\", "/")
        path, _, label = target.partition("::")
        if not label and not path.lower().endswith(".scr"):
            path, label = "", path
        if path.lower().startswith("global/"):
            self.globals.add(path.lower())
            return
        args = []
        while i < len(T) and len(args) < 16:
            v, j = self._add(T, i)
            if j == i:
                break
            args.append(v)
            i = j
        if path:
            fi = self._load(path)
            if fi is None:
                return
            if not label:
                queue.append(fi)                   # a whole script: read after this one
                return
        else:
            fi = self.fi
        keep = dict(self.level) if side else None
        self._run_label(fi, label.lower(), who, args, queue)
        if keep is not None:
            self.level = keep

    def _run_file(self, fi, queue):
        """A file as it is read on its own: what comes before its labels, then each label
        nothing runs by name (unknown self and parameters)."""
        if fi in self._file_ran:
            return
        self._file_ran.add(fi)
        save = self._scope(fi, None, [], None)
        brk, self._brk = self._brk, []
        try:
            self._run(self.fdata[fi]["top"], queue)
        except (_ScrBreak, _ScrContinue, _ScrMaybe):
            pass
        finally:
            self._brk = brk
            self._unscope(save)
        key = self.files[fi][0].replace("\\", "/").lower().lstrip("/")
        for lab in self.fdata[fi]["order"]:
            if (fi, lab) in self._ran or (key, lab) in self._called:
                continue
            self._run_label(fi, lab, None, None, queue)

    def read(self, path):
        """Read a script and the map scripts it runs, as the game would find them."""
        self.fdata, self._fkey, self._called = [], {}, set()
        self._ran, self._stack, self._file_ran = set(), [], set()
        first = self._load(path)
        if first is None:
            return False
        queue = [first]
        try:
            while queue:
                fi = queue.pop(0)
                self._run_file(fi, queue)
            # labels run by name somewhere the walk never reached: on their own
            for fi in range(len(self.files)):
                for lab in self.fdata[fi]["order"]:
                    if (fi, lab) not in self._ran:
                        self._run_label(fi, lab, None, None, queue)
                while queue:
                    self._run_file(queue.pop(0), queue)
        except _ScrStop:
            self.stopped = True
        except RecursionError:
            pass
        return True

    def payload(self, base):
        """For the page: the placed entities (an origin known) and the rest, and the map
        entities the script changes."""
        placed, unplaced = [], []
        same = set()
        for E in self.ents:
            # a thread run several times that spawns the same thing in the same place (a
            # wave of the same actors): one of them is enough to see
            sig = (E["f"], E["l"], tuple(sorted(tuple(kv) for kv in E["kv"])))
            if sig in same:
                continue
            same.add(sig)
            keys = {k for k, _ in E["kv"]}
            rec = {"kv": E["kv"], "f": E["f"], "l": E["l"], "s": E["s"], "x": E["x"][-40:]}
            if E.get("unk"):
                rec["u"] = E["unk"]
            if "origin" in keys and "classname" in keys:
                placed.append(rec)
            else:
                rec["why"] = ("its class isn't known: " + E["unk"]["class"]) if "class" in E.get("unk", {}) else \
                    ("its origin comes from " + E["unk"]["origin"]) if "origin" in E.get("unk", {}) else \
                    "the script gives it no origin it can be followed to"
                unplaced.append(rec)
        # each map entity's target as the script last sets it
        last = {}
        for m in self.mods:
            last[(m[0], m[1])] = m
        return {"files": self.files, "base": base, "ents": placed, "un": unplaced[:500], "nun": len(unplaced),
                "rain": self.rain, "rainv": sorted(self.rain_varies), "glob": sorted(self.globals),
                "mods": list(last.values())[:5000], "stop": int(self.stopped),
                "cvars": self.cvars[:2000], "world": self.world[:200], "miss": self.missing[:50],
                "presolid": [[k, v] for k, v in sorted(self.presolid.items())]}


def script_payload(vfs, vpath, src, paks, ents, say=log):
    """The level script's spawned entities and settings (LevelScript), or None when the
    map has no .scr. A script is looked for as the game looks for it, a loose file in the
    folder the paks are in (main/maps/x.scr) before the paks, and for the map's own
    script also beside the file opened."""
    roots = []
    for p in paks or ():
        d = os.path.dirname(os.path.abspath(p))
        if d not in roots:
            roots.append(d)
    src_dir = os.path.dirname(os.path.abspath(src))

    def find(path):
        rel = path.replace("\\", "/").lstrip("/")
        cands = [os.path.join(src_dir, os.path.basename(rel))]
        cands += [os.path.join(r, *rel.split("/")) for r in roots]
        for c in cands:
            if os.path.isfile(c):
                try:
                    with open(c, "rb") as f:
                        return f.read().decode("latin-1", "replace"), c
                except OSError:
                    pass
        if vfs is not None and rel.lower() in vfs.index:
            zi, real = vfs.index[rel.lower()]
            return vfs.read(rel.lower()).decode("latin-1", "replace"), "%s (%s)" % (real, os.path.basename(vfs.zips[zi].filename))
        return None, None

    stem = os.path.splitext(vpath.replace("\\", "/"))[0]
    if not stem.lower().startswith("maps/"):
        stem = "maps/" + os.path.basename(stem)
    ls = LevelScript(find, ents)
    # (the file beside the one opened comes first: NormandyBridge_V1.bak's script is
    # NormandyBridge_V1.scr beside it)
    if not ls.read(stem + ".scr"):
        return {"_deps": [os.path.join(r, *(stem + ".scr").split("/")) for r in roots], "none": 1}
    out = ls.payload(len(ents))
    # the loose files read, and where the map's own script could appear, so the launcher
    # rebuilds the page when one changes (or appears)
    rel = stem + ".scr"
    deps = [os.path.join(r, *rel.split("/")) for r in roots]
    deps += [w for _p, w in ls.files if os.path.isabs(w) and os.path.isfile(w)]
    out["_deps"] = deps
    say("level script: %s%s - %d entities spawned (%d placed), %d target%s of the map's entities set, "
        "%d setcvar, %d $world line%s"
        % (ls.files[0][1], " and %d more" % (len(ls.files) - 1) if len(ls.files) > 1 else "",
           len(ls.ents), len(out["ents"]), len(out["mods"]), "" if len(out["mods"]) == 1 else "s",
           len(ls.cvars), len(ls.world), "" if len(ls.world) == 1 else "s"))
    if ls.stopped:
        say("! level script: stopped after %d statements (loops that run a very long way)" % ls.MAX_STEPS)
    if ls.missing:
        say("  scripts it runs that weren't found: %s" % ", ".join(ls.missing[:8]))
    return out


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
    """mohdm6.bsp -> mohdm6_bsp_view.html, obj_team2.map -> obj_team2_map_view.html,
    obj_team2.bak -> obj_team2_bak_view.html."""
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
    with open(src, "rb") as f:
        raw = f.read()
    # A .bak is MOHRadiant's previous save of a .map (or a backed-up .bsp): it opens as
    # what its first bytes say it is, and what it writes is marked with "_bak" so it can't
    # be taken for (or overwrite) what the real .map / .bsp writes.
    bak = src.lower().endswith(".bak") or ext.lower() == ".bak"
    if bak:
        kind = "bsp" if raw[:4] in (b"2015", b"EALA") else "map"
        log("%s is a backup of a %s" % (name, ".bsp" if kind == "bsp" else ".map"))
    else:
        kind = "bsp" if src.lower().endswith(".bsp") else "map"
    ostem = stem + "_bak" if bak else stem
    outdir = args.get("outdir") or os.path.dirname(os.path.abspath(src))
    os.makedirs(outdir, exist_ok=True)
    blobs = Blobs()
    bspinfo = None
    bsp = stats = None
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
        map_out = MB.output_map_path(outdir, ostem)
        if os.path.basename(map_out) != ostem + ".map":
            log("(%s.map in that folder isn't one this program wrote, so it's left alone)" % ostem)
        with open(map_out, "w", encoding="latin-1", errors="replace", newline="\n") as f:
            f.write(text)
        log("wrote %s" % map_out)
        bspinfo = {"version": bsp.version, "bounds": {str(k): [list(v[0]), list(v[1])] for k, v in stats["bounds"].items()},
                   "firstStatic": stats["first_static"], "aligned": stats["aligned"], "faces": stats["faces"],
                   "mapFile": map_out, "bcont": stats["bcont"]}
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
    # ---- the level script's spawned entities (drawn after the map's own) -----------------
    try:
        scr = script_payload(vfs, vpath, src, paks, ents)
    except Exception as e:
        log("! level script left out: %s" % e)
        scr = None
    scr_deps = (scr or {}).pop("_deps", [])
    if scr and scr.get("none"):
        scr = None
    scr_ents = []
    for r in (scr or {}).get("ents", ()):
        kv = [tuple(x) for x in r["kv"]]
        scr_ents.append({"kv": kv, "kvd": MB.kv_dict(kv), "brushes": 0, "patches": 0, "terrain": 0})
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
        for ei, e in enumerate(ents + scr_ents):
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
    for i, e in enumerate(ents + scr_ents):
        cls = e["kvd"].get("classname", "")
        cl = cls.lower()
        if i < len(ents):
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
    # the permanent decals (.dcl) and the leak trail (.lin) beside the map
    try:
        dcl = dcl_payload(vfs, vpath, src, texs, blobs)
    except Exception as e:
        log("! decals left out: %s" % e)
        dcl = None
    try:
        # the .lin's age says something only beside a .map: a leaking compile writes
        # its .bsp after the .lin (and the light stage much later)
        leak = leak_payload(vfs, vpath, src, os.path.getmtime(src) if kind == "map" else None)
    except Exception as e:
        log("! leak trail left out: %s" % e)
        leak = None
    # the light grid (r_light_showgrid) and the rain's reach (cg_rain_drawcoverage)
    lgrid = None
    if bsp is not None:
        try:
            lgrid = lightgrid_payload(bsp, blobs)
        except Exception as e:
            log("! light grid left out: %s" % e)
    try:
        rain = rain_payload(vfs, vpath)
    except Exception:
        rain = None
    try:
        weather = weather_payload(vfs, texs, scr)
    except Exception as e:
        log("! weather left out: %s" % e)
        weather = None
    # the sun flare: the worldspawn's keys as the renderer reads them (a .bsp's entity
    # lump, else the .map's), and for a .bsp which leafs see the sun
    try:
        sun = sun_payload(MB.parse_entity_string(bsp.entity_text) if bsp is not None else [e["kv"] for e in ents],
                          vfs, shaders, blobs)
    except Exception as e:
        sun = {"none": "The sun flare couldn't be read: %s" % e}
    if "d" in sun:
        seen = None
        if vis is not None:
            try:
                seen = bsp.sun_leafs(vis["nl"])
            except Exception:
                seen = None
            if seen is not None:
                vis["sun"] = blobs.add(bytes(seen))
        log("sun flare: \"%s\" (%d flare%s, %s), looked for %s"
            % (sun["n"], len(sun["fl"]), "" if len(sun["fl"]) == 1 else "s",
               "with the screen's glare" if sun["full"] else "no glare",
               "from the %d of %d leafs that see the sun" % (sum(seen), len(seen)) if seen is not None
               else "from everywhere (no leaf lists the sun)" if bsp is not None else "from everywhere (a .map)"))
    else:
        log("sun flare: none - %s" % sun["none"])
    world = ents[0]["kvd"] if ents else {}
    title = vpath
    header = {"v": 1, "name": stem, "path": vpath, "kind": kind, "built": time.strftime("%Y-%m-%d %H:%M"),
              # the file the page was built from (MODIFY's Save as .bsp copies it)
              "srcFile": os.path.abspath(src),
              "src": blobs.add(text.encode("latin-1", "replace")),
              "tex": texs.entries, "models": mb.models if mb else [], "modelOf": model_of,
              "defs": defs, "editorFlags": {str(k): v for k, v in ME.EDITOR_FLAGS.items()},
              "bsp": bspinfo, "lit": lit, "sky": skies, "clouds": clouds, "legend": legend,
              "vis": vis, "paths": paths, "lg": lgrid, "rain": rain, "sun": sun, "dcl": dcl, "leak": leak, "scr": scr, "weather": weather,
              "ek": {"simple": sorted(ME.SIMPLE_CLASSES), "dropped": sorted(ME.DROPPED_CLASSES)},
              # the keys a "$" or "#" in front of a key can set (MB.SETTER_KEYS)
              "sk": sorted(MB.SETTER_KEYS)}
    t0 = time.time()
    b64, raw_len, gz_len = pack_payload(header, blobs)
    info = {"name": stem, "path": vpath, "kind": kind, "entities": len(ents), "brushes": nbrush,
            "real": kinds["real"], "simple": kinds["simple"], "static": kinds["static"],
            "patches": npatch, "terrain": nterr, "textures": len(used), "models": len(model_of),
            "message": world.get("message", ""), "classes": sorted(counts.items(), key=lambda kv: kv[0].lower()),
            "missing": texs.missing[:200], "bsp": bool(bspinfo), "bspVersion": bspinfo["version"] if bspinfo else None,
            "mapFile": bspinfo["mapFile"] if bspinfo else (os.path.abspath(src) if bak else None),
            "bak": bak, "decals": (dcl or {}).get("n", 0), "scriptEnts": len(scr_ents), "leak": len((leak or {}).get("p") or ()),
            "netBrushes": ents[0]["brushes"] if ents else 0}
    # the loose files this page was built from, with their times (0: not there), so the
    # launcher rebuilds it when one of them changes or appears
    deps = {}
    if not args.get("vfs"):
        deps[os.path.abspath(src)] = None
    for x in (".scr", ".dcl", ".lin", ".pth"):
        deps[os.path.splitext(os.path.abspath(src))[0] + x] = None
    for d in scr_deps:
        deps[os.path.abspath(d)] = None
    info["deps"] = [[p, round(os.path.getmtime(p), 3) if os.path.isfile(p) else 0] for p in deps]
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

#!/usr/bin/env python3
# mohaa_textures.py - resolve and load MOHAA model textures.
#
# Pipeline (Quake3-style, as MOHAA uses it):
#   model .tik   : "surface <name> shader <shadername>"   (one .tik may compose several .skd)
#   .shader file : "<shadername> { ... map textures/....tga ... }"
#   texture file : textures/....tga|.jpg|.dds   (lives in a textures pak)
#   .skd vertex  : carries the (s,t) UV used to sample that texture
#
# Everything is keyed case-insensitively because the assets are inconsistent
# (e.g. skd surface "Ranger_pants" vs tik "ranger_pants", "HBTpants.tga" vs "hbtpants").

import io, re, os, base64, hashlib, zipfile

# ----------------------------------------------------------------------------- VFS
class Vfs:
    """Several .pk3 archives merged into one case-insensitive namespace.
    Paks are given in load order; a later pak overrides an earlier one for the
    same path (this is how MOHAA's pak6/7/8 updates patch the base game)."""
    def __init__(self, pak_paths):
        self.zips=[]; self.index={}     # lower/normalised path -> (zip_idx, real_name)
        for p in pak_paths:
            try: z=zipfile.ZipFile(p)
            except Exception: continue
            zi=len(self.zips); self.zips.append(z)
            for n in z.namelist():
                if n.endswith("/"): continue
                self.index[n.lower().replace("\\","/")]=(zi,n)
    # No MOHAA asset comes close to this. A .pk3 is a zip, so its header can claim any
    # uncompressed size it likes and a few KB of compressed zeros will happily inflate to
    # gigabytes - zf.read() honours the declared size and the process dies on memory.
    # Reading through the stream with a ceiling makes that a clean skip instead.
    MAX_ENTRY=192*1024*1024
    @staticmethod
    def _k(path): return path.lower().replace("\\","/").lstrip("/")
    def exists(self,path): return self._k(path) in self.index
    def read(self,path):
        e=self.index.get(self._k(path))
        if not e: return None
        try:
            with self.zips[e[0]].open(e[1]) as fh:
                data=fh.read(self.MAX_ENTRY+1)
        except Exception:
            return None
        if len(data)>self.MAX_ENTRY: return None      # decompression bomb / corrupt header
        return data
    def names(self): return self.index.keys()
    def close(self):
        """Release the pak file handles. A Vfs is rebuilt on every pak reload, so without
        this each reload leaked one open descriptor per archive."""
        for z in self.zips:
            try: z.close()
            except Exception: pass
        self.zips=[]; self.index={}
    def find_texture(self,path):
        """Resolve a texture reference to an actual stored file, trying the given
        extension first then the common image extensions."""
        if not path: return None
        p=self._k(path)
        if p in self.index: return p
        base=re.sub(r'\.(tga|jpg|jpeg|dds|png|tif|tiff)$','',p)
        for e in (".tga",".jpg",".jpeg",".dds",".png",".tif",".tiff"):
            if base+e in self.index: return base+e
        return None

def _cache_id(s):
    """Stable short id for the on-demand animation cache.

    This is a cache key, not a security primitive - but hashlib.md5() RAISES ValueError
    on a FIPS-mode kernel (RHEL/CentOS booted with fips=1), which would take the whole
    animation catalogue down there. usedforsecurity=False fixes that but is Python 3.9+
    and everything else here runs on 3.7, so: try it, fall back to plain md5, and only if
    the platform refuses md5 outright fall back to blake2s. Normal machines therefore keep
    their existing ids and nobody's built-animation cache is invalidated."""
    b = s.encode("utf-8", "replace")
    try: return hashlib.md5(b, usedforsecurity=False).hexdigest()[:12]
    except TypeError:
        try: return hashlib.md5(b).hexdigest()[:12]
        except ValueError: pass
    except ValueError: pass
    return hashlib.blake2s(b, digest_size=6).hexdigest()[:12]

# ------------------------------------------------------------------- shader parsing
# Block-header pattern for a Quake3/MOHAA .shader script: leading whitespace, the shader
# name, an optional trailing // comment, then the opening brace.
#
# Compiled once and matched with an explicit `pos` (re.match(txt, i)) instead of the old
# re.match(pat, txt[i:]): slicing the remainder on every block made the scan O(n^2), so a
# large .shader took ~4x longer for every doubling of its size (16 KB of pathological
# input already cost ~5 s, and build_shader_index runs over every loaded pak BEFORE the
# user clicks anything). The name atom is also split so it can no longer share a '/' run
# with the comment branch - '[^\s{}/]*' cannot swallow the '//' the optional group wants,
# which removes the backtracking ambiguity as well as the slicing.
_SHADER_HDR=re.compile(r'[ \t\r\n]*([^\s{}/][^\s{}/]*(?:/[^\s{}/]+)*)[ \t]*(?://[^{\n]*)?[ \t\r\n]*\{')

def _is_aux_map(p):
    """True for environment/reflection/specular helper maps that aren't the diffuse."""
    pl=p.lower()
    return ("common/reflection" in pl or "common/env" in pl or "/env/" in pl
            or "reflection" in pl or "specular" in pl or "_spec." in pl or "cubemap" in pl)

def parse_shader_file(txt):
    """Return {shadername_lower: best_diffuse_texture_path} for one .shader script.
    Picks, in order of preference: the first non-auxiliary stage map (skipping
    environment/reflection/specular helpers), then qer_editorimage, then any map."""
    out={}; i=0; n=len(txt)
    while i<n:
        m=_SHADER_HDR.match(txt,i)
        if not m:
            nl=txt.find("\n",i)
            if nl<0: break
            i=nl+1; continue
        name=m.group(1).lower(); bstart=m.end()-1; depth=0; j=bstart
        while j<n:
            if txt[j]=="{": depth+=1
            elif txt[j]=="}":
                depth-=1
                if depth==0: break
            j+=1
        block=txt[bstart:j+1]
        stage_maps=[]; qer=None
        for line in block.splitlines():
            ls=line.strip()
            if ls.startswith("//"): continue                 # commented-out stage
            mm=re.match(r'(?i)(?:clampmap|map)\s+(\S+)', ls)
            if mm:
                p=mm.group(1)
                if not (p.startswith("$") or p.startswith("*")): stage_maps.append(p.replace("\\","/"))
                continue
            qm=re.match(r'(?i)qer_editorimage\s+(\S+)', ls)
            if qm: qer=qm.group(1).replace("\\","/")
        diffuse=[p for p in stage_maps if not _is_aux_map(p)]
        pick = (diffuse[0] if diffuse else None) or qer or (stage_maps[0] if stage_maps else None)
        if pick: out[name]=pick
        i=j+1
    return out

def build_shader_index(vfs):
    SH={}
    for k in list(vfs.names()):
        if k.endswith(".shader"):
            try: SH.update(parse_shader_file(vfs.read(k).decode("latin-1","replace")))
            except Exception: pass
    return SH

# ----------------------------------------------------- shader render properties
def _strip_line_comments(s):
    """Drop // ... end-of-line comments so brace scanning ignores commented-out stages
    (e.g. bangalore_pulsating_ghosting's commented base stage)."""
    out=[]
    for line in s.splitlines():
        c=line.find("//")
        out.append(line if c<0 else line[:c])
    return "\n".join(out)

def _shader_stages(block):
    """Split a shader's outer { ... } block into its inner stage sub-blocks (the
    depth-1 { ... } passes). Returns a list of stage body strings. Comments are
    stripped first so a fully commented-out stage is not counted as real."""
    inner=block.strip()
    if inner.startswith("{"): inner=inner[1:]
    if inner.endswith("}"): inner=inner[:-1]
    inner=_strip_line_comments(inner)
    stages=[]; depth=0; start=None
    for k,ch in enumerate(inner):
        if ch=="{":
            if depth==0: start=k+1
            depth+=1
        elif ch=="}":
            depth-=1
            if depth==0 and start is not None:
                stages.append(inner[start:k]); start=None
    return stages

def _stage_is_additive(ll, toks):
    return ("add" in ll or "alphaadd" in ll
            or ("gl_one" in toks and toks.count("gl_one")>=2)
            or ("gl_src_alpha" in toks and "gl_one" in toks))

def _parse_pulse_and_base(block):
    """Inspect a shader's stages for a pulsating overlay (items.shader bangalore_pulsating*):
    a stage carrying `rgbGen wave <func> <base> <amp> <phase> <freq>` together with an
    additive blendfunc. Returns (pulse, basevisible) where pulse is
        {"map":texpath, "wave":[func,base,amp,phase,freq], "distnear":N, "distrange":R}
    or None, and basevisible is True when some OTHER (non-pulse) stage draws a solid/alpha
    base (so the surface keeps its diffuse) vs. the ghosting case (pulse-only, no base)."""
    pulse=None; basevisible=False
    for st in _shader_stages(block):
        smap=None; wave=None; additive=False; dnear=1024.0; drange=512.0; sawblend=False
        for line in st.splitlines():
            ls=line.strip()
            if not ls: continue
            ll=ls.lower(); toks=ll.split()
            mm=re.match(r'(?i)(?:clampmap|map)\s+(\S+)', ls)
            if mm:
                p=mm.group(1)
                # $whiteimage is the engine's built-in solid-white texture (r_common: it is
                # not a file on disk). The healthpack shaders (items.shader firstaid_dm,
                # firstaid, healthcanteen, surgeonpack) pulse a WHITE glow with
                # `map $whiteimage` + `blendFunc GL_SRC_ALPHA GL_ONE`. Treat it as a valid
                # pulse map (sentinel) so the pulse stage is recognised; other $-tokens and
                # *-lightmaps stay ignored.
                if p.lower() in ("$whiteimage","$white"):
                    smap="$whiteimage"
                elif not (p.startswith("$") or p.startswith("*")):
                    smap=p.replace("\\","/")
            if ll.startswith("blendfunc") and not sawblend:
                additive=_stage_is_additive(ll, toks); sawblend=True
            wm=re.match(r'(?i)rgbgen\s+wave\s+(\S+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)', ls)
            if wm:
                try: wave=[wm.group(1).lower(), float(wm.group(2)), float(wm.group(3)),
                           float(wm.group(4)), float(wm.group(5))]
                except Exception: wave=None
            am=re.match(r'(?i)alphagen\s+distfade\s+([-\d.]+)\s+([-\d.]+)', ls)
            if am:
                try: dnear=float(am.group(1)); drange=float(am.group(2))
                except Exception: pass
        if wave and additive and smap:
            pulse={"map":smap,"wave":wave,"distnear":dnear,"distrange":drange}
        elif smap and not additive:
            basevisible=True            # an opaque / alpha-blended solid base stage
    return pulse, basevisible

def parse_shader_props_file(txt):
    """Return {shadername_lower: {additive, autosprite, frames:[texpaths], fps}}.
    Captures the render hints the viewer needs to reproduce in-game emitter look:
      - additive  : a stage blends add / GL_ONE GL_ONE / alphaadd / src_alpha ONE
      - autosprite: deformVertexes autosprite[2] -> the surface is a camera-facing sprite
      - frames+fps: animmap / animMapPhase <fps> [phase] f1 f2 ...  (flame/arc cycles)"""
    out={}; i=0; n=len(txt)
    while i<n:
        m=_SHADER_HDR.match(txt,i)
        if not m:
            nl=txt.find("\n",i)
            if nl<0: break
            i=nl+1; continue
        name=m.group(1).lower(); bstart=m.end()-1; depth=0; j=bstart
        while j<n:
            if txt[j]=="{": depth+=1
            elif txt[j]=="}":
                depth-=1
                if depth==0: break
            j+=1
        block=txt[bstart:j+1]
        additive=False; autosprite=False; autosprite2=False; lightglow=False; frames=[]; fps=0; sawblend=False
        # sprite_type stays None unless the shader carries an explicit `spritegen` line -
        # the engine default (no keyword) is SPRITE_PARALLEL (tr_shader.c), and consumers
        # use None to mean "shader did not declare an orientation".
        spritescale=1.0; sawsprite=False; sprite_type=None
        twosided=False; sawcull=False
        _rgbvert=False; _sawrgb=False; _srcalpha=None
        _fade_inv=False; _fade_near=None; _fade_range=None
        _flaps=[]
        for line in block.splitlines():
            ls=line.strip()
            if ls.startswith("//"): continue
            ll=ls.lower()
            # deformVertexes autoSprite vs autoSprite2 are DISTINCT deforms (tr_shader.c
            # ParseDeform :1837-1845, exact-token match -> DEFORM_AUTOSPRITE /
            # DEFORM_AUTOSPRITE2). `autosprite` stays True for BOTH (it drives all the
            # existing billboard routing / cull exemptions); `autosprite2` additionally
            # marks the long-axis-pivot variant (tr_shade_calc.c Autosprite2Deform).
            if ll.startswith("deformvertexes"):
                _dt=ll.split()
                _dv=_dt[1] if len(_dt)>1 else ""
                if _dv=="autosprite": autosprite=True
                elif _dv=="autosprite2": autosprite=True; autosprite2=True
                # deformVertexes lightglow -> DEFORM_LIGHTGLOW (tr_shader.c ParseDeform
                # :1580-1583). LightGlowDeform (tr_shade_calc.c :809-897, dispatch :933-934)
                # rebuilds each 4-vert quad as a camera-facing square at its midpoint
                # (half-size=|corner-mid|*0.707, view left/up via RB_AddQuadStamp) and then
                # PUSHES that midpoint toward the eye by radius (clamped to |eye-mid|-4 up
                # close). It billboards like autosprite, so autosprite=True routes it into the
                # existing camera-facing pass; the separate `lightglow` flag additionally marks
                # the toward-eye push / placement-orbit that the viewer applies opt-in.
                elif _dv=="lightglow": autosprite=True; lightglow=True
            # MOHAA sprite sizing: `spritegen <type>` marks a sprite shader and resets scale to
            # 1.0; `spritescale <v>` sets it. Rendered quad world width = texW * entScale *
            # spritescale (tr_sprite.c), which the viewer needs to size VSS smoke puffs correctly.
            if ll.startswith("spritegen"):
                sawsprite=True; spritescale=1.0
                # capture the sprite orientation type - the engine has FOUR (tr_sprite.c
                # RB_DrawSprite), and `parallel_oriented` must be tested BEFORE `oriented`
                # (substring!) or the most common authored type (muzzle flashes, explosions,
                # sparks) collapses into the world-fixed one:
                #   parallel_upright  - up = world Z, only yaws to face the camera; never
                #                       tilts (mortar_dirthit dirt/dust plumes) (:135-160)
                #   parallel_oriented - camera-facing, view axes rotated by the sprite's
                #                       ROLL (:64-83)
                #   oriented          - FIXED IN WORLD SPACE on the entity axes, right =
                #                       axis[1], up = axis[2]; never faces the camera
                #                       (water rings/wakes lie flat, glass shards keep
                #                       their thrown orientation) (:96-99)
                #   parallel          - pure view axes, right negated, roll IGNORED (:84-91)
                _t=ll.split()
                _st=_t[1] if len(_t)>1 else ""
                if "upright" in _st: sprite_type="upright"
                elif "parallel" in _st and "oriented" in _st: sprite_type="parallel_oriented"
                elif "oriented" in _st: sprite_type="oriented"
                else: sprite_type="parallel"
            elif ll.startswith("spritescale"):
                t=ls.split()
                if len(t)>1:
                    try: spritescale=float(t[1]); sawsprite=True
                    except Exception: pass
            # cull mode: `cull none|disable|twosided` (or `nocull`) = render both faces. MOHAA's
            # cull_* garment shaders (cull_brownpants/cull_browncoat) use this for the thin two-
            # sided ankle/inner-leg panels; the viewer must NOT backface-cull them or they shatter
            # into slivers (the "pinched ankle"). cull back/front stay single-sided (engine default).
            _ct=ll.split()
            if _ct and _ct[0]=="cull":
                _cv=_ct[1] if len(_ct)>1 else ""
                twosided=_cv in ("none","disable","twosided","two-sided"); sawcull=True
            elif _ct and _ct[0]=="nocull":
                twosided=True; sawcull=True
            if ll.startswith("blendfunc"):
                b=ll.split()
                is_add=("add" in ll or "alphaadd" in ll
                    or ("gl_one" in b and b.count("gl_one")>=2)
                    or ("gl_src_alpha" in b and "gl_one" in b))
                # the FIRST blend stage defines how the sprite composites against the scene;
                # a later detail stage (e.g. water_g's `alphaadd` highlight over a `blend` base)
                # must NOT flip an alpha sprite to additive, or it stacks to opaque white.
                if not sawblend: additive=is_add; sawblend=True
                # srcalpha: does the FIRST blend's SOURCE factor read the vertex/shader alpha?
                # GL_SRC_ALPHA (explicit or via `blend`/`alphaadd` shorthands) -> yes; plain
                # `add` == GL_ONE GL_ONE (tr_shader.c NameToSrcBlendMode) -> alpha is IGNORED
                # by the hardware, so the emitter's alpha/fade/flickeralpha are no-ops in-game
                # (corona_util, gren_boom, air_explosion in scripts/sprites.shader).
                if _srcalpha is None:
                    _srcalpha=("alphaadd" in ll
                               or (len(b)>1 and b[1]=="blend")
                               or (len(b)>1 and b[1]=="gl_src_alpha")
                               or (len(b)>1 and b[1]=="gl_one_minus_src_alpha"))
            # rgbGen vertex/exactvertex/entity: the stage colour is driven by the entity's
            # shaderRGBA - i.e. the tik `color` tint actually applies. Without any such stage
            # (`blendfunc add`-only coronas) the texture renders untinted at full strength.
            if ll.startswith("rgbgen"):
                _t2=ll.split()
                if len(_t2)>1 and _t2[1] in ("vertex","exactvertex","entity","oneminusvertex"):
                    _rgbvert=True
                _sawrgb=True
            # deformVertexes flap <s|t> <div> <func> <base> <amp> <phase> <freq> [min] [max]
            # (tr_shader.c ParseDeform :1638-1696; ParseWaveForm :359-380 fixes the wave field
            # order as func/base/amp/phase/freq). This is MOHAA's foliage wind. `div` becomes
            # deformationSpread, and `min`/`max` land in bulgeWidth/bulgeHeight - defaulting to
            # 0 and 1 respectively when the shader omits them.
            _fl=re.match(r'(?i)deformvertexes\s+flap\s+([st])\s+([-\d.]+)\s+(\w+)'
                         r'\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)'
                         r'(?:\s+([-\d.]+))?(?:\s+([-\d.]+))?', ls)
            if _fl:
                try:
                    _div=float(_fl.group(2))
                    _flaps.append({"axis":_fl.group(1).lower(),
                                   "spread":(1.0/_div) if _div else 100.0,
                                   "func":_fl.group(3).lower(),
                                   "base":float(_fl.group(4)),
                                   "amp":float(_fl.group(5)),
                                   "phase":float(_fl.group(6)),
                                   "freq":float(_fl.group(7)),
                                   "min":float(_fl.group(8)) if _fl.group(8) is not None else 0.0,
                                   "max":float(_fl.group(9)) if _fl.group(9) is not None else 1.0})
                except Exception: pass
            if ll.startswith("alphagen"):
                _sawrgb=True
                # alphaGen distFade | oneMinusDistFade | tikiDistFade | oneMinusTikiDistFade
                # (tr_shader.c ParseStage :1168-1194). fDistNear / fDistRange are SHADER-level
                # fields, not per-stage, and BOTH default to 256 when the operands are omitted.
                _fm=re.match(r'(?i)alphagen\s+(oneminus)?(tiki)?distfade(?:\s+([-\d.]+))?(?:\s+([-\d.]+))?', ls)
                if _fm:
                    _fade_inv=bool(_fm.group(1))
                    try: _fade_near=float(_fm.group(3)) if _fm.group(3) else 256.0
                    except Exception: _fade_near=256.0
                    try: _fade_range=float(_fm.group(4)) if _fm.group(4) else 256.0
                    except Exception: _fade_range=256.0
            am=re.match(r'(?i)(animmap|animmapphase)\s+(.*)', ls)
            if am:
                toks=am.group(2).split()
                kind=am.group(1).lower()
                try: fps=float(toks[0]); toks=toks[1:]
                except Exception: fps=0
                if kind=="animmapphase" and toks: toks=toks[1:]   # drop the phase arg
                fr=[t.replace("\\","/") for t in toks if not (t.startswith("$") or t.startswith("*"))]
                if fr: frames=fr
        # pulsating overlay (rgbGen wave + additive blendfunc), e.g. bangalore_pulsating:
        # a separate stage drawn additively whose brightness oscillates over time. basevisible
        # distinguishes pulsating (solid base + pulse) from ..._ghosting (pulse-only, no base).
        pulse, basevisible = _parse_pulse_and_base(block)
        # OPACITY (tr_shader.c FinishShader): a surface is opaque unless its BASE (first) stage
        # blends or alpha-tests. A diffuse map's alpha is scene coverage ONLY when the shader
        # needs it (alphaFunc cutout, or a translucent base stage); otherwise it is a reflection/
        # spec weight consumed by a later stage (tc_coat/facewrap/tc_hat: opaque reflection
        # stage 0 + `blendFunc GL_ONE_MINUS_SRC_ALPHA GL_SRC_ALPHA` diffuse -> still SS_OPAQUE).
        _stlist=_shader_stages(block)
        _has_atest=any(re.search(r'(?i)\balpha(func|test)\b', st) for st in _stlist)
        _fb=None
        for _line in (_stlist[0].splitlines() if _stlist else []):
            _l=_line.strip().lower()
            if _l.startswith("blendfunc"): _fb=_l.split()[1:]; break   # FIRST stage only
        _base_opaque=(not _fb) or _fb[:2]==["gl_one","gl_zero"] or _fb[:1]==["opaque"]
        # FIRST-STAGE ALPHA TEST + DETAIL BUNDLE (for emitter sprites).
        #   alphafunc GT0|LT128|GE128 (tr_shader.c NameToAFunc :175-196): a per-pixel TEST -
        #   pass or discard, nothing in between. When the stage also has NO blendfunc
        #   (mortar_dirthit / dirtplume: `blendfunc blend` is commented out), passing pixels
        #   draw fully OPAQUE and failing ones are see-through holes; alphaGen vertex scales
        #   texel alpha BEFORE the test, so fading particles ERODE instead of washing out.
        #   Only exported in that opaque case (`atest`); with a real blendfunc the current
        #   blended path is already the closer approximation.
        #   nextbundle (tr_shader.c :1841-1853, anything but `add` -> GL_MODULATE): a second
        #   texture multiplied over the first - the fine grain detail on the dirt plumes.
        #   Captured as `bundle` {map, scale[sx,sy]} from `tcmod scale`; animated tcmods
        #   (scroll/rotate) are baked at phase 0 by the consumer.
        _atest0=None; _bundle0=None
        if _stlist:
            _s0=_stlist[0]
            for _line in _s0.splitlines():
                _l=_line.strip()
                if _l.startswith("//"): continue
                _ma=re.match(r'(?i)alpha(?:func|test)\s+(\S+)', _l)
                if _ma:
                    _fn=_ma.group(1).lower()
                    if _fn in ("gt0","lt128","ge128"): _atest0=_fn
            _bp=re.split(r'(?im)^\s*nextbundle\b.*$', _s0, maxsplit=1)
            if len(_bp)>1:
                _bmap=None; _bsc=None; _bscr=None; _brot=None; _scr_i=None; _sc_i=None
                for _li,_line in enumerate(_bp[1].splitlines()):
                    _l=_line.strip()
                    if _l.startswith("//"): continue
                    _mm=re.match(r'(?i)(?:clamp)?map\s+(\S+)', _l)
                    if _mm and _bmap is None and not _mm.group(1).startswith(("$","*")):
                        _bmap=_mm.group(1).replace("\\","/")
                    _ms=re.match(r'(?i)tcmod\s+scale\s+([\-\d.]+)\s+([\-\d.]+)', _l)
                    if _ms and _bsc is None:
                        try: _bsc=(float(_ms.group(1)), float(_ms.group(2))); _sc_i=_li
                        except Exception: _bsc=None
                    _msc=re.match(r'(?i)tcmod\s+scroll\s+([\-\d.]+)\s+([\-\d.]+)', _l)
                    if _msc and _bscr is None:
                        try: _bscr=(float(_msc.group(1)), float(_msc.group(2))); _scr_i=_li
                        except Exception: _bscr=None
                    _mr=re.match(r'(?i)tcmod\s+rotate\s+([\-\d.]+)', _l)
                    if _mr and _brot is None:
                        try: _brot=float(_mr.group(1))
                        except Exception: _brot=None
                if _bmap:
                    _bundle0={"map":_bmap,"scale":list(_bsc or (1.0,1.0))}
                    # BASE-stage `tcmod rotate` (before nextbundle): the base texcoords spin
                    # too (RB_CalcRotateTexCoords, tr_shade_calc.c:1599-1631). vsssource /
                    # vsssource2 (scripts/sprites.shader) counter-rotate base +20 / bundle
                    # -20 - the in-game volumetric churn. Exported as `brot` so the viewer
                    # rotates the base image at runtime alongside the bundle pattern.
                    for _line in _bp[0].splitlines():
                        _l=_line.strip()
                        if _l.startswith("//"): continue
                        _mbr=re.match(r'(?i)tcmod\s+rotate\s+([\-\d.]+)', _l)
                        if _mbr:
                            try:
                                _bundle0["brot"]=float(_mbr.group(1)); break
                            except Exception: pass
                    # ANIMATED tcmods: exported so the viewer composites them at RUNTIME
                    # (the drifting grain that reads as falling dirt in-game). tcmods apply
                    # in LISTED order (tr_shader.c ParseStage tcMod chain): scroll BEFORE
                    # scale (mortar_dirthit: `scroll 0 -.1` then `scale 8 16`) means
                    # tc=(uv+o)*S, so the pattern drifts at the scroll rate in BASE uv/sec
                    # regardless of S; scroll listed after scale drifts at rate/scale.
                    if _bscr and (_bscr[0] or _bscr[1]):
                        _bundle0["scroll"]=list(_bscr)
                        _bundle0["prescale"]=bool(_scr_i is not None and (_sc_i is None or _scr_i<_sc_i))
                    if _brot: _bundle0["rotate"]=_brot
        # BASE-stage (single-bundle) `tcmod rotate <deg/sec>`: the whole first-stage texture
        # spins about its centre every frame (RB_CalcRotateTexMatrix, tr_shade_calc.c:809-826:
        # degs = -degsPerSecond * shaderTime, texcoords rotated about (0.5,0.5)). This is the
        # aircraft propeller effect - the prop / c47prop vehicle shaders draw a flat clampmap
        # quad whose texcoords rotate at `tcmod rotate 5000` so it reads as a spinning disc.
        # Only the part of stage 0 BEFORE any nextbundle is the base (the nextbundle's own
        # `tcmod rotate` is already captured as bundle.rotate above). clamp is exported only
        # alongside a rotate: a static clampmap sits inside [0,1] where clamp vs repeat is
        # invisible, so flagging it there would risk regressing other clampmap surfaces.
        _texrotate=None; _clampbase=False
        if _stlist:
            _s0base=re.split(r'(?im)^\s*nextbundle\b.*$', _stlist[0], maxsplit=1)[0]
            for _line in _s0base.splitlines():
                _l=_line.strip()
                if _l.startswith("//"): continue
                if _texrotate is None:
                    _mtr=re.match(r'(?i)tcmod\s+rotate\s+([\-\d.]+)', _l)
                    if _mtr:
                        try: _texrotate=float(_mtr.group(1))
                        except Exception: _texrotate=None
                if re.match(r'(?i)clampmap\s+\S', _l): _clampbase=True
        needs_alpha=bool(_has_atest or (not _base_opaque))
        # no explicit cull keyword -> fall back to the cull_* naming convention.
        if not sawcull and name.startswith("cull_"): twosided=True
        # record any shader that declares a blend (even alpha) so emitter sprites can read an
        # explicit additive=False, distinguishing "known alpha" from "no shader info".
        if additive or autosprite or frames or sawblend or sawsprite or pulse or twosided or needs_alpha or _sawrgb or _atest0 or _bundle0 or _texrotate or _flaps:
            rec={"additive":additive,"autosprite":autosprite,"autosprite2":autosprite2,"lightglow":lightglow,"frames":frames,"fps":fps,
                 "spritescale":spritescale,"sprite":sawsprite,"twosided":twosided,"sprite_type":sprite_type,
                 "pulse":pulse,"basevisible":basevisible,"needs_alpha":needs_alpha}
            if _atest0 and _base_opaque: rec["atest"]=_atest0
            if _bundle0: rec["bundle"]=_bundle0
            if _texrotate:
                rec["texrotate"]=_texrotate
                if _clampbase: rec["clamp"]=True
            # camera-distance LOD fade. inv=False -> AGEN_DIST_FADE (opaque inside near,
            # gone by near+range: the real leaf/branch cards). inv=True ->
            # AGEN_ONE_MINUS_DIST_FADE (invisible inside near, opaque past near+range: the
            # billboard stand-in the engine swaps in at long range).
            if _flaps: rec["flap"]=_flaps
            if _fade_near is not None:
                rec["distfade"]={"near":_fade_near,
                                 "range":(_fade_range if _fade_range else 256.0) or 256.0,
                                 "inv":_fade_inv}
            # only assert tint/alpha facts when the shader actually declared its stages
            # (a bare qer_editorimage stub tells us nothing) - a blend line is the signal
            # that the stage list is real.
            if sawblend:
                rec["rgbvertex"]=_rgbvert
                rec["srcalpha"]=bool(_srcalpha)
            out[name]=rec
        i=j+1
    return out

def build_shader_props(vfs):
    P={}
    for k in list(vfs.names()):
        if k.endswith(".shader"):
            try: P.update(parse_shader_props_file(vfs.read(k).decode("latin-1","replace")))
            except Exception: pass
    return P

# ---------------------------------------------------------------------- tik parsing
def expand_tik_includes(txt, vfs, _depth=0, _chain=None, _budget=None):
    """Splice $include'd files inline, mirroring the engine's TikiScript parser
    (corepp/tiki_script.cpp ProcessCommand: a `$include <path>` line loads that file
    in place at the directive). Several MOHAA assets - notably both grenades - keep their
    whole setup/animations body in a shared _base.txt that each wrapper .tik pulls in this
    way, so without expansion the wrapper parses as empty (no skelmodel, no surface->shader
    map). The include path is used verbatim as a VFS path (engine LoadFile(argument1)) and
    may nest; a chain guard blocks include cycles and a depth cap stops runaway recursion.

    The cycle guard only blocks a file that includes itself somewhere in its OWN ancestry,
    which leaves sibling fan-out unbounded: 16 levels of a file that includes the next one
    50 times expands to ~50**16 lines with no cycle anywhere. _budget caps the TOTAL
    spliced output instead, so a hostile (or merely broken) include graph stops rather
    than eating all memory. 24 MB is far beyond any real .tik chain."""
    if vfs is None or _depth>16 or "$include" not in txt.lower(): return txt
    if _budget is None: _budget=[24*1024*1024]
    if _budget[0]<=0: return txt
    if _chain is None: _chain=()
    out=[]
    for line in txt.splitlines(keepends=True):
        m=re.match(r'\s*\$include\s+(\S+)', line, re.I)
        if not m:
            out.append(line); continue
        inc=m.group(1).strip().strip('"').replace("\\","/")
        key=inc.lower()
        if key in _chain:                       # cycle -> drop the directive
            continue
        data=vfs.read(inc)
        if data is None:                        # unresolved include: leave the directive as-is
            out.append(line); continue
        try: sub=data.decode("latin-1","replace")
        except Exception:
            out.append(line); continue
        _budget[0]-=len(sub)
        if _budget[0]<=0:                       # include graph too large - stop splicing
            out.append(line); break
        out.append(expand_tik_includes(sub, vfs, _depth+1, _chain+(key,), _budget))
    return "".join(out)

def parse_tik_setup(txt):
    """Return {skdpath_lower: [(surface_lower, shader_name), ...]} for one .tik.
    A .tik's setup block lists `path`, then `skelmodel x.skd`, then the `surface`
    lines that belong to that model until the next skelmodel."""
    out={}; cur_path=""; cur=None
    m=re.search(r'(?is)\bsetup\b\s*\{', txt)
    if m:
        bstart=m.end()-1; depth=0; j=bstart
        while j<len(txt):
            if txt[j]=="{": depth+=1
            elif txt[j]=="}":
                depth-=1
                if depth==0: break
            j+=1
        body=txt[bstart+1:j]
    else:
        body=txt
    for line in body.splitlines():
        line=line.split("//")[0].strip()
        if not line: continue
        tok=line.split()
        t0=tok[0].lower().lstrip("$")          # player models spell these as $path / $skelmodel
        if t0=="path" and len(tok)>1:
            cur_path=tok[1].strip().rstrip("/")
        elif t0=="skelmodel" and len(tok)>1:
            cur=(cur_path+"/"+tok[1]).lower().replace("\\","/"); out.setdefault(cur,[])
        elif t0=="surface" and "shader" in [x.lower() for x in tok]:
            low=[x.lower() for x in tok]; si=low.index("shader")
            sname=" ".join(tok[1:si]).lower(); shader=tok[si+1] if si+1<len(tok) else ""
            if cur is not None and shader: out[cur].append((sname,shader))
    return out

def build_tik_index(vfs):
    """Return {skdpath_lower: [(surface_lower, shader), ...]} merged across all .tik,
    keeping for each .skd the mapping that covers the most surfaces (best skin)."""
    TI={}
    for k in list(vfs.names()):
        if not k.endswith(".tik"): continue
        try: mapping=parse_tik_setup(expand_tik_includes(vfs.read(k).decode("latin-1","replace"), vfs))
        except Exception: continue
        for skd,surfs in mapping.items():
            if surfs and len(surfs)>len(TI.get(skd,[])):
                TI[skd]=surfs
    return TI

# ------------------------------------------------------------------ texture loading
def _have_pil():
    try:
        import PIL  # noqa
        return True
    except Exception:
        return False

def texture_has_varied_alpha(vfs, texpath):
    """True if the texture carries a REAL alpha channel (not constant ~255). Decides
    whether an animated nextbundle modulates the ALPHA-TEST pattern too (GL_MODULATE
    multiplies alpha as well as RGB - scrolling holes), or only the RGB grain."""
    try:
        if not _have_pil(): return False
        from PIL import Image
        d=vfs.read(texpath)
        if not d: return False
        im=Image.open(io.BytesIO(d)); im.load()
        if "A" not in im.getbands(): return False
        lo,hi=im.convert("RGBA").getchannel("A").getextrema()
        return lo<250
    except Exception:
        return False

_GL1_LUT=None
def _gl1_lut():
    """256x256 byte table: _GL1_LUT[m*256+v] = round(v*255/m) - the un-premultiply divide,
    done as a lookup so the per-texel pass below needs no float math and no numpy."""
    global _GL1_LUT
    if _GL1_LUT is None:
        t=bytearray(256*256)
        for m in range(1,256):
            b=m*256
            for v in range(m+1): t[b+v]=(v*255+m//2)//m
        _GL1_LUT=bytes(t)
    return _GL1_LUT

def dataurl_gl_one_additive(durl):
    """Re-encode a sprite so Canvas-2D 'lighter' reproduces `blendFunc GL_ONE GL_ONE`.

    A stage whose SOURCE blend factor is GL_ONE (`blendFunc GL_ONE GL_ONE`, or the
    `blendfunc add` shorthand - tr_shader.c NameToSrcBlendMode -> GLS_SRCBLEND_ONE)
    never reads the fragment alpha: the GPU computes dst.rgb = src.rgb + dst.rgb, so
    EVERY texel of the texture's RGB is added regardless of its alpha channel, and
    `alphaGen entity` on such a stage is a no-op.

    Canvas 'lighter' is PREMULTIPLIED - it adds (rgb * a) - so shipping the native
    alpha masks the sprite down to its alpha footprint. bh_metal_fastpiece.tga (the
    spark splinter skin) carries alpha only over x 2..5 / y 3..28 of 8x32 while its RGB
    spans x 1..6 / y 1..30: the browser added 2.18x less light than the GPU, which is
    the ~0.5x spark size against in-game footage. corona_util's hard-keyed synthetic
    alpha cost 1.92x and took the soft glow falloff with it.

    Flattening alpha to 255 fixes the light but breaks the BACKDROP: 'lighter' is
    `plus-lighter`, alpha_r = alpha_s + alpha_b, and the viewer's canvas is transparent
    (draw(): ctx.clearRect over the CSS backdrop). An opaque BLACK texel adds nothing to
    the colour but drives destination alpha to 1, punching an opaque black square where
    the backdrop used to show - the corona boxes.

    So compensate instead of flatten: let the alpha carry the texel's own intensity as
    COVERAGE and pre-divide the RGB by it.
        A'   = max(R,G,B)
        RGB' = RGB * 255 / A'          (A' > 0; pure black -> fully transparent)
    Canvas then adds RGB' * A'/255 == RGB - the exact GPU contribution, verified to
    within half a byte per texel - while a black texel contributes zero alpha, so the
    backdrop is untouched and no square appears. Bright cores (A' ~ 255) are unchanged.
    """
    if not durl or not _have_pil(): return durl
    try:
        from PIL import Image
        im=Image.open(io.BytesIO(base64.b64decode(durl.split(",",1)[1]))); im.load()
        im=im.convert("RGBA")
        d=bytearray(im.tobytes()); L=_gl1_lut()
        for i in range(0,len(d),4):
            r=d[i]; g=d[i+1]; b=d[i+2]
            m=r if r>=g else g
            if b>m: m=b
            if m==0:
                d[i]=0; d[i+1]=0; d[i+2]=0; d[i+3]=0     # black adds nothing AND no coverage
            else:
                k=m<<8
                d[i]=L[k|r]; d[i+1]=L[k|g]; d[i+2]=L[k|b]; d[i+3]=m
        buf=io.BytesIO(); Image.frombytes("RGBA",im.size,bytes(d)).save(buf,"PNG")
        return "data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return durl                                       # never lose a sprite over this

def texture_to_dataurl(vfs, texpath, max_dim=512, emitter_clean=False, keep_alpha=False, bundle_path=None, bundle_scale=(1.0,1.0)):
    """Load a stored texture and return a browser-embeddable data: URL.
    jpg/png pass through; tga/dds are decoded (Pillow) and re-encoded.
    emitter_clean=True (for additive emitter sprites): never JPEG-encode, and floor
    near-black pixels to pure (0,0,0). JPEG's lossy near-black leaves a faint box that
    additive ('lighter') blending then adds in as a visible rectangle behind the glow;
    lossless PNG + a black floor makes the background add exactly zero -> no box."""
    data=vfs.read(texpath)
    if data is None: return None
    ext=texpath.rsplit(".",1)[-1].lower()
    if ext in ("jpg","jpeg") and not emitter_clean:
        return "data:image/jpeg;base64,"+base64.b64encode(data).decode()
    if ext=="png" and not emitter_clean:
        return "data:image/png;base64,"+base64.b64encode(data).decode()
    # tga / dds / tif need decoding (and so does anything we want to clean)
    if not _have_pil(): 
        if ext in ("jpg","jpeg"): return "data:image/jpeg;base64,"+base64.b64encode(data).decode()
        if ext=="png": return "data:image/png;base64,"+base64.b64encode(data).decode()
        return None
    try:
        from PIL import Image
        im=Image.open(io.BytesIO(data)); im.load()
        if max(im.size)>max_dim:
            r=max_dim/max(im.size)
            im=im.resize((max(1,int(im.size[0]*r)),max(1,int(im.size[1]*r))))
        has_alpha=("A" in im.getbands())
        if bundle_path is not None:
            # nextbundle GL_MODULATE bake (tr_shader.c:1841-1853): RGB(A) *= detail texel,
            # bundle tiled `tcmod scale sx sy` times across the quad (texcoords *s with
            # GL_REPEAT). Animated tcmods (mortar_noise scroll, dirtnoise rotate) are baked
            # at phase 0 - static grain; the drift/spin is not reproduced. RGB-only when the
            # base has no alpha so the emitter_clean alpha synthesis below still applies.
            try:
                _nd=vfs.read(bundle_path)
                if _nd:
                    _nim=Image.open(io.BytesIO(_nd)); _nim.load()
                    _sx,_sy=(bundle_scale or (1.0,1.0))
                    _sx=abs(float(_sx)) or 1.0; _sy=abs(float(_sy)) or 1.0
                    _tw=max(1,int(round(im.size[0]/_sx))); _th=max(1,int(round(im.size[1]/_sy)))
                    from PIL import ImageChops
                    if has_alpha:
                        _tile=_nim.convert("RGBA").resize((_tw,_th))
                        _lay=Image.new("RGBA",im.size)
                    else:
                        _tile=_nim.convert("RGB").resize((_tw,_th))
                        _lay=Image.new("RGB",im.size)
                    for _yy in range(0,im.size[1],_th):
                        for _xx in range(0,im.size[0],_tw): _lay.paste(_tile,(_xx,_yy))
                    im=ImageChops.multiply(im.convert("RGBA" if has_alpha else "RGB"),_lay)
            except Exception:
                pass
        if emitter_clean:
            # Give the sprite a transparent background so it composites cleanly in any blend
            # mode (a plain black background still draws as a box where a sprite is drawn
            # source-over). For a no-alpha glow/arc texture, synthesise alpha by hard-keying
            # near-black to transparent and everything brighter to fully opaque - the bright
            # pixels keep alpha 255 so the additive glow is unchanged. Done with C-level
            # Pillow ops (no slow/fragile per-pixel Python loop). If anything here fails we
            # fall through to the normal encoding below so a texture never silently vanishes.
            try:
                from PIL import ImageChops
                TH=18
                if not has_alpha:
                    rgb=im.convert("RGB"); r,g,b=rgb.split()
                    mx=ImageChops.lighter(ImageChops.lighter(r,g),b)   # per-pixel max(r,g,b)
                    # Alpha from brightness. A pure 0-or-255 cutoff dithered the dirt sprites
                    # (mortar_dirthit) into a crunchy mess; a smooth ramp keeps their edges and
                    # see-through gaps clean like in-game. Pure black (< TH) floors to 0 so
                    # additive blending adds no background box; from TH up, alpha rises
                    # smoothly to 255 by ~64 brightness (so mid/bright dirt is fully opaque,
                    # only the darkest fringes fade) - crisp, not washed out, not dithered.
                    def _a(v):
                        if v<TH: return 0
                        return 255 if v>=64 else int((v-TH)*255/(64-TH))
                    alpha=mx.point(_a)
                    rgb.putalpha(alpha); im=rgb
                else:
                    # texture HAS a real alpha channel. Keep its own soft alpha (mist, dust,
                    # smoke rely on the gradient) and only floor the NEAR-TRANSPARENT fringe
                    # to zero so faint <~10% pixels don't haze the edges. A steep 96->150
                    # alpha test was tried to crisp up the dirt sprites but it crushed soft
                    # sprites (the white `mist`) into blocky low-quality patches and, under
                    # additive blend, whitened them at grazing angles. The dirt sprites read
                    # fine with their native alpha at 512px; a gentle fringe floor is enough.
                    im=im.convert("RGBA")
                    _a=im.getchannel("A")
                    im.putalpha(_a.point(lambda v: 0 if v<26 else v))
                buf=io.BytesIO(); im.save(buf,"PNG")
                return "data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode()
            except Exception:
                pass   # fall through to the normal encoding so the texture still loads
        if has_alpha and keep_alpha:
            im=im.convert("RGBA"); buf=io.BytesIO(); im.save(buf,"PNG")
            return "data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode()
        # MOHAA model surfaces are opaque unless the shader's BASE stage blends/alpha-tests
        # (tr_shader.c FinishShader). A diffuse map's alpha is then a reflection/spec weight,
        # NOT scene coverage (tc_coat, facewrap: opaque reflection stage 0 + blendFunc
        # GL_ONE_MINUS_SRC_ALPHA GL_SRC_ALPHA diffuse stage 1 -> SS_OPAQUE). Drop it here.
        im=im.convert("RGB"); buf=io.BytesIO(); im.save(buf,"JPEG",quality=86)
        return "data:image/jpeg;base64,"+base64.b64encode(buf.getvalue()).decode()
    except Exception:
        # last resort: if the bytes are already a browser format, embed them raw so the
        # texture appears (a box is far better than an invisible sprite -> sphere fallback)
        try:
            if ext in ("jpg","jpeg"): return "data:image/jpeg;base64,"+base64.b64encode(data).decode()
            if ext=="png": return "data:image/png;base64,"+base64.b64encode(data).decode()
        except Exception: pass
        return None

def build_global_surface_shaders(tik_index):
    """Most common shader assigned to each exact surface name across all tiks -
    a last-resort skin for surfaces like 'head'/'hand' on composite models whose
    own folder has no sibling defining them."""
    from collections import Counter
    cnt={}
    for pairs in tik_index.values():
        for s,sh in pairs:
            if "*" in s or s=="all": continue
            cnt.setdefault(s,Counter())[sh]+=1
    return {s:c.most_common(1)[0][0] for s,c in cnt.items()}

def resolve_surface_texmap(skd_relpath, surface_names, vfs, shader_index, tik_index, global_surf=None):
    """Like resolve_surface_textures but returns {surface_lower: (texpath, shadername)}
    so callers can also look up per-surface shader render properties."""
    import fnmatch
    key=skd_relpath.lower().replace("\\","/")
    pairs=tik_index.get(key, [])
    if not pairs:                               # borrow skins from sibling models in the same folder
        folder=key.rsplit("/",1)[0]+"/"
        sib=[]
        for sk,sp in tik_index.items():
            if sk!=key and sk.rsplit("/",1)[0]+"/"==folder: sib+=sp
        pairs=sib
    exact={s:sh for s,sh in pairs if "*" not in s and s!="all"}
    globs=[(s,sh) for s,sh in pairs if "*" in s]
    all_shader=next((sh for s,sh in pairs if s=="all"), None)
    def shader_for(sl):
        if sl in exact: return exact[sl]
        best=None
        for pat,sh in globs:
            if fnmatch.fnmatch(sl,pat) and (best is None or len(pat)>len(best[0])): best=(pat,sh)
        if best: return best[1]
        for s,sh in exact.items():              # loose: skd 'pants' vs tik 'ranger_pants'
            if sl and (sl in s or s in sl): return sh
        base=re.sub(r'\d+$','',sl)              # numbered variants share a texture: jeep8 ~ jeep3
        if base and base!=sl:
            for s,sh in exact.items():
                if re.sub(r'\d+$','',s)==base: return sh
        if all_shader: return all_shader        # own tik's 'surface all' beats cross-model guess
        if global_surf and sl in global_surf: return global_surf[sl]
        return None
    res={}
    for s in surface_names:
        sl=s.lower(); tex=None
        shader=shader_for(sl)
        if shader:
            mp=shader_index.get(shader.lower())
            tex=vfs.find_texture(mp) if mp else None
            if tex is None: tex=vfs.find_texture(shader)
        if tex is None:                        # surface name itself may be a shader/texture
            mp=shader_index.get(sl)
            tex=vfs.find_texture(mp) if mp else vfs.find_texture(sl)
            if mp and shader is None: shader=sl
        res[sl]=(tex, shader)
    return res

def resolve_surface_textures(skd_relpath, surface_names, vfs, shader_index, tik_index, global_surf=None):
    """Map each .skd surface name to a stored texture path (backward-compatible)."""
    return {s:t for s,(t,sh) in resolve_surface_texmap(
        skd_relpath, surface_names, vfs, shader_index, tik_index, global_surf).items()}

def _solid_white_dataurl():
    """A small solid-OPAQUE white PNG data URL, standing in for the engine's built-in
    `$whiteimage` (which has no file on disk). Used as the pulse overlay for the healthpack
    shaders (firstaid_dm etc.), whose `map $whiteimage` + `blendFunc GL_SRC_ALPHA GL_ONE`
    stage adds a white glow modulated by rgbGen wave. Built with stdlib zlib/struct so it
    never depends on Pillow (and sidesteps the Pillow optimize=True encoding pitfall)."""
    # Rebuilt each call (no module-level cache to accidentally drop): a 4x4 opaque-white PNG,
    # built with stdlib zlib/struct so it never depends on Pillow (sidesteps the Pillow
    # optimize=True encoding pitfall). Stands in for the engine's built-in $whiteimage.
    import zlib, struct
    w=h=4
    raw=b"".join(b"\x00"+b"\xff\xff\xff\xff"*w for _ in range(h))   # opaque white RGBA rows
    def _chunk(t,d):
        c=t+d
        return struct.pack(">I",len(d))+c+struct.pack(">I",zlib.crc32(c)&0xffffffff)
    png=(b"\x89PNG\r\n\x1a\n"
         +_chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,6,0,0,0))
         +_chunk(b"IDAT",zlib.compress(raw,9))
         +_chunk(b"IEND",b""))
    return "data:image/png;base64,"+base64.b64encode(png).decode()

# ------------------------------------------------------------------- convenience
def write_textures_manifest(vfs, skd_relpath, surface_names, shader_index, tik_index,
                            out_path, max_dim=512, global_surf=None, shader_props=None,
                            anim_max_dim=128, anim_max_frames=32):
    """Resolve a .skd's surfaces to textures, embed them as data URLs, and write a
    {surface_name: entry} JSON manifest for mohaa_view.py --textures.

    entry is either a plain data-url string (simple opaque surface) or, when the
    surface's shader carries render hints, an object:
        {"tex":url, "additive":bool, "autosprite":bool, "frames":[url,...], "fps":N}
    The viewer reproduces additive glow, camera-facing sprites and frame animation
    (flames, electric arcs) from these. Returns (n_textured, n_surfaces)."""
    import json
    tm=resolve_surface_texmap(skd_relpath, surface_names, vfs, shader_index, tik_index, global_surf)
    man={}; framecache={}
    for s in surface_names:
        tp, sh = tm.get(s.lower(), (None,None))
        props=(shader_props or {}).get((sh or "").lower())
        # PULSATING OVERLAY (items.shader bangalore_pulsating / _ghosting): a shader with a
        # base diffuse stage PLUS a separate additive `rgbGen wave` pulse stage. The diffuse
        # pick (tp) is the SOLID base when one is visible; the pulse texture is its own stage.
        # Built specially so the base is encoded opaque (NOT black-keyed) and the pulse is
        # carried as an overlay the viewer animates. _ghosting has no base (pulse only).
        pulse=props.get("pulse") if props else None
        if pulse:
            entry={}
            if props.get("basevisible") and tp:
                bdu=texture_to_dataurl(vfs, tp, max_dim=max_dim, emitter_clean=False)
                if bdu: entry["tex"]=bdu
            if str(pulse["map"]).lower() in ("$whiteimage","$white"):
                pdu=_solid_white_dataurl()   # engine $whiteimage -> solid opaque white glow
            else:
                ptp=vfs.find_texture(pulse["map"])
                pdu=texture_to_dataurl(vfs, ptp, max_dim=max_dim, emitter_clean=True) if ptp else None
            if pdu:
                entry["pulse"]={"tex":pdu,"wave":pulse["wave"],
                                "distnear":pulse["distnear"],"distrange":pulse["distrange"]}
            if entry: man[s]=entry
            continue
        if not tp:
            # animmap-only shader on a MAIN-model surface (building bh_wood_puff.tik / any
            # spritebeam-style .tik DIRECTLY, not as a sub-tik): the shader is `animmap 20
            # woodpuff1..7.tga` with no `map`/`clampmap`, so resolve_surface_texmap found no
            # base texture and the surface would render as an untextured flat quad. Fall back
            # to the FIRST animmap frame as the base (the frame list below carries the cycle),
            # mirroring the sub-tik / emitter animmap fallback so the puff shows its texture
            # even when viewed as a standalone model.
            if props and props.get("frames"):
                tp=vfs.find_texture(props["frames"][0])
            if not tp: continue
        # effect surfaces (additive flame/arc, autosprite, frame-animated) get a transparent
        # background via emitter_clean so the flame/arc has no black box; ordinary opaque
        # surfaces (vehicle body, world geometry) keep their plain encoding.
        eff=bool(props and (props["additive"] or props["autosprite"] or props["frames"]))
        # base-stage `tcmod rotate` (spinning propeller disc) + its clampmap flag: carried
        # through on whichever entry shape this surface ends up as (FX object, twosided
        # object, or - via the tail below - a plain surface promoted to an object).
        texrot=props.get("texrotate") if props else None
        clampf=bool(props and props.get("clamp"))
        dfade=props.get("distfade") if props else None
        # keep the diffuse alpha only when the shader needs it as coverage (alphaFunc cutout or
        # translucent base stage); opaque garment/face shaders (tc_coat, facewrap, wehrmact_*)
        # otherwise drop it so the surface renders solid instead of see-through.
        keepA=bool(props and props.get("needs_alpha"))
        du=texture_to_dataurl(vfs, tp, max_dim=max_dim, emitter_clean=eff, keep_alpha=keepA)
        if not du: continue
        if eff:
            entry={"tex":du,"additive":bool(props["additive"]),
                   "autosprite":bool(props["autosprite"]),
                   "autosprite2":bool(props.get("autosprite2")),"lightglow":bool(props.get("lightglow")),"fps":props.get("fps") or 0}
            frs=[]
            for fp in (props["frames"] or [])[:anim_max_frames]:
                t=vfs.find_texture(fp)
                if t:
                    d=framecache.get(t)
                    if d is None:
                        d=texture_to_dataurl(vfs, t, max_dim=anim_max_dim, emitter_clean=True); framecache[t]=d
                    if d: frs.append(d)
            if len(frs)>1: entry["frames"]=frs
            if props.get("twosided"): entry["twosided"]=True
            if texrot: entry["texrotate"]=texrot
            if clampf: entry["clamp"]=True
            if dfade: entry["distfade"]=dfade
            if props.get("atest"): entry["atest"]=props["atest"]
            if props.get("flap"): entry["flap"]=props["flap"]
            man[s]=entry
        else:
            # plain (non-FX) surface. Promote to an object when the shader declares two-sided
            # culling (cull_* garment panels) and/or a spinning-propeller `tcmod rotate`;
            # a bare opaque surface stays a compact plain data-url string.
            extra={}
            if props and props.get("twosided"): extra["twosided"]=True
            if texrot: extra["texrotate"]=texrot
            if clampf: extra["clamp"]=True
            if dfade: extra["distfade"]=dfade
            # alphaFunc on an opaque base stage: the surface is alpha-TESTED, not blended
            # (tr_shader.c:1129-1146). The viewer needs the threshold to reproduce the hard
            # cutout; without it a leaf card's sub-threshold texels ghost instead of vanishing.
            if props and props.get("atest"): extra["atest"]=props["atest"]
            if props and props.get("flap"): extra["flap"]=props["flap"]
            if extra: extra["tex"]=du; man[s]=extra
            else: man[s]=du
    with open(out_path,"w",encoding="utf-8") as f: json.dump(man,f)
    return len(man), len(surface_names)

# ===========================================================================
# TIKI ANIMATION CATALOG - full $include / $path / includes{} resolution
# ===========================================================================
# A character .tik almost never lists its own animations. allied_pilot.tik ends
# its setup with `path models/human/protoanimations` and then pulls the real
# list in with `$include models/human/new_generic_human.tik`; the player models
# go `$include models/player/base/include.txt` -> twelve anims_*.txt files. The
# engine resolves that with TikiScript, and the rules that matter here are:
#
#   $path <dir>      TikiScript::ProcessCommand (corepp/tiki_script.cpp:414-421)
#                    stores <dir> in THIS script's `path`, appending a trailing
#                    '/' when absent. `path` inside setup{} writes the same field
#                    (TIKI_ParseSetup, tiki/tiki_parse.cpp:1038-1045).
#
#   $include <file>  opens a CHILD TikiScript (tiki_script.cpp:398-412). A fresh
#                    TikiScript starts with path[0]=0 (tiki_script.cpp:50), so an
#                    include does NOT inherit the parent's path - each file owns
#                    its own path scope, and every anim inside it resolves against
#                    that file's own $path.
#
#   <alias> <file>   TIKI_ParseAnimations (tiki_parse.cpp:470-472) builds the .skc
#                    reference as currentScript->path + token, where currentScript
#                    is the INNERMOST script that produced the token
#                    (tiki_script.cpp:646,666). Flags follow on the SAME line -
#                    TIKI_ParseAnimationFlags uses TokenAvailable(false)
#                    (tiki_parse.cpp:240): weight/crossblend take a value,
#                    deltadriven/default_angles/notimecheck/dontrepeate/random/
#                    autosteps_run/autosteps_walk/autosteps_dog are bare.
#
#   includes <names…>{…}
#                    TIKI_ParseIncludes (tiki_parse.cpp:320-341) activates the
#                    block only when one of <names> prefix-matches sv_mapname, and
#                    with no map loaded the mapname defaults to "utils" - which is
#                    exactly why the developers named the everything-block
#                    `includes test utils`. The viewer is not a level, so instead
#                    of picking one group it walks EVERY group and files each one
#                    under its own menu branch; nothing is hidden.
#
#   $mapspec <names>{…}
#                    the same map gate applied inside animations{} (tiki_parse.cpp:
#                    415-447). Walked as a branch here for the same reason.
#
# The result is a node tree plus one de-duplicated animation table. Nodes are
# referenced BY INDEX, so a file included by forty mission groups is emitted once
# and pointed at forty times: the tree stays small and building an animation once
# serves every branch it appears under.
_CAT_DEPTH_MAX = 24
_CAT_SPLIT_MIN = 20        # anims in one node before it is split by .skc subfolder
_CAT_FLAG_VAL  = ("weight", "crossblend")     # flags that consume the next token

def _cat_comments(text):
    """Strip TikiScript comments. Line comments FIRST, block comments second -
    retail tiks carry `//****...` banner lines whose stray `/*` would otherwise
    pair with a later `*/QUAKED` and swallow a whole animations{} block."""
    text = "\n".join(l.split("//", 1)[0] for l in text.splitlines())
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)

def _cat_brace(text, open_idx):
    """Given the index of a '{', return (inner_text, index_of_matching_close)."""
    depth = 0
    for j in range(open_idx, len(text)):
        c = text[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:j], j
    return text[open_idx + 1:], len(text)

def _cat_norm(p):
    return (p or "").replace("\\", "/").strip().strip('"').lstrip("/")

def _cat_join(curpath, token):
    """currentScript->path + token, per tiki_parse.cpp:470-472. An absolute-looking
    token (already rooted at models/) is used as-is: retail files spell both forms."""
    t = _cat_norm(token)
    if not t:
        return t
    if t.lower().startswith("models/") or not curpath:
        return t
    return curpath + t

def _cat_setpath(token):
    """$path/path semantics: store the directory with a guaranteed trailing '/'
    (tiki_script.cpp:415-421)."""
    p = _cat_norm(token)
    if p and not p.endswith("/"):
        p += "/"
    return p

# ---- node helpers ---------------------------------------------------------
def _cat_node(st, name):
    st["nodes"].append({"n": name, "a": [], "k": []})
    return len(st["nodes"]) - 1

def _cat_child(st, parent, name):
    """Fetch-or-create a named child of `parent` (so two `$path` runs writing into
    the same folder branch don't produce two identical menu entries)."""
    for ci in st["nodes"][parent]["k"]:
        if st["nodes"][ci]["n"] == name:
            return ci
    ci = _cat_node(st, name)
    st["nodes"][parent]["k"].append(ci)
    return ci

def _cat_add_anim(st, node, alias, skc, flags, client, server, direct=False):
    """Register one animation, de-duplicated on (alias, resolved .skc). The same
    entry may be listed under many branches; it is stored - and later built - once."""
    key = (alias.lower(), skc.lower())
    ai = st["akey"].get(key)
    if ai is None and direct:
        # An alias the primary .tik lists inline that one of its $include files has
        # already registered is the SAME animation, even when the two spell the path
        # differently (the inline copy resolves against the .tik's own $path). TIKI
        # looks animations up by alias, so alias identity is what counts here - and
        # collapsing them is what stops a .tik that inlines a few hundred of its
        # included aliases from baking all of them into the page a second time.
        ai = st["alias"].get(alias.lower())
    if ai is None:
        ent = {"n": alias, "s": skc}
        if flags:
            ent["f"] = flags
        if direct:
            # declared in the PRIMARY .tik's own animations{} block, and not already
            # claimed by one of its $include files. Only these are baked into the page;
            # everything reached through $include/$path is built on click.
            ent["d"] = 1
        # a stable id keyed on identity, not on menu position: the on-demand build
        # cache next to the HTML stays valid across rebuilds and across models
        ent["id"] = _cache_id(alias + "|" + skc)
        if client:
            ent["c"] = client
        if server:
            ent["v"] = server
        st["anims"].append(ent)
        ai = len(st["anims"]) - 1
        st["akey"][key] = ai
        st["alias"].setdefault(alias.lower(), ai)
    if ai not in st["nodes"][node]["a"]:
        st["nodes"][node]["a"].append(ai)
    return ai

# ---- animations{} body ----------------------------------------------------
def _cat_animations(st, body, node, curpath, depth, direct=False):
    """Walk one animations{} body. Returns the (possibly updated) curpath: a $path
    inside the block is a plain TikiScript command, so it also governs everything
    after the block in the same file."""
    i = 0
    n = len(body)
    while i < n:
        while i < n and body[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        if body[i] == "{":                       # orphan command block: skip balanced
            _, end = _cat_brace(body, i)
            i = end + 1
            continue
        j = body.find("\n", i)
        j = n if j < 0 else j
        line = body[i:j]
        toks = line.split()
        if not toks:
            i = j + 1
            continue
        t0 = toks[0].lower().split("{", 1)[0]
        if t0 in ("$path", "path"):
            if len(toks) > 1:
                curpath = _cat_setpath(toks[1])
            i = j + 1
            continue
        if t0 == "$include":
            if len(toks) > 1:
                _cat_include(st, toks[1], node, depth)
            i = j + 1
            continue
        if t0 == "$mapspec":
            k = body.find("{", i)
            if k < 0:
                break
            names = " ".join(toks[1:]) or "mapspec"
            blk, end = _cat_brace(body, k)
            sub = _cat_child(st, node, "$mapspec: " + names)
            _cat_animations(st, blk, sub, curpath, depth, direct)
            i = end + 1
            continue
        if len(toks) >= 2:
            alias = toks[0]
            skc = _cat_join(curpath, toks[1])
            flags = []
            fi = 2
            while fi < len(toks):
                ft = toks[fi].lower()
                flags.append(toks[fi])
                if ft in _CAT_FLAG_VAL and fi + 1 < len(toks):
                    flags.append(toks[fi + 1])
                    fi += 1
                fi += 1
            i = j + 1
            client = server = None
            k = i                                # optional { client{} server{} }
            while k < n and body[k] in " \t\r\n":
                k += 1
            if k < n and body[k] == "{":
                blk, end = _cat_brace(body, k)
                for ms in re.finditer(r'\b(client|server)\b\s*\{', blk):
                    sb, _ = _cat_brace(blk, ms.end() - 1)
                    txt = "\n".join(x.strip() for x in sb.splitlines() if x.strip())
                    if ms.group(1).lower() == "client":
                        client = txt
                    else:
                        server = txt
                i = end + 1
            if skc.lower().endswith(".skc"):
                _cat_add_anim(st, node, alias, skc, flags, client, server, direct)
            continue
        i = j + 1
    return curpath

# ---- one file / one same-file block --------------------------------------
def _cat_include(st, token, parent, depth):
    """$include: open the referenced file as its own script with a FRESH path
    scope, filed under its own menu branch. The node for a given file is built
    once and re-referenced, so `human_rifle.tik` pulled in by forty mission
    groups costs one subtree."""
    if depth >= _CAT_DEPTH_MAX:
        return
    inc = _cat_norm(token)
    key = inc.lower()
    if not inc:
        return
    disp = inc.split("/")[-1]
    if key in st["fcache"]:                       # already built: reference it
        ci = st["fcache"][key]
        if ci is not None and ci not in st["nodes"][parent]["k"]:
            st["nodes"][parent]["k"].append(ci)
        return
    data = st["vfs"].read(inc) if st["vfs"] is not None else None
    if data is None:
        st["fcache"][key] = None
        st["missing"].append(inc)
        return
    try:
        sub = data.decode("latin-1", "replace")
    except Exception:
        st["fcache"][key] = None
        return
    ci = _cat_node(st, disp)
    st["fcache"][key] = ci                        # cache BEFORE recursing (cycle guard)
    st["nodes"][parent]["k"].append(ci)
    st["files"] += 1
    _cat_scan(st, _cat_comments(sub), ci, "", depth + 1)

def _cat_lastpath(body, curpath):
    """The $path in force after a block has been walked. Used when an animations{}
    body is deferred: its $path lines are ordinary TikiScript commands and still
    govern the rest of the file, so the last one has to carry out of the block."""
    for ln in body.splitlines():
        t = ln.split()
        if t and t[0].lower().lstrip("$") == "path" and len(t) > 1:
            curpath = _cat_setpath(t[1])
    return curpath

def _cat_scan(st, text, node, curpath, depth, deferred=None):
    """Walk one script body (comments already stripped). `curpath` is this
    script's TikiScript::path and is threaded through every same-file block.

    The file's OWN animations{} bodies are deferred to the end of the walk so that
    every $include has already registered its aliases. De-duplication is
    first-wins, so an alias a .tik lists inline AND pulls in through an include is
    kept once, on the include side - which is what stops a model that inlines a
    few hundred of its included aliases from baking all of them into the page."""
    top = deferred is None
    if top:
        deferred = []
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        if text[i] == "{":                        # stray block
            _, end = _cat_brace(text, i)
            i = end + 1
            continue
        j = text.find("\n", i)
        j = n if j < 0 else j
        toks = text[i:j].split()
        if not toks:
            i = j + 1
            continue
        # retail tiks write both `setup\n{` and `setup{`; key off the bare keyword
        t0 = toks[0].lower().split("{", 1)[0]
        if t0 in ("$path", "path"):
            if len(toks) > 1:
                curpath = _cat_setpath(toks[1])
            i = j + 1
            continue
        if t0 == "$include":
            if len(toks) > 1:
                _cat_include(st, toks[1], node, depth)
            i = j + 1
            continue
        if t0 == "animations":
            k = text.find("{", i)
            if k < 0:
                break
            blk, end = _cat_brace(text, k)
            deferred.append((blk, curpath, node, depth))
            curpath = _cat_lastpath(blk, curpath)
            i = end + 1
            continue
        if t0 == "includes":
            k = text.find("{", i)
            if k < 0:
                break
            # names run from the keyword up to the '{' - they may wrap lines
            names = " ".join(text[i + len(t0):k].replace("{", " ").split()) or "?"
            blk, end = _cat_brace(text, k)
            sub = _cat_child(st, node, "includes: " + names)
            # SAME script, so the block shares this file's path scope both ways
            curpath = _cat_scan(st, blk, sub, curpath, depth, deferred)
            i = end + 1
            continue
        if t0 == "setup":
            k = text.find("{", i)
            if k < 0:
                break
            blk, end = _cat_brace(text, k)
            # `path` inside setup{} writes the same TikiScript field
            # (tiki_parse.cpp:1038-1045), so it carries out of the block
            for ln in blk.splitlines():
                st2 = ln.split()
                if st2 and st2[0].lower().lstrip("$") == "path" and len(st2) > 1:
                    curpath = _cat_setpath(st2[1])
            i = end + 1
            continue
        # any other keyword: skip its block if it opens one on/just after this line
        k = text.find("{", i)
        if 0 <= k <= j:
            _, end = _cat_brace(text, k)
            i = end + 1
            continue
        i = j + 1
    if top:
        # every $include has been walked; now this file's own aliases, deduped
        # against them. depth 0 is the primary .tik, whose survivors get baked.
        for blk, cp, nd_i, dp in deferred:
            _cat_animations(st, blk, nd_i, cp, dp, dp == 0)
    return curpath

# ---- post passes ----------------------------------------------------------
def _cat_split(st, node, done=None):
    """A single file can contribute several hundred aliases (new_generic_human.tik
    alone runs to the high hundreds). When a node holds more than _CAT_SPLIT_MIN
    of them and they span more than one .skc folder, break it into one child per
    folder so the submenu stays walkable."""
    if done is None:
        done = set()
    if node in done:
        return
    done.add(node)
    nd = st["nodes"][node]
    for ci in list(nd["k"]):
        _cat_split(st, ci, done)
    if len(nd["a"]) <= _CAT_SPLIT_MIN:
        return
    dirs = {}
    for ai in nd["a"]:
        d = st["anims"][ai]["s"].rsplit("/", 1)[0] if "/" in st["anims"][ai]["s"] else ""
        dirs.setdefault(d, []).append(ai)
    if len(dirs) < 2:
        return
    # name each branch by what is left after the folders' shared prefix
    parts = [d.split("/") for d in dirs]
    common = 0
    while all(len(p) > common + 1 for p in parts) and len({p[common] for p in parts}) == 1:
        common += 1
    kids = []
    for d in sorted(dirs):
        label = "/".join(d.split("/")[common:]) or "(root)"
        ci = _cat_node(st, label + "/")
        st["nodes"][ci]["a"] = dirs[d]
        kids.append(ci)
    nd["k"] = kids + nd["k"]
    nd["a"] = []

def _cat_prune(st, node, done=None):
    """Drop branches that carry nothing. After de-duplication a mission group whose
    every include already appeared under `test utils` collapses to empty; the
    groups that DO add something (lockpick / caught_smoking / plunger) survive."""
    if done is None:
        done = {}
    if node in done:
        return done[node]
    done[node] = True                             # optimistic, for cycles
    nd = st["nodes"][node]
    nd["k"] = [ci for ci in nd["k"] if _cat_prune(st, ci, done)]
    keep = bool(nd["a"] or nd["k"])
    done[node] = keep
    return keep

def _cat_count(st, node, seen=None):
    """Total distinct animations reachable from a node (for the menu's counts)."""
    if seen is None:
        seen = set()
    acc = set()
    stack = [node]
    walked = set()
    while stack:
        x = stack.pop()
        if x in walked:
            continue
        walked.add(x)
        acc.update(st["nodes"][x]["a"])
        stack.extend(st["nodes"][x]["k"])
    return len(acc)

def build_anim_catalog(txt, vfs, self_path=None):
    """Resolve every animation a .tik can reach, through $include chains, per-file
    $path scopes and all `includes <map>{}` groups. Returns

        {"anims":[{n,s,f,id,c,v}, ...],     # unique animations, de-duplicated
         "nodes":[{n,a:[animIdx],k:[nodeIdx]}, ...],
         "root": <node index>,
         "files": <files pulled in>,
         (each anim carries "d":1 when the PRIMARY .tik declares it itself)
         "missing": [unresolved $include paths]}

    Nodes reference each other by index, so a file included by many groups is
    stored once. Nothing is filtered by map name - every group is a branch."""
    st = {"anims": [], "akey": {}, "alias": {}, "nodes": [], "fcache": {}, "vfs": vfs,
          "files": 1, "missing": []}
    root = _cat_node(st, os.path.basename(_cat_norm(self_path) or "model.tik"))
    try:
        _cat_scan(st, _cat_comments(txt or ""), root, "", 0, None)
    except RecursionError:
        pass
    _cat_split(st, root)
    _cat_prune(st, root)
    for i, nd in enumerate(st["nodes"]):
        nd["c"] = _cat_count(st, i)
    return {"anims": st["anims"], "nodes": st["nodes"], "root": root,
            "files": st["files"], "missing": st["missing"]}

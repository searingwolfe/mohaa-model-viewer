#!/usr/bin/env python3
# mohaa_textures.py - resolve and load MOHAA model textures.
#
# Resolution chain (Quake 3 style):
#   .tik    : "surface <name> shader <shadername>"  (a .tik may combine several .skd)
#   .shader : "<shadername> { ... map textures/....tga ... }"
#   texture : textures/....tga|.jpg|.dds inside a pak
#   .skd    : per-vertex (s,t) UVs used to sample the texture
#
# All lookups are case-insensitive because asset names are inconsistent
# (skd "Ranger_pants" vs tik "ranger_pants", "HBTpants.tga" vs "hbtpants").

import io, re, os, base64, hashlib, zipfile

# ----------------------------------------------------------------------------- VFS
class Vfs:
    """Several .pk3 archives merged into one case-insensitive namespace.
    Later paks override earlier ones for the same path (how pak6/7/8 patch the base game)."""
    def __init__(self, pak_paths):
        self.zips=[]; self.index={}     # lower/normalised path -> (zip_idx, real_name)
        self._by_name=None              # image file name minus extension -> [paths], built on first use
        for p in pak_paths:
            try: z=zipfile.ZipFile(p)
            except Exception: continue
            zi=len(self.zips); self.zips.append(z)
            for n in z.namelist():
                if n.endswith("/"): continue
                self.index[n.lower().replace("\\","/")]=(zi,n)
    # Per-entry read limit. A zip header can declare any uncompressed size, so a tiny
    # entry could inflate to gigabytes; reading with a ceiling turns that into a skip.
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
        """Release the pak file handles (a Vfs is rebuilt on every pak reload)."""
        for z in self.zips:
            try: z.close()
            except Exception: pass
        self.zips=[]; self.index={}; self._by_name=None
    def find_texture(self,path):
        """Resolve a texture reference to a stored file, trying the given extension first,
        then the common image extensions."""
        if not path: return None
        p=self._k(path)
        if p in self.index: return p
        base=re.sub(r'\.(tga|jpg|jpeg|dds|png|tif|tiff)$','',p)
        for e in (".tga",".jpg",".jpeg",".dds",".png",".tif",".tiff"):
            if base+e in self.index: return base+e
        return None
    _IMG_EXT=(".tga",".jpg",".jpeg",".dds",".png",".tif",".tiff")
    def find_texture_by_name(self,path):
        """A texture with the same file name as `path` in some other folder, e.g. the
        mapfrance shader's `map textures/models/items/france.tga`, which only exists under
        textures/models/maps/. With several matches, the one sharing the most leading
        folders with `path` wins, then the usual extension order."""
        p=self._k(path)
        if not p: return None
        stem=re.sub(r'\.(tga|jpg|jpeg|dds|png|tif|tiff)$','',p).rsplit("/",1)[-1]
        if self._by_name is None:
            self._by_name={}
            for k in self.index:
                b,dot,ext=k.rpartition(".")
                if dot and "."+ext in self._IMG_EXT:
                    self._by_name.setdefault(b.rsplit("/",1)[-1],[]).append(k)
        cands=self._by_name.get(stem)
        if not cands: return None
        want=p.split("/")[:-1]
        def _rank(k):
            have=k.split("/")[:-1]; n=0
            while n<len(want) and n<len(have) and want[n]==have[n]: n+=1
            return (-n, self._IMG_EXT.index("."+k.rsplit(".",1)[-1]), k)
        return min(cands,key=_rank)
    def pak_of(self,path):
        """File name of the pak a stored path is read from (the last one loaded wins)."""
        e=self.index.get(self._k(path))
        if not e: return ""
        try: return os.path.basename(self.zips[e[0]].filename or "")
        except Exception: return ""

def _cache_id(s):
    """Short stable id for the animation cache (not a security hash).

    md5() raises ValueError on FIPS-mode systems. usedforsecurity=False avoids that but
    needs Python 3.9+, so try it, then plain md5, then blake2s. Using md5 wherever possible
    keeps existing cache ids valid."""
    b = s.encode("utf-8", "replace")
    try: return hashlib.md5(b, usedforsecurity=False).hexdigest()[:12]
    except TypeError:
        try: return hashlib.md5(b).hexdigest()[:12]
        except ValueError: pass
    except ValueError: pass
    return hashlib.blake2s(b, digest_size=6).hexdigest()[:12]

# ------------------------------------------------------------------- shader parsing
# Header of a .shader block: optional whitespace, the shader name, an optional trailing
# // comment, then '{'. Matched with an explicit pos (no slicing) so the scan stays
# linear on large files; the name atom excludes '/' so it cannot compete with the //
# comment branch and backtrack.
_SHADER_HDR=re.compile(r'[ \t\r\n]*([^\s{}/][^\s{}/]*(?:/[^\s{}/]+)*)[ \t]*(?://[^{\n]*)?[ \t\r\n]*\{')

def _is_aux_map(p):
    """True for environment/reflection/specular helper maps that aren't the diffuse."""
    pl=p.lower()
    return ("common/reflection" in pl or "common/env" in pl or "/env/" in pl
            or "reflection" in pl or "specular" in pl or "_spec." in pl or "cubemap" in pl)

def parse_shader_file(txt, editor=None):
    """Return {shadername_lower: diffuse_texture_path} for one .shader script.
    Prefers the first stage map that isn't an environment/reflection/specular helper,
    then qer_editorimage, then any map. If `editor` is a dict, each shader's
    qer_editorimage is also stored in it."""
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
        if editor is not None:
            if qer: editor[name]=qer
            else: editor.pop(name,None)          # a later redefinition without one
        i=j+1
    return out

def build_shader_index(vfs, editor=None):
    """{shader: diffuse path} across all .shader files; `editor` collects the
    qer_editorimage paths (see parse_shader_file)."""
    SH={}
    for k in list(vfs.names()):
        if k.endswith(".shader"):
            try: SH.update(parse_shader_file(vfs.read(k).decode("latin-1","replace"), editor))
            except Exception: pass
    return SH

# ----------------------------------------------------- shader render properties
def _strip_line_comments(s):
    """Drop // end-of-line comments so brace scanning ignores commented-out stages
    (e.g. bangalore_pulsating_ghosting's base stage)."""
    out=[]
    for line in s.splitlines():
        c=line.find("//")
        out.append(line if c<0 else line[:c])
    return "\n".join(out)

def _shader_stages(block):
    """Split a shader's outer { ... } block into its depth-1 stage bodies.
    Comments are stripped first so a commented-out stage is not counted."""
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
    """Find a pulsating overlay stage (e.g. items.shader bangalore_pulsating*): a stage with
    `rgbGen wave <func> <base> <amp> <phase> <freq>` and an additive blendfunc.

    Returns (pulse, basevisible, basefade). pulse is
        {"map":texpath, "wave":[func,base,amp,phase,freq], "distnear":N, "distrange":R}
    or None. basevisible is True when another stage draws a solid/alpha base, as opposed
    to the pulse-only "ghosting" variant. basefade is True when that base stage has its
    own `alphaGen distFade` (bplane_pulse does, bangalore_pulsating doesn't)."""
    pulse=None; basevisible=False; basefade=False
    for st in _shader_stages(block):
        smap=None; wave=None; additive=False; dnear=1024.0; drange=512.0; sawblend=False; fade=False
        for line in st.splitlines():
            ls=line.strip()
            if not ls: continue
            ll=ls.lower(); toks=ll.split()
            mm=re.match(r'(?i)(?:clampmap|map)\s+(\S+)', ls)
            if mm:
                p=mm.group(1)
                # $whiteimage is the engine's built-in white texture, not a file. The healthpack
                # shaders (items.shader firstaid*, healthcanteen, surgeonpack) pulse it with
                # `blendFunc GL_SRC_ALPHA GL_ONE`, so accept it as a pulse map; other $/* maps are ignored.
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
            if re.match(r'(?i)alphagen\s+distfade\b', ls): fade=True
            am=re.match(r'(?i)alphagen\s+distfade\s+([-\d.]+)\s+([-\d.]+)', ls)
            if am:
                try: dnear=float(am.group(1)); drange=float(am.group(2))
                except Exception: pass
        if wave and additive and smap:
            pulse={"map":smap,"wave":wave,"distnear":dnear,"distrange":drange}
        elif smap and not additive:
            basevisible=True            # opaque or alpha-blended base stage
            basefade=basefade or fade
    return pulse, basevisible, basefade

def parse_shader_props_file(txt):
    """Return {shadername_lower: render-hint dict} for one .shader script.

    Covers what the viewer needs to match the in-game look: blending, autosprite/lightglow
    billboards, sprite type and scale, animmap frames+fps, cull mode, alpha test and
    distance fade, pulse overlays, nextbundle detail layers, tcmod rotate and flap deforms.
    Shaders that declare none of these are omitted."""
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
        # sprite_type stays None unless `spritegen` is present (engine default is
        # SPRITE_PARALLEL, tr_shader.c); None means "no orientation declared".
        spritescale=1.0; sawsprite=False; sprite_type=None
        twosided=False; sawcull=False
        _rgbvert=False; _sawrgb=False; _srcalpha=None
        _fade_inv=False; _fade_near=None; _fade_range=None
        _flaps=[]
        for line in block.splitlines():
            ls=line.strip()
            if ls.startswith("//"): continue
            ll=ls.lower()
            # autoSprite and autoSprite2 are separate deforms (tr_shader.c ParseDeform :1837-1845).
            # `autosprite` is set for both (billboard routing, cull exemption); `autosprite2` also
            # marks the long-axis pivot variant (tr_shade_calc.c Autosprite2Deform).
            if ll.startswith("deformvertexes"):
                _dt=ll.split()
                _dv=_dt[1] if len(_dt)>1 else ""
                if _dv=="autosprite": autosprite=True
                elif _dv=="autosprite2": autosprite=True; autosprite2=True
                # lightglow -> DEFORM_LIGHTGLOW (tr_shader.c ParseDeform :1580-1583). LightGlowDeform
                # (tr_shade_calc.c :809-897) rebuilds each quad as a camera-facing square at its
                # midpoint, so it also sets autosprite; `lightglow` enables the viewer's corona handling.
                elif _dv=="lightglow": autosprite=True; lightglow=True
            # `spritegen <type>` marks a sprite shader and resets scale to 1.0; `spritescale <v>`
            # sets it. Quad width = texture width * entity scale * spritescale (tr_sprite.c).
            if ll.startswith("spritegen"):
                sawsprite=True; spritescale=1.0
                # Sprite orientation (tr_sprite.c RB_DrawSprite). Check `parallel_oriented` before
                # `oriented`, which is a substring of it:
                #   parallel_upright  - up = world Z, only yaws toward the camera (:135-160)
                #   parallel_oriented - camera-facing, rotated by the sprite's roll (:64-83)
                #   oriented          - fixed on the entity axes, never faces the camera (:96-99)
                #   parallel          - pure view axes, roll ignored (:84-91)
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
            # `cull none|disable|twosided` or `nocull` draws both faces. The cull_* garment shaders
            # need this for thin two-sided panels, which break up if backface-culled.
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
                # Only the first blendfunc decides how the stage composites; a later detail stage
                # (e.g. water_g's alphaadd highlight) must not turn an alpha sprite additive.
                if not sawblend: additive=is_add; sawblend=True
                # srcalpha: whether the first blend's source factor uses alpha. Plain `add` is
                # GL_ONE GL_ONE (tr_shader.c NameToSrcBlendMode), so alpha/fade/flickeralpha have no
                # visible effect with those shaders in-game (e.g. corona_util, gren_boom).
                if _srcalpha is None:
                    _srcalpha=("alphaadd" in ll
                               or (len(b)>1 and b[1]=="blend")
                               or (len(b)>1 and b[1]=="gl_src_alpha")
                               or (len(b)>1 and b[1]=="gl_one_minus_src_alpha"))
            # rgbGen vertex/exactvertex/entity lets the entity colour (tik `color`) tint the stage;
            # without it the texture draws untinted.
            if ll.startswith("rgbgen"):
                _t2=ll.split()
                if len(_t2)>1 and _t2[1] in ("vertex","exactvertex","entity","oneminusvertex"):
                    _rgbvert=True
                _sawrgb=True
            # deformVertexes flap <s|t> <div> <func> <base> <amp> <phase> <freq> [min] [max]
            # (tr_shader.c ParseDeform :1638-1696): MOHAA's foliage wind. div sets the spread;
            # min/max default to 0 and 1.
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
                # alphaGen [oneMinus][tiki]distFade [near] [range] (tr_shader.c ParseStage :1168-1194).
                # near/range are shader-level values and default to 256.
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
        # Pulsating overlay (e.g. bangalore_pulsating); basevisible separates it from the
        # pulse-only _ghosting variant.
        pulse, basevisible, _basefade = _parse_pulse_and_base(block)
        # Opacity (tr_shader.c FinishShader): opaque unless the first stage blends or a stage
        # alpha-tests. Otherwise the diffuse alpha is a reflection/spec weight for a later stage
        # (tc_coat, facewrap, tc_hat) and must not be treated as coverage.
        _stlist=_shader_stages(block)
        _has_atest=any(re.search(r'(?i)\balpha(func|test)\b', st) for st in _stlist)
        _fb=None
        for _line in (_stlist[0].splitlines() if _stlist else []):
            _l=_line.strip().lower()
            if _l.startswith("blendfunc"): _fb=_l.split()[1:]; break   # first stage only
        _base_opaque=(not _fb) or _fb[:2]==["gl_one","gl_zero"] or _fb[:1]==["opaque"]
        # First-stage alpha test and nextbundle detail layer (emitter sprites).
        #   alphafunc GT0|LT128|GE128 (tr_shader.c NameToAFunc :175-196) is pass/discard. With no
        #   blendfunc (mortar_dirthit, dirtplume) passing pixels are fully opaque and fading
        #   particles erode instead of fading; exported as `atest` only in that case.
        #   nextbundle (tr_shader.c :1841-1853) multiplies a second texture over the first;
        #   exported as `bundle` {map, scale} plus any tcmods.
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
                    # Base-stage `tcmod rotate` (RB_CalcRotateTexCoords, tr_shade_calc.c:1599-1631).
                    # vsssource/vsssource2 counter-rotate base and bundle to get the smoke churn.
                    for _line in _bp[0].splitlines():
                        _l=_line.strip()
                        if _l.startswith("//"): continue
                        _mbr=re.match(r'(?i)tcmod\s+rotate\s+([\-\d.]+)', _l)
                        if _mbr:
                            try:
                                _bundle0["brot"]=float(_mbr.group(1)); break
                            except Exception: pass
                    # Animated bundle tcmods are applied by the viewer at runtime. tcmods run in listed
                    # order: scroll before scale (mortar_dirthit) drifts at the scroll rate in base UV
                    # space, scroll after scale drifts at rate/scale. `prescale` records which.
                    if _bscr and (_bscr[0] or _bscr[1]):
                        _bundle0["scroll"]=list(_bscr)
                        _bundle0["prescale"]=bool(_scr_i is not None and (_sc_i is None or _scr_i<_sc_i))
                    if _brot: _bundle0["rotate"]=_brot
        # Base-stage `tcmod rotate <deg/sec>` (RB_CalcRotateTexCoords, tr_shade_calc.c:1599-1631)
        # spins the texture about (0.5,0.5), e.g. the prop/c47prop propeller discs. Only the part
        # of stage 0 before any nextbundle counts. `clamp` is exported only with a rotate, since
        # clamp vs repeat is invisible on a static clampmap.
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
        # Record any shader with render hints, so emitter sprites can tell an explicit
        # additive=False apart from "no shader info".
        if additive or autosprite or frames or sawblend or sawsprite or pulse or twosided or needs_alpha or _sawrgb or _atest0 or _bundle0 or _texrotate or _flaps:
            rec={"additive":additive,"autosprite":autosprite,"autosprite2":autosprite2,"lightglow":lightglow,"frames":frames,"fps":fps,
                 "spritescale":spritescale,"sprite":sawsprite,"twosided":twosided,"sprite_type":sprite_type,
                 "pulse":pulse,"basevisible":basevisible,"needs_alpha":needs_alpha}
            if _atest0 and _base_opaque: rec["atest"]=_atest0
            if _bundle0: rec["bundle"]=_bundle0
            if _texrotate:
                rec["texrotate"]=_texrotate
                if _clampbase: rec["clamp"]=True
            if _flaps: rec["flap"]=_flaps
            # distfade: inv=False fades out between near and near+range (leaf cards); inv=True
            # fades in over that range (the long-range billboard stand-ins).
            # fDistNear/fDistRange are per shader, so the last distFade sets them for every
            # stage (tr_shader.c ParseStage :1389-1414): bplane_pulse's wire fades at 1024 512
            # like its pulse. A pulse shader's base only fades if its own stage asks for it.
            if _fade_near is not None and (not pulse or _basefade):
                rec["distfade"]={"near":_fade_near,
                                 "range":(_fade_range if _fade_range else 256.0) or 256.0,
                                 "inv":_fade_inv}
            # Only report tint/alpha facts when a blendfunc shows the stage list is real
            # (a bare qer_editorimage stub says nothing).
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
    """Splice $include'd files inline, like the engine's TikiScript parser
    (corepp/tiki_script.cpp ProcessCommand). Some assets (e.g. both grenades) keep their
    whole setup/animations body in a shared _base.txt, so the wrapper .tik parses as empty
    without this. Includes may nest: _chain blocks cycles, _depth caps recursion, and
    _budget caps the total spliced size (24 MB) so a fan-out include graph can't exhaust
    memory."""
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
        if _budget[0]<=0:                       # include graph too large: stop splicing
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
    """True if the texture has a real (non-constant) alpha channel. Decides whether an
    animated nextbundle also modulates the alpha-test pattern or only the RGB grain."""
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
    """256x256 table: LUT[m*256+v] = round(v*255/m). The un-premultiply divide as a
    lookup, so the per-texel loop needs no float math or numpy."""
    global _GL1_LUT
    if _GL1_LUT is None:
        t=bytearray(256*256)
        for m in range(1,256):
            b=m*256
            for v in range(m+1): t[b+v]=(v*255+m//2)//m
        _GL1_LUT=bytes(t)
    return _GL1_LUT

def dataurl_gl_one_additive(durl):
    """Re-encode a sprite so Canvas-2D 'lighter' matches `blendFunc GL_ONE GL_ONE`.

    With a GL_ONE source factor (also `blendfunc add`; tr_shader.c NameToSrcBlendMode) the
    GPU adds every texel's RGB regardless of alpha. Canvas 'lighter' is premultiplied (adds
    rgb*a), so the native alpha would clip the sprite to its alpha footprint (e.g. the
    bh_metal_fastpiece sparks drew at about half size). Forcing alpha to 255 restores the
    light, but 'lighter' also sums alpha, so black texels would paint opaque squares over
    the transparent canvas backdrop.

    Instead, move the intensity into alpha and pre-divide RGB by it:
        A'   = max(R,G,B)
        RGB' = RGB * 255 / A'   (pure black -> fully transparent)
    Canvas then adds RGB' * A'/255 == RGB, and black texels add no alpha.
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
                d[i]=0; d[i+1]=0; d[i+2]=0; d[i+3]=0     # black: no colour, no coverage
            else:
                k=m<<8
                d[i]=L[k|r]; d[i+1]=L[k|g]; d[i+2]=L[k|b]; d[i+3]=m
        buf=io.BytesIO(); Image.frombytes("RGBA",im.size,bytes(d)).save(buf,"PNG")
        return "data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return durl                                       # keep the original on any failure

def texture_to_dataurl(vfs, texpath, max_dim=512, emitter_clean=False, keep_alpha=False, bundle_path=None, bundle_scale=(1.0,1.0)):
    """Load a stored texture and return a data: URL for the browser.

    jpg/png pass through; tga/dds are decoded with Pillow and re-encoded.
    emitter_clean: for additive emitter sprites. Always PNG, with near-black keyed to
        transparent, so JPEG noise doesn't add up to a visible box behind the glow.
    keep_alpha: keep the alpha channel instead of flattening to opaque JPEG.
    bundle_path/bundle_scale: bake a nextbundle detail layer into the image."""
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
            # Bake the nextbundle layer (GL_MODULATE, tr_shader.c:1841-1853): multiply by the detail
            # texture tiled `tcmod scale` times. Animated tcmods are baked at phase 0. RGB-only when
            # the base has no alpha, so the alpha synthesis below still applies.
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
            # Give emitter sprites a transparent background so they composite cleanly in any blend
            # mode. On failure, fall through to the normal encoding so the texture still loads.
            try:
                from PIL import ImageChops
                TH=18
                if not has_alpha:
                    rgb=im.convert("RGB"); r,g,b=rgb.split()
                    mx=ImageChops.lighter(ImageChops.lighter(r,g),b)   # per-pixel max(r,g,b)
                    # No alpha channel: derive alpha from brightness. Below TH -> 0 (no background box under
                    # additive blending), then a smooth ramp to 255 by 64. A hard cutoff made the dirt
                    # sprites (mortar_dirthit) look dithered.
                    def _a(v):
                        if v<TH: return 0
                        return 255 if v>=64 else int((v-TH)*255/(64-TH))
                    alpha=mx.point(_a)
                    rgb.putalpha(alpha); im=rgb
                else:
                    # Real alpha channel: keep its soft gradient (mist, dust, smoke) and only zero the
                    # near-transparent fringe (< ~10%) so the edges don't haze. A steeper alpha test turned
                    # soft sprites like `mist` into blocky patches.
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
        # Model surfaces are opaque unless the base stage blends or alpha-tests
        # (tr_shader.c FinishShader); otherwise the diffuse alpha is a reflection/spec weight
        # (tc_coat, facewrap), so drop it.
        im=im.convert("RGB"); buf=io.BytesIO(); im.save(buf,"JPEG",quality=86)
        return "data:image/jpeg;base64,"+base64.b64encode(buf.getvalue()).decode()
    except Exception:
        # Last resort: embed browser-native bytes as-is so the texture still appears.
        try:
            if ext in ("jpg","jpeg"): return "data:image/jpeg;base64,"+base64.b64encode(data).decode()
            if ext=="png": return "data:image/png;base64,"+base64.b64encode(data).decode()
        except Exception: pass
        return None

def build_global_surface_shaders(tik_index):
    """Most common shader for each exact surface name across all tiks. A last-resort skin
    for surfaces like 'head'/'hand' on composite models with no sibling defining them."""
    from collections import Counter
    cnt={}
    for pairs in tik_index.values():
        for s,sh in pairs:
            if "*" in s or s=="all": continue
            cnt.setdefault(s,Counter())[sh]+=1
    return {s:c.most_common(1)[0][0] for s,c in cnt.items()}

def resolve_surface_texmap(skd_relpath, surface_names, vfs, shader_index, tik_index, global_surf=None,
                           editor_index=None, misses=None):
    """Like resolve_surface_textures but returns {surface_lower: (texpath, shadername)}
    so callers can also look up per-surface shader render properties.

    When a shader's map isn't in the paks, the engine fails to load the stage
    (tr_shader.c ParseStage :925-932), so in-game the pulse_map* models show no texture.
    Here the shader's qer_editorimage, then a texture of the same file name elsewhere in
    the paks, stands in. `misses`, if a dict, gets
    {surface: (shader, missing_path, found_path_or_None, "editor"|"name"|"surface"|None)}."""
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
        sl=s.lower(); tex=None; miss=None; via=None
        shader=shader_for(sl)
        if shader:
            mp=shader_index.get(shader.lower())
            tex=vfs.find_texture(mp) if mp else None
            if tex is None: tex=vfs.find_texture(shader)
            if tex is None and mp:
                miss=(shader, mp)
                qer=(editor_index or {}).get(shader.lower())
                if qer and qer.lower()!=mp.lower():
                    tex=vfs.find_texture(qer); via="editor"
                if tex is None:
                    tex=vfs.find_texture_by_name(mp); via="name"
        if tex is None:                        # surface name itself may be a shader/texture
            mp=shader_index.get(sl)
            tex=vfs.find_texture(mp) if mp else vfs.find_texture(sl)
            if mp and shader is None: shader=sl
            via="surface"
        if miss and misses is not None: misses[sl]=miss+(tex, via if tex else None)
        res[sl]=(tex, shader)
    return res

def resolve_surface_textures(skd_relpath, surface_names, vfs, shader_index, tik_index, global_surf=None):
    """Map each .skd surface name to a stored texture path."""
    return {s:t for s,(t,sh) in resolve_surface_texmap(
        skd_relpath, surface_names, vfs, shader_index, tik_index, global_surf).items()}

def _solid_white_dataurl():
    """4x4 opaque white PNG data URL standing in for the engine's built-in `$whiteimage`
    (no file on disk). Used as the pulse overlay for the healthpack shaders. Built with
    zlib/struct so it doesn't depend on Pillow."""
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

def _translucent(durl, props):
    """True for a base that blends with its own alpha (barbwire's `blendFunc blend`), as
    opposed to an opaque or alpha-tested one. Only a PNG kept its alpha channel."""
    return bool(props and props.get("needs_alpha") and not props.get("atest")
                and not props.get("additive") and durl.startswith("data:image/png"))

# ------------------------------------------------------------------- convenience
def write_textures_manifest(vfs, skd_relpath, surface_names, shader_index, tik_index,
                            out_path, max_dim=512, global_surf=None, shader_props=None,
                            anim_max_dim=128, anim_max_frames=32, editor_index=None, log=None):
    """Resolve a .skd's surfaces to textures, embed them as data URLs, and write a
    {surface_name: entry} JSON manifest for mohaa_view.py --textures.

    An entry is a plain data-URL string for a simple opaque surface, or an object
    {"tex": url, ...} carrying the shader's render hints (additive, autosprite, frames/fps,
    twosided, texrotate, distfade, atest, flap, pulse, ...). Returns (n_textured, n_surfaces).

    log(kind, text), if given, reports shader maps missing from the paks: "warn" (red) for
    the miss, "note" (yellow) for the stand-in found by resolve_surface_texmap."""
    import json
    misses={}
    tm=resolve_surface_texmap(skd_relpath, surface_names, vfs, shader_index, tik_index, global_surf,
                              editor_index=editor_index, misses=misses)
    man={}; framecache={}
    for s in surface_names:
        tp, sh = tm.get(s.lower(), (None,None))
        props=(shader_props or {}).get((sh or "").lower())
        # Pulsating overlay (bangalore_pulsating / _ghosting): the base diffuse is encoded
        # opaque (not black-keyed) and the pulse stage is carried separately for the viewer to
        # animate. _ghosting has no visible base.
        pulse=props.get("pulse") if props else None
        if pulse:
            entry={}
            if props.get("basevisible") and tp:
                # A blended base (bplane_pulse's barbed wire) keeps its alpha like the plain
                # shader does; an opaque one (bangalore_pulsating) is encoded solid.
                bdu=texture_to_dataurl(vfs, tp, max_dim=max_dim, emitter_clean=False,
                                       keep_alpha=bool(props.get("needs_alpha")))
                if bdu:
                    entry["tex"]=bdu
                    for k in ("twosided","distfade","atest"):
                        if props.get(k): entry[k]=props[k]
                    if _translucent(bdu,props): entry["blend"]=True
            if str(pulse["map"]).lower() in ("$whiteimage","$white"):
                pdu=_solid_white_dataurl()   # engine $whiteimage: solid white glow
            else:
                ptp=vfs.find_texture(pulse["map"])
                pdu=texture_to_dataurl(vfs, ptp, max_dim=max_dim, emitter_clean=True) if ptp else None
            if pdu:
                entry["pulse"]={"tex":pdu,"wave":pulse["wave"],
                                "distnear":pulse["distnear"],"distrange":pulse["distrange"]}
            if entry: man[s]=entry
            continue
        if not tp:
            # animmap-only shader (e.g. bh_wood_puff.tik opened directly) has no map/clampmap, so
            # use the first animmap frame as the base instead of leaving the quad untextured.
            if props and props.get("frames"):
                tp=vfs.find_texture(props["frames"][0])
            if not tp: continue
        # Effect surfaces (additive, autosprite, frame-animated) get a transparent background so
        # they draw without a black box; ordinary opaque surfaces keep the plain encoding.
        eff=bool(props and (props["additive"] or props["autosprite"] or props["frames"]))
        # Texture rotation (propeller discs) and clamp flag, carried on whichever entry shape
        # the surface ends up as.
        texrot=props.get("texrotate") if props else None
        clampf=bool(props and props.get("clamp"))
        dfade=props.get("distfade") if props else None
        # Keep the diffuse alpha only when the shader uses it as coverage (alpha test or a
        # translucent base); opaque garment/face shaders (tc_coat, facewrap) render solid.
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
            # Plain surface: a bare data-URL string, promoted to an object only when it carries
            # extra hints (two-sided cull, tcmod rotate, distfade, alpha test, flap).
            extra={}
            if props and props.get("twosided"): extra["twosided"]=True
            if texrot: extra["texrotate"]=texrot
            if clampf: extra["clamp"]=True
            if dfade: extra["distfade"]=dfade
            # alphaFunc on an opaque base means alpha-tested, not blended (tr_shader.c:1129-1146);
            # the viewer needs the threshold to reproduce the hard cutout.
            if props and props.get("atest"): extra["atest"]=props["atest"]
            if props and props.get("flap"): extra["flap"]=props["flap"]
            if _translucent(du,props): extra["blend"]=True
            if extra: extra["tex"]=du; man[s]=extra
            else: man[s]=du
    # Only misses that still produced an entry are reported here: a stand-in was found, or
    # the surface draws just its pulse stage. A surface left out of the manifest is reported
    # by the launcher's untextured-surface check instead.
    if log:
        for s in surface_names:
            m=misses.get(s.lower())
            if not m or s not in man: continue
            sh,mp,found,via=m
            log("warn","MISSING ASSET  surface '%s'  ->  shader '%s' maps '%s', which isn't in any "
                       "of the loaded .pk3 files." % (s, sh, mp))
            if found:
                src={"editor":"the shader's qer_editorimage","name":"same file name"}.get(via,"named after the surface")
                pak=vfs.pak_of(found)
                log("note","  Found '%s' elsewhere in the loaded paks and loaded it from %s (%s%s)."
                    % (mp.replace("\\","/").rsplit("/",1)[-1], found, src, ", "+pak if pak else ""))
    with open(out_path,"w",encoding="utf-8") as f: json.dump(man,f)
    return len(man), len(surface_names)

# ===========================================================================
# TIKI ANIMATION CATALOG - $include / $path / includes{} resolution
# ===========================================================================
# Character .tiks rarely list their own animations: allied_pilot.tik sets
# `path models/human/protoanimations` and then `$include`s new_generic_human.tik, and
# the player models include base/include.txt, which pulls in twelve anims_*.txt files.
# The TikiScript rules followed here:
#
#   $path <dir>      Sets THIS script's path, adding a trailing '/'
#                    (corepp/tiki_script.cpp:414-421). `path` inside setup{} writes
#                    the same field (tiki/tiki_parse.cpp:1038-1045).
#
#   $include <file>  Opens a child script with an empty path (tiki_script.cpp:50,
#                    398-412), so each file resolves anims against its own $path.
#
#   <alias> <file>   The .skc path is the innermost script's path + token
#                    (tiki_parse.cpp:470-472). Flags follow on the same line
#                    (tiki_parse.cpp:240): weight/crossblend take a value, the rest
#                    (deltadriven, default_angles, notimecheck, ...) are bare.
#
#   includes <names>{...}
#                    Active only when a name prefix-matches sv_mapname, which is
#                    "utils" with no map loaded (tiki_parse.cpp:320-341). The viewer
#                    has no map, so it walks every group, each under its own branch.
#
#   $mapspec <names>{...}
#                    The same map gate inside animations{} (tiki_parse.cpp:415-447),
#                    walked the same way.
#
# The result is a node tree plus one de-duplicated animation table. Nodes reference
# anims by index, so a file included by forty groups is stored and built only once.
_CAT_DEPTH_MAX = 24
_CAT_SPLIT_MIN = 20        # anims in one node before it is split by .skc subfolder
_CAT_FLAG_VAL  = ("weight", "crossblend")     # flags that consume the next token

def _cat_comments(text):
    """Strip TikiScript comments. Line comments go first: retail tiks have `//****`
    banner lines whose `/*` would otherwise pair with a later `*/` and swallow a block."""
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
    """Register one animation, de-duplicated on (alias, resolved .skc). An entry can be
    listed under many branches but is stored, and later built, only once."""
    key = (alias.lower(), skc.lower())
    ai = st["akey"].get(key)
    if ai is None and direct:
        # An alias listed inline in the primary .tik that an $include already registered is
        # the same animation (TIKI looks anims up by alias), even if its path is spelled
        # differently. Merging them avoids baking hundreds of duplicates into the page.
        ai = st["alias"].get(alias.lower())
    if ai is None:
        ent = {"n": alias, "s": skc}
        if flags:
            ent["f"] = flags
        if direct:
            # Declared directly in the primary .tik (not via $include): baked into the page.
            # Everything reached through $include/$path is built on demand.
            ent["d"] = 1
        # Stable id from identity rather than menu position, so the on-demand build cache
        # survives rebuilds and is shared across models.
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
    """$include: open the file as its own script with a fresh path scope, under its own
    menu branch. Each file's node is built once and re-referenced by later includes."""
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
    """The $path in force after a deferred animations{} body. Its $path lines are ordinary
    commands, so the last one still governs the rest of the file."""
    for ln in body.splitlines():
        t = ln.split()
        if t and t[0].lower().lstrip("$") == "path" and len(t) > 1:
            curpath = _cat_setpath(t[1])
    return curpath

def _cat_scan(st, text, node, curpath, depth, deferred=None):
    """Walk one script body (comments already stripped). `curpath` is this script's
    TikiScript path, threaded through every same-file block.

    The file's own animations{} bodies are deferred until every $include has registered
    its aliases. De-duplication is first-wins, so an alias that is both inlined and
    included is kept once, on the include side, and isn't baked into the page."""
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
    """Split a node with more than _CAT_SPLIT_MIN aliases spanning several .skc folders
    into one child per folder, so large submenus (e.g. new_generic_human.tik) stay usable."""
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
    """Drop empty branches. After de-duplication, a mission group whose includes all
    appeared under `test utils` is empty; groups that add something survive."""
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
    """Resolve every animation a .tik can reach through $include chains, per-file $path
    scopes and all `includes <map>{}` groups. Returns

        {"anims":   [{n,s,f,id,c,v,d}, ...],   # unique animations; d=1 when the primary
                                                # .tik declares it itself
         "nodes":   [{n,a:[animIdx],k:[nodeIdx],c}, ...],
         "root":    <node index>,
         "files":   <number of files read>,
         "missing": [unresolved $include paths]}

    Nodes reference each other by index, so a file included by many groups is stored
    once. Nothing is filtered by map name; every group becomes a branch."""
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

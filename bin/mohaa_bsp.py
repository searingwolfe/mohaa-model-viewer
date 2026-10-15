#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
#  mohaa_bsp.py  --  read compiled MOHAA maps (.bsp) and turn them back into .map
#
#  Reads Allied Assault (version 17-19, ident "2015") and Spearhead / Breakthrough
#  (version 20-21, ident "EALA") .bsp files and writes MOHRadiant-style .map source:
#  every brush rebuilt from its planes, curved patches, LOD terrain, static models
#  and all entities.
#
#  A compiled map keeps its brushes only as plane lists, so each face's texture
#  alignment is recovered from the matching draw surface (the textured polygon the
#  game renders), giving the real shift / rotation / scale instead of a default.
#
#  The approach follows wfowler1's BSP Decompiler (LibBSP); the file layout follows
#  OpenMoHAA (qcommon/qfiles.h, qcommon/cm_load.c, renderergl1/tr_bsp.c).
#
#  Command line:  python mohaa_bsp.py <map.bsp> [out.map]
# ==============================================================================
import math, os, re, struct, sys

# ------------------------------------------------------------------------------
#  File layout
# ------------------------------------------------------------------------------
# Lump numbers (qfiles.h). Version 18 and older carry an extra fog lump after the
# brushes, so every lump past LUMP_BRUSHES moves up one slot there.
LUMP_SHADERS, LUMP_PLANES, LUMP_LIGHTMAPS, LUMP_SURFACES = 0, 1, 2, 3
LUMP_DRAWVERTS, LUMP_DRAWINDEXES, LUMP_LEAFBRUSHES, LUMP_LEAFSURFACES = 4, 5, 6, 7
LUMP_LEAFS, LUMP_NODES, LUMP_SIDEEQUATIONS, LUMP_BRUSHSIDES = 8, 9, 10, 11
LUMP_BRUSHES, LUMP_MODELS, LUMP_ENTITIES, LUMP_VISIBILITY = 12, 13, 14, 15
LUMP_LIGHTGRIDPALETTE, LUMP_LIGHTGRIDOFFSETS, LUMP_LIGHTGRIDDATA = 16, 17, 18
LUMP_TERRAIN, LUMP_TERRAININDEXES = 22, 23
LUMP_STATICMODELDATA, LUMP_STATICMODELDEF, LUMP_STATICMODELINDEXES = 24, 25, 26
HEADER_LUMPS = 28

# Draw surface types (mapSurfaceType_t)
MST_BAD, MST_PLANAR, MST_PATCH, MST_TRIANGLE_SOUP, MST_FLARE, MST_TERRAIN = range(6)

# A few content / surface bits used here (qcommon/surfaceflags.h)
CONTENTS_ORIGIN = 0x1000000
CONTENTS_DETAIL = 0x8000000
SURF_SKY = 0x4
SURF_NODRAW = 0x80

# Lightmaps are 128 x 128 RGB pages (tr_bsp.c LIGHTMAP_SIZE).
LIGHTMAP_SIZE = 128

# cTerraPatch_t flags (qfiles.h)
TERPATCH_FLIP = 0x40
TERPATCH_NEIGHBOR = 0x80

# q3map writes at most 300 sides per brush (MAX_BUILD_SIDES); a count far past that
# means a damaged file, and rebuilding such a brush would take forever.
MAX_BRUSH_SIDES = 1024

# Largest coordinate a brush can reach; base windings start this big and are
# cut down by the brush's other planes.
MAX_WORLD_COORD = 16384.0
BOGUS_RANGE = MAX_WORLD_COORD * 4

# First line of every .map this decompiler writes. The viewer looks for it so the only
# .map files it ever replaces or deletes are ones it wrote, never a mapper's own source.
DECOMPILE_TAG = "// MOHAA map source rebuilt from "


class BspError(Exception):
    """The file is not a .bsp this module can read, or its header is damaged."""


def is_decompiled_map(path):
    """True if the .map at path was written by this decompiler."""
    try:
        with open(path, "rb") as f:
            return f.read(len(DECOMPILE_TAG)).decode("latin-1") == DECOMPILE_TAG
    except OSError:
        return False


def output_map_path(folder, stem):
    """Where the decompiled <stem>.map goes. A .map of that name that this program didn't
    write (the mapper's source sitting next to the .bsp) is left alone, and the decompile
    goes to <stem>_decompiled.map instead (then _decompiled2, _decompiled3...)."""
    path = os.path.join(folder, stem + ".map")
    n = 1
    while os.path.exists(path) and not is_decompiled_map(path):
        path = os.path.join(folder, "%s_decompiled%s.map" % (stem, "" if n == 1 else n))
        n += 1
    return path


def _cstr(b):
    """A NUL-terminated byte string from a fixed-size field."""
    return b.split(b"\0", 1)[0].decode("latin-1", "replace")


class Bsp:
    """The parts of a .bsp the decompiler and viewer need, already unpacked."""

    def __init__(self, data, name="map.bsp"):
        # The header holds 28 lump entries (29 in versions 17-18, which have an extra
        # fog lump); 29 are always read, so the file must be at least that long.
        if len(data) < 12 + 8 * (HEADER_LUMPS + 1):
            raise BspError("%s is too small to be a .bsp file" % name)
        self.name = name
        self.ident = data[:4]
        self.version, self.checksum = struct.unpack_from("<ii", data, 4)
        if self.ident not in (b"2015", b"EALA"):
            raise BspError("%s is not a MOHAA .bsp (ident %r)" % (name, self.ident))
        if not (17 <= self.version <= 21):
            raise BspError("%s has unsupported .bsp version %d" % (name, self.version))
        self._data = data
        self._lumps = [struct.unpack_from("<ii", data, 12 + 8 * i) for i in range(HEADER_LUMPS + 1)]

        self.shaders = []
        for rec in self._records(LUMP_SHADERS, 140):
            self.shaders.append({
                "name": _cstr(rec[:64]),
                "surface": struct.unpack_from("<i", rec, 64)[0],
                "contents": struct.unpack_from("<i", rec, 68)[0],
                "subdivisions": struct.unpack_from("<i", rec, 72)[0],
                "fencemask": _cstr(rec[76:140]),
            })
        self.planes = list(struct.iter_unpack("<4f", self.lump(LUMP_PLANES)))
        self.surfaces = []
        for t in struct.iter_unpack("<12i3f9f2if", self._trim(LUMP_SURFACES, 108)):
            self.surfaces.append({
                "shader": t[0], "type": t[2], "firstVert": t[3], "numVerts": t[4],
                "firstIndex": t[5], "numIndexes": t[6], "lightmapNum": t[7],
                "patchWidth": t[24], "patchHeight": t[25], "subdivisions": t[26],
            })
        self._verts = self._trim(LUMP_DRAWVERTS, 44)
        self.num_verts = len(self._verts) // 44
        self.indexes = [v[0] for v in struct.iter_unpack("<i", self._trim(LUMP_DRAWINDEXES, 4))]
        self.sideeqs = list(struct.iter_unpack("<8f", self._trim(LUMP_SIDEEQUATIONS, 32)))
        self.brushsides = list(struct.iter_unpack("<3i", self._trim(LUMP_BRUSHSIDES, 12)))
        self.brushes = list(struct.iter_unpack("<3i", self._trim(LUMP_BRUSHES, 12)))
        self.models = []
        for t in struct.iter_unpack("<6f4i", self._trim(LUMP_MODELS, 40)):
            self.models.append({"mins": t[0:3], "maxs": t[3:6], "firstSurface": t[6],
                                "numSurfaces": t[7], "firstBrush": t[8], "numBrushes": t[9]})
        self.entity_text = self.lump(LUMP_ENTITIES).split(b"\0", 1)[0].decode("latin-1", "replace")
        self.terrain = [self._terra_patch(rec) for rec in self._records(LUMP_TERRAIN, 388)]
        self.static_models = []
        if self.version > 17:
            for rec in self._records(LUMP_STATICMODELDEF, 164):
                self.static_models.append({
                    "model": _cstr(rec[:128]),
                    "origin": struct.unpack_from("<3f", rec, 128),
                    "angles": struct.unpack_from("<3f", rec, 140),
                    "scale": struct.unpack_from("<f", rec, 152)[0],
                    # where its baked vertex lighting starts in the static model data lump
                    # (a byte offset into the RGB triples) and how many vertices it covers
                    "firstVertexData": struct.unpack_from("<i", rec, 156)[0],
                    "numVertexData": struct.unpack_from("<h", rec, 160)[0],
                })

    # ---- raw lump access -------------------------------------------------
    def lump(self, num):
        """Bytes of a lump, honouring the older layout's shifted lump numbers."""
        if self.version <= 18 and num > LUMP_BRUSHES:
            num += 1
        ofs, length = self._lumps[num]
        if ofs < 0 or length < 0 or ofs + length > len(self._data):
            raise BspError("%s: lump %d lies outside the file" % (self.name, num))
        return self._data[ofs:ofs + length]

    def _trim(self, num, size):
        """A lump cut to a whole number of `size`-byte records."""
        b = self.lump(num)
        return b[:len(b) - len(b) % size]

    def _records(self, num, size):
        """A lump split into `size`-byte records."""
        b = self._trim(num, size)
        return [b[i:i + size] for i in range(0, len(b), size)]

    def vert(self, i):
        """(xyz, st) of draw vertex i."""
        x, y, z, s, t = struct.unpack_from("<5f", self._verts, i * 44)
        return (x, y, z), (s, t)

    def vert_normal(self, i):
        """The normal of draw vertex i."""
        return struct.unpack_from("<3f", self._verts, i * 44 + 28)

    def vert_light(self, i):
        """(lightmap s, t) and the raw RGBA vertex light of draw vertex i."""
        ls, lt = struct.unpack_from("<2f", self._verts, i * 44 + 20)
        o = i * 44 + 40
        return (ls, lt), tuple(self._verts[o:o + 4])

    def lightmap_count(self):
        """How many 128 x 128 lightmap pages the file holds."""
        return len(self.lump(LUMP_LIGHTMAPS)) // (LIGHTMAP_SIZE * LIGHTMAP_SIZE * 3)

    @staticmethod
    def _terra_patch(rec):
        """One cTerraPatch_t (qfiles.h): a 9x9 heightmap on a 512-unit square."""
        flags, lmscale, ls, lt = struct.unpack_from("<4B", rec, 0)
        tc = struct.unpack_from("<8f", rec, 4)
        x, y = struct.unpack_from("<2b", rec, 36)
        base, shader, lightmap = struct.unpack_from("<hHH", rec, 38)
        var = struct.unpack_from("<126H", rec, 52)            # (bytes 44-51: neighbour links)
        hmap = struct.unpack_from("<81B", rec, 304)
        return {"flags": flags, "texCoord": [[(tc[0], tc[1]), (tc[2], tc[3])],
                                             [(tc[4], tc[5]), (tc[6], tc[7])]],
                "x": x, "y": y, "base": base, "shader": shader,
                "var": (var[:63], var[63:]), "height": hmap,
                # lightmap page and placement: the patch's corner texel and texels per 64 units
                "lightmap": lightmap, "ls": ls, "lt": lt, "lmscale": lmscale}

    def shader_name(self, num):
        """Shader name by number; caulk for a number past the shader lump."""
        if 0 <= num < len(self.shaders):
            return self.shaders[num]["name"]
        return "textures/common/caulk"


# ------------------------------------------------------------------------------
#  Entity string
# ------------------------------------------------------------------------------
_TOKEN = re.compile(r'"([^"]*)"|(//[^\n]*)|([{}])|(\S+)')


def parse_entity_string(text):
    """Entities from a .bsp entity lump as lists of (key, value) pairs, in file order.
    Repeated keys are kept, since a few spawn keys may legally repeat."""
    ents = []
    cur = None
    key = None
    for m in _TOKEN.finditer(text or ""):
        q, comment, brace, bare = m.groups()
        if comment is not None:
            continue
        if brace == "{":
            cur = []
            key = None
        elif brace == "}":
            if cur is not None:
                ents.append(cur)
            cur = None
        elif cur is not None:
            tok = q if q is not None else bare
            if key is None:
                key = tok
            else:
                cur.append((key, tok))
                key = None
    return ents


def ent_get(pairs, key, default=""):
    """The first value of a key in an entity's (key, value) pairs, ignoring case."""
    kl = key.lower()
    for k, v in pairs:
        if k.lower() == kl:
            return v
    return default


def parse_vec(s, n=3):
    """n numbers from a space-separated string such as "0 0 64", or None."""
    try:
        v = [float(x) for x in str(s).split()[:n]]
    except ValueError:
        return None
    return v if len(v) == n else None


# ------------------------------------------------------------------------------
#  Brush geometry: planes -> face polygons (shared with the map builder)
# ------------------------------------------------------------------------------
def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(v):
    L = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if L < 1e-12:
        return None
    return (v[0] / L, v[1] / L, v[2] / L)


def base_winding(normal, dist):
    """A huge square lying on the plane, wound clockwise seen from the front
    (BaseWindingForPlane in q3map's polylib.c)."""
    ax = max(range(3), key=lambda i: abs(normal[i]))
    vup = (0.0, 0.0, 1.0) if ax in (0, 1) else (1.0, 0.0, 0.0)
    d = _dot(vup, normal)
    vup = _norm((vup[0] - d * normal[0], vup[1] - d * normal[1], vup[2] - d * normal[2]))
    if vup is None:
        return []
    org = (normal[0] * dist, normal[1] * dist, normal[2] * dist)
    vr = _cross(vup, normal)
    R = BOGUS_RANGE
    vu = (vup[0] * R, vup[1] * R, vup[2] * R)
    vr = (vr[0] * R, vr[1] * R, vr[2] * R)
    return [(org[0] - vr[0] + vu[0], org[1] - vr[1] + vu[1], org[2] - vr[2] + vu[2]),
            (org[0] + vr[0] + vu[0], org[1] + vr[1] + vu[1], org[2] + vr[2] + vu[2]),
            (org[0] + vr[0] - vu[0], org[1] + vr[1] - vu[1], org[2] + vr[2] - vu[2]),
            (org[0] - vr[0] - vu[0], org[1] - vr[1] - vu[1], org[2] - vr[2] - vu[2])]


def clip_winding(w, normal, dist, eps=0.01):
    """Keep the part of polygon `w` behind the plane (dot(n,p) <= dist). Points within
    eps of the plane count as on it and are kept (ChopWindingInPlace, polylib.c)."""
    if not w:
        return w
    dists = [_dot(p, normal) - dist for p in w]
    if not any(d > eps for d in dists):
        return w
    if not any(d < -eps for d in dists):
        return []
    out = []
    n = len(w)
    for i in range(n):
        p1 = w[i]
        d1 = dists[i]
        if d1 <= eps:
            out.append(p1)
        d2 = dists[(i + 1) % n]
        if (d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps):
            p2 = w[(i + 1) % n]
            t = d1 / (d1 - d2)
            out.append((p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]),
                        p1[2] + t * (p2[2] - p1[2])))
    return out


def winding_area(w):
    """Area of a planar polygon."""
    if len(w) < 3:
        return 0.0
    ax = ay = az = 0.0
    p0 = w[0]
    for i in range(1, len(w) - 1):
        c = _cross(_sub(w[i], p0), _sub(w[i + 1], p0))
        ax += c[0]
        ay += c[1]
        az += c[2]
    return 0.5 * math.sqrt(ax * ax + ay * ay + az * az)


def brush_windings(planes, eps=0.01):
    """Face polygons of a convex brush given as (normal, dist) planes facing out.
    A side whose polygon is cut away completely (bevel planes the compiler adds for
    collision, duplicate or inverted planes) comes back as an empty list."""
    out = []
    for i, (n, d) in enumerate(planes):
        w = base_winding(n, d)
        for j, (n2, d2) in enumerate(planes):
            if j == i or not w:
                continue
            if _dot(n, n2) > 0.999999 and abs(d - d2) < 0.001:
                if j < i:
                    w = []           # a duplicate plane: only the first copy gets the face
                continue
            w = clip_winding(w, n2, d2, eps)
        out.append(w)
    return out


def plane_from_points(p0, p1, p2):
    """MapPlaneFromPoints (q3map map.c): normal = cross(p0-p1, p2-p1)."""
    n = _norm(_cross(_sub(p0, p1), _sub(p2, p1)))
    if n is None:
        return None
    return n, _dot(p0, n)


# ------------------------------------------------------------------------------
#  Texture projection (q3map map.c TextureAxisFromPlane / QuakeTextureVecs)
# ------------------------------------------------------------------------------
BASE_AXIS = (
    ((0, 0, 1), (1, 0, 0), (0, -1, 0)),     # floor
    ((0, 0, -1), (1, 0, 0), (0, -1, 0)),    # ceiling
    ((1, 0, 0), (0, 1, 0), (0, 0, -1)),     # west wall
    ((-1, 0, 0), (0, 1, 0), (0, 0, -1)),    # east wall
    ((0, 1, 0), (1, 0, 0), (0, 0, -1)),     # south wall
    ((0, -1, 0), (1, 0, 0), (0, 0, -1)),    # north wall
)


def texture_axis(normal):
    """The two world axes a face's texture is projected along (TextureAxisFromPlane):
    those of the floor, ceiling or wall whose normal is closest to the face's."""
    best = 0.0
    bi = 0
    for i, ax in enumerate(BASE_AXIS):
        d = _dot(normal, ax[0])
        if d > best:
            best = d
            bi = i
    return BASE_AXIS[bi][1], BASE_AXIS[bi][2]


def quake_texture_vecs(normal, shift, rotate, scale):
    """World-to-texture vectors (pixel units) for an old-style .map texdef:
    s = dot(p, v[0][:3]) + v[0][3], t = dot(p, v[1][:3]) + v[1][3]."""
    xv, yv = texture_axis(normal)
    vecs = [list(xv), list(yv)]
    sx = scale[0] or 1.0
    sy = scale[1] or 1.0
    if rotate == 0:
        s, c = 0.0, 1.0
    elif rotate == 90:
        s, c = 1.0, 0.0
    elif rotate == 180:
        s, c = 0.0, -1.0
    elif rotate == 270:
        s, c = -1.0, 0.0
    else:
        a = rotate / 180.0 * math.pi
        s, c = math.sin(a), math.cos(a)
    sv = 0 if vecs[0][0] else (1 if vecs[0][1] else 2)
    tv = 0 if vecs[1][0] else (1 if vecs[1][1] else 2)
    for v in vecs:
        ns = c * v[sv] - s * v[tv]
        nt = s * v[sv] + c * v[tv]
        v[sv] = ns
        v[tv] = nt
    return ([vecs[0][0] / sx, vecs[0][1] / sx, vecs[0][2] / sx, shift[0]],
            [vecs[1][0] / sy, vecs[1][1] / sy, vecs[1][2] / sy, shift[1]])


def _lstsq3(rows, vals):
    """Least squares a,b,c for vals ~ a*u + b*v + c over rows of (u, v)."""
    n = len(rows)
    su = sv = suu = svv = suv = 0.0
    sz = szu = szv = 0.0
    for (u, v), z in zip(rows, vals):
        su += u
        sv += v
        suu += u * u
        svv += v * v
        suv += u * v
        sz += z
        szu += z * u
        szv += z * v
    M = ((suu, suv, su), (suv, svv, sv), (su, sv, float(n)))
    r = (szu, szv, sz)
    det = (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1])
           - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
           + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))
    if abs(det) < 1e-9:
        return None

    def col(k):
        m = [list(row) for row in M]
        for i in range(3):
            m[i][k] = r[i]
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    return col(0) / det, col(1) / det, col(2) / det


def _neat(v, places=4):
    """A number rounded for a .map file, snapping near-integers."""
    r = round(v)
    if abs(v - r) < 10 ** -places:
        return int(r)
    return round(v, places)


def fit_texdef(normal, pts, sts, tex_w, tex_h):
    """Recover an old-style texdef (shift, rotate, scale) from points on a face and
    their normalized texture coordinates. Inverts quake_texture_vecs: the texture
    vectors only use the two world axes TextureAxisFromPlane picks, so a 2D affine
    fit in those axes gives them directly. Returns None if the points don't fit."""
    xv, yv = texture_axis(normal)
    sv = 0 if xv[0] else (1 if xv[1] else 2)
    tv = 0 if yv[0] else (1 if yv[1] else 2)
    rows = [(p[sv], p[tv]) for p in pts]
    fs = _lstsq3(rows, [st[0] * tex_w for st in sts])
    ft = _lstsq3(rows, [st[1] * tex_h for st in sts])
    if fs is None or ft is None:
        return None
    if not all(math.isfinite(v) for v in fs + ft):
        return None
    a1, a2, a0 = fs
    b1, b2, b0 = ft
    r = math.hypot(a1, a2)
    if r < 1e-9:
        return None
    # xv is always +1 on its axis and yv always -1 on its axis (BASE_AXIS), so
    # a = (cos, sin) / scale_x and b = (sin, -cos) / scale_y.
    ang = math.atan2(a2, a1)
    sx = 1.0 / r
    s, c = math.sin(ang), math.cos(ang)
    q = b1 * s - b2 * c
    if abs(q) < 1e-9:
        return None
    sy = 1.0 / q
    # Values are kept as fitted, float noise included: the level designer's own texdefs
    # carry the same noise (MOHRadiant's texture lock), and rounding them would let the
    # texture drift on large faces.
    rot = math.degrees(ang) % 360.0
    if abs(rot - 360.0) < 1e-4:
        rot = 0.0
    sh0 = a0 % tex_w if tex_w else a0
    sh1 = b0 % tex_h if tex_h else b0
    if tex_w and abs(sh0 - tex_w) < 1e-3:
        sh0 = 0.0
    if tex_h and abs(sh1 - tex_h) < 1e-3:
        sh1 = 0.0
    return (_neat(sh0, 3), _neat(sh1, 3)), _neat(rot, 3), (_neat(sx, 6), _neat(sy, 6))


# ------------------------------------------------------------------------------
#  Terrain holes (qcommon/cm_terrain.c): which of the two triangles in each of a
#  patch's 8x8 squares the level designer cut away. The engine stores this in
#  the patch's variance trees; the table below maps square triangles to tree
#  nodes, following CM_PrepareGenerateTerrainCollide.
# ------------------------------------------------------------------------------
_VNI = None


def _terrain_vni():
    """vni[diagonal][i][j] = ((tree, node), (tree, node)): the variance tree node that
    holds the hole bit of each of square (i, j)'s two triangles, for both diagonal
    layouts (built once, as CM_PrepareGenerateTerrainCollide does)."""
    global _VNI
    if _VNI is not None:
        return _VNI
    vni = [[[[(0, 0), (0, 0)] for _ in range(8)] for _ in range(8)] for _ in range(2)]

    # CM_CalculateTerrainIndices: split one root triangle (corners i0 j0, i1 j1, i2 j2)
    # down to its 32 leaves (node n's children are 2n and 2n+1), then record for each
    # half-square a leaf covers its tree, the flag bit that cuts it away, and the node.
    def calc(start, diag, tree):
        wn = [None] * 64
        wn[1] = list(start)
        for i in range(31):
            a = wn[i + 1]
            i2 = a[0] + a[2]
            j2 = a[1] + a[3]
            wn[i * 2 + 2] = [a[2], a[3], a[4], a[5], i2 >> 1, j2 >> 1]
            wn[i * 2 + 3] = [a[4], a[5], a[0], a[1], i2 >> 1, j2 >> 1]
        for i in range(32, 64):
            a = wn[i]
            i2 = (a[0] + a[2]) >> 1
            j2 = (a[1] + a[3]) >> 1
            def put(ii, jj, k, mask):
                if 0 <= ii < 8 and 0 <= jj < 8:
                    vni[diag][ii][jj][k] = (tree | mask, i - 1)
            if a[0] == a[2]:
                if a[1] <= a[3]:
                    put(i2, j2, 1, 0x2000)
                    put(i2, j2 - 1, 0, 0x1000)
                else:
                    put(i2 - 1, j2, 1, 0x1000)
                    put(i2 - 1, j2 - 1, 0, 0x2000)
            else:
                if a[0] <= a[2]:
                    put(i2, j2 - 1, 0, 0x2000)
                    put(i2 - 1, j2 - 1, 0, 0x1000)
                else:
                    put(i2, j2, 1, 0x1000)
                    put(i2 - 1, j2, 1, 0x2000)

    calc((8, 8, 0, 0, 0, 8), 0, 0)
    calc((0, 0, 8, 8, 8, 0), 0, 1)
    calc((8, 0, 0, 8, 8, 8), 1, 0)
    calc((0, 8, 8, 0, 0, 0), 1, 1)
    _VNI = vni
    return vni


def terrain_holes(patch):
    """{(i, j): (hole_on_+x_triangle, hole_on_-x_triangle)} for the patch's cut-away
    triangles, (i, j) being the square's lowest corner. Squares alternate their diagonal
    in a checkerboard (CM_GenerateTerrainCollide); the "+x" triangle is the one on the
    square's +x edge, and a terrainDef's two "( nodraw )" groups per vertex follow the
    same order."""
    vni = _terrain_vni()[1 if patch["flags"] & TERPATCH_NEIGHBOR else 0]
    var = patch["var"]
    out = {}
    for i in range(8):
        for j in range(8):
            v0, v1 = vni[i][j]
            # h0 / h1: the collision code's plane[0] / plane[1] triangle is cut away
            h0 = bool(v0[0] & var[v0[0] & 1][v0[1]] & 0xFFFE) if v0[1] < 63 else False
            h1 = bool(v1[0] & var[v1[0] & 1][v1[1]] & 0xFFFE) if v1[1] < 63 else False
            if h0 or h1:
                # plane[0] is the +x triangle on odd squares and the -x one on even ones
                out[(i, j)] = (h0, h1) if (i + j) & 1 else (h1, h0)
    return out


# ------------------------------------------------------------------------------
#  Decompiler
# ------------------------------------------------------------------------------
def _fmt(v):
    """A coordinate for the .map file: integers stay plain, the rest keep enough
    digits to reproduce the plane. NaN or infinity (a damaged file) is written as 0."""
    if not math.isfinite(v):
        return "0"
    r = round(v)
    if abs(v - r) < 0.0005:
        return "%d" % r
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


class _PlanarIndex:
    """Planar draw surfaces grouped by shader and plane, and by where they lie, so each
    brush side can find the polygons the game draws for it and read their texture
    coordinates."""

    CELL = 256.0

    def __init__(self, bsp, first, count):
        self.by_key = {}
        self.cells = {}          # (shader, cell x, y, z) -> surfaces whose middle is there
        self.names = set()
        self.surfs = []          # (surface number, normal, centre, shader) for _assign_owners
        self._global = {}
        for si in range(first, first + count):
            s = bsp.surfaces[si]
            if s["type"] != MST_PLANAR or s["numVerts"] < 3:
                continue
            pts = []
            sts = []
            for k in range(s["numVerts"]):
                p, st = bsp.vert(s["firstVert"] + k)
                pts.append(p)
                sts.append(st)
            # The face normal comes from the surface's largest triangle. Vertex normals can't
            # be trusted for this: surfaces with smoothed shading carry bent normals. Their
            # side of the plane is still right, so they settle which way the face points.
            n = None
            best = 0.0
            idx = bsp.indexes[s["firstIndex"]:s["firstIndex"] + s["numIndexes"]]
            for t in range(0, min(len(idx), 60) - 2, 3):
                a, b, c = (pts[idx[t]] if 0 <= idx[t] < len(pts) else None,
                           pts[idx[t + 1]] if 0 <= idx[t + 1] < len(pts) else None,
                           pts[idx[t + 2]] if 0 <= idx[t + 2] < len(pts) else None)
                if a is None or b is None or c is None:
                    continue
                cr = _cross(_sub(c, a), _sub(b, a))
                area = _dot(cr, cr)
                if area > best:
                    best = area
                    n = cr
            n = _norm(n) if n is not None else None
            vn = _norm(bsp.vert_normal(s["firstVert"]))
            if n is None:
                n = vn
            elif vn is not None and _dot(n, vn) < 0:
                n = (-n[0], -n[1], -n[2])
            if n is None:
                continue
            d = _dot(n, pts[0])
            name = bsp.shader_name(s["shader"]).lower()
            cen = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts),
                   sum(p[2] for p in pts) / len(pts))
            if not all(math.isfinite(v) for v in n + cen):
                continue                                    # damaged vertices
            key = (name, round(n[0], 1), round(n[1], 1), round(n[2], 1))
            rec = (n, d, cen, pts, sts, si)
            self.by_key.setdefault(key, []).append(rec)
            cell = (name, int(math.floor(cen[0] / self.CELL)), int(math.floor(cen[1] / self.CELL)),
                    int(math.floor(cen[2] / self.CELL)))
            self.cells.setdefault(cell, []).append(rec)
            self.names.add(name)
            self.surfs.append((si, n, cen, name))

    def inside(self, name, n, d, w):
        """The surfaces on the face's plane whose middle lies inside its polygon w."""
        if name not in self.names or not w:
            return []
        mins = [min(p[i] for p in w) - 1.0 for i in range(3)]
        maxs = [max(p[i] for p in w) + 1.0 for i in range(3)]
        lo = [int(math.floor(mins[i] / self.CELL)) for i in range(3)]
        hi = [int(math.floor(maxs[i] / self.CELL)) for i in range(3)]
        if (hi[0] - lo[0] + 1) * (hi[1] - lo[1] + 1) * (hi[2] - lo[2] + 1) > len(self.cells):
            # A face spanning more cells than there are filled ones (a huge sky face, or
            # an unclosed brush in a damaged file): walk the filled cells instead, in the
            # same order.
            keys = sorted(k for k in self.cells if k[0] == name and lo[0] <= k[1] <= hi[0]
                          and lo[1] <= k[2] <= hi[1] and lo[2] <= k[3] <= hi[2])
        else:
            keys = [(name, cx, cy, cz) for cx in range(lo[0], hi[0] + 1)
                    for cy in range(lo[1], hi[1] + 1) for cz in range(lo[2], hi[2] + 1)]
        return [rec for k in keys for rec in self.cells.get(k, ())
                if _dot(rec[0], n) > 0.999 and abs(_dot(rec[2], n) - d) < 0.5
                and _point_in_winding(rec[2], w, n)]

    def candidates(self, name, n, d, key=None):
        """Every surface on the face's plane, wherever it lies (cached per key)."""
        if name not in self.names:
            return []
        if key is not None and key in self._global:
            return self._global[key]
        out = []
        base = (round(n[0], 1), round(n[1], 1), round(n[2], 1))
        seen = set()
        for dx in (0, -0.1, 0.1):
            for dy in (0, -0.1, 0.1):
                for dz in (0, -0.1, 0.1):
                    key = (name, round(base[0] + dx, 1), round(base[1] + dy, 1), round(base[2] + dz, 1))
                    if key in seen:
                        continue
                    seen.add(key)
                    for rec in self.by_key.get(key, ()):
                        # Compiled vertices are snapped to a small grid, which tilts the
                        # plane of a small polygon a little, so the test is how far the
                        # polygon's middle lies from the brush face's own plane.
                        if _dot(rec[0], n) > 0.999 and abs(_dot(rec[2], n) - d) < 0.5:
                            out.append(rec)
        if key is not None:
            self._global[key] = out
        return out


def _point_in_winding(p, w, n, eps=0.5):
    """Is p (on the face plane) inside the convex polygon w (clockwise from front)?"""
    m = len(w)
    for i in range(m):
        a = w[i]
        b = w[(i + 1) % m]
        e = _sub(b, a)
        # for a clockwise winding the inside lies to the right of every edge
        c = _cross(e, _sub(p, a))
        if _dot(c, n) > eps * math.sqrt(_dot(e, e)):
            return False
    return True


def _assign_owners(pidx, origin, face_recs, ei, owners):
    """Which written brush face each of a model's drawn polygons belongs to, so the
    viewer can show and hide the game's own polygons along with their brushes. Most
    were matched while the faces were written; this places the rest (a polygon whose
    middle lies just outside its face) on the nearest face of the same plane.
    face_recs: (normal, dist, winding, shader, face number, brush number) in world
    space. owners[surface] = (entity, brush number, face number), or (entity, -1, -1)
    when no face matches (the polygon then follows its entity only)."""
    left = [s for s in pidx.surfs if s[0] not in owners]
    if not left:
        return
    by = {}
    for fr in face_recs:
        n = fr[0]
        by.setdefault((fr[3], round(n[0], 1), round(n[1], 1), round(n[2], 1)), []).append(fr)
    for si, n, cen, name in left:
        c = (cen[0] + origin[0], cen[1] + origin[1], cen[2] + origin[2])
        base = (round(n[0], 1), round(n[1], 1), round(n[2], 1))
        best = None
        fallback = None
        seen = set()
        for dx in (0, -0.1, 0.1):
            for dy in (0, -0.1, 0.1):
                for dz in (0, -0.1, 0.1):
                    key = (name, round(base[0] + dx, 1), round(base[1] + dy, 1), round(base[2] + dz, 1))
                    if key in seen or key not in by:
                        continue
                    seen.add(key)
                    for fr in by[key]:
                        if _dot(fr[0], n) < 0.999 or abs(_dot(fr[0], c) - fr[1]) > 1.0:
                            continue
                        if _point_in_winding(c, fr[2], fr[0], 1.0):
                            best = fr
                            break
                        if fallback is None:
                            fallback = fr
                    if best:
                        break
                if best:
                    break
            if best:
                break
        best = best or fallback
        owners[si] = (ei, best[5], best[4]) if best else (ei, -1, -1)


def _origin_brush(o):
    """A 16-unit common/origin cube around o, as written by MOHRadiant."""
    x, y, z = o
    h = 8
    faces = [((x - h, y - h, z + h), (x - h, y + h, z + h), (x + h, y + h, z + h)),   # top
             ((x + h, y + h, z - h), (x - h, y + h, z - h), (x - h, y - h, z - h)),   # bottom
             ((x + h, y - h, z + h), (x + h, y + h, z + h), (x + h, y + h, z - h)),   # +x
             ((x - h, y + h, z + h), (x - h, y - h, z + h), (x - h, y - h, z - h)),   # -x
             ((x + h, y + h, z + h), (x - h, y + h, z + h), (x - h, y + h, z - h)),   # +y
             ((x - h, y - h, z + h), (x + h, y - h, z + h), (x + h, y - h, z - h))]   # -y
    lines = ["{"]
    for p0, p1, p2 in faces:
        lines.append("( %s ) ( %s ) ( %s ) common/origin 0 0 0 0.5 0.5 %d 0 0"
                     % (" ".join(_fmt(c) for c in p0), " ".join(_fmt(c) for c in p1),
                        " ".join(_fmt(c) for c in p2), CONTENTS_ORIGIN))
    lines.append("}")
    return lines


def decompile(bsp, tex_size=None, static_classname=None, log=None):
    """Rebuild .map source text from a parsed Bsp.

    tex_size(shader) -> (width, height): the texture size q3map used when it
        computed texture coordinates (the shader's qer_editorimage, else the image
        named after the shader). Without it, 256x256 is assumed, which still gives
        correct alignment in this viewer but odd scales in MOHRadiant.
    static_classname(model_path) -> classname for a static model, normally read
        from the /*QUAKED ... */ header of its .tik; "static_<name>" otherwise.
    log(text): progress messages.
    Returns (map_text, stats)."""
    say = log or (lambda *_: None)
    ents = parse_entity_string(bsp.entity_text)
    if not ents or ent_get(ents[0], "classname").lower() != "worldspawn":
        ents.insert(0, [("classname", "worldspawn")])
    size_cache = {}

    # Texture size for the brush-side texture maths; 256 x 256 when it isn't known.
    def tsize(shader):
        k = shader.lower()
        if k not in size_cache:
            wh = None
            if tex_size is not None:
                try:
                    wh = tex_size(shader)
                except Exception:
                    wh = None
            if not wh or not wh[0] or not wh[1]:
                wh = (256, 256)
            size_cache[k] = (int(wh[0]), int(wh[1]))
        return size_cache[k]

    owner = {0: 0}
    for ei, e in enumerate(ents):
        m = ent_get(e, "model")
        if m.startswith("*"):
            try:
                owner[int(m[1:])] = ei
            except ValueError:
                pass
    by_ent = {}
    for mi, ei in owner.items():
        if 0 <= mi < len(bsp.models):
            by_ent.setdefault(ei, []).append(mi)

    stats = {"brushes": 0, "faces": 0, "aligned": 0, "patches": 0, "terrain": len(bsp.terrain),
             "static": len(bsp.static_models), "entities": len(ents), "soups": 0, "dropped": 0,
             # entity number -> the exact (mins, maxs) of its brush model around its
             # origin: the box the game itself uses for that entity (triggers, doors...)
             "bounds": {}, "first_static": len(ents),
             # for the viewer's in-game lighting: which brush face / patch / terrain block
             # each draw surface and terrain patch was written as
             "owners": {}, "patch_owner": {}, "terrain_owner": [],
             # brush model number -> (entity number, origin its surfaces are stored around)
             "models": {}}
    for ei, mis in by_ent.items():
        for mi in mis:
            if mi > 0:
                mdl = bsp.models[mi]
                stats["bounds"][ei] = (tuple(mdl["mins"]), tuple(mdl["maxs"]))
                break
    out = [DECOMPILE_TAG + "%s (.bsp version %d)" % (os.path.basename(bsp.name), bsp.version),
           "// by MOHAA Map Viewer's built-in decompiler. Texture alignment comes from the",
           "// compiled draw surfaces; faces the game never draws keep a default alignment."]
    for ei, e in enumerate(ents):
        out.append("// entity %d" % ei)
        out.append("{")
        cls = ent_get(e, "classname").lower()
        for k, v in e:
            if k.lower() == "model" and v.startswith("*"):
                continue           # brush model number: the brushes are written inline below
            out.append('"%s" "%s"' % (k, v.replace('"', "'")))
        origin = (0.0, 0.0, 0.0)
        models = by_ent.get(ei, [])
        if any(mi > 0 for mi in models):
            o = parse_vec(ent_get(e, "origin"))
            if o:
                origin = tuple(o)
        bn = 0
        for mi in models:
            mdl = bsp.models[mi]
            stats["models"][mi] = (ei, origin)
            pidx = _PlanarIndex(bsp, mdl["firstSurface"], mdl["numSurfaces"])
            face_recs = []
            for b in range(mdl["firstBrush"], mdl["firstBrush"] + mdl["numBrushes"]):
                written = []
                lines = _brush_lines(bsp, b, origin, pidx, tsize, stats, written)
                if lines:
                    for fr in written:
                        for si in fr[5]:
                            stats["owners"].setdefault(si, (ei, bn, fr[4]))
                        face_recs.append(fr[:5] + (bn,))
                    out.append("// brush %d" % bn)
                    out.extend(lines)
                    bn += 1
            for si in range(mdl["firstSurface"], mdl["firstSurface"] + mdl["numSurfaces"]):
                s = bsp.surfaces[si]
                if s["type"] == MST_PATCH:
                    stats["patch_owner"][si] = (ei, bn)
                    out.append("// brush %d" % bn)
                    out.extend(_patch_lines(bsp, s, origin))
                    stats["patches"] += 1
                    bn += 1
                elif s["type"] == MST_TRIANGLE_SOUP:
                    stats["soups"] += 1
            _assign_owners(pidx, origin, face_recs, ei, stats["owners"])
        if ei == 0:
            for tp in bsp.terrain:
                stats["terrain_owner"].append(bn)
                out.append("// brush %d" % bn)
                out.extend(_terrain_lines(bsp, tp, tsize))
                bn += 1
        # The compiler gives every brush entity an origin: an origin brush's centre,
        # else the centre of its brushes. Only the first kind needs an origin brush
        # in the source (a door's hinge, say); the second is recreated on compile.
        if origin != (0.0, 0.0, 0.0) and bn and cls != "worldspawn":
            mdl = bsp.models[[mi for mi in models if mi > 0][0]]
            off = [abs((mdl["mins"][k] + mdl["maxs"][k]) * 0.5) for k in range(3)]
            if max(off) > 1.5:
                out.append("// brush %d" % bn)
                out.extend(_origin_brush(origin))
        out.append("}")
    for k, sm in enumerate(bsp.static_models):
        path = sm["model"]
        cls = None
        if static_classname is not None:
            try:
                cls = static_classname(path)
            except Exception:
                cls = None
        if not cls:
            stem = os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]
            cls = "static_" + stem
        out.append("// entity %d" % (len(ents) + k))
        out.append("{")
        out.append('"classname" "%s"' % cls)
        out.append('"model" "%s"' % path)
        out.append('"origin" "%s"' % " ".join(_fmt(c) for c in sm["origin"]))
        a = sm["angles"]
        if any(abs(x) > 1e-6 for x in a):
            out.append('"angles" "%s"' % " ".join(_fmt(c) for c in a))
        if abs(sm["scale"] - 1.0) > 1e-6:
            out.append('"scale" "%s"' % _fmt(sm["scale"]))
        out.append("}")
    stats["entities"] = len(ents) + len(bsp.static_models)
    say("decompiled: %d brushes (%d of %d faces aligned from draw surfaces), %d patches, "
        "%d terrain patches, %d static models, %d entities"
        % (stats["brushes"], stats["aligned"], stats["faces"], stats["patches"], stats["terrain"],
           stats["static"], stats["entities"]))
    return "\n".join(out) + "\n", stats


def _brush_lines(bsp, b, origin, pidx, tsize, stats, written=None):
    """The .map lines of brush b (None if too few faces survive). written, if given,
    collects (normal, dist, winding, shader, face number, drawn surfaces inside it) for
    each face written."""
    first, num, bshader = bsp.brushes[b]
    if not 0 < num <= MAX_BRUSH_SIDES:
        return None
    sides = bsp.brushsides[first:first + num]
    planes = []
    for pn, sh, eq in sides:
        nx, ny, nz, d = bsp.planes[pn]
        n = (nx, ny, nz)
        # brushes of an entity with an origin are stored around (0,0,0); move them back
        planes.append((n, d + _dot(n, origin)))
        if not all(math.isfinite(v) for v in n + (planes[-1][1],)):
            return None                                     # damaged plane
    wins = brush_windings(planes)
    lines = ["{"]
    nfaces = 0
    detail = bool(bsp.shaders[bshader]["contents"] & CONTENTS_DETAIL) if 0 <= bshader < len(bsp.shaders) else False
    for (pn, sh, eq), (n, d), w in zip(sides, planes, wins):
        if len(w) < 3 or winding_area(w) < 0.01:
            stats["dropped"] += 1
            continue
        shader = bsp.shader_name(sh)
        sname = shader[9:] if shader.lower().startswith("textures/") else shader
        rec = bsp.shaders[sh] if 0 <= sh < len(bsp.shaders) else {"contents": 0, "surface": 0}
        tw, th = tsize(shader)
        texdef = None
        # The draw surfaces of a brush model are stored around the entity's origin, so
        # the face is matched there. Their texture coordinates were worked out in world
        # space, before the move (checked against EA's own map sources), so the fit
        # uses world positions and gives back the texdef as the level designer wrote it.
        d_loc = d - _dot(n, origin)
        w_loc = [(p[0] - origin[0], p[1] - origin[1], p[2] - origin[2]) for p in w]
        # The polygons drawn inside this face give its alignment; a face the game never
        # draws (hidden against another brush) borrows it from any polygon on its plane.
        inside = pidx.inside(shader.lower(), n, d_loc, w_loc)
        pick = inside[0] if inside else None
        if pick is None:
            cands = pidx.candidates(shader.lower(), n, d_loc, (sh, pn))
            if cands:
                pick = cands[0]
        sky = bool(rec["surface"] & SURF_SKY)
        if sky:
            # A sky polygon's texture coordinates aren't the face's projection (each one
            # is laid out on its own), so nothing can be fitted from them. EA's sources
            # give every sky face "0 0 0 1 1"; so does this.
            texdef = ((0, 0), 0, (1, 1))
        elif pick is not None:
            pts = [(p[0] + origin[0], p[1] + origin[1], p[2] + origin[2]) for p in pick[3]]
            texdef = fit_texdef(n, pts, pick[4], tw, th)
        if texdef is None and not sky and eq and 0 <= eq < len(bsp.sideeqs):
            # Fence-mask faces also carry an exact texture equation. The collision code
            # evaluates it in the model's own space, so it is applied to the local
            # corners and the result fitted against the world ones.
            se = bsp.sideeqs[eq]
            sts = [(_dot(p, se[0:3]) + se[3], _dot(p, se[4:7]) + se[7]) for p in w_loc[:6]]
            texdef = fit_texdef(n, w[:6], sts, tw, th)
        if texdef is None:
            shift, rot, scale = (0, 0), 0, (0.5, 0.5)
        else:
            shift, rot, scale = texdef
            if not sky:
                stats["aligned"] += 1
        # three corners of the face, in the order q3map reads back as this plane
        p0, p1, p2 = _three_points(w) or (w[0], w[1], w[2])
        cont = rec["contents"]
        if detail:
            cont |= CONTENTS_DETAIL
        line = "( %s ) ( %s ) ( %s ) %s %s %s %s %s %s %d %d 0" % (
            " ".join(_fmt(c) for c in p0), " ".join(_fmt(c) for c in p1), " ".join(_fmt(c) for c in p2),
            sname, _fmt(shift[0]), _fmt(shift[1]), _fmt(rot), _fmt(scale[0]), _fmt(scale[1]),
            cont, rec["surface"])
        if detail:
            line += " +surfaceparm detail"
        lines.append(line)
        if written is not None:
            written.append((n, d, w, shader.lower(), nfaces, [r[5] for r in inside]))
        nfaces += 1
    if nfaces < 4:
        return None
    stats["brushes"] += 1
    stats["faces"] += nfaces
    lines.append("}")
    return lines


def _three_points(w):
    """Three well-spread corners of a clockwise winding, kept in winding order so
    plane_from_points gives back the outward normal."""
    m = len(w)
    best = None
    besta = -1.0
    step = max(1, m // 3)
    for i in range(m):
        a, b, c = w[i], w[(i + step) % m], w[(i + 2 * step) % m]
        ar = _dot(_cross(_sub(a, b), _sub(c, b)), _cross(_sub(a, b), _sub(c, b)))
        if ar > besta:
            besta = ar
            best = (a, b, c)
    return best


def _patch_lines(bsp, s, origin):
    """The .map lines of a patch draw surface: a patchDef2 with its control points."""
    w = s["patchWidth"]
    h = s["patchHeight"]
    shader = bsp.shader_name(s["shader"])
    sname = shader[9:] if shader.lower().startswith("textures/") else shader
    rec = bsp.shaders[s["shader"]] if 0 <= s["shader"] < len(bsp.shaders) else {"contents": 0, "surface": 0}
    lines = [" {", "  patchDef2", "  {", "   " + sname,
             "   ( %d %d %d %d 0 )" % (w, h, rec["contents"], rec["surface"]), "("]
    for j in range(w):
        row = []
        for i in range(h):
            p, st = bsp.vert(s["firstVert"] + i * w + j)
            row.append("( %s %s %s %s %s )" % (_fmt(p[0] + origin[0]), _fmt(p[1] + origin[1]),
                                               _fmt(p[2] + origin[2]), _fmt(st[0]), _fmt(st[1])))
        lines.append("( " + " ".join(row) + " )")
    lines += [")", "  }", " }"]
    return lines


def _terrain_lines(bsp, tp, tsize):
    """The .map lines of a terrain patch: a 9 x 9 terrainDef with its texture, heights
    and holes."""
    shader = bsp.shader_name(tp["shader"])
    sname = shader[9:] if shader.lower().startswith("textures/") else shader
    x0 = tp["x"] * 64.0
    y0 = tp["y"] * 64.0
    z0 = float(tp["base"])
    tw, th = tsize(shader)
    tc = tp["texCoord"]
    # Terrain texture coordinates run from the terrainDef's own origin, not the
    # world origin, so the fit uses corner positions relative to the patch.
    corners = [(0.0, 0.0, 0.0), (0.0, 512.0, 0.0), (512.0, 0.0, 0.0), (512.0, 512.0, 0.0)]
    sts = [tc[0][0], tc[0][1], tc[1][0], tc[1][1]]
    texdef = fit_texdef((0.0, 0.0, 1.0), corners, sts, tw, th)
    if texdef is None:
        texdef = ((0, 0), 0, (1, 1))
    (sh0, sh1), rot, (sx, sy) = texdef
    td = "( %s %s %s %s %d %s %s 0 0 0 )" % (sname, _fmt(sh0), _fmt(sh1), _fmt(rot), tw, _fmt(sx), _fmt(sy))
    holes = terrain_holes(tp)
    lines = [" {", "  terrainDef", "  {", "   9 9 0",
             "   %s %s %s" % ("%.6f" % x0, "%.6f" % y0, "%.6f" % z0), "\t\t{"]
    for _ in range(4):
        lines.append("\t\t\t0 0 " + td)
    lines.append("\t\t}")
    lines.append("\t\t{")
    hm = tp["height"]
    for j in range(9):
        for i in range(9):
            h1, h2 = holes.get((i, j), (False, False))
            lines.append("\t\t\t%.6f ( %s) ( %s)" % (hm[j * 9 + i] * 2.0, "nodraw " if h1 else "",
                                                     "nodraw " if h2 else ""))
    lines += ["\t\t}", "  }", " }"]
    return lines


# ------------------------------------------------------------------------------
#  In-game lighting: lightmaps, vertex light, static model light, the light grid
# ------------------------------------------------------------------------------
# The game brightens all baked light by one bit (r_mapOverBrightBits 1, r_overBrightBits
# 0 in renderergl1/tr_init.c, so tr.overbrightShift = 1 in R_SetColorMappings). A colour
# pushed past 255 is scaled down as a whole to keep its hue, not clipped per channel.
OVERBRIGHT_SHIFT = 1

_DOUBLE = bytes(min(255, v << OVERBRIGHT_SHIFT) for v in range(256))
_HIGH = bytes(1 if (v << OVERBRIGHT_SHIFT) > 255 else 0 for v in range(256))


def color_shift(raw, stride=3):
    """Lightmap texels or vertex colours brightened the way R_ColorShiftLightingBytes
    (tr_bsp.c) does it. raw holds RGB (stride 3) or RGBA (stride 4) bytes; alpha is kept."""
    out = bytearray(raw.translate(_DOUBLE))
    if stride == 4:
        out[3::4] = raw[3::4]
    mask = raw.translate(_HIGH)
    if stride == 4:
        mask = bytearray(mask)
        mask[3::4] = b"\0" * len(mask[3::4])
        mask = bytes(mask)
    i = mask.find(1)
    while i >= 0:
        t = i - i % stride
        r, g, b = raw[t] << OVERBRIGHT_SHIFT, raw[t + 1] << OVERBRIGHT_SHIFT, raw[t + 2] << OVERBRIGHT_SHIFT
        m = max(r, g, b)
        out[t] = r * 255 // m
        out[t + 1] = g * 255 // m
        out[t + 2] = b * 255 // m
        i = mask.find(1, t + stride)
    return bytes(out)


def static_model_light(bsp):
    """The baked vertex light of every static model, brightened as R_InitStaticModels
    (tr_staticmodels.cpp) does it, as RGB triples."""
    raw = bsp.lump(LUMP_STATICMODELDATA) if bsp.version > 17 else b""
    raw = raw[:len(raw) - len(raw) % 3]
    out = bytearray(raw.translate(_DOUBLE))
    mask = raw.translate(_HIGH)
    i = mask.find(1)
    while i >= 0:
        t = i - i % 3
        r, g, b = raw[t] * 2.0, raw[t + 1] * 2.0, raw[t + 2] * 2.0
        f = 255.0 / max(r, g, b)
        out[t], out[t + 1], out[t + 2] = int(r * f), int(g * f), int(b * f)
        i = mask.find(1, t + 3)
    return bytes(out)


class LightGrid:
    """The light grid that lights entity models: one colour per grid point, run-length
    packed in columns along z (R_LoadLightGrid in tr_bsp.c, R_GetLightingGridValue in
    tr_light.c)."""

    def __init__(self, bsp):
        self.ok = False
        try:
            pal = bsp.lump(LUMP_LIGHTGRIDPALETTE)
            offs = bsp.lump(LUMP_LIGHTGRIDOFFSETS)
            data = bsp.lump(LUMP_LIGHTGRIDDATA)
        except BspError:
            return
        if not pal or not offs or not data or not bsp.models:
            return
        v = bsp.version
        self.size = (80.0, 80.0, 80.0) if v == 21 else (48.0, 48.0, 64.0) if v == 20 else (32.0, 32.0, 32.0)
        wmins, wmaxs = bsp.models[0]["mins"], bsp.models[0]["maxs"]
        self.mins = [self.size[i] * math.ceil(wmins[i] / self.size[i]) for i in range(3)]
        maxs = [self.size[i] * math.floor(wmaxs[i] / self.size[i]) for i in range(3)]
        self.bounds = [int((maxs[i] - self.mins[i]) / self.size[i] + 1) for i in range(3)]
        num = self.bounds[0] * self.bounds[1] + self.bounds[0]
        if len(offs) != num * 2 or len(pal) != 768 or min(self.bounds) < 2:
            return
        self.offsets = struct.unpack("<%dH" % num, offs)
        self.pal = pal
        self.data = data
        self.ok = True

    def value(self, pos):
        """The grid's light at pos (0-255 per channel), as R_GetLightingGridValue."""
        if not self.ok:
            return (255.0, 255.0, 255.0)
        gp = [0, 0, 0]
        fr = [0.0, 0.0, 0.0]
        for i in range(3):
            fv = (pos[i] - self.mins[i]) / self.size[i]
            g = int(math.floor(fv))
            fr[i] = fv - g
            gp[i] = max(0, min(self.bounds[i] - 2, g))
        om = [1.0 - f for f in fr]
        step = self.bounds[1]
        base = self.bounds[0] + gp[1] + step * gp[0]
        offs, d, pal = self.offsets, self.data, self.pal
        light = [0.0, 0.0, 0.0]
        total = 0.0

        def add(ci, w):
            light[0] += pal[ci * 3] * w
            light[1] += pal[ci * 3 + 1] * w
            light[2] += pal[ci * 3 + 2] * w

        try:
            for corner in range(4):
                if corner == 0:
                    w1, w2 = om[0] * om[1] * om[2], om[0] * om[1] * fr[2]
                    off = offs[base] + (offs[gp[0]] << 8)
                elif corner == 1:
                    w1, w2 = om[0] * fr[1] * om[2], om[0] * fr[1] * fr[2]
                    off = offs[base + 1] + (offs[gp[0]] << 8)
                elif corner == 2:
                    w1, w2 = fr[0] * om[1] * om[2], fr[0] * om[1] * fr[2]
                    off = offs[base + step] + (offs[gp[0] + 1] << 8)
                else:
                    w1, w2 = fr[0] * fr[1] * om[2], fr[0] * fr[1] * fr[2]
                    off = offs[base + step + 1] + (offs[gp[0] + 1] << 8)
                row = gp[2]
                k = 0
                done = False
                ln = 0
                # A column is a list of runs: a negative count n is followed by n separate
                # colours, a count n >= 0 by one colour repeated n + 2 times.
                while True:
                    while True:
                        cur = d[off + k]
                        if cur > 127:
                            cur -= 256
                        k += 1
                        if cur >= 0:
                            break
                        ln = -cur
                        if ln > row:
                            k += row
                            if d[off + k]:
                                add(d[off + k], w1)
                                total += w1
                            k += 1
                            if ln - 1 == row:
                                k += 1
                            if d[off + k]:
                                add(d[off + k], w2)
                                total += w2
                            done = True
                            break
                        row -= ln
                        k += ln
                    if done:
                        break
                    ln = cur + 2
                    if ln - 1 >= row:
                        break
                    row -= ln
                    k += 1
                if done:
                    continue
                if ln - 1 > row:
                    if d[off + k]:
                        add(d[off + k], w1 + w2)
                        total += w1 + w2
                else:
                    if d[off + k]:
                        add(d[off + k], w1)
                        total += w1
                    k += 2
                    if d[off + k]:
                        add(d[off + k], w2)
                        total += w2
        except IndexError:
            return (255.0, 255.0, 255.0)
        if 0.0 < total < 0.99:
            light = [c / total for c in light]
        if not total:
            return (255.0, 255.0, 255.0)
        m = max(light)
        if m > 255.0:
            light = [c * 255.0 / m for c in light]
        return tuple(light)

    def entity_light(self, pos):
        """The colour a model at pos is drawn with: the grid value brightened and
        clamped as RB_GetEntityGridLighting / RB_SetupStaticModelGridLighting do."""
        v = [c * (1 << OVERBRIGHT_SHIFT) for c in self.value(pos)]
        m = max(v)
        if m > 255.0:
            v = [c * 255.0 / m for c in v]
        return [int(min(255.0, c)) for c in v]


def load(path):
    """Read a .bsp file from disk."""
    with open(path, "rb") as f:
        return Bsp(f.read(), os.path.basename(path))


def main(argv):
    """Command line: decompile one .bsp to .map (next to it unless a path is given)."""
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print("usage: python mohaa_bsp.py <map.bsp> [out.map]")
        return 1
    src = args[0]
    if len(args) > 1:
        dst = args[1]
    else:
        dst = output_map_path(os.path.dirname(os.path.abspath(src)), os.path.splitext(os.path.basename(src))[0])
    try:
        bsp = load(src)
    except (OSError, BspError) as e:
        print("error: %s" % e)
        return 2
    try:
        text, stats = decompile(bsp, log=print)
    except (struct.error, IndexError) as e:
        print("error: %s looks damaged: %s" % (os.path.basename(src), e))
        return 3
    with open(dst, "w", encoding="latin-1", errors="replace", newline="\n") as f:
        f.write(text)
    print("wrote %s" % dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
#  mohaa_map_actor.py  --  the actors of the Map Viewer's SIMULATE (path nodes)
#
#  SIMULATE on an info_pathnode (or info_waypoint) stands a human on the node, holding a
#  weapon, plays the animation the game plays at a node with those spawnflags, and runs or
#  walks him along a path. This module is what the launcher needs for that, kept apart
#  from the Tk code so it can be tested on its own:
#
#    - which .tik files are humans (classname Actor) and which are weapons
#      (classname Weapon with a weapongroup), read from the paks
#    - which animations a role plays for a weapon group (a node's spawnflags, or running
#      and walking), from the scripts the game runs (anim/cornerleft.scr, cornerright.scr,
#      overattack.scr, highwall.scr, lowwall.scr, stand.scr, run.scr, walk.scr)
#    - the skin weights and base pose the page needs to pose the human itself
#    - one animation clip solved against the human's own skeleton (the Model Viewer's
#      solve_anim), as the record the page plays
#
#  Nothing here touches Tk or the network. Failures raise ValueError with the reason the
#  page shows; unexpected errors are logged by the caller (MC.swallowed) and reported.
# ==============================================================================
# --- Vendored dependencies (bin/libs on Windows, bin/libs-linux on Linux, bin/libs-mac on macOS)
import sys
import os
_LIBS_NAME = "libs" if sys.platform.startswith("win") else ("libs-mac" if sys.platform == "darwin" else "libs-linux")
_libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), _LIBS_NAME)
if os.path.isdir(_libs_dir) and _libs_dir not in sys.path:
    sys.path.insert(0, _libs_dir)
_bin_dir = os.path.dirname(os.path.abspath(__file__))
if _bin_dir not in sys.path:
    sys.path.insert(0, _bin_dir)
import re
import struct
import tempfile

import mohaa_common as MC                       # logging, swallowed()
try:
    import mohaa_view as MV                     # .skc reader and the animation solver
except Exception:                               # pragma: no cover - shipped together
    MC.swallowed()
    MV = None

# ------------------------------------------------------------------------------
#  Constants
# ------------------------------------------------------------------------------
HUMAN_DIR = "models/human/"
WEAPON_DIR = "models/weapons/"
ACTOR_TAG = "tag_weapon_right"      # Weapon::attachToTag_main (weapon.cpp): the main hand
ACTOR_TAG_OFF = "tag_weapon_left"   # Weapon::attachToTag_offhand: the other hand
MAX_VPATH = 260                     # longest path the page may ask for
MAX_CLIP_FRAMES = 600               # a clip longer than this is refused (the longest is ~100)
MIN_STEP_HOLD = 0.35                # seconds a step shows at least (the page holds its last frame)

# Spawnflag bits of an info_pathnode (mohaa_entdefs.py, navigate.h AI_*).
SF_DONT_LINK, SF_DUCK, SF_COVER, SF_CONCEALMENT = 1, 2, 4, 8
SF_CORNER_LEFT, SF_CORNER_RIGHT, SF_SNIPER, SF_CRATE = 16, 32, 64, 128
SF_LOW_WALL_ARC = 256               # Spearhead / Breakthrough only

# A role is what a node's flags make the man do. Each step is
#   (animation base name, required, legs)
# and the animation is "<weapongroup>_<base>". `required` steps decide whether the role
# can play at all (the others are skipped when the weapon group has none). `legs` names
# the clip whose first frame supplies the legs an upper-body clip lacks (the engine
# blends such a clip over a movement animation; stand.scr uses <wg>_stand_alert_legs).
# The orders are the ones the scripts play: cornerleft.scr (_wall_alert_left, then
# _wall_left_shoot_intro / _wall_left_shoot / _wall_left_shoot_outro), overattack.scr
# (_crate_standtocrouch, _crate_alert, _crate_crouchtostand, _crate_shoot,
# _crate_standtocrouch).
LEGS_ALERT = "stand_alert_legs"
LEGS_CROUCH = "crouch_alert"
ROLE_STEPS = {
    "idle": [("stand_alert01", True, LEGS_ALERT)],
    "left": [("wall_alert_left", False, None), ("wall_left_shoot_intro", False, None),
             ("wall_left_shoot", True, None), ("wall_left_shoot_outro", False, None)],
    "right": [("wall_alert_right", False, None), ("wall_right_shoot_intro", False, None),
              ("wall_right_shoot", True, None), ("wall_right_shoot_outro", False, None)],
    "crate": [("crate_standtocrouch", False, None), ("crate_alert", False, None),
              ("crate_crouchtostand", False, None), ("crate_shoot", True, None),
              ("crate_standtocrouch", False, None)],
    "sniper": [("aim", True, LEGS_ALERT), ("shoot", False, LEGS_ALERT)],
    # LOW_WALL_ARC (Spearhead / Breakthrough, anim/highwall.scr and lowwall.scr): stand (or, with
    # DUCK, crouch), then aim, and shoot while he sees the enemy
    "highwall": [("aim", True, LEGS_ALERT), ("shoot", False, LEGS_ALERT)],
    "lowwall": [("aim", True, LEGS_CROUCH), ("shoot", False, LEGS_CROUCH)],
    "duck": [("crouch_alert", True, None)],
    # moving (anim/run.scr -> runto_casual.scr, walk.scr -> WalkPlayMotionBlendAnim with no
    # movedir): one looping clip, played while he crosses the map
    "run": [("run_forward", True, None)],
    "walk": [("walk_forward", True, None)],
}
ROLES = tuple(ROLE_STEPS)

# ------------------------------------------------------------------------------
#  Model lists
# ------------------------------------------------------------------------------
def strip_tik_comments(text):
    """A .tik's text with its // comments removed (a `weapongroup rifle //TODO` line
    must read as rifle). Takes str; returns str."""
    if not isinstance(text, str):
        raise ValueError("strip_tik_comments: text must be str, not %s" % type(text).__name__)
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def is_actor_tik(text):
    """True when the .tik's own text declares `classname Actor` (a human the game spawns
    as an Actor). `text` is the .tik as str; $include files are not expanded."""
    return bool(re.search(r"(?im)^\s*classname\s+Actor\b", strip_tik_comments(text)))


def weapon_group(text):
    """The weapon group of a weapon .tik (`weapongroup rifle`), lower case, or None when
    the .tik isn't a Weapon with one (grenades and static props have none). The group,
    not the weapon's name, is the prefix of its animations (shotgun and springfield are
    `rifle`)."""
    t = strip_tik_comments(text)
    if not re.search(r"(?im)^\s*classname\s+Weapon\b", t):
        return None
    m = re.search(r"(?im)^\s*weapongroup\s+(\S+)", t)
    return m.group(1).lower() if m else None


def weapon_name(text):
    """The weapon's `name "..."` (what a case weapon branch of a human .tik matches), or ''."""
    m = re.search(r'(?im)^\s*name\s+"([^"]*)"', strip_tik_comments(text))
    return m.group(1) if m else ""


def list_models(vfs):
    """(humans, weapons) from the loaded paks: humans is a sorted list of .tik paths
    directly under models/human/, weapons a sorted list of [path, weapongroup] directly
    under models/weapons/. Reads each candidate .tik once. `vfs` is a Vfs."""
    humans, weapons = [], []
    for n in sorted(vfs.names()):
        if not n.endswith(".tik"):
            continue
        if n.startswith(HUMAN_DIR) and "/" not in n[len(HUMAN_DIR):]:
            kind = "h"
        elif n.startswith(WEAPON_DIR) and "/" not in n[len(WEAPON_DIR):]:
            kind = "w"
        else:
            continue
        data = vfs.read(n)
        if data is None:
            continue
        text = data.decode("latin-1", "replace")
        if kind == "h":
            if is_actor_tik(text):
                humans.append(n)
        else:
            g = weapon_group(text)
            if g:
                weapons.append([n, g])
    return humans, weapons


def check_vpath(vp, folder):
    """A path the page sent, normalised, or ValueError. It must be a .tik directly under
    `folder` (HUMAN_DIR / WEAPON_DIR) with no `..` and no control characters."""
    if not isinstance(vp, str):
        raise ValueError("the model path is not text")
    p = vp.strip().replace("\\", "/").lower()
    if (not p.startswith(folder) or not p.endswith(".tik") or ".." in p or len(p) > MAX_VPATH
            or "/" in p[len(folder):] or any(ord(c) < 32 for c in p)):
        raise ValueError("not a model in %s" % folder)
    return p


# ------------------------------------------------------------------------------
#  Flags -> role
# ------------------------------------------------------------------------------
def flags_role(sf):
    """(role, note) for a path node's spawnflags, as the game prefers them: the special
    attacks are taken in the order PathNode::GetSpecialAttack tests them (CORNER_LEFT,
    CORNER_RIGHT, CRATE). A flag combination the AI refuses (IsValidPathnode) has no
    role. `role` is one of ROLES, or None with the reason in `note`. `sf` is an int."""
    sf = int(sf) & 0xFFFF
    return _role_of(sf & 0x1FE)                     # DONT_LINK (1) has no say


def _role_of(v):
    """The body of flags_role on the flags without DONT_LINK (see there)."""
    duck, cover, conc, cl, cr, sniper, crate = 2, 4, 8, 16, 32, 64, 128
    lowwall = 256                                   # LOW_WALL_ARC: Spearhead / Breakthrough only
    names = (("DUCK", duck), ("COVER", cover), ("CONCEALMENT", conc), ("CORNER_LEFT", cl),
             ("CORNER_RIGHT", cr), ("SNIPER", sniper), ("CRATE", crate), ("LOW_WALL_ARC", lowwall))
    on = [n for n, b in names if v & b]
    if not on:
        return None, "no spawnflags: he only stands there"
    # IsValidPathnode (navigate.cpp 1458-1490): the combinations the AI can't use
    bad = ((v & duck and v & (conc | cl | cr | sniper | crate))
           or (v & conc and v & (cover | cl | cr | sniper))
           or (v & cl and v & (duck | conc | cr | sniper | crate))
           or (v & cr and v & (duck | conc | cl | sniper | crate))
           or (v & sniper and v & (duck | cover | conc | cl | cr | crate))
           or (v & crate and v & (duck | conc | cl | cr | sniper)))
    if bad:
        return None, "%s: the AI can't combine these flags (the game draws the node black)" % " + ".join(on)
    if v & cl:
        return "left", "CORNER_LEFT"
    if v & cr:
        return "right", "CORNER_RIGHT"
    if v & crate:
        return "crate", "CRATE"
    if v & lowwall:                                 # GetSpecialAttack: after the corners and CRATE
        if v & duck:
            return "lowwall", "LOW_WALL_ARC + DUCK (Spearhead / Breakthrough)"
        return "highwall", "LOW_WALL_ARC (Spearhead / Breakthrough)"
    if v & sniper:
        return "sniper", "SNIPER"
    if v & duck:
        return "duck", "DUCK"
    return None, "%s has no special animation: he only stands there" % " + ".join(on)


# ------------------------------------------------------------------------------
#  Clips
# ------------------------------------------------------------------------------
def catalog_names(cat):
    """{lower animation name: catalogue entry} from MTX.build_anim_catalog's result."""
    out = {}
    for e in (cat or {}).get("anims", []):
        n = (e.get("n") or "").lower()
        if n and n not in out:
            out[n] = e
    return out


def resolve_clip(names, wg, base):
    """The catalogue entry for "<wg>_<base>": the exact name, then `<name>01`, then the
    lowest `<name><digits>` (mp40 and bar have crate_shoot01, pistol wall_shoot_left01).
    Returns (name, entry) or (None, None). `names` is catalog_names()'s dict."""
    full = "%s_%s" % (wg, base)
    if full in names:
        return full, names[full]
    if full + "01" in names:
        return full + "01", names[full + "01"]
    pat = re.compile("^" + re.escape(full) + r"(\d+)$")
    hits = sorted((int(m.group(1)), n) for n in names for m in [pat.match(n)] if m)
    if hits:
        return hits[0][1], names[hits[0][1]]
    return None, None


def plan_role(names, wg, role):
    """The clips a role plays for a weapon group: ([(name, entry, legs name or None)],
    why). `why` is '' when it can play, else the reason it can't (steps is then []).
    The `idle` role falls back to the model's own `idle` clip."""
    if role not in ROLE_STEPS:
        raise ValueError("unknown role %r" % (role,))
    steps = []
    missing_key = None
    for base, req, legs in ROLE_STEPS[role]:
        nm, ent = resolve_clip(names, wg, base)
        if ent is None:
            if req:
                missing_key = "%s_%s" % (wg, base)
            continue
        steps.append((nm, ent, legs))
    if missing_key:
        if role == "idle" and "idle" in names:
            return [("idle", names["idle"], None)], ""
        return [], "this weapon group (%s) has no %s animation" % (wg, missing_key)
    if not steps:
        return [], "this weapon group (%s) has no animation for this node" % wg
    return steps, ""


def roles_available(names, wg):
    """{role: reason or ''} for every role but idle: '' when it can play."""
    return {r: plan_role(names, wg, r)[1] for r in ROLES if r != "idle"}


_HAND_CMD = re.compile(r"^\s*(\S+)\s+(?:commanddelay\s+\S+\s+)?weaponcommand\s+mainhand\s+attachtohand\s+(mainhand|offhand)\s*$",
                       re.I)
_HAND_FRAME = {"entry": 0, "enter": 0, "first": 0, "start": 0, "last": -1, "end": -1, "exit": -1}


def hand_events(block):
    """The hand changes a clip's server frame commands make, [[frame, hand]] in file order:
    `<frame> weaponcommand mainhand attachtohand mainhand|offhand` puts the weapon on the
    main hand (0, tag_weapon_right) or the other (1, tag_weapon_left) when the clip reaches
    that frame; `entry` / `first` is frame 0 and `last` / `end` / `exit` is -1, the last
    frame. The right-corner clips hold the weapon in the other hand. `block` is the
    catalogue entry's "v" (the commands, one per line) or None. Other commands are ignored."""
    out = []
    for line in (block or "").splitlines():
        m = _HAND_CMD.match(line.split("//", 1)[0])
        if not m:
            continue
        w = m.group(1).lower()
        if w in _HAND_FRAME:
            fr = _HAND_FRAME[w]
        elif w.isdigit() and int(w) < MAX_CLIP_FRAMES:
            fr = int(w)
        else:
            continue
        out.append([fr, 1 if m.group(2).lower() == "offhand" else 0])
    return out


def _read_skc(vfs, vpath):
    """An .skc's bytes from the paks (the catalogue's path, else a file of that name
    anywhere: a few retail entries have a stale $path), or None."""
    if not vpath:
        return None
    d = vfs.read(vpath)
    if d is not None:
        return d
    bn = "/" + os.path.basename(vpath.replace("\\", "/")).lower()
    k = next((kk for kk in vfs.names() if kk.endswith(bn)), None)
    return vfs.read(k) if k else None


def _parse_skc_bytes(data):
    """MV.parse_skc on bytes (it reads a path): through a temporary file, removed again."""
    fd, tmp = tempfile.mkstemp(suffix=".skc")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return MV.parse_skc(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            MC.swallowed()


def solve_clip(vfs, bones, name, entry, legs_entry=None, solver_ctx=None):
    """One clip as the page plays it: {"name", "frameTime", "frames": [{bone index:
    [px,py,pz,qx,qy,qz,qw] or [qx,qy,qz,qw]}]}, solved against `bones` (the merged
    skeleton the page's mesh was built from, so the indices agree: this is the Model
    Viewer's solve_anim). `legs_entry` supplies the first frame's channels beneath an
    upper-body clip. Raises ValueError with the reason when the clip can't be used."""
    if MV is None:
        raise ValueError("mohaa_view.py is missing")
    data = _read_skc(vfs, (entry or {}).get("s"))
    if data is None:
        raise ValueError("%s: its .skc is not in the paks" % name)
    skc = _parse_skc_bytes(data)
    if not skc.get("frames"):
        raise ValueError("%s: the .skc has no frames" % name)
    if len(skc["frames"]) > MAX_CLIP_FRAMES:
        raise ValueError("%s: %d frames is more than the %d allowed" % (name, len(skc["frames"]), MAX_CLIP_FRAMES))
    have = {b["name"] for b in bones}
    if not ({n.rsplit(" ", 1)[0] for n in skc["names"]} & have):
        raise ValueError("%s: drives none of this skeleton's %d bones" % (name, len(have)))
    mv = None
    if legs_entry is not None:
        ld = _read_skc(vfs, legs_entry.get("s"))
        if ld is not None:
            lskc = _parse_skc_bytes(ld)
            if lskc.get("frames"):
                mv = lskc["frames"][0]
    hi, lc = solver_ctx if solver_ctx is not None else MV.anim_solver_ctx(bones)
    rec = MV.solve_anim(bones, {"name": name, "data": skc}, hi, lc, mv)
    out = {"name": name, "frameTime": rec["frameTime"], "frames": rec["frames"]}
    # where the clip has moved him by each frame: the running sum of the frames' deltas (x ahead,
    # y left, game units), flat [x, y, z, ...]. Only sent when the clip moves him at all.
    acc = [0.0, 0.0, 0.0]
    dl = []
    for d in skc.get("fdelta") or []:
        acc = [acc[0] + d[0], acc[1] + d[1], acc[2] + d[2]]
        dl.extend(round(v, 3) for v in acc)
    if any(abs(v) > 0.01 for v in dl):
        out["dl"] = dl
    hand = hand_events((entry or {}).get("v"))
    if hand:
        out["hand"] = hand
    if not out["frames"]:
        raise ValueError("%s: no frames" % name)
    return out


# ------------------------------------------------------------------------------
#  The skinned mesh's extra data
# ------------------------------------------------------------------------------
def base_pose(bones, channels):
    """Every bone's local (position, rotation) with the idle frame `channels` applied, as
    the Model Viewer's build_payload computes its `base`: the pose a bone a clip doesn't
    drive falls back to. Returns a list of ([px,py,pz], [qx,qy,qz,qw])."""
    if MV is None:
        raise ValueError("mohaa_view.py is missing")
    bwR, bwT = MV.compute_world(bones, channels)
    ik = set()
    for th, ca, fo in MV._leg_ik_chains(bones):
        if (bones[fo]["name"] + " pos") in channels:
            ik.update((th, ca, fo))
    for bi, bn in enumerate(bones):
        if bn.get("boneType") in (5, 6) and bn.get("solvable"):
            ik.add(bi)
    out = []
    for bi, bn in enumerate(bones):
        if bi in ik:
            p, q = MV._world_to_local(bones, bi, bwR, bwT)
        else:
            p, q = MV._solved_local(bones, bi, channels, bwR, bwT)
        out.append(([float(x) for x in p[:3]], [float(x) for x in q[:4]]))
    return out


class SkinRecorder:
    """Collects each drawn vertex's bone weights in the order ModelBuilder writes the
    vertices, so the page can pose the mesh again for every animation frame."""

    def __init__(self):
        self.counts = bytearray()
        self.bones = []
        self.weights = []
        self.offsets = []

    def vertex(self, items):
        """Record one vertex. `items` is its list of (bone index, weight, (x, y, z)) that
        were valid (the ones ModelBuilder sums into the vertex)."""
        n = 0
        for bi, wv, off in items:
            self.bones.append(int(bi))
            self.weights.append(float(wv))
            self.offsets.extend((float(off[0]), float(off[1]), float(off[2])))
            n += 1
        if n > 255:
            raise ValueError("a vertex has %d bone weights" % n)
        self.counts.append(n)

    def pack(self, blobs, bones, channels):
        """The model's "sk" record for the page: bone names and parents, the base pose and
        the weights as blobs (wc: u8 counts, wb: u32 bones, ww / wo: f32 weight and offset)."""
        base = base_pose(bones, channels)
        flat = []
        for p, q in base:
            flat.extend(p)
            flat.extend(q)
        return {
            "bn": [b["name"].lower() for b in bones],
            "bp": [int(b["parentIdx"]) for b in bones],
            "base": blobs.add(struct.pack("<%df" % len(flat), *flat)),
            "wc": blobs.add(bytes(self.counts)),
            "wb": blobs.add(struct.pack("<%dI" % len(self.bones), *self.bones)),
            "ww": blobs.add(struct.pack("<%df" % len(self.weights), *self.weights)),
            "wo": blobs.add(struct.pack("<%df" % len(self.offsets), *self.offsets)),
        }

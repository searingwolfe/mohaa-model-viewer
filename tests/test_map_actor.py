#!/usr/bin/env python3
"""Tests for SIMULATE's actors on path nodes (bin/mohaa_map_actor.py), stdlib unittest.

Run from the project folder:   python tests/test_map_actor.py

Two groups:
  * always run: the flag -> role rules, the weapon-hand commands, the clip-name resolver (against a catalogue made
    up like the real one), the path checks the launcher applies to the page's requests,
    and the .tik readers (human / weapon lists);
  * run only when MOHAA_GAMEFOLDER names a folder of the game's files (models/, anim/ ...:
    an extracted pak, or the game's main folder): the real catalogue of a human and
    every weapon group, a human built with its skin weights, and one animation solved
    against its skeleton, checked against the Model Viewer's own pose. Skipped otherwise."""
import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
sys.path.insert(0, BIN)
for _l in ("libs", "libs-linux", "libs-mac"):
    if os.path.isdir(os.path.join(BIN, _l)):
        sys.path.insert(0, os.path.join(BIN, _l))

import mohaa_map_actor as MA          # noqa: E402

GAME = os.environ.get("MOHAA_GAMEFOLDER", "")


def fake_names(groups=("rifle", "mp40")):
    """A catalogue's {name: entry} with the clips a weapon group usually has."""
    base = ["stand_alert01", "stand_alert_legs", "wall_alert_left", "wall_left_shoot_intro", "wall_left_shoot",
            "wall_left_shoot_outro", "wall_alert_right", "wall_right_shoot_intro", "wall_right_shoot",
            "wall_right_shoot_outro", "crate_standtocrouch", "crate_alert", "crate_crouchtostand", "crate_shoot",
            "aim", "shoot", "crouch_alert"]
    out = {}
    for g in groups:
        for b in base:
            out["%s_%s" % (g, b)] = {"n": "%s_%s" % (g, b), "s": "models/human/animation/%s_%s.skc" % (g, b)}
    return out


class FlagRoles(unittest.TestCase):
    def role(self, sf):
        return MA.flags_role(sf)[0]

    def test_no_flags_is_idle_only(self):
        self.assertIsNone(self.role(0))
        self.assertIsNone(self.role(1))                    # DONT_LINK alone

    def test_single_flags(self):
        self.assertEqual(self.role(16), "left")
        self.assertEqual(self.role(32), "right")
        self.assertEqual(self.role(128), "crate")
        self.assertEqual(self.role(64), "sniper")
        self.assertEqual(self.role(2), "duck")

    def test_dont_link_does_not_change_the_role(self):
        self.assertEqual(self.role(16 | 1), "left")

    def test_cover_and_concealment_have_no_animation(self):
        for sf in (4, 8):
            role, note = MA.flags_role(sf)
            self.assertIsNone(role)
            self.assertIn("only stands", note)

    def test_combinations_the_ai_refuses_have_no_role(self):
        for sf in (16 | 32, 16 | 128, 32 | 128, 64 | 16, 2 | 16, 8 | 16, 2 | 128, 64 | 4):
            role, note = MA.flags_role(sf)
            self.assertIsNone(role, sf)
            self.assertIn("can't combine", note)

    def test_combinations_the_ai_allows(self):
        self.assertEqual(self.role(16 | 4), "left")        # corner + cover
        self.assertEqual(self.role(128 | 4), "crate")      # crate + cover (crate + concealment is refused)
        self.assertEqual(self.role(2 | 4), "duck")         # duck + cover

    def test_matches_the_pages_nodeFlagsBad(self):
        """The page's own copy of IsValidPathnode (nodeFlagsBad) and this one agree on every combination."""
        def page_bad(sf):
            v = sf & 0xfe
            return bool(((v & 2) and (v & ~0x06)) or ((v & 8) and (v & ~0x8a)) or ((v & 16) and (v & ~0x14))
                        or ((v & 32) and (v & ~0x24)) or ((v & 64) and (v & ~0x40)) or ((v & 128) and (v & ~0x84)))
        for sf in range(256):
            note = MA.flags_role(sf)[1]
            self.assertEqual("can't combine" in note, page_bad(sf), sf)


class ClipNames(unittest.TestCase):
    def test_exact_then_01_then_numbered(self):
        names = {"mp40_crate_shoot01": {"n": "a"}, "bar_wall_shoot_left03": {"n": "b"}, "bar_wall_shoot_left02": {"n": "c"},
                 "rifle_crate_shoot": {"n": "d"}, "rifle_crate_shoot01": {"n": "e"}}
        self.assertEqual(MA.resolve_clip(names, "mp40", "crate_shoot")[0], "mp40_crate_shoot01")
        self.assertEqual(MA.resolve_clip(names, "bar", "wall_shoot_left")[0], "bar_wall_shoot_left02")
        self.assertEqual(MA.resolve_clip(names, "rifle", "crate_shoot")[0], "rifle_crate_shoot")
        self.assertEqual(MA.resolve_clip(names, "pistol", "crate_shoot"), (None, None))

    def test_a_numbered_name_is_not_a_longer_name(self):
        self.assertEqual(MA.resolve_clip({"rifle_aim_up": {}}, "rifle", "aim"), (None, None))

    def test_corner_left_plays_the_scripts_order(self):
        steps, why = MA.plan_role(fake_names(), "rifle", "left")
        self.assertEqual(why, "")
        self.assertEqual([s[0] for s in steps], ["rifle_wall_alert_left", "rifle_wall_left_shoot_intro",
                                                 "rifle_wall_left_shoot", "rifle_wall_left_shoot_outro"])

    def test_crate_plays_overattack_scrs_order(self):
        steps, _ = MA.plan_role(fake_names(), "mp40", "crate")
        self.assertEqual([s[0] for s in steps], ["mp40_crate_standtocrouch", "mp40_crate_alert",
                                                 "mp40_crate_crouchtostand", "mp40_crate_shoot",
                                                 "mp40_crate_standtocrouch"])

    def test_idle_has_legs_from_stand_alert_legs(self):
        steps, _ = MA.plan_role(fake_names(), "rifle", "idle")
        self.assertEqual(steps[0][0], "rifle_stand_alert01")
        self.assertEqual(steps[0][2], "stand_alert_legs")

    def test_a_group_without_the_key_clip_cannot_play(self):
        names = fake_names(("bazooka",))
        for k in [k for k in names if "wall" in k or "crate" in k]:
            del names[k]
        steps, why = MA.plan_role(names, "bazooka", "left")
        self.assertEqual(steps, [])
        self.assertIn("bazooka_wall_left_shoot", why)
        self.assertNotEqual(MA.roles_available(names, "bazooka")["left"], "")
        self.assertEqual(MA.roles_available(names, "bazooka")["sniper"], "")

    def test_an_optional_step_may_be_missing(self):
        names = fake_names()
        del names["rifle_wall_left_shoot_intro"]
        steps, why = MA.plan_role(names, "rifle", "left")
        self.assertEqual(why, "")
        self.assertNotIn("rifle_wall_left_shoot_intro", [s[0] for s in steps])

    def test_unknown_role_is_refused(self):
        with self.assertRaises(ValueError):
            MA.plan_role(fake_names(), "rifle", "../x")


class HandEvents(unittest.TestCase):
    """The weapon changes hands in some clips' server commands (the right corner's)."""

    def test_entry_numbers_and_last(self):
        block = ("entry\tweaponcommand mainhand attachtohand mainhand\n10\tweaponcommand mainhand attachtohand offhand\n"
                 "last\tweaponcommand mainhand attachtohand mainhand\n2\tfire\n")
        self.assertEqual(MA.hand_events(block), [[0, 0], [10, 1], [-1, 0]])

    def test_the_right_corner_holds_the_weapon_in_the_other_hand(self):
        self.assertEqual(MA.hand_events("entry\tweaponcommand mainhand attachtohand offhand\n2\tfire"), [[0, 1]])
        self.assertEqual(MA.hand_events("first weaponcommand mainhand attachtohand offhand"), [[0, 1]])
        self.assertEqual(MA.hand_events("exit\tweaponcommand mainhand attachtohand offhand"), [[-1, 1]])

    def test_other_commands_and_junk_are_ignored(self):
        for b in (None, "", "0 fire", "entry weaponcommand mainhand fire", "bogus weaponcommand mainhand attachtohand offhand",
                  "99999 weaponcommand mainhand attachtohand offhand", "// 3 weaponcommand mainhand attachtohand offhand"):
            self.assertEqual(MA.hand_events(b), [], b)


class Requests(unittest.TestCase):
    def test_check_vpath_accepts_only_a_tik_directly_in_the_folder(self):
        self.assertEqual(MA.check_vpath(" Models\\Human\\German_X.TIK ", MA.HUMAN_DIR), "models/human/german_x.tik")
        for bad in ("models/human/../x.tik", "models/human/animation/x.tik", "models/weapons/mp40.tik",
                    "models/human/x.skd", "models/human/x\n.tik", "", None, 5, "models/human/" + "a" * 300 + ".tik"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                MA.check_vpath(bad, MA.HUMAN_DIR)
        with self.assertRaises(ValueError):
            MA.check_vpath("models/human/x.tik", MA.WEAPON_DIR)

    def test_tik_readers(self):
        self.assertTrue(MA.is_actor_tik("init\n{\n\tserver\n\t{\n\t\tclassname Actor\n\t}\n}"))
        self.assertFalse(MA.is_actor_tik("//classname Actor\nsetup\n{\n}"))
        self.assertFalse(MA.is_actor_tik("classname Weapon"))
        self.assertEqual(MA.weapon_group("classname\tWeapon\nweapongroup rifle //TODO: shotgun group\n"), "rifle")
        self.assertIsNone(MA.weapon_group("weapongroup rifle"))                    # not a Weapon
        self.assertIsNone(MA.weapon_group("classname Weapon\nammotype x"))         # no group (grenade)
        self.assertEqual(MA.weapon_name('classname Weapon\nname "StG 44"\n'), "StG 44")
        with self.assertRaises(ValueError):
            MA.is_actor_tik(b"bytes")

    def test_list_models_reads_only_the_two_folders(self):
        files = {
            "models/human/a.tik": b"classname Actor", "models/human/b.tik": b"setup\n{\n}",
            "models/human/animation/c.tik": b"classname Actor",
            "models/weapons/w.tik": b"classname Weapon\nweapongroup mp40", "models/weapons/g.tik": b"classname Weapon",
            "models/weapons/x.skd": b"weapongroup rifle", "models/other/o.tik": b"classname Actor"}

        class V:
            def names(self):
                return files.keys()

            def read(self, n):
                return files.get(n)
        humans, weapons = MA.list_models(V())
        self.assertEqual(humans, ["models/human/a.tik"])
        self.assertEqual(weapons, [["models/weapons/w.tik", "mp40"]])


@unittest.skipUnless(GAME and os.path.isdir(GAME), "set MOHAA_GAMEFOLDER to a folder of the game's files")
class RealData(unittest.TestCase):
    """Against the game's own files (see the module docstring)."""

    @classmethod
    def setUpClass(cls):
        import mohaa_textures as MTX
        import mohaa_view as MV
        import mohaa_map_view as MMV
        cls.MTX, cls.MV, cls.MMV = MTX, MV, MMV

        class Dir(MTX.Vfs):
            """A Vfs over a folder instead of .pk3 files (the builders only read through it)."""
            def __init__(self, root):
                super().__init__([])
                for dp, _dn, fn in os.walk(root):
                    for f in fn:
                        full = os.path.join(dp, f)
                        self.index[os.path.relpath(full, root).replace("\\", "/").lower()] = (None, full)

            def read(self, p):
                e = self.index.get(self._k(p))
                if not e:
                    return None
                with open(e[1], "rb") as fh:
                    return fh.read()
        cls.vfs = Dir(GAME)
        cls.hum = "models/human/german_wehrmact_soldier.tik"
        if not cls.vfs.exists(cls.hum):
            raise unittest.SkipTest("%s is not in the game folder" % cls.hum)

    def test_lists_and_roles(self):
        humans, weapons = MA.list_models(self.vfs)
        self.assertIn(self.hum, humans)
        groups = {g for _p, g in weapons}
        self.assertTrue({"rifle", "mp40", "pistol"} <= groups)
        self.assertFalse([p for p, _g in weapons if "grenade" in p or "granate" in p or "static_" in p])
        raw = self.vfs.read(self.hum).decode("latin-1")
        names = MA.catalog_names(self.MTX.build_anim_catalog(raw, self.vfs, self.hum))
        for g in ("rifle", "mp40", "pistol", "bar", "thompson", "mp44"):
            self.assertEqual(MA.roles_available(names, g)["left"], "", g)
            self.assertEqual(MA.roles_available(names, g)["crate"], "", g)
        self.assertNotEqual(MA.roles_available(names, "bazooka")["left"], "")

    def test_skin_and_a_solved_clip_match_the_viewers_pose(self):
        """The skin weights reproduce ModelBuilder's own mesh, and a solved clip frame
        skinned from them equals compute_world's pose of the same .skc frame."""
        class T:
            def __init__(self):
                self.entries = []

            def add(self, name, model=False):
                self.entries.append({"n": name, "f": 0})
                return len(self.entries) - 1
        blobs = self.MMV.Blobs()
        mb = self.MMV.ModelBuilder(self.vfs, T(), blobs, say=lambda *a: None)
        mb.skin_wanted = True
        mi = mb.get(self.hum)
        self.assertGreaterEqual(mi, 0, mb.failed)
        m, sk = mb.models[mi], mb.models[mi]["sk"]
        chunks = b"".join(blobs.chunks)

        def blob(i):
            o, n = blobs.table[i]
            return chunks[o:o + n]
        wc = list(blob(sk["wc"]))
        wb = struct.unpack("<%dI" % (len(blob(sk["wb"])) // 4), blob(sk["wb"]))
        self.assertEqual(len(wc), m["nv"])
        self.assertEqual(sum(wc), len(wb))
        self.assertIn(MA.ACTOR_TAG, sk["bn"])
        raw = self.vfs.read(self.hum).decode("latin-1")
        names = MA.catalog_names(self.MTX.build_anim_catalog(raw, self.vfs, self.hum))
        bones = mb.skins[self.hum]["skd"]["bones"]
        steps, why = MA.plan_role(names, "rifle", "crate")
        self.assertEqual(why, "")
        nm, ent, _legs = steps[-1]
        rec = MA.solve_clip(self.vfs, bones, nm, ent, None)
        self.assertEqual(rec["name"], nm)
        self.assertGreater(len(rec["frames"]), 1)
        self.assertIn(MA.ACTOR_TAG_OFF, sk["bn"])
        right = MA.plan_role(names, "rifle", "right")[0]
        shoot = next(s for s in right if s[0] == "rifle_wall_right_shoot")
        self.assertEqual(MA.solve_clip(self.vfs, bones, shoot[0], shoot[1], None)["hand"][0], [0, 1])
        with self.assertRaises(ValueError):
            MA.solve_clip(self.vfs, bones, "nope", {"s": "models/human/animation/none.skc"}, None)


if __name__ == "__main__":
    unittest.main(verbosity=2)

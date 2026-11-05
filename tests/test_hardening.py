#!/usr/bin/env python3
"""Regression tests for the 1.0.001 hardening pass (stdlib unittest; no pytest needed).

Run from the project folder:   python tests/test_hardening.py
Needs tkinter (the launcher modules import it). Pillow is used if bin/libs* has it.

What is real and what is simulated:
  * file writes, zips, settings files, .bsp files and child processes are all REAL
    (temp folders, the real code paths);
  * three failures are SIMULATED, because they can't be caused on demand: a crash in the
    middle of a write (os.replace / a read raising), a file that can't be written during
    an update, and the network (the updater's download is served from a local zip by
    replacing mohaa_common.http_get). Each such test says so in its docstring."""
import io
import json
import logging
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
sys.path.insert(0, BIN)
for _l in ("libs", "libs-linux", "libs-mac"):
    if os.path.isdir(os.path.join(BIN, _l)):
        sys.path.insert(0, os.path.join(BIN, _l))

import mohaa_common as MC          # noqa: E402
import mohaa_bsp as MB             # noqa: E402


def bsp_seed(ver=19):
    """A tiny but valid .bsp: one 6-sided brush in worldspawn plus one path node."""
    lumps = [b""] * 29
    lumps[0] = b"common/caulk".ljust(64, b"\0") + struct.pack("<3i", 0, 1, 0) + b"\0" * 64
    lumps[1] = b"".join(struct.pack("<4f", *p) for p in
                        ((1, 0, 0, 64), (-1, 0, 0, 64), (0, 1, 0, 64), (0, -1, 0, 64), (0, 0, 1, 64), (0, 0, -1, 64)))
    lumps[11] = b"".join(struct.pack("<3i", i, 0, 0) for i in range(6))
    lumps[12] = struct.pack("<3i", 0, 6, 0)
    mi = 13 + (1 if ver <= 18 else 0)
    ei = 14 + (1 if ver <= 18 else 0)
    lumps[mi] = struct.pack("<6f4i", -64, -64, -64, 64, 64, 64, 0, 0, 0, 1)
    lumps[ei] = b'{\n"classname" "worldspawn"\n}\n{\n"classname" "info_pathnode"\n"origin" "0 0 0"\n}\n\0'
    hdr = b"2015" + struct.pack("<ii", ver, 0)
    ofs = 12 + 8 * 29
    body = b""
    dirs = b""
    for lump in lumps:
        dirs += struct.pack("<ii", ofs + len(body), len(lump))
        body += lump
        body += b"\0" * ((-len(body)) % 4)
    return hdr + dirs + body


class TempDirCase(unittest.TestCase):
    """Gives each test a fresh temp folder in self.d."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mohaa_test_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def p(self, *parts):
        return os.path.join(self.d, *parts)


class AtomicWrites(TempDirCase):
    def test_write_and_backup(self):
        f = self.p("a.json")
        MC.atomic_write_bytes(f, b"one")
        MC.atomic_write_bytes(f, b"two", backup=True)
        self.assertEqual(open(f, "rb").read(), b"two")
        self.assertEqual(open(f + ".bak", "rb").read(), b"one")
        self.assertEqual([n for n in os.listdir(self.d) if n.endswith(".tmp")], [])

    def test_crash_during_replace_keeps_original(self):
        """SIMULATED crash: os.replace raises; the original must be untouched, no temp left."""
        f = self.p("a.txt")
        MC.atomic_write_bytes(f, b"original")
        with mock.patch.object(MC.os, "replace", side_effect=OSError("simulated crash")):
            with self.assertRaises(OSError):
                MC.atomic_write_bytes(f, b"new data that must not land")
        self.assertEqual(open(f, "rb").read(), b"original")
        self.assertEqual(sorted(os.listdir(self.d)), ["a.txt"])

    def test_stream_short_copy_never_lands(self):
        f = self.p("x.skd")
        with self.assertRaises(OSError):
            MC.atomic_write_stream(f, io.BytesIO(b"12345"), expected_size=10)
        self.assertFalse(os.path.exists(f))
        self.assertEqual(os.listdir(self.d), [])

    def test_text_newlines_match_open_w(self):
        f = self.p("t.txt")
        MC.atomic_write_text(f, "a\nb\n")
        self.assertEqual(open(f, "rb").read(), ("a" + os.linesep + "b" + os.linesep).encode())
        MC.atomic_write_text(f, "a\nb\n", newline="\n")
        self.assertEqual(open(f, "rb").read(), b"a\nb\n")

    def test_json_writes_forward_slashes(self):
        f = self.p("c.json")
        MC.atomic_write_json(f, {"pk3s": ["E:\\Games\\MOHAA\\main\\Pak0.pk3"], "n": 3})
        self.assertIn("E:/Games/MOHAA/main/Pak0.pk3", open(f, encoding="utf-8").read())


class Settings(TempDirCase):
    def test_hand_typed_backslashes_are_repaired(self):
        f = self.p("cfg.json")
        with open(f, "w", encoding="utf-8") as h:     # how a user types it in Notepad
            h.write('{"outdir": "E:\\Files\\new\\maps", "theme": "dark"}')
        cfg, notice = MC.load_settings(f)
        self.assertEqual(cfg["outdir"], "E:/Files/new/maps")
        self.assertIsNotNone(notice)
        self.assertTrue(os.path.isfile(f + ".bak"))
        self.assertEqual(json.load(open(f, encoding="utf-8"))["outdir"], "E:/Files/new/maps")

    def test_control_char_corruption_is_repaired(self):
        f = self.p("cfg.json")
        with open(f, "w", encoding="utf-8") as h:     # parses, but \n and \t become control chars
            h.write('{"outdir": "C:\\new\\tex"}')
        cfg, notice = MC.load_settings(f)
        self.assertEqual(cfg["outdir"], "C:/new/tex")
        self.assertIsNotNone(notice)

    def test_damaged_file_restored_from_bak(self):
        f = self.p("cfg.json")
        MC.atomic_write_json(f, {"pk3s": ["a.pk3"]}, backup=False)
        MC.atomic_write_json(f, {"pk3s": ["a.pk3", "b.pk3"]}, backup=True)
        with open(f, "w", encoding="utf-8") as h:
            h.write('{"pk3s": ["a.pk3", "b.p')        # truncated by a crash
        cfg, notice = MC.load_settings(f)
        self.assertEqual(cfg, {"pk3s": ["a.pk3"]})
        self.assertIn("restored", notice)
        self.assertTrue(any(".corrupt-" in n for n in os.listdir(self.d)))

    def test_damaged_file_without_bak_is_kept_aside(self):
        f = self.p("cfg.json")
        with open(f, "w", encoding="utf-8") as h:
            h.write("\x00\x00garbage")
        cfg, notice = MC.load_settings(f)
        self.assertEqual(cfg, {})
        self.assertIn("damaged", notice)
        self.assertFalse(os.path.exists(f))
        self.assertTrue(any(".corrupt-" in n for n in os.listdir(self.d)))

    def test_missing_file_is_first_run(self):
        self.assertEqual(MC.load_settings(self.p("none.json")), ({}, None))


class Logging(TempDirCase):
    def test_swallowed_logs_traceback_then_counts(self):
        lg = logging.getLogger("mohaa")
        stream = io.StringIO()
        h = logging.StreamHandler(stream)
        h.setLevel(logging.DEBUG)
        lg.addHandler(h)
        old = lg.level
        lg.setLevel(logging.DEBUG)
        try:
            for _ in range(MC.SWALLOW_LOG_LIMIT + 3):
                try:
                    raise ValueError("boom")
                except ValueError:
                    MC.swallowed()
        finally:
            lg.removeHandler(h)
            lg.setLevel(old)
        out = stream.getvalue()
        self.assertEqual(out.count("Traceback"), MC.SWALLOW_LOG_LIMIT)
        self.assertIn("counted, not logged", out)

    def test_swallowed_outside_except_is_a_no_op(self):
        MC.swallowed()


class PillowGuard(unittest.TestCase):
    def setUp(self):
        try:
            self.Image = MC.pil_image()
        except ImportError as e:
            self.skipTest("Pillow not available: %s" % e)

    def test_floor_and_limit(self):
        ok, why = MC.pil_status()
        self.assertTrue(ok, why)
        self.assertEqual(self.Image.MAX_IMAGE_PIXELS, MC.IMAGE_MAX_PIXELS)

    def test_oversized_image_is_refused(self):
        """A 9000 x 9000 image (81 Mpx > the 67 Mpx limit) must raise, not decode."""
        buf = io.BytesIO()
        old = self.Image.MAX_IMAGE_PIXELS
        self.Image.MAX_IMAGE_PIXELS = None              # allow building the test file itself
        try:
            self.Image.new("1", (9000, 9000)).save(buf, "PNG")
        finally:
            self.Image.MAX_IMAGE_PIXELS = old
        buf.seek(0)
        with self.assertRaises((self.Image.DecompressionBombError, self.Image.DecompressionBombWarning)):
            self.Image.open(buf).load()

    def test_old_pillow_is_refused(self):
        saved = dict(MC._pil_state)
        MC._pil_state.clear()
        try:
            import PIL
            with mock.patch.object(PIL, "__version__", "10.2.0"):
                with self.assertRaises(ImportError) as cm:
                    MC.pil_image()
            self.assertIn("older than", str(cm.exception))
        finally:
            MC._pil_state.clear()
            MC._pil_state.update(saved)


class LauncherPieces(TempDirCase):
    @classmethod
    def setUpClass(cls):
        try:
            import tkinter  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("tkinter missing")
        import mohaa_launcher as ML
        cls.ML = ML

    def stub(self):
        """An object with just what App._extract_one / _safe_target use."""
        import queue
        ML = self.ML

        class Stub:
            _EXTRACT_OK = ML.App._EXTRACT_OK
            _WIN_RESERVED = ML.App._WIN_RESERVED
            _safe_target = ML.App._safe_target
            _extract_one = ML.App._extract_one
        s = Stub()
        s._tmp = self.p("ws")
        os.makedirs(s._tmp)
        s._log_q = queue.Queue()
        return s

    def pak(self, entries):
        z = self.p("test.pk3")
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for n, d in entries.items():
                zf.writestr(n, d)
        return z

    def test_truncated_cache_is_extracted_again(self):
        """Bug 1: a short file left by an earlier crash used to be reused forever."""
        s = self.stub()
        data = os.urandom(50000)
        z = self.pak({"models/a/b.skd": data})
        target = os.path.join(s._tmp, "models", "a", "b.skd")
        os.makedirs(os.path.dirname(target))
        with open(target, "wb") as f:
            f.write(data[:1234])                         # what an interrupted extract left
        with zipfile.ZipFile(z) as zf:
            self.assertEqual(s._extract_one(zf, "models/a/b.skd"), target)
        self.assertEqual(open(target, "rb").read(), data)

    def test_interrupted_extract_leaves_nothing(self):
        """SIMULATED crash mid-extract: the read fails part-way; no file may appear."""
        s = self.stub()
        z = self.pak({"models/a/c.tga": os.urandom(300000)})

        class Dying(io.RawIOBase):
            def __init__(self, inner):
                self.inner, self.n = inner, 0

            def read(self, k=-1):
                self.n += 1
                if self.n > 1:
                    raise OSError("simulated crash")
                return self.inner.read(1000)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        with zipfile.ZipFile(z) as zf:
            real_open = zf.open
            with mock.patch.object(zf, "open", side_effect=lambda n: Dying(real_open(n))):
                with self.assertRaises(OSError):
                    s._extract_one(zf, "models/a/c.tga")
        self.assertFalse(os.path.exists(os.path.join(s._tmp, "models", "a", "c.tga")))

    def test_unsafe_entries_still_refused(self):
        s = self.stub()
        for bad in ("../x.tga", "models/../../x.tga", "C:/x.tga", "models/con.tga", "models/a.exe", "a/b:c.tga"):
            self.assertIsNone(s._safe_target(bad), bad)

    def test_import_has_no_side_effects(self):
        """Importing mohaa_launcher (as the Map Viewer does) must not create output/."""
        root = self.p("inst")
        shutil.copytree(BIN, os.path.join(root, "bin"),
                        ignore=shutil.ignore_patterns("libs*", "__pycache__"))
        code = ("import sys; sys.path.insert(0, %r); import mohaa_launcher, os; "
                "print(os.path.isdir(%r))" % (os.path.join(root, "bin"), os.path.join(root, "output")))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "False")


class Updater(TempDirCase):
    """The update installer, run against a local release zip.
    SIMULATED: the network (mohaa_common.http_get copies the local zip instead)."""

    @classmethod
    def setUpClass(cls):
        try:
            import tkinter  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("tkinter missing")
        import mohaa_launcher as ML
        cls.ML = ML

    def make_install(self):
        root = self.p("install")
        for rp, txt in (("bin/mohaa_launcher.py", "old launcher"), ("bin/mohaa_view.py", "old view"),
                        ("docs/version.txt", "1.0.000\n"), ("output/keep.json", "user data")):
            f = os.path.join(root, rp)
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f, "w", encoding="utf-8") as h:
                h.write(txt)
        return root

    def make_release(self, version_txt):
        z = self.p("release.zip")
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("mohaa-model-viewer-1.0.001/bin/mohaa_launcher.py", "new launcher")
            zf.writestr("mohaa-model-viewer-1.0.001/bin/mohaa_view.py", "new view")
            zf.writestr("mohaa-model-viewer-1.0.001/bin/mohaa_common.py", "new module")
            zf.writestr("mohaa-model-viewer-1.0.001/docs/version.txt", version_txt)
            zf.writestr("mohaa-model-viewer-1.0.001/output/evil.json", "must never be written")
        return z

    def run_update(self, root, release, version="1.0.001", fail_on=None):
        ML = self.ML

        def fake_get(url, ua, timeout=None, dest=None, max_bytes=None, attempts=3):
            shutil.copyfile(release, dest)
            return dest
        real_write = MC.atomic_write_bytes

        def maybe_fail(path, data, backup=False):
            if fail_on and path.endswith(fail_on + ".new"):
                raise OSError("simulated write failure")
            return real_write(path, data, backup=backup)
        app = ML.App.__new__(ML.App)
        with mock.patch.object(ML, "_install_root", return_value=root), \
             mock.patch.object(ML, "DATADIR", os.path.join(root, "output")), \
             mock.patch.object(MC, "http_get", side_effect=fake_get), \
             mock.patch.object(MC, "atomic_write_bytes", side_effect=maybe_fail):
            return app._update_download_and_apply(version)

    def read(self, root, rp):
        with open(os.path.join(root, rp), encoding="utf-8") as f:
            return f.read()

    def test_success_with_numbered_backup(self):
        root = self.make_install()
        res = self.run_update(root, self.make_release("1.0.001\n"))
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.read(root, "bin/mohaa_launcher.py"), "new launcher")
        self.assertEqual(self.read(root, "bin/mohaa_common.py"), "new module")
        self.assertEqual(self.read(root, "output/keep.json"), "user data")
        self.assertFalse(os.path.exists(os.path.join(root, "output", "evil.json")))
        bak = os.path.join(root, "output", "previous-versions", "1")
        self.assertEqual(self.read(bak, "bin/mohaa_launcher.py"), "old launcher")
        log = self.read(os.path.join(root, "output", "previous-versions"), "changelog.txt")
        self.assertTrue(log.startswith("1 - version "), log)
        res2 = self.run_update(root, self.make_release("1.0.001\n"))
        self.assertTrue(res2["ok"])
        self.assertTrue(os.path.isdir(os.path.join(root, "output", "previous-versions", "2")))

    def test_wrong_version_changes_nothing(self):
        root = self.make_install()
        res = self.run_update(root, self.make_release("1.0.999\n"))
        self.assertFalse(res["ok"])
        self.assertIn("nothing was changed", res["error"])
        self.assertEqual(self.read(root, "bin/mohaa_launcher.py"), "old launcher")

    def test_failed_file_rolls_everything_back(self):
        """SIMULATED: one file can't be written; every file already replaced must come back."""
        root = self.make_install()
        res = self.run_update(root, self.make_release("1.0.001\n"), fail_on="mohaa_view.py")
        self.assertFalse(res["ok"])
        self.assertIn("undone", res["error"])
        self.assertEqual(self.read(root, "bin/mohaa_launcher.py"), "old launcher")
        self.assertEqual(self.read(root, "bin/mohaa_view.py"), "old view")
        self.assertEqual(self.read(root, "docs/version.txt"), "1.0.000\n")
        self.assertFalse(os.path.exists(os.path.join(root, "bin", "mohaa_common.py")))

    def test_damaged_zip_is_refused(self):
        root = self.make_install()
        z = self.make_release("1.0.001\n")
        b = bytearray(open(z, "rb").read())
        i = b.find(b"new launcher")
        b[i:i + 3] = b"XXX"                             # CRC no longer matches
        with open(z, "wb") as f:
            f.write(b)
        res = self.run_update(root, z)
        self.assertFalse(res["ok"])
        self.assertEqual(self.read(root, "bin/mohaa_launcher.py"), "old launcher")


class BspSave(TempDirCase):
    def test_save_verifies_then_keeps_bak(self):
        out = self.p("m_mod.bsp")
        node = '{\n"classname" "info_pathnode"\n"origin" "8 8 8"\n}\n'
        MB.write_bsp_entities(bsp_seed(), node, out)
        first = open(out, "rb").read()
        MB.write_bsp_entities(bsp_seed(), node + node, out)
        self.assertEqual(open(out + ".bak", "rb").read(), first)
        self.assertEqual(len(MB.parse_entity_string(MB.bsp_entity_text(open(out, "rb").read()))), 4)

    def test_failed_check_never_reaches_destination(self):
        """SIMULATED: the read-back check fails; the destination must not be created."""
        out = self.p("bad.bsp")
        with mock.patch.object(MB, "parse_entity_string", side_effect=[[], [], []]):
            with self.assertRaises(MB.BspError):
                MB.write_bsp_entities(bsp_seed(), '{\n"classname" "info_pathnode"\n}\n', out)
        self.assertFalse(os.path.exists(out))
        self.assertEqual(os.listdir(self.d), [])


class ChildBuilds(TempDirCase):
    def test_map_build_end_to_end(self):
        """Build a real page from a synthetic .bsp with the real child process and env."""
        src = self.p("tiny.bsp")
        with open(src, "wb") as f:
            f.write(bsp_seed())
        out = self.p("out")
        r = subprocess.run([sys.executable, os.path.join(BIN, "mohaa_map_view.py"), src,
                            "--outdir=" + out, "--no-open"],
                           capture_output=True, text=True, encoding="utf-8", env=MC.child_env())
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        names = os.listdir(out)
        self.assertTrue(any(n.endswith(".html") for n in names), names)
        self.assertTrue(any(n.endswith(".map") for n in names), names)
        self.assertFalse(any(n.endswith(".tmp") for n in names), names)

    def test_non_ascii_name_builds(self):
        """Bug 5: a file name outside the Windows code page must not crash the build.
        SIMULATED Windows console: the child's stdout is forced to cp1252, which is what a
        Windows child gets when its output is piped. Old behaviour (no PYTHONIOENCODING)
        is run first to show the failure, then the launcher's env (MC.child_env)."""
        src = self.p("карта_地图.bsp")
        with open(src, "wb") as f:
            f.write(bsp_seed())
        cmd = [sys.executable, os.path.join(BIN, "mohaa_map_view.py"), src,
               "--outdir=" + self.p("out2"), "--no-open"]
        old_env = dict(os.environ, PYTHONIOENCODING="cp1252")
        r_old = subprocess.run(cmd, capture_output=True, env=old_env)
        r_new = subprocess.run(cmd, capture_output=True, env=MC.child_env())
        self.assertNotEqual(r_old.returncode, 0, "expected the cp1252 child to fail on this name")
        self.assertEqual(r_new.returncode, 0, r_new.stderr[-800:])


if __name__ == "__main__":
    unittest.main(verbosity=2)

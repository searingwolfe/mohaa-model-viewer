# Third-Party Notices & Licensing

## 1. The OpenMOHAA question — read this before choosing a licence

This project's engine behaviour is verified against **OpenMoHAA**
(<https://github.com/openmoh/openmohaa>), which is licensed under the
**GNU General Public License, version 2**. Its `COPYING.txt` is GPLv2, inherited
from the id Tech 3 / Quake III Arena source that id Software released under GPLv2.

The source files here cite OpenMOHAA extensively by file and line
(`cg_tempmodels.cpp:531-557`, `tiki_shared.h:76-79`, `tr_shader.c`, and so on).
Those citations are excellent engineering practice — they are why the renderer
matches the game — but they also document, in writing, that the behaviour was
derived by reading GPLv2 source.

Two things are worth separating:

* **File-format facts are not copyrightable.** That `numBone` sits at offset
  `0x4C`, that a bone record is 72 bytes in SKB, that `SKAN` is the SKC ident —
  these are facts about a data format, and learning them from any source is fine.
* **Translating an implementation is a derivative work.** Copyright law treats
  translation between languages as derivation. Where a routine here follows an
  OpenMOHAA function's logic closely — even reimplemented in Python or
  JavaScript — a court could reasonably regard it as derived from GPLv2 code.

**Recommendation: release this project under GPLv2 (or GPLv2-or-later).**

A `LICENSE` file containing the GPLv2 text is included in this repository for
that purpose. Reasons it is the sensible choice here:

* It removes the ambiguity entirely, at zero cost for a free tool.
* It matches the norms of the OpenMOHAA / MOHAA modding community this tool
  serves, and keeps you welcome in it.
* Every runtime dependency is permissively licensed and therefore GPL-compatible
  (see section 2), so nothing breaks.
* It is the honest reflection of how the code was actually developed.

If you are confident that no routine here is a transliteration — that everything
was written from format documentation and observed behaviour rather than from
the C++ — then a permissive licence such as MIT is defensible. In that case,
consider softening the OpenMOHAA citations from "this is what the code does" to
"this matches the behaviour documented at", and keep a written note of how each
algorithm was derived.

**This is not legal advice.** If the distinction matters to you commercially,
ask a lawyer. If it does not, GPLv2 is the low-effort, low-risk answer.

### What GPLv2 does and does not require of your users

* Users may run, copy, study and modify the program freely.
* Anyone who **distributes** the program or a modified version must pass on the
  source and the same licence.
* It places **no obligation whatsoever on the models, textures or `.pk3` files a
  user opens with it.** Output is the user's own.

## 2. Runtime dependencies

None of these are bundled in this repository; each is installed separately by
`python_installer_updater.bat` or by the user. Their licences are listed so that
anyone redistributing a packaged build knows what to include.

| Component | Role | Licence | GPLv2-compatible |
|---|---|---|---|
| **Python** (CPython) | Interpreter, `tkinter` GUI | PSF License Agreement | Yes |
| **Pillow** | Decodes `.tga` / `.dds` / `.jpg` game textures | MIT-CMU (HPND) | Yes |
| **pythonnet** | .NET bridge for the embedded pane (Windows only, optional) | MIT | Yes |
| **pywebview** (pinned 4.4.1) | WebView host (Windows only, optional) | BSD 3-Clause | Yes |
| **tkwebview2** | Embeds Edge WebView2 in Tk (Windows only, optional) | See the package's own metadata — verify before redistributing a bundled build | Verify |
| **Microsoft Edge WebView2 Runtime** | Renders the 3D pane (Windows only, optional) | Microsoft proprietary redistributable, ships with Windows 10/11 | Not redistributed by this project |

If you ever ship a frozen build (PyInstaller and similar) rather than source,
you must include the licence texts of everything bundled into it, and GPLv2
requires that the corresponding source be available too.

## 3. Game content and trademarks

**No game assets are contained in this repository, and none may be added.**

*Medal of Honor* and *Medal of Honor: Allied Assault* are trademarks of their
respective owners. This project is an unofficial, non-commercial fan tool. It is
not affiliated with, authorised, sponsored or endorsed by Electronic Arts Inc.
or any other rights holder. The trademarks are used solely to identify the game
whose file formats this tool reads, which is nominative fair use.

Users must supply their own legally obtained copy of the game. Do not commit,
attach or redistribute extracted `.pk3` contents, models, textures, sounds or
maps — including in bug reports. The `.gitignore` in this repository is
configured to block the common cases, but it is a safety net, not a substitute
for checking what you commit.

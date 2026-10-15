# Third-Party Notices & Licensing

## 1. Licence and OpenMOHAA

This project is released under the **GNU General Public License, version 2** (see
[`LICENSE`](../LICENSE)).

Its engine behaviour is verified against **OpenMoHAA**
(<https://github.com/openmoh/openmohaa>), which is also GPLv2: its `COPYING.txt` is
inherited from the id Tech 3 / Quake III Arena source that id Software released under
GPLv2.

The source files here cite OpenMOHAA extensively by file and line
(`cg_tempmodels.cpp:531-538`, `tiki_shared.h:76-79`, `tr_shader.c`, and so on), and
several routines follow OpenMOHAA functions closely, reimplemented in Python or
JavaScript. Two things are worth separating:

* **File-format facts are not copyrightable.** That `numBone` sits at a given offset,
  that a bone record has a given size, that `SKAN` is the SKC ident: these are facts
  about a data format, and learning them from any source is fine.
* **Translating an implementation can be a derivative work.** Where a routine follows
  an OpenMOHAA function's logic closely, even in another language, it may be regarded
  as derived from GPLv2 code.

The Map Viewer adds two sources of the same kind: its decompiler follows the id Tech 3
map compiler's geometry and texture code (q3map's `polylib.c` and `map.c`, part of the
Quake III Arena source id Software released under GPLv2), and its built-in table of
entity classes is generated from the `/*QUAKED*/` comments in OpenMoHAA's game code.
MOHRadiant's drawing rules (entity box colours, face shading) were worked out from the
editor itself and are reproduced as behaviour; none of its code is used.

Using GPLv2 for this project settles that question: it matches OpenMOHAA, it fits the
MOHAA / OpenMOHAA modding community, and every runtime dependency is GPL-compatible
(section 2). *This is a plain-language summary, not legal advice.*

### What GPLv2 means for users

* Users may run, copy, study and modify the program freely.
* Anyone who **distributes** the program or a modified version must pass on the
  source and the same licence.
* It places **no obligation whatsoever on the models, maps, textures or `.pk3` files
  a user opens with it**, or on the pages and `.map` files built from them. (Those stay
  the work of whoever made the original; see section 3.)

## 2. Runtime dependencies

Both viewers use the same ones. None of these are bundled in this repository; each is
installed separately by a RUN `.bat` on first launch, by `python_installer_updater.bat`,
or by the user. Their licences are listed so that anyone redistributing a packaged build
knows what to include.

| Component | Role | Licence | GPLv2-compatible |
|---|---|---|---|
| **Python** (CPython) | Interpreter, `tkinter` GUI | PSF License Agreement | Yes |
| **Pillow** | Decodes `.tga` / `.dds` / `.jpg` game textures | MIT-CMU (HPND) | Yes |
| **pythonnet** | .NET bridge for the embedded pane (Windows only, optional) | MIT | Yes |
| **pywebview** (pinned 4.4.1) | WebView host (Windows only, optional) | BSD 3-Clause | Yes |
| **tkwebview2** | Embeds Edge WebView2 in Tk (Windows only, optional) | MIT | Yes |
| **Microsoft Edge WebView2 Runtime** | Renders the 3D pane (Windows only, optional) | Microsoft proprietary redistributable, ships with Windows 10/11 | Not redistributed by this project |
| pywebview / pythonnet dependencies | `bottle`, `proxy_tools`, `clr_loader`, `cffi`, `pycparser`, `typing_extensions` (installed automatically) | MIT, MIT, MIT, MIT, BSD 3-Clause, PSF | Yes |

If you ever ship a frozen build (PyInstaller and similar) rather than source,
you must include the licence texts of everything bundled into it, and GPLv2
requires that the corresponding source be available too.

## 3. Game content and trademarks

**No game assets are contained in this repository, and none may be added.**

*Medal of Honor* and *Medal of Honor: Allied Assault* are trademarks of their
respective owners. This project is an unofficial, non-commercial fan tool. It is
not affiliated with, authorised, sponsored or endorsed by Electronic Arts Inc.
or any other rights holder. The trademarks are used solely to identify the game
whose file formats these tools read, which is nominative fair use.

Users must supply their own legally obtained copy of the game. Do not commit,
attach or redistribute extracted `.pk3` contents, models, textures, sounds or
maps, including in bug reports. A `.map` decompiled from someone else's `.bsp` is
still their work: don't publish one without the author's permission. The
`.gitignore` in this repository is configured to block the common cases, but it is
a safety net, not a substitute for checking what you commit.

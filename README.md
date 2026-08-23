# MOHAA Model Viewer

A browser-based 3D asset viewer for *Medal of Honor: Allied Assault (2002)*, aiming at
exact in-game visual parity across every asset type the engine ships: skeletal
models, animations, vehicles, weapons, projectiles, static props, and the
particle emitters and FX effects that existing tools do not handle.

#### [Jump to: Install instructions](https://github.com/searingwolfe/mohaa-model-viewer#install)<br>

Load your `.pk3` archives, browse the model tree, and open any `.skd` or `.tik`
in a self-contained HTML viewer with animation playback, tag display, texture
resolution through the shader chain, and live particle effects.

> **Screenshot / GIF —** an FX effect or explosion playing in the viewer (the hero shot).

## Why this exists

Plenty of tools open MOHAA's static geometry — vehicles, weapons and props load
fine in LightRay3D or Milkshape 3D. None of them show you a *running* asset: the
particle emitters, the FX scripts, the explosions, a skeletal model actually
playing its animation with its effects firing on the right frames. This viewer
does, rebuilding each effect from the `.tik` / `.shader` commands the way the
engine would, so what you see on screen is what the game draws.

## Features

> **Screenshot —** the launcher with a `.pk3` tree loaded and a model open in the 3D pane.

**Loading & browsing**

* Open one or more `.pk3` archives and navigate the `models/` tree, or drag a
  loose `.skd` / `.tik` straight onto the launcher.
* Loaded paks and preferences are remembered between sessions, with a
  recent-files list, tree search (`Ctrl+F`) and Explorer-style keyboard
  navigation.
* Open a `.tik` in your text editor, or a `.skd` in LightRay3D / Milkshape 3D,
  directly from the launcher (Options → external programs).
* Every opened model is also exported as a Wavefront `.obj` you can open in other 3D tools.

**Rendering & animation**

* Skeletal `.skd` / `.skb` models with textures resolved through the full
  `.shader` chain, plus `.skc` / `.tik` animation playback — play/pause, loop,
  reset, per-frame scrub and a speed control.
* The animation browser follows the model's own `$include` / `includes{}`
  structure, so you can reach every anim the asset can play.
* **Particle emitters, FX scripts and explosions**, rebuilt from the effect
  commands and fired on their real frames — the part other tools skip.
* Hang other models off any bone or tag with **attach-to-bone**, each with its
  own editable scale, offset and angles.

> **Screenshot / GIF —** a skeletal model playing an animation (bonus: a weapon attached to a bone).

**Inspect & tweak**

* Display toggles: Texture, Mesh, Wireframe, Setsizes box, Nodes, Labels, Face
  Anims, Corona orbit and the long-range Tree Sprite stand-in.
* **Edit a model's `setsize` bounding box live** — a pencil toggle on the setsize
  line turns the two `( x y z )` triples into number fields that redraw the red
  box as you type, then revert to the file's original values when you toggle it
  back off.
* Copy the `setsize` line, or any attach-to-bone `scale / offset / angles` row,
  as one flat line in MOHAA `.tik` spacing — ready to paste straight into a
  script.
* Free-look (WASD fly) and Tag-lock (orbit a clicked tag) cameras; tag/bone nodes
  and labels with a Tags-vs-Bones filter; an entity placement-angle
  (pitch / yaw / roll) dial.
* Light / dark theme and a custom backdrop colour, plus a full keyboard-shortcut
  set (press `H` in the viewer).

> **Screenshot —** the live `setsize` box editor, or tag/bone nodes with the Tags-vs-Bones filter.

**Self-contained by design**

* Each generated page is a single `.html` file — textures embedded as `data:`
  URIs, a restrictive Content-Security-Policy, and no network access at all
  (see [Privacy](#privacy) and [Security](#security)).

---

## Requirements

* **Python 3.7 or newer** (3.11+ recommended). Needs the `tkinter` GUI module.
* **Pillow 10.3 or newer** — required; MOHAA textures are `.tga` and nothing else
  decodes them.
* Your own legally obtained copy of the game, for its `.pk3` files.
* Optional, Windows only: an embedded 3D pane instead of a browser tab.

## Install

### Windows

Run **`bin\python_installer_updater.bat`** once. It detects your Windows version and
CPU, installs a suitable Python (Windows 7 → 3.8, Windows 8/8.1 → 3.11,
Windows 10/11 → latest), verifies the installer's Authenticode signature before
running it, and installs the packages.

It deliberately **does not modify your `PATH`** — Python's own installer handles
that, and hand-editing the registry `PATH` is how environments get broken.

Then launch with **`RUN -- Medal of Honor Model Viewer.bat`**, or drag a `.skd` / `.tik` onto it.

If "Smart App Control" blocked the .bat file from opening:
Right-click the .bat file --> Properties --> General tab --> Security: [✓] Unblock file.

### macOS

```sh
brew install python-tk          # or use the python.org installer, which bundles Tk
pip3 install "Pillow>=10.3.0"
python3 bin/mohaa_launcher.py
```

### Linux

```sh
sudo apt install python3-tk     # Debian / Ubuntu / Mint
sudo dnf install python3-tkinter # Fedora / RHEL
sudo pacman -S tk               # Arch

pip3 install "Pillow>=10.3.0"
python3 bin/mohaa_launcher.py
```

The embedded 3D pane is Windows-only. Everywhere else, models open in your
default browser — same viewer, same output.

## Where your files go

| | |
|---|---|
| Settings & console log | the program's `output/` folder (next to `bin/`); in a flat / portable install, the scripts' own folder |
| Built viewers | your chosen output folder (default: `output/models/`) |
| Scratch space | a `mohaaview_*` folder in your system temp directory |

Clear any of them from **Options → Clear built models / Clear %temp% files**.

---

## Privacy

**This program collects nothing and sends nothing.** No telemetry, no analytics,
no crash reporting, and nothing is ever checked or sent automatically. Everything
happens on your machine.

The program uses the network only when you ask it to: **Help → Check for updates**
reads a small version file from this repository and, if you choose, downloads the
newer files from GitHub. (The optional Windows setup script also downloads Python
from python.org and packages from pypi.org when you choose to run it.)

Full notice: [`PRIVACY.md`](docs/PRIVACY.md), or **Help → Privacy & Legal** inside the
program.

## Security

`.pk3` files are ordinary ZIP archives, and downloaded ones should be treated as
untrusted input. The program is hardened accordingly — archive paths are confined
to its workspace, model headers are bounds-checked, parsers are protected against
decompression and expansion bombs, and generated pages escape game-file text and
carry a restrictive Content-Security-Policy.

Found a hole? See [`SECURITY.md`](docs/SECURITY.md). **Please report privately, not in
a public issue**, and please don't attach copyrighted game assets to reports.

## Licence

Released under the **GNU General Public License v2** — see [`LICENSE`](LICENSE).

Engine behaviour is verified against [OpenMoHAA](https://github.com/openmoh/openmohaa),
which is GPLv2. [`THIRD_PARTY_NOTICES.md`](docs/THIRD_PARTY_NOTICES.md) explains that
relationship, why GPLv2 is the appropriate choice here, and lists every
dependency's licence.

## Legal

*Medal of Honor* and *Medal of Honor: Allied Assault* are trademarks of their
respective owners. This is an unofficial, non-commercial fan project. It is
**not affiliated with, authorised, sponsored or endorsed by Electronic Arts Inc.**
or any other rights holder. Those names are used only to identify the game whose
file formats this tool reads.

**No game assets are distributed with this project**, and none may be committed
to it. You must supply your own copy of the game. Do not redistribute extracted
game content.

## Credits

Made by **Searingwolfe**.

Engine reference: the [OpenMoHAA](https://github.com/openmoh/openmohaa) project,
without which matching the original renderer would not have been possible.

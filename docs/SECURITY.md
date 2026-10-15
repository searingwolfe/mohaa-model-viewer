# Security Policy

## Threat model — please read

Both programs exist to open **`.pk3` archives and game files that you supply**:
models in the Model Viewer, `.bsp` and `.map` files in the Map Viewer. A `.pk3` is an
ordinary ZIP file. If you downloaded one (or a map) from a mod site, a Discord server or
a forum, treat it as untrusted input, because that is exactly what it is.

The programs are written on that assumption. Specifically:

| Attack surface | Mitigation |
|---|---|
| Archive entry names (`ZipSlip`) | Every entry is confined to the temporary workspace by `_safe_target()`: components are reduced to plain names, `..`, drive tokens and NTFS alternate-data-stream syntax are rejected, Windows device names are rejected, an extension allow-list is enforced, and the final path is re-checked against the workspace root with `realpath` so symlinks and junctions cannot escape it. |
| Malformed `.skd` / `.skb` / `.skc` headers | Every count read from a file header is bounded by what the file can physically hold, and structural advance offsets must be positive, so a hostile file cannot produce an unbounded loop or allocation. |
| Hostile `.shader` scripts | The block scanner is linear-time and matched with an explicit position, so a crafted shader cannot cause a quadratic parse hang during pak loading. |
| Decompression bombs | Archive entries are capped at 192 MB, whether read into memory or extracted to the workspace, and skipped beyond that. |
| `$include` expansion bombs | Cycle guard, depth cap, **and** a total-output budget, so sibling fan-out cannot exhaust memory. |
| Malformed `.bsp` files | Every lump must lie inside the file, record counts come from the lump sizes rather than from count fields, a brush with more sides than the map compiler allows (300) is skipped, and NaN or infinite numbers are skipped or written as 0. A file that still breaks the reader is reported as damaged, and nothing is written for it. |
| Malformed `.map` text | The page's parser skips a broken primitive up to the next one and lists it as a warning, and rejects patch grids over the engine's 129-point limit and terrain blocks far past the 9 x 9 the editor writes, so a crafted file can't make it allocate without bound. |
| Decompiled `.map` files | A decompile never replaces a `.map` the program didn't write (its own start with a marker line); the mapper's source next to a `.bsp` is kept, and the decompile is saved as `<name>_decompiled.map`. Clear built maps deletes only its own pages and the `.map` files carrying that marker, and only inside its `maps` / `maps_standalone` folders. |
| Game-file text reaching the generated HTML | Model payload and title are escaped for inline-`<script>` embedding. A map page carries the map's text, textures and models base64-encoded in a non-executable block, its title and summary escaped, and shows game-file text only through escaping. Both pages carry a Content-Security-Policy that pins every source to `self`/`file`/`data`/`blob` with `connect-src 'none'`. |
| Configured external programs | Only an existing file at an absolute path is launched, without a shell and with the model or map file as its only argument, so a planted config can't trigger a `PATH` or current-directory lookup or smuggle in extra arguments. |

**No mitigation is perfect.** If you find a way around any of the above, please
report it.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private reporting: **Security → Report a vulnerability** on this
repository. If that option isn't available, open an issue that only asks for a
private contact, without any details of the problem.

Please include:

* what the flaw is and what an attacker gains,
* the affected file(s) and, if you have them, line numbers,
* a minimal reproducer — for archive-handling bugs, the smallest `.pk3` or model
  file that triggers it,
* your platform, Python version and program version.

**Do not attach copyrighted game assets.** A synthetic file that demonstrates the
bug is always preferable and is usually smaller anyway.

### What to expect

This is a volunteer, non-commercial project, so please read these as good-faith
intentions rather than a contractual SLA:

| Stage | Target |
|---|---|
| Acknowledgement | within 7 days |
| Initial assessment | within 14 days |
| Fix or documented mitigation | within 90 days, sooner for anything permitting code execution or file writes outside the workspace |
| Public disclosure | coordinated with you, normally after a fix ships |

Credit will be given in the release notes unless you ask otherwise.

## Supported versions

Only the latest release receives security fixes. There is no long-term support
branch and no back-porting.

## Regulatory note (EU Cyber Resilience Act)

Regulation (EU) 2024/2847 ("CRA") applies to products with digital elements
placed on the EU market. Its vulnerability- and incident-reporting obligations
have applied since **11 September 2026**, and the remaining obligations apply from
**11 December 2027**.

Free and open-source software that is **not supplied in the course of a
commercial activity** is outside the scope of those manufacturer obligations,
and non-commercial open-source developers are not subject to CRA fines. This
project is distributed free of charge, with full source, with no paid edition,
no paid support, no mandatory donation and no collection of personal data — so
it is intended to sit squarely within that exemption.

That status is **not permanent by default**. According to the European
Commission's guidance on the CRA and open source, a project can move into scope
by, among other things: selling the software or a paid edition, monetising
services through it, making donations effectively mandatory for access or for
essential updates, or requiring personal data for purposes beyond security and
interoperability. Purely voluntary donations, sponsorship, public funding and
optional paid consulting or training do not by themselves make a project
commercial, provided the software itself stays freely available.

If this project's distribution model ever changes in one of those directions,
this policy and the CRA position must be revisited first.

*This section is a plain-language summary for contributors, not legal advice.*

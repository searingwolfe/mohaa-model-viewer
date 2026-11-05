# Privacy Notice

This is the same text shown in the program under **Help -> Privacy & Legal**.
If you change one, change the other (`PRIVACY_TEXT` in `mohaa_launcher.py`).

The Map Viewer shows the same notice under its own name, worded for its own files:
`mohaa_map_viewer_config.json`, `output_console_map.log` and `mohaamap_*` temp folders,
its decompiled `.map` files among the working files, and the grid's size and colour and
where the Edit parameters box was left among the display choices (`_PRIVACY_SWAPS` in
`mohaa_map_launcher.py`).

`python tests/check_privacy_sync.py` checks that this file, `PRIVACY_TEXT` and every
`_PRIVACY_SWAPS` entry agree; `--write` regenerates the block below from `PRIVACY_TEXT`.

```
PRIVACY NOTICE  --  MOHAA Model Viewer
Last updated: 4 November 2026

1. THE SHORT VERSION
   This program does not collect, transmit, sell, share or profile anything.
   It contains no telemetry, no analytics, no crash reporting, no advertising
   and no tracking identifiers, and it never checks for updates on its own. The
   program uses the network only when YOU open Help --> Check for updates, and
   the startup scripts only to install missing Python packages (see 3);
   everything else happens entirely on your computer.

2. WHAT IS STORED, AND WHERE
   The program stores six things, all on your own machine, all readable and
   deletable by you at any time:

     a) Settings file  --  mohaa_viewer_config.json
        Written to the program's "output" folder (the one beside the "bin" folder
        that holds the scripts). In a flat / portable install - all files in one
        folder - it sits in that folder instead. Same on Windows, macOS and Linux.
        Contains: the .pk3 paths you loaded, the recent-files list (unless
        Options --> Don't save recent files is on), your chosen output folder,
        theme, window layout, view angles, and the paths of any external
        programs you configured. It contains file paths, which on most systems
        include your user name. The previous copy is kept beside it as a .bak
        file, and a damaged file is set aside as .corrupt-<date>. Options -->
        Reset settings... clears it.

     b) Console log  --  output_console.log, in the same folder as (a).
        A copy of the Output pane, replaced on each launch (the previous
        launch's copy is kept with ".prev" in its name). It contains the file
        paths the program touched, so it too may include your user name.

     c) Program logs  --  the "logs" folder inside the folder of (a).
        A timestamped record of what the program did and of any errors, with
        their technical details, one file for each part of the program. Each
        file is capped at 2 MB, with five older copies kept. Like (b) it
        contains file paths. Options --> Open log folder shows it.

     d) Working files
        A temporary workspace under your system temp folder (mohaaview_*), and
        the generated .html viewers in your chosen output folder. Both are
        removable from File --> Clear built models / Clear %temp% files. On
        Windows, the embedded 3D pane (Microsoft Edge WebView2) also keeps its
        browser files in a "webview2" folder beside (a).

     e) Display choices in the browser
        The viewer pages remember a few display choices (theme, backdrop colour,
        renderer, placement angles, game cvars) in the browser's local storage.
        The embedded pane runs in private mode and forgets them when the program
        closes; in your own browser they stay with that browser's data for local
        files.

     f) Previous versions  --  the "previous-versions" folder beside (a).
        When Help --> Check for updates installs a new version, the files it
        replaces are copied here first, one numbered folder per update, with a
        changelog.txt listing them. Delete them whenever you like.

   None of this is transmitted anywhere. If you want it gone, delete the folders
   above; the program will simply start fresh.

3. NETWORK ACCESS
   The viewer itself makes no network requests. The generated .html page is
   self-contained (textures are embedded as data: URIs) and is served with a
   Content-Security-Policy that blocks outbound connections even if a malformed
   game file were to inject script into it.

   The program reaches the network in only two places, both of which you start
   yourself and neither of which runs in the background:

     - Help --> Check for updates reads a small version file from this project's
       GitHub repository, and, if you choose to install an update, downloads the
       new files from GitHub. This reveals your IP address to GitHub under its
       privacy policy, not this one. It happens only when you open that window and
       click to install; nothing is ever checked automatically.

     - The startup script (MOH Model-Map Viewer (Windows x86-x64).bat, or the .sh
       file on Linux and macOS) installs any missing Python packages from
       pypi.org into the program's own bin folder. On Windows, if no suitable
       Python is found and you agree when asked, it runs
       python_installer_updater.bat, which downloads Python from python.org.
       Both sites apply their own privacy policies.

   The viewer itself makes no other network requests.

   If you open a model in an external web browser rather than the built-in pane,
   that browser is governed by its own privacy policy.

4. YOUR DATA AND THE DEVELOPER
   Because nothing leaves your computer, the developer of this program never
   receives, sees or holds any of your data. There is no account, no sign-in and
   no server. Under the EU/UK GDPR this means the developer is not acting as a
   controller or processor of your personal data through this software, and
   there is correspondingly no data to access, rectify, export or erase from any
   service. You retain full control of the local files listed in section 2.

   For the same reason there is no "sale" or "sharing" of personal information
   within the meaning of the California Consumer Privacy Act, and no personal
   information is collected from anyone, including children (COPPA).

5. CHILDREN
   The program is not directed at children and collects no information from
   anyone of any age.

6. SECURITY
   The program reads .pk3 archives, which are ordinary zip files that you supply.
   Treat downloaded paks as untrusted content. The program is hardened against
   hostile archives (archive paths are confined to the workspace, model headers
   are bounds-checked, and generated pages escape game-file text), but no
   software is perfect. Please report suspected vulnerabilities as described in
   SECURITY.md rather than in a public issue.

7. TRADEMARKS AND GAME CONTENT
   Medal of Honor and Medal of Honor: Allied Assault are trademarks of their
   respective owners. This is an unofficial, non-commercial fan tool. It is not
   affiliated with, authorised, sponsored or endorsed by Electronic Arts Inc. or
   any other rights holder. Trademarks are used only to identify the game whose
   files this tool reads.

   No game assets are included with this program. You must supply your own
   legally obtained copy of the game. Do not redistribute extracted game assets.

8. CHANGES
   Any change to this notice will be reflected here and in PRIVACY.md, with the
   date above updated. Changes reach you when you download or update to a newer
   version.

9. CONTACT
   Questions about this notice: open an issue on the project's GitHub
   repository (github.com/searingwolfe/mohaa-model-viewer).
```

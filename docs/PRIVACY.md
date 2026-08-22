# Privacy Notice

This is the same text shown in the program under **Help -> Privacy & Legal**.
If you change one, change the other (`PRIVACY_TEXT` in `mohaa_launcher.py`).

```
PRIVACY NOTICE  --  MOHAA Model Viewer
Last updated: 22 August 2026

1. THE SHORT VERSION
   This program does not collect, transmit, sell, share or profile anything.
   It contains no telemetry, no analytics, no crash reporting, no advertising
   and no tracking identifiers, and it never checks for updates on its own. The
   only time it uses the network is when YOU open Help --> Check for updates;
   everything else it does happens entirely on your computer.

2. WHAT IS STORED, AND WHERE
   The program writes three things, all on your own machine, all readable and
   deletable by you at any time:

     a) Settings file  --  mohaa_viewer_config.json
        Written to the program's "output" folder (the one beside the "bin" folder
        that holds the scripts). In a flat / portable install - all files in one
        folder - it sits in that folder instead. Same on Windows, macOS and Linux.
        Contains: the .pk3 paths you loaded, your chosen output folder, theme,
        window layout, view angles, and the paths of any external programs you
        configured. It contains file paths, which on most systems include your
        user name.

     b) Console log  --  output_console.log, in the same folder as (a).
        A copy of the Output pane. Overwritten on each launch. It contains the
        file paths the program touched, so it too may include your user name.

     c) Working files
        A temporary workspace under your system temp folder (mohaaview_*), and
        the generated .html viewers in your chosen output folder. Both are
        removable from Options --> Clear %temp% files / Clear built models.

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

     - The optional setup script, python_installer_updater.bat, downloads Python
       from python.org and packages from pypi.org when you choose to run it, under
       those sites' own privacy policies.

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
   Questions about this notice: open an issue on the project's repository, or
   use the contact address given in the repository README.
```

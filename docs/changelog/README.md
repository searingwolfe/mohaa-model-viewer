# Project notes

Background for anyone maintaining or forking the viewer: history, architecture, and the
engine details that took the longest to get right.

| File | What's in it |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | Page revisions (`VIEWER_REV`), cache-floor bumps, and notable fixes with the behaviour they replaced |
| [project-overview.md](project-overview.md) | Goals, repository layout, how a model is built, caching and versions, known issues and open work |
| [development-workflow.md](development-workflow.md) | Checks to run before shipping, values that must change together, how engine references are cited |
| [engine-notes.md](engine-notes.md) | Format, skeleton, TikiScript, shader and WebView2 findings |
| [emitter-commands.md](emitter-commands.md) | Every `.tik` emitter keyword the viewer understands and what it does |
| [sprite-roll-rules.md](sprite-roll-rules.md) | When sprites roll in the engine, how `randomroll` behaves, and how that was verified |

The source files carry the exact OpenMOHAA file and line references beside the code that
depends on them; these notes summarise and link the bigger picture.

---
name: anno
description: Use when the user wants to open or create figure annotations, mind maps, mermaid or D2 diagrams, screenshots, webcam captures, or 3D mesh/simulation exports, or when suggesting visual or mesh documentation. Triggers: Inkscape, Minder, flowchart, sequence, state, class, D2, co-work, cam, ParaView.
---

# anno

Visual notes CLI. Run from **project root** (`notes/` lives here).

Install: `pipx install git+https://github.com/wr1/anno` or `uv tool install git+https://github.com/wr1/anno`; clone: `uv tool install .`. Skill: symlink this file into the runtime skills dir.

## Discover

Treeparse CLI. Infer the branch from `anno -h` names, then **that path only**.

- `anno <path> -h` → one branch
- **`anno -j`** → types, defaults, choices
- install / upgrade / parse fail → rediscover from that output, not memory

On close: clipboard already has the payload; tell the user to paste.

Unwritten (not in `-h`): `anno para new` installs **Anno Selection Comment** + **Anno Array Comment** (shortcuts once: Tools → Manage Custom Shortcuts). Style-name collision: `anno mermaid flowchart sequence`.

## Steno

Mermaid and D2 dumps are **steno**: dense labels, load-bearing nouns, arrows. The graph is the tree. Human notes (`where X?`, `add Y`, questions) stay in comments until implemented.

## Co-work

Every mermaid/d2 open (named or scratch). Command returns immediately; sidecar stays until Done.

- stdout has `preview:` → **1m implement loop** on the `saved :` path
- launch incomplete until that loop is running
- other runtimes: whatever 1m recurring prompt the harness provides
- Grok: `scheduler_create` interval `1m`, `fire_immediately: true`
- sidecar already rerenders; re-run the command only if it is down

```
Co-work on PATH (anno mermaid/d2 implement loop).
Read PATH once. If the human added notes (where X?, add Y, stray lines, questions)
that are not already nodes/edges, implement them in steno: dense labels, connect
node ids, files on edge labels, write a non-empty PATH. Leave a complete dump alone.
Move implemented notes to a ticked done list at the top (mermaid: - [x] <note>
above the fence; d2: # [x] <note>). Drop the original open note. Skip [x] lines.
User corrections win over leftover add-lines. If the file is gone, stop.
If nothing to do, reply exactly: EDITS none
Otherwise: EDITS applied: <one line>.
```

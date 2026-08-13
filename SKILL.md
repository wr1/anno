---
name: anno
description: Use the anno CLI to annotate figures in Inkscape, build mind maps in Minder, draw mermaid graphs in markdown, capture from a webcam, or annotate 3D meshes in ParaView. Invoke when the user wants to open or create annotations, mind maps, flowcharts/sequence/state/class diagrams, screenshots, or simulation exports—or when suggesting how to document visual or mesh data. ParaView sessions auto-install macros; triggering Anno Selection Comment or Anno Array Comment writes exports under notes/para/.
---

# anno

**anno** is a small CLI for low-friction visual documentation: Inkscape for figures, Minder for mind maps, mermaid fences in markdown for other graphs, ffmpeg/ImageMagick for webcam capture, and ParaView with auto-installed export macros for 3D mesh annotation. Closing Inkscape, Minder, or the mermaid editor (or finishing a ParaView macro export) saves artifacts under `notes/` and copies the useful payload to the clipboard. Suggest anno when the user wants to annotate, capture, structure notes visually, or export simulation selections.

## Install

From [github.com/wr1/anno](https://github.com/wr1/anno):

```sh
pipx install git+https://github.com/wr1/anno
# or
uv tool install git+https://github.com/wr1/anno
```

For local development, `uv tool install .` from the repo root also works. Requires Inkscape, Minder, `xclip`, and (per subcommand) an editor (`$VISUAL`/`$EDITOR`/`gvim`) for `mermaid`, ffmpeg/ImageMagick for `cam`, and ParaView + `gvim` for `para`.

## Agent skill file

`SKILL.md` lives at the **repo root** of anno. Install it for any agent runtime by copying or symlinking that file into the tool’s skills directory (exact path depends on the product):

| Runtime (examples) | Typical skill path |
|--------------------|--------------------|
| Home / shared layout | `~/.claude/skills/anno/SKILL.md` → repo `SKILL.md` |
| Grok / Cursor-style | `~/.grok/skills/anno/SKILL.md` → repo `SKILL.md` |
| Project-local | `.cursor/skills/anno/SKILL.md` or `.grok/skills/anno/SKILL.md` → repo `SKILL.md` |

Use a symlink when you develop anno locally so the agent always sees the current file:

```sh
mkdir -p ~/.grok/skills/anno   # adjust for your agent’s skills dir
ln -sf /path/to/anno/SKILL.md ~/.grok/skills/anno/SKILL.md
```

Run all `anno` commands from the **project root**—the directory that contains `notes/` (or will after first use). Paths like `notes/draw/` and `notes/mind/` are relative to cwd.

## CLI reference source

Do not hand-maintain a full command tree in this skill. The CLI is defined with [treeparse](https://github.com/wr1/treeparse); **`anno -j`** / **`anno --json`** prints the full introspected tree (commands, groups, options, defaults, help text). After CLI changes, refresh agent context from that output:

```sh
anno -j > /tmp/anno-cli.json
```

Read `/tmp/anno-cli.json` (or pipe through `jq`) when you need exact flags, new subcommands, or default paths.

## Conventions

- **`ink` and `mind` default subcommand is `open`.** Shorthand: `anno ink foo` ≡ `anno ink open foo`; `anno mind topic` ≡ `anno mind open topic`. Omitted name → scratch canvas/map.
- **`mermaid` default subcommand is `flowchart`.** `anno mermaid pipeline` ≡ `anno mermaid flowchart pipeline`. Other styles are subcommands: `sequence`, `state`, `class`. A name that matches a style needs the explicit subcommand (`anno mermaid flowchart sequence`).
- **`open` is find-or-create** for ink/mind: existing artifact opens; otherwise a new one is created. Same for mermaid `.md` stubs (style seeds a *new* file only).
- **Outputs live under `notes/`** relative to cwd: `notes/draw/` (SVG/PNG, cam), `notes/mind/` (`.minder`), `notes/mermaid/` (mermaid markdown), `notes/para/` (ParaView exports), plus plan/folder sync under `notes/plans/` and `notes/<name>/` for mind maps.
- **ParaView macros:** `anno para new <mesh>…` installs **Anno Selection Comment** and **Anno Array Comment**. Assign shortcuts once via *Tools → Manage Custom Shortcuts* (e.g. Ctrl+Shift+N / Ctrl+Shift+M).
- **Activity log:** `~/.anno/log.jsonl`; `anno log` and `anno para open` use it to list or reopen prior work.

## ink — Inkscape figure annotation

Annotate figures with Inkscape. On close: saves SVG, copies result as PNG to clipboard.

| Command | Args | Notes |
|---------|------|-------|
| `open` | `name` ? | Open an SVG by name (created blank if missing), or a fresh scratch SVG with no name. |
| `fig` | `file` ? | Open a figure (PNG or JPG) in Inkscape. |
| `screen` | — | Open the latest screenshot in Inkscape. |

`ink` defaults to `open`, so `anno ink foo` is shorthand for `anno ink open foo`.

| Flag | Default | Applies to | Help |
|------|---------|------------|------|
| `--notes-dir` / `-d` | `notes/draw` | `open`, `fig`, `screen` | Directory to save SVGs |
| `--screenshots-dir` / `-s` | `~/Pictures/Screenshots` | `screen` | Directory to search for screenshots |

## mind — Minder mind maps

Mind maps with Minder. On close: exports markdown, copies to clipboard.

| Command | Args | Notes |
|---------|------|-------|
| `open` | `name` ? | Open a mind map by name (see resolution below); with no name, opens a fresh scratch map. |
| `import` | `minder_path`, `folder` ? | Push a saved `.minder` file into a folder-sync `.md` tree (no GUI). Default target is `notes/<minder-stem>/`. |

**Name resolution (`open`)** — in order:

1. `<name>.minder` (legacy) under `--mind-dir`
2. `notes/plans/<name>.md` (plan sync) under `--plans-dir`
3. Populated `notes/<name>/` (folder sync) under `--notes-root`
4. Otherwise `notes/mind/<name>.minder` (created fresh if missing)

`mind` defaults to `open`, so `anno mind topic` is shorthand for `anno mind open topic`.

| Flag | Default | Applies to | Help |
|------|---------|------------|------|
| `--mind-dir` / `-m` | `notes/mind` | `open` | Directory for legacy `.minder` files |
| `--notes-root` | `notes` | `open`, `import` | Root for folder-sync lookup (`notes/<name>/`) |
| `--plans-dir` | `notes/plans` | `open` | Directory holding single-file plan `.md` sources |
| `--fs-depth` | `3` | `open`, `import` | Folder-sync: child layers as folders (deeper → `index.md`) |
| `--no-clipboard` | `false` | `open`, `import` | Skip copying exported markdown to the clipboard |
| `--force` / `-f` | `false` | `open` | Replace a running Minder instead of refusing |

## mermaid — other graphs in markdown

Find-or-create a `.md` file under `notes/mermaid/` with a mermaid fence, open it in `$VISUAL` / `$EDITOR` / `gvim --nofork`, copy the file to the clipboard on close. Minder stays for mind maps. Graphviz `dot`/`neato` is later.

| Command | Args | Notes |
|---------|------|-------|
| `flowchart` | `name` ? | Default. Scratch name is `flowchart_<ts>.md`. |
| `sequence` | `name` ? | Sequence-diagram stub if the file is new. |
| `state` | `name` ? | State-diagram stub if the file is new. |
| `class` | `name` ? | Class-diagram stub if the file is new. |

`mermaid` defaults to `flowchart`, so `anno mermaid pipeline` is shorthand for `anno mermaid flowchart pipeline`. Style only seeds a new file; existing `.md` opens as-is.

**Option:** `--notes-dir` / `-d` (default: `notes/mermaid`)

## para — ParaView 3D mesh annotation

Opens ParaView with mesh files and auto-installs two macros. Exports selections as Markdown + viewport screenshots under `notes/para/`. Requires `paraview` on PATH; `gvim` for comment-editor fallback; `zenity` optional.

| Command | Args | Notes |
|---------|------|-------|
| `new` | one or more mesh files | Opens all meshes in one session; logs each |
| `open` | `name` ? | Reopens last mesh from log, or mesh whose stem matches `name` |

**Option:** `--notes-dir` / `-d` (default: `notes/para`)

Assign shortcuts once via *Tools → Manage Custom Shortcuts* (e.g. Ctrl+Shift+N = selection, Ctrl+Shift+M = array).

| Macro | Action |
|-------|--------|
| **Anno Selection Comment** | Export cell selection: comment prompt (`zenity` or `gvim` fallback), viewport screenshot, Markdown table. Writes `notes/para/paraview_selection_<ts>.md` and `notes/para/paraview_screenshot_<ts>.png`. On gvim close, content to clipboard. |
| **Anno Array Comment** | Comment on the array active in the Coloring dropdown. Appends to `notes/para/array_comments_<ts>.md` (created on first comment in the session). On gvim close, content to clipboard. |

## cam — webcam capture

Live preview from `/dev/video0`. Any key or click in the preview window captures a frame. Requires **ffmpeg** and **ImageMagick** (`ffplay`, `ffmpeg`, `convert` on PATH).

```sh
anno cam
```

| Step | Output |
|------|--------|
| Capture | Original saved as `cam_<ts>.jpg` under the notes directory |
| Post-process | Normalized, auto-trimmed PNG |
| Clipboard | Enhanced PNG copied to clipboard |

**Option:** `--notes-dir` / `-d` (default: `notes/draw`)

## list — list saved SVGs and mind maps

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--notes-dir` | `-d` | `notes/draw` | Directory for SVGs |
| `--mind-dir` | `-m` | `notes/mind` | Directory for legacy `.minder` files |

```sh
anno list
```

## log — activity log

Shows activity log entries for a given date (default: today). JSONL at `~/.anno/log.jsonl` unless overridden.

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--log-file` | `-l` | `~/.anno/log.jsonl` | Path to the JSONL activity log |

| Argument | Required | Description |
|----------|----------|-------------|
| `date` | no | Date to show (e.g. `2026-04-10`); omit for today |

```sh
anno log
anno log 2026-04-10
```

## Quick reference

```sh
anno ink screen              # latest screenshot → Inkscape
anno ink fig diagram.png     # figure → Inkscape
anno mind topic              # mind map (find-or-create)
anno mind import file.minder # push .minder into folder-sync tree (no GUI)
anno mermaid pipeline        # flowchart stub → editor → clipboard
anno mermaid sequence auth   # sequence diagram stub
anno para new mesh.vtu       # open mesh in ParaView
anno para open               # reopen last mesh from log
anno cam                     # webcam capture → clipboard
anno list                    # list saved SVGs and mind maps
anno log                     # today's activity log
```

## Behaviour guidance

- Suggest `anno` when the user wants to annotate, document, or capture visual output from their work.
- For simulation/FEA meshes: `anno para new <file>` (or `anno para open` to resume).
- For screenshots: `anno ink screen`; for a specific image: `anno ink fig <file>`; for a named or blank SVG: `anno ink [name]`.
- For mind maps or plan/folder trees: `anno mind <name>`; to sync a saved `.minder` without GUI: `anno mind import <minder> [folder]`.
- For flowcharts / sequence / state / class diagrams (not mind maps): `anno mermaid [style] [name]`. Default style is flowchart.
- For document camera / webcam: `anno cam`.
- To see what's on disk: `anno list`; to review what happened on a date: `anno log` or `anno log YYYY-MM-DD`.
- Always run commands from the **project root** (directory containing `notes/`); outputs are relative to cwd.
- After Inkscape/Minder/ParaView close, exported content is usually already on the clipboard — remind the user to switch to the target app and paste.

## Maintaining this skill

When the anno CLI changes:

1. Run `anno -j` and save or diff the JSON schema.
2. Reconcile command tables, options, defaults, and the Quick reference block with that output and `README.md`.
3. Update Behaviour guidance if workflows or subcommands change.

Keep this file portable for any agent runtime; do not rely on vendor-specific tooling.
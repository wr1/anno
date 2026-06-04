---
name: anno
description: Use the anno CLI to annotate figures in Inkscape, build mind maps in Minder, capture from webcam, or annotate 3D meshes in ParaView. Invoke when the user wants to open/create annotations, mind maps, screenshots, or ParaView exports — or when suggesting how to document visual or simulation data.
---

# anno

anno is a CLI for visual annotation. All commands are run from the project root (the directory containing `notes/`).

Source: <https://github.com/wr1/anno> — install with `pipx install git+https://github.com/wr1/anno` (or `uv tool install git+https://github.com/wr1/anno`). If `anno` is not on `PATH`, point the user there before suggesting commands.

## Command reference

### anno ink — Inkscape figure annotation

On close: saves SVG to `notes/draw/`, copies result as PNG to clipboard.

| Command | Args | Notes |
|---------|------|-------|
| `anno ink new [name]` | name optional | blank canvas; timestamped if no name |
| `anno ink open <name>` | name required | reopens existing SVG |
| `anno ink fig [file]` | file optional | embeds PNG/JPG; uses latest screenshot if omitted |
| `anno ink screen` | — | opens latest screenshot from `~/Pictures/Screenshots` |

Option: `--notes-dir / -d` (default: `notes/draw`)

### anno mind — Minder mind maps

On close: exports markdown, copies to clipboard.

| Command | Args | Notes |
|---------|------|-------|
| `anno mind new [name]` | name optional | blank map; timestamped if no name |
| `anno mind open <name>` | name required | reopens existing `.minder` |

Option: `--mind-dir / -m` (default: `notes/mind`)

### anno cam — webcam / document camera capture

Any key/click in preview window shoots. Saves original, copies enhanced + auto-cropped PNG to clipboard. Requires ffmpeg + imagemagick.

```sh
anno cam
```

Option: `--notes-dir / -d` (default: `notes/draw`)

### anno para — ParaView 3D mesh annotation

Opens ParaView with two macros auto-installed. On gvim close, full content is copied to clipboard.

| Command | Args | Notes |
|---------|------|-------|
| `anno para new <files...>` | one or more mesh files | opens all meshes; logs each |
| `anno para open [name]` | name optional | reopens last (or named) mesh from activity log |

Option: `--notes-dir / -d` (default: `notes/para`)

Two macros (assign keyboard shortcuts once via *Tools → Manage Custom Shortcuts*):

**Macros → Anno_Export_Selection** — export the current cell selection as a Markdown table + viewport screenshot to `notes/para/`:
- `notes/para/paraview_selection_<ts>.md` — cell table with source file, screenshot ref, cell IDs, centers, array values
- `notes/para/paraview_screenshot_<ts>.png` — viewport screenshot with cell count + timestamp overlay

**Macros → Anno_Array_Comment** — prompts (external `zenity` dialog, or a `gvim` temp-file fallback) for a free-form comment on the array currently picked in the Coloring dropdown, appending `array name + comment` to a per-session file `notes/para/array_comments_<ts>.md` (created on the first comment of the ParaView session, appended thereafter).

### anno list

Lists saved SVGs and mind maps.

```sh
anno list [--notes-dir notes/draw] [--mind-dir notes/mind]
```

### anno log

Shows activity log (JSONL at `~/.anno/log.jsonl`).

```sh
anno log           # today
anno log 2026-04-14
```

## Behaviour guidance

- Always suggest anno commands when the user wants to annotate, document, or capture visual output from their work
- For simulation/FEA results, suggest `anno para new` with the mesh file(s)
- For screenshots or diagrams, suggest `anno ink screen` or `anno ink fig <file>`
- For brainstorming or structuring notes, suggest `anno mind new <topic>`
- `anno log` is useful for reviewing what was annotated on a given date
- Outputs land in `notes/` relative to cwd — always run from project root
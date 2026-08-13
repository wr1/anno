# anno

[![CI](https://github.com/wr1/anno/actions/workflows/ci.yml/badge.svg)](https://github.com/wr1/anno/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/wr1/anno)](https://github.com/wr1/anno/releases/latest)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Annotate figures, sketch mind maps, shoot from a webcam, and mark up 3D simulation meshes — then paste the result wherever you need it. anno keeps the steps short: open a tool, work visually, close the window, paste from the clipboard.

<img src="help.svg" alt="anno command overview">

## Install

```sh
pipx install git+https://github.com/wr1/anno
```

Or from a clone:

```sh
uv tool install .
```

Run commands from your project directory. anno saves outputs under a `notes/` folder there (created on first use).

## Inkscape — figures and screenshots

```sh
anno ink screen              # latest screenshot from ~/Pictures/Screenshots
anno ink fig diagram.png     # open a PNG or JPG
anno ink myfigure            # open or create myfigure.svg
anno ink                     # blank scratch canvas
```

Edit in Inkscape, quit with Ctrl+Q. The annotated PNG is on your clipboard; SVG and PNG are saved under `notes/draw/`.

## Webcam / document camera

```sh
anno cam
```

A live preview opens. Press any key or click to capture. The enhanced, trimmed PNG is copied to the clipboard; the original frame is saved under `notes/draw/`.

## Mind maps

```sh
anno mind roadmap            # open or create a map named roadmap
anno mind                    # blank scratch map
```

Edit in [Minder](https://github.com/phase1geo/Minder), close the window. Exported markdown is on the clipboard and saved beside the map.

To sync a `.minder` file into a folder of markdown notes without opening the GUI:

```sh
anno mind import backup.minder
```

## Mermaid — flowcharts and other graphs

```sh
anno mermaid                 # scratch flowchart
anno mermaid pipeline        # find-or-create notes/mermaid/pipeline.md
anno mermaid flowchart api   # same, explicit style
anno mermaid sequence auth
anno mermaid state door
anno mermaid class model
```

Find-or-create a markdown file with a mermaid fence, open it in `$VISUAL` / `$EDITOR` / `gvim`, copy the file to the clipboard on close. Style only seeds a *new* file. A name that matches a style (e.g. `sequence`) needs the explicit subcommand: `anno mermaid flowchart sequence`.

Mind maps stay in Minder. Graphviz `dot`/`neato` is later.

## ParaView — 3D meshes

```sh
anno para new mesh.vtu       # open one or more mesh files
anno para open               # reopen the last mesh from the log
anno para open blade_r1      # reopen by file stem
```

ParaView installs two macros automatically:

| Macro | What it does |
|-------|----------------|
| **Anno Selection Comment** | Comment on the selected cells; writes markdown + a viewport screenshot under `notes/para/` |
| **Anno Array Comment** | Comment on the array used for coloring |

Assign shortcuts once: *Tools → Customize Shortcuts* (e.g. Ctrl+Shift+N for selection, Ctrl+Shift+M for array).

## Browse and review

```sh
anno list                    # saved SVGs and mind maps
anno log                     # what you opened today
anno log 2026-04-10          # activity on a given date
```

## What you need installed

| Feature | Tools on your PATH |
|---------|-------------------|
| Figures | [Inkscape](https://inkscape.org/) |
| Mind maps | [Minder](https://github.com/phase1geo/Minder) (`com.github.phase1geo.minder`) |
| Clipboard (Linux) | `xclip` |
| Webcam | `ffmpeg`, `ffplay`, ImageMagick `convert` |
| Mermaid | `$VISUAL` or `$EDITOR`, or `gvim` |
| ParaView | `paraview`, `gvim` (optional `zenity` for dialog prompts) |

## Options

Most subcommands accept `--notes-dir` or `--mind-dir` if you keep artifacts somewhere other than the defaults under `notes/`. Run `anno --help` or `anno ink --help` for the full tree.

## Development

```sh
uv sync
uv run pre-commit install
uv run pytest
```

## License

MIT. See [LICENSE](LICENSE).

# anno

[![CI](https://github.com/wr1/anno/actions/workflows/ci.yml/badge.svg)](https://github.com/wr1/anno/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/wr1/anno)](https://github.com/wr1/anno/releases/latest)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)

CLI for annotating figures in Inkscape, building mind maps in Minder, capturing from a webcam or document camera, and annotating 3D meshes in ParaView.

An ergonomics experiment for working with visual data — minimal friction from capture to clipboard.

<img src="help.svg" alt="CLI help output">

## Install

```sh
uv tool install .
```

## Daily workflow

Two terminals side by side — one for anno, one for your editor or chat.

**Annotate a screenshot or figure:**
```sh
anno ink screen           # grabs latest screenshot → Inkscape
anno ink fig diagram.png  # specific file → Inkscape
anno ink                  # blank scratch canvas → Inkscape
anno ink notes            # open notes.svg (created blank if new)
# annotate, then Ctrl+Q
# switch to target app, paste — PNG is already in clipboard
```

**Shoot from document camera:**
```sh
anno cam             # live preview opens; any key or click shoots
# original saved to notes/draw/
# enhanced + auto-cropped PNG copied to clipboard — just paste
```

**Mind map:**
```sh
anno mind topic       # open topic (created blank if new) → Minder
anno mind             # blank scratch map → Minder
# edit, close Minder
# paste — markdown is already in clipboard
```

`anno mind <name>` resolves the name in order: a legacy `<name>.minder`, a
single-file plan at `notes/plans/<name>.md`, a populated `notes/<name>/` folder
tree, otherwise a fresh map under `notes/mind/`. So the same command edits a
plan or a folder of notes as a mind map and writes the changes back on close.
(`ink` and `mind` default to `open`, so the verb is optional — `anno mind topic`
is `anno mind open topic`.)

**Annotate a 3D mesh in ParaView:**
```sh
anno para new mesh.vtu  # opens ParaView with export macro installed
anno para open         # reopen last mesh
anno para open blade_r1 # reopen specific mesh by name
# select cells interactively, then:
# Macros → Anno Selection Comment
# → saves Markdown + screenshot to notes/para/, opens in gvim
# → close gvim → full content copied to clipboard
# (Anno Array Comment does the same for the whole coloring array)
```

To set a keyboard shortcut (one-time):
1. Open ParaView via `anno para <file>`
2. Tools → Customize Shortcuts
3. Search `Anno Selection Comment`, click it, press your key (e.g. Ctrl+Shift+N)

**Review what you did today:**
```sh
anno log             # activity log for today
anno log 2026-04-10  # specific date
anno list            # all saved SVGs and mind maps
```

## Commands

```sh
anno ink [name]           # open SVG (created blank if new); no name → scratch
anno ink fig [file]       # embed PNG/JPG into SVG, open in Inkscape
anno ink screen           # use latest screenshot as figure
anno mind [name]          # open mind map (created if new); no name → scratch
anno mind import <minder> # apply a saved .minder to its folder tree (no GUI)
anno cam                  # webcam capture → enhanced PNG to clipboard
anno para new <file>      # open mesh in ParaView
anno para open [name]     # reopen last (or named) mesh from log
anno list                 # list annotations and mind maps
anno log [date]           # show activity log (default: today)
```

`ink` and `mind` use `open` as their default subcommand, so `anno ink foo` and
`anno mind foo` are shorthand for `anno ink open foo` / `anno mind open foo`.
`open` is find-or-create: it opens an existing annotation or makes a new one,
absorbing the old `new` command.

Options like `--notes-dir`, `--mind-dir`, and `--screenshots-dir` are available on the relevant subcommands.

## Requirements

- [Inkscape](https://inkscape.org/) (`inkscape` on PATH)
- [Minder](https://github.com/phase1geo/Minder) (`com.github.phase1geo.minder` on PATH)
- `xclip` for clipboard support on Linux
- `ffmpeg` and ImageMagick (`ffplay`, `ffmpeg`, `convert` on PATH) for `anno cam`
- [ParaView](https://www.paraview.org/) (`paraview` on PATH) and `gvim` for `anno para`

## Development

```sh
uv sync
uv run pre-commit install   # ruff lint + format on every commit
uv run ruff check src/
uv run ruff format src/
```

CI runs the same checks on every push and PR to `main`.

# anno

Quick CLI for annotating figures in Inkscape and building mind maps in Minder.

```
anno
├── ink
│   ├── fig <file>   open a PNG or JPG in Inkscape, save SVG, copy result to clipboard
│   └── screen       annotate the latest screenshot from ~/Pictures/Screenshots
├── mind
│   ├── new          open a blank mind map in Minder, export markdown to clipboard on exit
│   └── open <name>  reopen an existing mind map by name
└── list             list saved SVGs and mind maps
```

## Install

```sh
uv tool install .
```

## Usage

```sh
anno ink fig diagram.png
anno ink screen
anno mind new
anno mind open issue
anno list
```

Options like `--notes-dir`, `--mind-dir`, and `--screenshots-dir` are available on the relevant subcommands.

## Requirements

- [Inkscape](https://inkscape.org/) (`inkscape` on PATH)
- [Minder](https://github.com/phase1geo/Minder) (`com.github.phase1geo.minder` on PATH)
- `xclip` for clipboard support on Linux

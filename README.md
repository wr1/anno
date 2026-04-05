# anno

Quick CLI for annotating figures in Inkscape and building mind maps in Minder.

```ansi
[1mUsage: anno [0m[1;33m...[0m[1m [0m[1;38;2;45;45;45m [0m[1;38;2;45;45;45m([0m[1;38;2;45;45;45m--json, -j, --help, -h[0m[1;38;2;45;45;45m)[0m
[1;38;2;230;237;243mDescription: Quick CLI for annotating figures in Inkscape and building mind maps in Minder.[0m
[1;2;38;2;210;168;255manno[0m[38;2;48;54;61m──────────────────────────────[0m[2;38;2;139;148;158mQuick CLI for annotating figures in Inkscape and building mind maps in Minder.[0m
[38;2;48;54;61m├── [0m[1;38;2;121;192;255mink[0m[38;2;48;54;61m───────────────────────────[0m[38;2;139;148;158mAnnotate figures with Inkscape. On close: saves SVG, copies result as PNG to[0m
[38;2;48;54;61m│   [0m                              [38;2;139;148;158mclipboard.[0m
[38;2;48;54;61m│   [0m[38;2;48;54;61m├── [0m[38;2;165;214;255mfig[0m [38;2;255;166;87m[FILE][0m[38;2;48;54;61m────────────────[0m[38;2;139;148;158mOpen a figure (PNG or JPG) in Inkscape.[0m
[38;2;48;54;61m│   [0m[38;2;48;54;61m│   [0m[38;2;48;54;61m└── [0m[38;2;255;123;114m--notes-dir, -d[0m[38;2;48;54;61m───────[0m[3;38;2;255;123;114mDirectory to save SVGs[0m[1;2;37m (default: notes/draw)[0m
[38;2;48;54;61m│   [0m[38;2;48;54;61m└── [0m[38;2;165;214;255mscreen[0m[38;2;48;54;61m────────────────────[0m[38;2;139;148;158mOpen the latest screenshot in Inkscape.[0m
[38;2;48;54;61m│   [0m[38;2;48;54;61m    [0m[38;2;48;54;61m├── [0m[38;2;255;123;114m--notes-dir, -d[0m[38;2;48;54;61m───────[0m[3;38;2;255;123;114mDirectory to save SVGs[0m[1;2;37m (default: notes/draw)[0m
[38;2;48;54;61m│   [0m[38;2;48;54;61m    [0m[38;2;48;54;61m└── [0m[38;2;255;123;114m--screenshots-dir, -s[0m[38;2;48;54;61m─[0m[3;38;2;255;123;114mDirectory to search for screenshots[0m[1;2;37m (default: /home/wr1/Pictures/Screenshots)[0m
[38;2;48;54;61m├── [0m[1;38;2;121;192;255mmind[0m[38;2;48;54;61m──────────────────────────[0m[38;2;139;148;158mMind maps with Minder. On close: exports markdown, copies to clipboard.[0m
[38;2;48;54;61m│   [0m[38;2;48;54;61m├── [0m[38;2;165;214;255mnew[0m[38;2;48;54;61m───────────────────────[0m[38;2;139;148;158mOpen a new blank mind map in Minder.[0m
[38;2;48;54;61m│   [0m[38;2;48;54;61m│   [0m[38;2;48;54;61m└── [0m[38;2;255;123;114m--mind-dir, -m[0m[38;2;48;54;61m────────[0m[3;38;2;255;123;114mDirectory for mind maps[0m[1;2;37m (default: notes/mind)[0m
[38;2;48;54;61m│   [0m[38;2;48;54;61m└── [0m[38;2;165;214;255mopen[0m [38;2;255;166;87m[NAME][0m[38;2;48;54;61m───────────────[0m[38;2;139;148;158mOpen an existing mind map by name.[0m
[38;2;48;54;61m│   [0m[38;2;48;54;61m    [0m[38;2;48;54;61m└── [0m[38;2;255;123;114m--mind-dir, -m[0m[38;2;48;54;61m────────[0m[3;38;2;255;123;114mDirectory for mind maps[0m[1;2;37m (default: notes/mind)[0m
[38;2;48;54;61m└── [0m[38;2;165;214;255mlist[0m[38;2;48;54;61m──────────────────────────[0m[38;2;139;148;158mList saved annotations and mind maps.[0m
[38;2;48;54;61m    [0m[38;2;48;54;61m├── [0m[38;2;255;123;114m--notes-dir, -d[0m[38;2;48;54;61m───────────[0m[3;38;2;255;123;114mDirectory to save SVGs[0m[1;2;37m (default: notes/draw)[0m
[38;2;48;54;61m    [0m[38;2;48;54;61m└── [0m[38;2;255;123;114m--mind-dir, -m[0m[38;2;48;54;61m────────────[0m[3;38;2;255;123;114mDirectory for mind maps[0m[1;2;37m (default: notes/mind)[0m
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

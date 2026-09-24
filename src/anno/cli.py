from treeparse import argument, cli, color_config, command, group, option
from treeparse.utils.color_config import color_theme

from anno.activity_log import cmd_log
from anno.cam import cmd_cam
from anno.constants import (
    DEFAULT_D2_DIR,
    DEFAULT_DRAW_DIR,
    DEFAULT_MERMAID_DIR,
    DEFAULT_MIND_DIR,
    DEFAULT_PARA_NOTES_DIR,
)
from anno.d2 import cmd_d2_check, cmd_d2_open
from anno.ink import cmd_ink_fig, cmd_ink_open, cmd_ink_screen
from anno.listing import cmd_list
from anno.mermaid import (
    cmd_mermaid_class,
    cmd_mermaid_flowchart,
    cmd_mermaid_sequence,
    cmd_mermaid_state,
)
from anno.mind.sync import cmd_mind_import, cmd_mind_open
from anno.para_launch import cmd_para_new, cmd_para_open

app = cli(
    name="anno",
    help=(
        "CLI for annotating figures in Inkscape, building mind maps in Minder, "
        "drawing mermaid or D2 graphs, capturing from webcam, "
        "and annotating 3D meshes in ParaView."
    ),
    line_connect=True,
    show_types=False,
    show_defaults=True,
    theme=color_theme.GITHUB,
    colors=color_config.from_theme(color_theme.GITHUB),
)

_notes_option = option(
    flags=["--notes-dir", "-d"],
    dest="notes_dir",
    arg_type=str,
    default=str(DEFAULT_DRAW_DIR),
    help="Directory for Inkscape SVGs and PNGs",
    sort_key=10,
)
_cam_notes_option = option(
    flags=["--notes-dir", "-d"],
    dest="notes_dir",
    arg_type=str,
    default=str(DEFAULT_DRAW_DIR),
    help="Directory to save webcam captures",
    sort_key=10,
)
_mind_dir_option = option(
    flags=["--mind-dir", "-m"],
    dest="mind_dir",
    arg_type=str,
    default=str(DEFAULT_MIND_DIR),
    help="Directory for legacy .minder files",
    sort_key=10,
)
_template_option = option(
    flags=["--template", "-t"],
    dest="template",
    arg_type=str,
    default="",
    help="Seed a fresh map from a template (e.g. 'software'). Ignored when opening existing content.",
    sort_key=16,
)
_d2_notes_option = option(
    flags=["--notes-dir", "-d"],
    dest="notes_dir",
    arg_type=str,
    default=str(DEFAULT_D2_DIR),
    help="Directory to save D2 diagrams",
    sort_key=10,
)
_mermaid_notes_option = option(
    flags=["--notes-dir", "-d"],
    dest="notes_dir",
    arg_type=str,
    default=str(DEFAULT_MERMAID_DIR),
    help="Directory to save mermaid markdown",
    sort_key=10,
)
_para_notes_option = option(
    flags=["--notes-dir", "-d"],
    dest="notes_dir",
    arg_type=str,
    default=str(DEFAULT_PARA_NOTES_DIR),
    help="Directory to save ParaView exports",
    sort_key=10,
)
ink_group = group(
    name="ink",
    help="Annotate figures with Inkscape. On close: saves SVG, copies result as PNG to clipboard.",
    default="open",
)
ink_group.commands.append(
    command(
        name="open",
        help="Open an SVG by name (created blank if missing), or a fresh scratch SVG with no name.",
        callback=cmd_ink_open,
        arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_notes_option],
    )
)
ink_group.commands.append(
    command(
        name="fig",
        help="Open a figure (PNG or JPG) in Inkscape.",
        callback=cmd_ink_fig,
        arguments=[argument(name="file", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_notes_option],
    )
)
ink_group.commands.append(
    command(
        name="screen",
        help="Open the latest screenshot in Inkscape.",
        callback=cmd_ink_screen,
        options=[_notes_option],
    )
)
app.subgroups.append(ink_group)

mind_group = group(
    name="mind",
    help="Mind maps with Minder. On close: exports markdown, copies to clipboard.",
    default="open",
)
mind_group.commands.append(
    command(
        name="open",
        help=(
            "Open a mind map by name. Resolves in order: <name>.minder suffix (legacy), "
            "notes/plans/<name>.md (plan sync), populated notes/<name>/ (folder sync), "
            "otherwise notes/mind/<name>.minder (created fresh if missing). "
            "With no name, opens a fresh scratch map."
        ),
        callback=cmd_mind_open,
        arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[
            _mind_dir_option,
            _template_option,
        ],
    )
)
mind_group.commands.append(
    command(
        name="import",
        help=(
            "Push a saved .minder file into a folder-sync .md tree (no GUI). Default target is notes/<minder-stem>/."
        ),
        callback=cmd_mind_import,
        arguments=[
            argument(name="minder_path", arg_type=str, sort_key=0),
            argument(name="folder", arg_type=str, nargs="?", default="", sort_key=1),
        ],
    )
)
app.subgroups.append(mind_group)

mermaid_group = group(
    name="mermaid",
    help="Mermaid graphs in markdown. On close: copies .md to clipboard.",
    default="flowchart",
)
for _style, _cb, _help in (
    ("flowchart", cmd_mermaid_flowchart, "Find-or-create a mermaid flowchart .md and open it in an editor."),
    ("sequence", cmd_mermaid_sequence, "Find-or-create a mermaid sequence diagram .md and open it in an editor."),
    ("state", cmd_mermaid_state, "Find-or-create a mermaid state diagram .md and open it in an editor."),
    ("class", cmd_mermaid_class, "Find-or-create a mermaid class diagram .md and open it in an editor."),
):
    mermaid_group.commands.append(
        command(
            name=_style,
            help=_help,
            callback=_cb,
            arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
            options=[_mermaid_notes_option],
        )
    )
app.subgroups.append(mermaid_group)

d2_group = group(
    name="d2",
    help="D2 diagrams. Find-or-create a .d2 file and open a live preview.",
    default="open",
)
d2_group.commands.append(
    command(
        name="open",
        help="Find-or-create a .d2 diagram, compile-check it, then open the live preview.",
        callback=cmd_d2_open,
        arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[
            _d2_notes_option,
            option(
                flags=["--force", "-f"],
                dest="force",
                arg_type=bool,
                default=False,
                help="Open the preview even if compile-check fails",
                sort_key=11,
            ),
        ],
    )
)
d2_group.commands.append(
    command(
        name="check",
        help="Full-compile a .d2 file (d2 → SVG). Catches markdown errors validate misses.",
        callback=cmd_d2_check,
        arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_d2_notes_option],
    )
)
app.subgroups.append(d2_group)

app.commands.append(
    command(
        name="cam",
        help=(
            "Capture from webcam. Any key/click in preview window shoots; saves original, "
            "copies enhanced PNG to clipboard. Requires ffmpeg + imagemagick."
        ),
        callback=cmd_cam,
        options=[_cam_notes_option],
    )
)

para_group = group(
    name="para",
    help="3D mesh annotation in ParaView. Exports selections as Markdown + screenshot to notes/para/.",
)
para_group.commands.append(
    command(
        name="new",
        help="Open one or more meshes in ParaView.",
        callback=cmd_para_new,
        arguments=[argument(name="files", nargs="+", sort_key=0)],
        options=[_para_notes_option],
    )
)
para_group.commands.append(
    command(
        name="open",
        help="Reopen last (or named) mesh from activity log.",
        callback=cmd_para_open,
        arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_para_notes_option],
    )
)
app.subgroups.append(para_group)

app.commands.append(
    command(
        name="list",
        help="List saved annotations, mind maps, mermaid graphs, and D2 diagrams.",
        callback=cmd_list,
    )
)

app.commands.append(
    command(
        name="log",
        help="Show activity log for a given date (default: today).",
        callback=cmd_log,
        arguments=[argument(name="date", arg_type=str, nargs="?", default=None, sort_key=0)],
    )
)


def main() -> None:
    app.run()

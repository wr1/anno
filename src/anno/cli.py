from treeparse import argument, cli, color_config, command, group, option
from treeparse.utils.color_config import color_theme

from anno.activity_log import cmd_log
from anno.cam import cmd_cam
from anno.constants import (
    DEFAULT_FS_DEPTH,
    DEFAULT_LOG_FILE,
    DEFAULT_MIND_DIR,
    DEFAULT_NOTES_DIR,
    DEFAULT_NOTES_ROOT,
    DEFAULT_PARA_NOTES_DIR,
    DEFAULT_PLANS_DIR,
    DEFAULT_SCREENSHOTS_DIR,
)
from anno.ink import cmd_ink_fig, cmd_ink_open, cmd_ink_screen
from anno.listing import cmd_list
from anno.mind.sync import cmd_mind_import, cmd_mind_open
from anno.para_launch import cmd_para_new, cmd_para_open

app = cli(
    name="anno",
    help=(
        "Quick CLI for annotating figures in Inkscape, building mind maps in Minder, "
        "capturing from webcam, and annotating 3D meshes in ParaView."
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
    default=str(DEFAULT_NOTES_DIR),
    help="Directory to save SVGs",
    sort_key=10,
)
_screenshots_option = option(
    flags=["--screenshots-dir", "-s"],
    dest="screenshots_dir",
    arg_type=str,
    default=str(DEFAULT_SCREENSHOTS_DIR),
    help="Directory to search for screenshots",
    sort_key=11,
)
_mind_dir_option = option(
    flags=["--mind-dir", "-m"],
    dest="mind_dir",
    arg_type=str,
    default=str(DEFAULT_MIND_DIR),
    help="Directory for legacy .minder files",
    sort_key=10,
)
_notes_root_option = option(
    flags=["--notes-root"],
    dest="notes_root",
    arg_type=str,
    default=str(DEFAULT_NOTES_ROOT),
    help="Root for folder-sync lookup (notes/<name>/)",
    sort_key=11,
)
_plans_dir_option = option(
    flags=["--plans-dir"],
    dest="plans_dir",
    arg_type=str,
    default=str(DEFAULT_PLANS_DIR),
    help="Directory holding single-file plan .md sources",
    sort_key=12,
)
_fs_depth_option = option(
    flags=["--fs-depth"],
    dest="fs_depth",
    arg_type=int,
    default=DEFAULT_FS_DEPTH,
    help="Folder-sync: # of child layers stored as folders (deeper → index.md)",
    sort_key=13,
)
_no_clipboard_option = option(
    flags=["--no-clipboard"],
    dest="no_clipboard",
    arg_type=bool,
    default=False,
    help="Skip copying exported markdown to the clipboard",
    sort_key=14,
)
_force_option = option(
    flags=["--force", "-f"],
    dest="force",
    arg_type=bool,
    default=False,
    help="Replace a running Minder instead of refusing (kills the open window)",
    sort_key=15,
)
_para_notes_option = option(
    flags=["--notes-dir", "-d"],
    dest="notes_dir",
    arg_type=str,
    default=str(DEFAULT_PARA_NOTES_DIR),
    help="Directory to save ParaView exports",
    sort_key=10,
)
_log_option = option(
    flags=["--log-file", "-l"],
    dest="log_file",
    arg_type=str,
    default=str(DEFAULT_LOG_FILE),
    help="Path to the JSONL activity log",
    sort_key=12,
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
        options=[_notes_option, _screenshots_option],
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
            _notes_root_option,
            _plans_dir_option,
            _fs_depth_option,
            _no_clipboard_option,
            _force_option,
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
        options=[
            _notes_root_option,
            _fs_depth_option,
            _no_clipboard_option,
        ],
    )
)
app.subgroups.append(mind_group)

app.commands.append(
    command(
        name="cam",
        help=(
            "Capture from webcam. Any key/click in preview window shoots; saves original, "
            "copies enhanced PNG to clipboard. Requires ffmpeg + imagemagick."
        ),
        callback=cmd_cam,
        options=[_notes_option],
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
        help="List saved annotations and mind maps.",
        callback=cmd_list,
        options=[_notes_option, _mind_dir_option],
    )
)

app.commands.append(
    command(
        name="log",
        help="Show activity log for a given date (default: today).",
        callback=cmd_log,
        arguments=[argument(name="date", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_log_option],
    )
)


def main() -> None:
    app.run()

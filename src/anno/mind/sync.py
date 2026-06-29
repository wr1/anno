import sys
import tempfile
from datetime import datetime
from pathlib import Path

from anno.clipboard import copy_text_to_clipboard
from anno.constants import (
    DEFAULT_FS_DEPTH,
    DEFAULT_MIND_DIR,
    DEFAULT_NOTES_ROOT,
    DEFAULT_PLANS_DIR,
)
from anno.log_util import log_activity
from anno.mind.folder import folder_has_content, folder_to_tree, tree_to_folder
from anno.mind.process import (
    minder_export_markdown,
    minder_launch_gui,
    refuse_if_minder_running,
    run_minder,
    save_recovery_minder,
)
from anno.mind.templates import TemplateNotFoundError, seed_minder
from anno.mind.tree import (
    MindNode,
    flatten,
    parse_bullets_markdown,
    parse_headings_markdown,
    tree_to_headings_markdown,
    tree_to_minder_xml,
    tree_to_numbered_markdown,
)


def resolve_open_target(
    name: str,
    mind_dir: Path,
    notes_root: Path,
    plans_dir: Path,
) -> tuple[str, Path]:
    """Return (mode, path). Mode is "legacy", "plan", "folder", or "new".

    Resolution order:
      1. *.minder suffix       → legacy at <mind_dir>/<name>
      2. plans_dir/<name>.md   → plan smart sync
      3. populated notes/<name>/ → folder smart sync
      4. otherwise             → new map at <mind_dir>/<name>.minder
         (opens an existing one if it's already there; creates fresh if not).

    Rationale for (4): if there's no existing source content, the folder-sync
    round-trip would write the working .minder into a tempdir, launch Minder,
    then export back. Anything that interrupts that round-trip — single-instance
    forwarding, a crash, the user closing without saving — loses the freshly
    built map because the tempdir is gone. Falling through to a stable
    <mind_dir>/<name>.minder location preserves the user's work in every case;
    `anno mind import` can push it into a folder later if desired.
    """
    if name.endswith(".minder"):
        return ("legacy", mind_dir / name)
    plan_md = plans_dir / f"{name}.md"
    if plan_md.is_file():
        return ("plan", plan_md.resolve())
    folder = notes_root / name
    if folder_has_content(folder):
        return ("folder", folder.resolve())
    return ("new", (mind_dir / f"{name}.minder").resolve())


def template_applies(mode: str, target: Path) -> bool:
    """True when ``--template`` should seed content for this open target."""
    if mode == "new":
        return not target.exists()
    if mode == "plan":
        return not target.read_text().strip()
    return False


def run_minder_smart_sync_plan(
    plan_md: Path,
    copy_clipboard: bool,
    force: bool = False,
    template: str = "",
) -> None:
    print(f"mode   : plan sync ({plan_md})")
    with tempfile.TemporaryDirectory(prefix="anno-plan-") as td:
        tmp_minder = Path(td) / f"{plan_md.stem}.minder"
        body = plan_md.read_text() if plan_md.exists() else ""
        if body.strip():
            tree = parse_headings_markdown(body)
            tmp_minder.write_text(tree_to_minder_xml(tree))
            in_count = len(flatten(tree)) - 1
            print(f"import : {in_count} nodes from {plan_md.name}")
        else:
            seed_minder(tmp_minder, root_title=plan_md.stem, template=template)
            in_count = 0
            label = f"template '{template}'" if template else f"root '{plan_md.stem}'"
            print(f"import : empty plan, seeded {label}")
        try:
            minder_launch_gui(tmp_minder, force)
        except RuntimeError as exc:
            recovery = save_recovery_minder(tmp_minder, plan_md.stem)
            sys.exit(
                f"error  : {exc}\nrecovery: working .minder copied to {recovery}\n          {plan_md} is unchanged."
            )
        print("export : reading tree back from Minder…", flush=True)
        log_activity("mind_export", tmp_minder)
        exported_md = tmp_minder.with_suffix(".md")
        try:
            minder_export_markdown(tmp_minder, exported_md)
        except RuntimeError as exc:
            recovery = save_recovery_minder(tmp_minder, plan_md.stem)
            sys.exit(
                f"error  : {exc}\nrecovery: working .minder copied to {recovery}\n          {plan_md} is unchanged."
            )
        out_tree = parse_bullets_markdown(exported_md.read_text())
        if in_count > 0 and len(flatten(out_tree)) - 1 == 0:
            recovery = save_recovery_minder(tmp_minder, plan_md.stem)
            sys.exit(
                f"error  : Minder returned an empty tree from a {in_count}-node "
                f"source; refusing to wipe {plan_md}.\n"
                f"recovery: working .minder copied to {recovery}."
            )
        plan_md.parent.mkdir(parents=True, exist_ok=True)
        plan_md.write_text(tree_to_headings_markdown(out_tree))
        print(f"saved  : {plan_md}")
        if copy_clipboard:
            copy_text_to_clipboard(tree_to_numbered_markdown(out_tree))
            print("copied : markdown to clipboard")


def push_minder_to_folder(
    minder_file: Path,
    root_dir: Path,
    fs_depth: int,
) -> MindNode:
    """Export `minder_file` and write the resulting tree into `root_dir`.

    Refuses to wipe a non-empty source: if Minder exports an empty tree
    while `root_dir` already has content, that's overwhelmingly a tooling
    failure (Minder didn't save, headless export glitched), not the user
    deliberately deleting every node — so we raise instead of obeying it."""
    with tempfile.TemporaryDirectory(prefix="anno-export-") as td:
        md_file = Path(td) / f"{minder_file.stem}.md"
        minder_export_markdown(minder_file, md_file)
        out_tree = parse_bullets_markdown(md_file.read_text())
    existing_tree, ingested = folder_to_tree(root_dir, fs_depth)
    in_count = len(flatten(existing_tree)) - 1
    out_count = len(flatten(out_tree)) - 1
    if out_count == 0 and in_count > 0:
        raise RuntimeError(
            f"Minder returned an empty tree but {root_dir} contained {in_count} node(s) — aborting to avoid data loss."
        )
    # `ingested` are the index.md paths we read on entry. Deleting them
    # before writing lets us migrate content to the canonical leaf-depth
    # layout cleanly; the writer will recreate index.md where needed.
    tree_to_folder(out_tree, root_dir, fs_depth, delete_first=ingested)
    return out_tree


def run_minder_smart_sync_folder(root_dir: Path, fs_depth: int, copy_clipboard: bool, force: bool = False) -> None:
    print(f"mode   : folder sync ({root_dir}, fs-depth={fs_depth})")
    tree_in, _ingested = folder_to_tree(root_dir, fs_depth)
    with tempfile.TemporaryDirectory(prefix="anno-folder-") as td:
        tmp_minder = Path(td) / f"{root_dir.name}.minder"
        tmp_minder.write_text(tree_to_minder_xml(tree_in))
        print(f"import : {len(flatten(tree_in)) - 1} nodes from {root_dir}")
        try:
            minder_launch_gui(tmp_minder, force)
        except RuntimeError as exc:
            recovery = save_recovery_minder(tmp_minder, root_dir.name)
            sys.exit(
                f"error  : {exc}\n"
                f"recovery: working .minder copied to {recovery}\n"
                f"          {root_dir}/ is unchanged; run `anno mind import "
                f"{recovery}` after closing the other Minder window."
            )
        print("export : reading tree back from Minder…", flush=True)
        log_activity("mind_export", tmp_minder)
        try:
            out_tree = push_minder_to_folder(tmp_minder, root_dir, fs_depth)
        except RuntimeError as exc:
            recovery = save_recovery_minder(tmp_minder, root_dir.name)
            sys.exit(
                f"error  : {exc}\n"
                f"recovery: working .minder copied to {recovery}\n"
                f"          run `anno mind import {recovery}` to retry the "
                f"write into {root_dir}/."
            )
        print(f"saved  : {root_dir}/ ({len(flatten(out_tree)) - 1} nodes)")
        if copy_clipboard:
            copy_text_to_clipboard(tree_to_numbered_markdown(out_tree))
            print("copied : markdown to clipboard")


# --- mind callbacks ---


def cmd_mind_import(
    minder_path: str,
    folder: str = "",
    notes_root: str = str(DEFAULT_NOTES_ROOT),
    fs_depth: int = DEFAULT_FS_DEPTH,
    no_clipboard: bool = False,
) -> None:
    """Push a saved .minder back into a folder-sync .md tree.

    Used to recover from an interrupted `anno mind open` (the working
    .minder is copied to notes/.anno/recovery/… on failure) or to apply
    any .minder produced/saved out-of-band — no GUI is launched."""
    minder_file = Path(minder_path).expanduser().resolve()
    if not minder_file.is_file():
        sys.exit(f"not a file: {minder_file}")
    if folder:
        root_dir = Path(folder).expanduser().resolve()
    else:
        root_dir = (Path(notes_root) / minder_file.stem).resolve()
    print(f"mode   : import ({minder_file} → {root_dir}/, fs-depth={fs_depth})")
    try:
        out_tree = push_minder_to_folder(minder_file, root_dir, fs_depth)
    except RuntimeError as exc:
        sys.exit(f"error  : {exc}")
    print(f"saved  : {root_dir}/ ({len(flatten(out_tree)) - 1} nodes)")
    if not no_clipboard:
        copy_text_to_clipboard(tree_to_numbered_markdown(out_tree))
        print("copied : markdown to clipboard")


def cmd_mind_open(
    name: str = "",
    mind_dir: str = str(DEFAULT_MIND_DIR),
    notes_root: str = str(DEFAULT_NOTES_ROOT),
    plans_dir: str = str(DEFAULT_PLANS_DIR),
    fs_depth: int = DEFAULT_FS_DEPTH,
    no_clipboard: bool = False,
    force: bool = False,
    template: str = "",
) -> None:
    refuse_if_minder_running(force)
    copy_clipboard = not no_clipboard
    if not name:
        # No name: open a fresh timestamped scratch map.
        out_dir = Path(mind_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        minder_file = out_dir / f"mm_{ts}.minder"
        print(f"mode   : new ({minder_file} — created fresh)")
        try:
            seed_minder(minder_file, root_title=minder_file.stem, template=template)
        except TemplateNotFoundError as exc:
            sys.exit(str(exc))
        run_minder(minder_file, minder_file.with_suffix(".md"), force, copy_clipboard=copy_clipboard)
        return
    mode, target = resolve_open_target(
        name,
        Path(mind_dir).resolve(),
        Path(notes_root).resolve(),
        Path(plans_dir).resolve(),
    )
    use_template = template if template_applies(mode, target) else ""
    if template and not use_template:
        print("note   : --template ignored (opening existing content)")
    if mode == "legacy":
        print(f"mode   : legacy ({target})")
        md_file = target.with_suffix(".md")
        run_minder(target, md_file, force, copy_clipboard=copy_clipboard)
    elif mode == "plan":
        try:
            run_minder_smart_sync_plan(target, copy_clipboard, force, template=use_template)
        except TemplateNotFoundError as exc:
            sys.exit(str(exc))
    elif mode == "new":
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            print(f"mode   : new ({target} — opening existing)")
        else:
            print(f"mode   : new ({target} — created fresh)")
            try:
                seed_minder(target, root_title=target.stem, template=use_template)
            except TemplateNotFoundError as exc:
                sys.exit(str(exc))
        md_file = target.with_suffix(".md")
        run_minder(target, md_file, force, copy_clipboard=copy_clipboard)
    else:
        run_minder_smart_sync_folder(target, fs_depth, copy_clipboard, force)

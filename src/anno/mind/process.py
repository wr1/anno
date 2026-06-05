import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from anno.clipboard import copy_text_to_clipboard
from anno.constants import DEFAULT_NOTES_ROOT, MINDER, MINDER_GUI_MIN_ELAPSED
from anno.log_util import log_activity


def existing_minder_pids() -> list[int]:
    """PIDs of any com.github.phase1geo.minder processes owned by the current
    user. Walks /proc directly so we don't depend on pgrep/pidof being
    installed; on systems without /proc this returns []."""
    pids: list[int] = []
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return pids
    my_uid = os.getuid()
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != my_uid:
                continue
            cmdline = (entry / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if not cmdline:
            continue
        argv0 = cmdline.split(b"\x00", 1)[0].decode(errors="replace")
        if Path(argv0).name == MINDER:
            pids.append(int(entry.name))
    return pids


def reap_existing_minder(reason: str) -> None:
    """SIGTERM (then SIGKILL) any leftover Minder processes before launching a
    new one.

    Minder's GApplication keeps its primary instance alive after the last
    window closes in some GTK4/Wayland sessions, so the next invocation we
    spawn forwards into that zombie and exits immediately — surfacing here
    as anno's `subprocess.run` blocking on a windowless process or as the
    `MINDER_GUI_MIN_ELAPSED` guard firing. Reaping pre-flight gives us a
    clean primary instance every time.

    Trade-off: a Minder opened from another shell will also be killed, but
    parallel GUI sessions don't actually work with the singleton routing
    anyway — this just makes the constraint explicit."""
    pids = existing_minder_pids()
    if not pids:
        return
    pid_list = ", ".join(str(p) for p in pids)
    print(
        f"cleanup: terminating {len(pids)} existing Minder process(es) [{pid_list}] before {reason}",
        flush=True,
    )
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if not any(Path(f"/proc/{p}").exists() for p in pids):
            return
        time.sleep(0.1)
    for pid in pids:
        if Path(f"/proc/{pid}").exists():
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def refuse_if_minder_running(force: bool) -> None:
    """Graceful refusal: if a Minder instance is already running and the user
    didn't pass --force, exit cleanly without touching it.

    anno needs exclusive control of Minder to export-on-close (the launched
    process must be the GApplication primary instance it can wait on), so it
    won't open over a running window. --force reaps the existing instance
    instead — see `reap_existing_minder`."""
    if force:
        return
    pids = existing_minder_pids()
    if not pids:
        return
    pid_list = ", ".join(str(p) for p in pids)
    sys.exit(
        f"error  : Minder is already running (PID {pid_list}).\n"
        f"note   : anno exports your map when the window closes, which needs\n"
        f"         exclusive control of Minder — so it won't open over a running\n"
        f"         instance. Close that window and rerun, or pass --force to replace it."
    )


def run_minder(minder_file: Path, md_file: Path, force: bool = False) -> None:
    try:
        minder_launch_gui(minder_file, force)
    except RuntimeError as exc:
        sys.exit(
            f"error  : {exc}\n"
            f"note   : {minder_file} is at its final location, so nothing is lost — "
            f"close the other Minder window and rerun."
        )
    log_activity("mind_export", minder_file)
    minder_export_markdown(minder_file, md_file)
    md = md_file.read_text() if md_file.exists() else ""
    copy_text_to_clipboard(md)
    print(f"saved  : {minder_file}")
    print(f"saved  : {md_file}")
    print("copied : markdown to clipboard")


# Both entry points (`minder_launch_gui`, `minder_export_markdown`) reap any
# existing Minder process up-front so the GApplication singleton can't route
# this invocation to a stale primary instance. A previous `dbus-run-session`
# isolation wrapper achieved the same thing but stalled 5-10s on portal/secrets
# init in sessions without xdg-desktop-portal; reaping is cheaper and fixes
# the same wedge.
def minder_export_markdown(minder_file: Path, md_file: Path) -> None:
    reap_existing_minder("markdown export")
    # Hard-fail on a missing/empty output file. We ignore the process exit
    # code because Minder exits rc=1 even on a successful export (Gtk/portal
    # noise on teardown); the actual signal of success is whether the .md
    # got written. A silent failure here used to leave smart-sync thinking
    # the user emptied the tree, which proceeded to wipe the source folder.
    result = subprocess.run(
        [MINDER, str(minder_file), "--export=markdown", str(md_file)],
        capture_output=True,
    )
    if not md_file.exists() or not md_file.read_text().strip():
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(
            f"Minder export produced no markdown for {minder_file} "
            f"(rc={result.returncode}); stderr: {stderr[:400] or '<empty>'}"
        )


def minder_launch_gui(minder_file: Path, force: bool = False) -> None:
    # Default is graceful refusal, enforced up-front by `refuse_if_minder_running`
    # in the command callbacks; here we only reap when the caller opted in with
    # --force. The fast-exit guard below stays as a backstop for the rare race
    # where an instance starts between the refusal check and this launch.
    if force:
        reap_existing_minder("GUI launch (--force)")
    t0 = time.monotonic()
    # Popen + KeyboardInterrupt handler so the user has an escape hatch: if
    # Minder keeps the process alive after closing its window (intermittent
    # bug under GTK4/Wayland), Ctrl-C terminates Minder cleanly and we still
    # run the markdown export from the saved .minder file.
    proc = subprocess.Popen([MINDER, str(minder_file)])
    sigint_count = 0
    try:
        while True:
            try:
                proc.wait()
                break
            except KeyboardInterrupt:
                sigint_count += 1
                if sigint_count == 1:
                    print(
                        "\ninfo   : Ctrl-C — terminating Minder so anno can "
                        "finish the export. Press Ctrl-C again to abort.",
                        flush=True,
                    )
                    proc.terminate()
                    continue
                proc.kill()
                raise
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    elapsed = time.monotonic() - t0
    if sigint_count == 0 and elapsed < MINDER_GUI_MIN_ELAPSED:
        raise RuntimeError(
            f"Minder GUI exited after {elapsed:.2f}s — that's too fast to be a real "
            f"edit session, so it almost certainly forwarded the open request to an "
            f"already-running Minder window (GApplication single-instance). The "
            f"pre-flight reap should have prevented this; check "
            f"`ps -ef | grep minder` for an unexpected process and rerun."
        )


def save_recovery_minder(src: Path, stem: str) -> Path:
    """Copy a working .minder out of its tempdir to a stable location so
    `anno mind import` can retry the round-trip after a failed sync."""
    recovery_dir = DEFAULT_NOTES_ROOT / ".anno" / "recovery"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = recovery_dir / f"{ts}_{stem}.minder"
    shutil.copy2(src, dest)
    return dest

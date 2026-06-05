import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from anno.clipboard import copy_png_to_clipboard
from anno.constants import DEFAULT_NOTES_DIR
from anno.log_util import log_activity


def cmd_cam(notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    for tool in ("ffplay", "ffmpeg", "convert"):
        if not shutil.which(tool):
            sys.exit(f"cam requires {tool!r} on PATH (install ffmpeg + imagemagick)")

    device = "/dev/video0"
    print("Webcam preview open — press any key or click to capture.")
    subprocess.run(
        [
            "ffplay",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-input_format",
            "mjpeg",
            "-video_size",
            "1920x1080",
            "-i",
            device,
            "-window_title",
            "anno cam — any key / click to capture",
            "-exitonkeydown",
            "-exitonmousedown",
        ],
        stderr=subprocess.DEVNULL,
    )

    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    orig_path = out_dir / f"cam_{ts}.jpg"

    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-input_format",
            "mjpeg",
            "-video_size",
            "1920x1080",
            "-i",
            device,
            "-frames:v",
            "1",
            "-y",
            str(orig_path),
        ],
        check=True,
    )
    log_activity("cam_capture", orig_path)
    print(f"saved  : {orig_path}")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        subprocess.run(
            [
                "convert",
                str(orig_path),
                "-normalize",
                "-fuzz",
                "5%",
                "-trim",
                "+repage",
                str(tmp_path),
            ],
            check=True,
        )
        copy_png_to_clipboard(tmp_path)
        print("copied : enhanced PNG to clipboard")
    finally:
        tmp_path.unlink(missing_ok=True)

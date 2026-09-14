"""Minder 2.0 `.minder` files: gzip tar containing `map.xml` (plus images).

anno only writes and reads this archive. Minder 1.x XML documents are refused.
"""

from __future__ import annotations

import gzip
import io
import os
import tarfile
from pathlib import Path

MINDER_FILE_VERSION = "2.0.3"
MAP_XML_NAME = "map.xml"
GZIP_MAGIC = b"\x1f\x8b"


def _looks_like_xml(data: bytes) -> bool:
    head = data.lstrip(b"\xef\xbb\xbf").lstrip()
    return head.startswith(b"<?xml") or head.startswith(b"<minder")


def is_minder2_archive(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as f:
        return f.read(2) == GZIP_MAGIC


def require_minder_archive(path: Path) -> None:
    """Raise ValueError unless `path` is a Minder 2.0 gzip-tar archive."""
    if not path.is_file():
        raise ValueError(f"not a file: {path}")
    if is_minder2_archive(path):
        return
    head = path.read_bytes()[:256]
    if _looks_like_xml(head):
        raise ValueError(f"{path} is Minder 1.x XML; only Minder 2.0 archives are supported")
    raise ValueError(f"{path} is not a Minder 2.0 archive (gzip tar with {MAP_XML_NAME})")


def write_minder_archive(path: Path, xml: str) -> None:
    """Write `xml` as `map.xml` inside a gzip tar at `path`."""
    xml_bytes = xml.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        info = tarfile.TarInfo(name=MAP_XML_NAME)
        info.size = len(xml_bytes)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(xml_bytes))
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        with tmp.open("wb") as raw, gzip.GzipFile(filename=path.name, mode="wb", fileobj=raw) as gz:
            gz.write(tar_buf.getvalue())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def read_map_xml(path: Path) -> str:
    """Return `map.xml` from a Minder 2.0 archive."""
    require_minder_archive(path)
    try:
        with tarfile.open(path, "r:gz") as tar:
            try:
                member = tar.getmember(MAP_XML_NAME)
            except KeyError as exc:
                names = ", ".join(tar.getnames()) or "<empty>"
                raise ValueError(f"no {MAP_XML_NAME} in {path} (members: {names})") from exc
            extracted = tar.extractfile(member)
            if extracted is None:
                raise ValueError(f"could not extract {MAP_XML_NAME} from {path}")
            return extracted.read().decode("utf-8")
    except tarfile.TarError as exc:
        raise ValueError(f"{path} is not a Minder 2.0 archive") from exc

"""File utilities — hashing, magic-byte detection, path helpers, Windows attributes."""

import ctypes
import hashlib
import os

from app.utils.helpers import iso_datetime_from_ts


def ensure_unique_path(path: str) -> str:
    """Return *path* if it doesn't exist, otherwise append (1), (2), … suffix."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        p = f"{base} ({i}){ext}"
        if not os.path.exists(p):
            return p
        i += 1


def is_file_locked_windows(path: str) -> bool:
    if not os.path.exists(path):
        return False
    try:
        with open(path, "a+b"):
            pass
        return False
    except OSError:
        return True


def find_all_images(root: str, supported_extensions: tuple[str, ...]) -> list[str]:
    """Walk *root* recursively and return paths of files whose extension is supported."""
    out: list[str] = []
    for folder, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(supported_extensions):
                out.append(os.path.join(folder, f))
    return out


def count_by_extension(paths: list[str], supported_extensions: tuple[str, ...]) -> dict[str, int]:
    counts = {ext: 0 for ext in supported_extensions}
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        if ext in counts:
            counts[ext] += 1
    return counts


# --------------- Hashing ---------------

def compute_hashes(path: str, chunk_size: int = 1024 * 1024) -> dict[str, str]:
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            md5.update(b)
            sha1.update(b)
            sha256.update(b)
    return {"md5": md5.hexdigest(), "sha1": sha1.hexdigest(), "sha256": sha256.hexdigest()}


# --------------- Magic-byte detection ---------------

def detect_magic_type(path: str) -> str:
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except Exception:
        return ""

    if head.startswith(b"\xFF\xD8\xFF"):
        return "JPEG"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    if head.startswith(b"II*\x00") or head.startswith(b"MM\x00*"):
        return "TIFF"
    if head.startswith(b"BM"):
        return "BMP"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "ISOBMFF"
    return "UNKNOWN"


# --------------- Windows file attributes ---------------

def get_windows_file_attributes(path: str) -> dict[str, str]:
    if os.name != "nt":
        return {"attributes_raw": "", "read_only": "false"}

    FILE_ATTRIBUTE_READONLY = 0x1
    try:
        GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
        GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
        GetFileAttributesW.restype = ctypes.c_uint32
        attrs = GetFileAttributesW(path)
        if attrs == 0xFFFFFFFF:
            return {"attributes_raw": "", "read_only": "false"}
        read_only = "true" if (attrs & FILE_ATTRIBUTE_READONLY) else "false"
        return {"attributes_raw": str(int(attrs)), "read_only": read_only}
    except Exception:
        return {"attributes_raw": "", "read_only": "false"}

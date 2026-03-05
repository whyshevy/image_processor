"""Image service — RAW helpers, image properties extraction, JPEG conversion."""

import io
import os

from PIL import Image, UnidentifiedImageError  # noqa: F401

from app.services.file_service import (
    compute_hashes,
    detect_magic_type,
    get_windows_file_attributes,
)
from app.utils.helpers import iso_datetime_from_ts

_RAW_EXTS = {".nef", ".cr2", ".cr3", ".arw", ".dng", ".rw2"}


def _rawpy_get_raw_size(path: str, try_rawpy: bool = True) -> tuple[int | None, int | None, str]:
    if not try_rawpy:
        return None, None, ""
    try:
        import rawpy  # type: ignore
    except ImportError:
        return None, None, ""

    try:
        with rawpy.imread(path) as raw:
            w = int(getattr(raw.sizes, "iwidth", 0) or 0)
            h = int(getattr(raw.sizes, "iheight", 0) or 0)
            if w > 0 and h > 0:
                return w, h, "rawpy"
    except Exception:
        pass
    return None, None, ""


def _pil_get_size(path: str) -> tuple[int | None, int | None, str, str]:
    try:
        img = Image.open(path)
        w, h = int(getattr(img, "width", 0) or 0), int(getattr(img, "height", 0) or 0)
        fmt = str(img.format or "")
        if w > 0 and h > 0:
            return w, h, fmt, "pil"
    except Exception:
        pass
    return None, None, "", ""


def extract_image_basic_properties(image_path: str, try_rawpy: bool = True) -> dict[str, str]:
    """Build a dict of original-image metadata (dimensions, hashes, etc.)."""
    st = os.stat(image_path)
    hashes = compute_hashes(image_path)
    magic = detect_magic_type(image_path)
    win_attrs = get_windows_file_attributes(image_path)

    ext = os.path.splitext(image_path)[1].lower()

    width = ""
    height = ""
    pixel_count = ""
    aspect = ""
    pil_format = ""
    dim_source = ""

    if ext in _RAW_EXTS:
        w_raw, h_raw, src = _rawpy_get_raw_size(image_path, try_rawpy)
        if w_raw and h_raw:
            width, height = str(w_raw), str(h_raw)
            pixel_count = str(w_raw * h_raw)
            aspect = f"{w_raw / h_raw:.6f}"
            dim_source = src

    if not width or not height:
        w, h, fmt, src = _pil_get_size(image_path)
        pil_format = fmt
        dim_source = dim_source or src
        if w and h:
            width, height = str(w), str(h)
            pixel_count = str(w * h)
            aspect = f"{w / h:.6f}"

    return {
        "OriginalFullPath": image_path,
        "OriginalFileName": os.path.basename(image_path),
        "OriginalExtension": ext,
        "OriginalFileSizeBytes": str(int(st.st_size)),
        "OriginalModifiedTime": iso_datetime_from_ts(getattr(st, "st_mtime", 0)),
        "OriginalMagicType": magic,
        "OriginalPILFormat": pil_format,
        "OriginalWidthPx": width,
        "OriginalHeightPx": height,
        "OriginalPixelCount": pixel_count,
        "OriginalAspectRatio": aspect,
        "OriginalMD5": hashes["md5"],
        "OriginalSHA1": hashes["sha1"],
        "WinAttributesRaw": win_attrs["attributes_raw"],
        "ReadOnly": win_attrs["read_only"],
        "DimSource": dim_source,
    }


def convert_any_image_to_jpeg_bytes(
    image_path: str,
    jpeg_quality: int = 92,
    try_rawpy: bool = True,
) -> bytes:
    """Convert any supported image to JPEG bytes in memory."""
    ext = os.path.splitext(image_path)[1].lower()

    if ext in _RAW_EXTS and try_rawpy:
        try:
            import rawpy  # type: ignore
            import imageio.v3 as iio  # type: ignore

            with rawpy.imread(image_path) as raw:
                rgb = raw.postprocess(use_auto_wb=True, no_auto_bright=False, output_bps=8)
            buf = io.BytesIO()
            iio.imwrite(buf, rgb, extension=".jpg", quality=jpeg_quality)
            return buf.getvalue()
        except Exception:
            pass

    img = Image.open(image_path)

    if ext == ".mpo":
        try:
            img.seek(0)
        except Exception:
            pass

    img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    return buf.getvalue()


def convert_file_to_processing_jpeg(
    src_path: str,
    dst_jpeg_path: str,
    jpeg_quality: int = 92,
    try_rawpy: bool = True,
) -> str:
    """Convert *src_path* to a JPEG saved at *dst_jpeg_path*. Returns the dest path."""
    data = convert_any_image_to_jpeg_bytes(src_path, jpeg_quality, try_rawpy)
    os.makedirs(os.path.dirname(dst_jpeg_path), exist_ok=True)
    with open(dst_jpeg_path, "wb") as f:
        f.write(data)
    return dst_jpeg_path

"""Excel service — generate .xlsx report with image thumbnails."""

import os

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage

HEADERS = [
    "FileImage",
    "ProcJPEGName",
    "OriginalFullPath",
    "AI_Description",
    "UKR_Keywords",
    "EN_Keywords",
    "OriginalFileName",
    "OriginalExtension",
    "OriginalFileSizeBytes",
    "OriginalWidthPx",
    "OriginalHeightPx",
    "OriginalPixelCount",
    "OriginalAspectRatio",
    "OriginalPILFormat",
    "OriginalMagicType",
    "OriginalModifiedTime",
    "OriginalMD5",
    "OriginalSHA1",
    "DimSource",
]


def create_workbook() -> tuple[Workbook, any]:
    """Create a new Workbook with headers. Returns (wb, ws)."""
    wb = Workbook()
    ws = wb.active
    ws.append(HEADERS)
    return wb, ws


def append_row(
    ws,
    proc_jpeg_path: str,
    preprops: dict[str, str],
    description: str,
    uk_pipe: str,
    en_pipe: str,
    orig_path: str,
) -> None:
    """Append a data row and embed a thumbnail image."""
    excel_row = ws.max_row + 1
    row = [
        "",  # FileImage placeholder — filled with XLImage
        os.path.basename(proc_jpeg_path),
        preprops.get("OriginalFullPath", orig_path),
        description,
        uk_pipe,
        en_pipe,
        preprops.get("OriginalFileName", ""),
        preprops.get("OriginalExtension", ""),
        preprops.get("OriginalFileSizeBytes", ""),
        preprops.get("OriginalWidthPx", ""),
        preprops.get("OriginalHeightPx", ""),
        preprops.get("OriginalPixelCount", ""),
        preprops.get("OriginalAspectRatio", ""),
        preprops.get("OriginalPILFormat", ""),
        preprops.get("OriginalMagicType", ""),
        preprops.get("OriginalModifiedTime", ""),
        preprops.get("OriginalMD5", ""),
        preprops.get("OriginalSHA1", ""),
        preprops.get("DimSource", ""),
    ]
    ws.append(row)

    try:
        xlimg = XLImage(proc_jpeg_path)
        xlimg.width, xlimg.height = 120, 120
        ws.row_dimensions[excel_row].height = 100
        ws.add_image(xlimg, f"A{excel_row}")
    except Exception as e:
        print(f"[EXCEL] Image embed error: {proc_jpeg_path} -> {e}")


def save_workbook(wb: Workbook, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)

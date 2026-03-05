"""API routes — scanning, processing, progress SSE, data viewing."""

import json
import os
import time

from flask import Blueprint, current_app, jsonify, request, Response

from app.services.processing_service import (
    get_job,
    list_jobs,
    scan_directory,
    start_processing,
    stop_job,
)
from app.services.db_service import get_records_by_job, get_all_records

api_bp = Blueprint("api", __name__)


# ---- Helper: safe directory iteration ----
def _safe_iterdir(path):
    """Yield only subdirectories, swallowing permission errors."""
    try:
        for child in path.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                yield child
    except (PermissionError, OSError):
        return


@api_bp.route("/list-directory", methods=["POST"])
def api_list_directory():
    """List subdirectories for the web-based folder browser.

    Expects JSON: { "path": "/media" }  (or empty → MEDIA_ROOT).
    Returns: { "path": "/media", "parent": null, "dirs": ["photo", "homes"] }
    """
    import pathlib

    media_root = current_app.config.get("MEDIA_ROOT", "")
    if not media_root:
        # Local / Windows mode — no server-side browser needed
        return jsonify({"error": "Server-side browser not available in local mode."}), 400

    root = pathlib.Path(media_root).resolve()
    data = request.get_json(silent=True) or {}
    requested = (data.get("path") or str(root)).strip()
    target = pathlib.Path(requested).resolve()

    # Security: never go above MEDIA_ROOT
    try:
        target.relative_to(root)
    except ValueError:
        target = root

    if not target.is_dir():
        target = root

    # Get parent (only if not already at root)
    parent = None
    if target != root:
        parent = str(target.parent)

    dirs = sorted(
        [d.name for d in _safe_iterdir(target)],
        key=str.lower,
    )

    return jsonify({
        "path": str(target),
        "parent": parent,
        "dirs": dirs,
    })


@api_bp.route("/server-mode")
def api_server_mode():
    """Return deployment mode info so the frontend knows which browse method to use."""
    media_root = current_app.config.get("MEDIA_ROOT", "")
    return jsonify({
        "mode": "synology" if media_root else "local",
        "media_root": media_root,
    })


@api_bp.route("/browse-folder", methods=["POST"])
def api_browse_folder():
    """Open a native OS folder picker dialog (Windows only) or return error."""
    media_root = current_app.config.get("MEDIA_ROOT", "")
    if media_root:
        # Running on Synology / headless — no native picker available.
        # The frontend should use the web folder-browser instead.
        return jsonify({"path": "", "use_browser": True})

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="Оберіть папку з фото")
        root.destroy()

        if folder:
            folder = folder.replace("/", "\\")
            return jsonify({"path": folder})
        return jsonify({"path": ""})
    except Exception:
        return jsonify({"path": "", "use_browser": True})


@api_bp.route("/resolve-folder", methods=["POST"])
def api_resolve_folder():
    """Find full path of a folder by name — searches user dirs, drive roots and 2 levels deep."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"path": ""})

    import pathlib

    # On Synology / Docker — search inside MEDIA_ROOT
    media_root = current_app.config.get("MEDIA_ROOT", "")
    if media_root:
        root = pathlib.Path(media_root)
        if root.is_dir():
            # Direct child
            candidate = root / name
            if candidate.is_dir():
                return jsonify({"path": str(candidate)})
            # Search 3 levels deep
            for lvl1 in _safe_iterdir(root):
                candidate = lvl1 / name
                if candidate.is_dir():
                    return jsonify({"path": str(candidate)})
                for lvl2 in _safe_iterdir(lvl1):
                    candidate = lvl2 / name
                    if candidate.is_dir():
                        return jsonify({"path": str(candidate)})
                    for lvl3 in _safe_iterdir(lvl2):
                        candidate = lvl3 / name
                        if candidate.is_dir():
                            return jsonify({"path": str(candidate)})
        return jsonify({"path": ""})

    home = pathlib.Path.home()

    # Priority 1: direct children of common user folders
    priority_dirs = [
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
        home / "Pictures",
        home,
    ]
    for parent in priority_dirs:
        candidate = parent / name
        if candidate.is_dir():
            return jsonify({"path": str(candidate)})

    # Priority 2: root of every drive + 2 levels deep
    if os.name == "nt":
        import string
        for letter in string.ascii_uppercase:
            drive = pathlib.Path(f"{letter}:\\")
            if not drive.exists():
                continue
            # Direct child of drive root
            candidate = drive / name
            if candidate.is_dir():
                return jsonify({"path": str(candidate)})
            # 2 levels deep on each drive
            try:
                for lvl1 in drive.iterdir():
                    if not lvl1.is_dir():
                        continue
                    candidate = lvl1 / name
                    if candidate.is_dir():
                        return jsonify({"path": str(candidate)})
                    try:
                        for lvl2 in lvl1.iterdir():
                            if not lvl2.is_dir():
                                continue
                            candidate = lvl2 / name
                            if candidate.is_dir():
                                return jsonify({"path": str(candidate)})
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                continue

    return jsonify({"path": ""})


@api_bp.route("/scan", methods=["POST"])
def api_scan():
    """Scan a local directory for supported images."""
    data = request.get_json(silent=True) or {}
    directory = data.get("directory", "").strip()

    if not directory or not os.path.isdir(directory):
        return jsonify({"error": "Невірний шлях або папка не існує."}), 400

    supported = current_app.config["SUPPORTED_EXTENSIONS"]
    result = scan_directory(directory, supported)
    return jsonify(result)


@api_bp.route("/process", methods=["POST"])
def api_process():
    """Start processing selected images."""
    data = request.get_json(silent=True) or {}
    directory = data.get("directory", "").strip()
    files = data.get("files", [])

    if not directory or not os.path.isdir(directory):
        return jsonify({"error": "Невірний шлях або папка не існує."}), 400
    if not files:
        return jsonify({"error": "Не обрано жодного файлу."}), 400

    api_key = current_app.config["OPENAI_API_KEY"]
    if not api_key:
        return jsonify({"error": "OPENAI_API_KEY не налаштовано. Додайте його до .env файлу."}), 400

    config = {
        "OPENAI_API_KEY": api_key,
        "OPENAI_MODEL": current_app.config["OPENAI_MODEL"],
        "JPEG_QUALITY": current_app.config["JPEG_QUALITY"],
        "TRY_RAWPY": current_app.config["TRY_RAWPY"],
        "SUPPORTED_EXTENSIONS": current_app.config["SUPPORTED_EXTENSIONS"],
        "KEYWORDS_LIMIT": current_app.config["KEYWORDS_LIMIT"],
        "PROCESSED_FOLDER": current_app.config["PROCESSED_FOLDER"],
        "DB_DRIVER": current_app.config["DB_DRIVER"],
        "DB_SERVER": current_app.config["DB_SERVER"],
        "DB_NAME": current_app.config["DB_NAME"],
        "DB_USER": current_app.config["DB_USER"],
        "DB_PASSWORD": current_app.config["DB_PASSWORD"],
    }

    job_id = start_processing(directory, files, config)
    return jsonify({"job_id": job_id})


@api_bp.route("/jobs", methods=["GET"])
def api_jobs():
    return jsonify(list_jobs())


@api_bp.route("/jobs/<job_id>", methods=["GET"])
def api_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    return jsonify({
        "id": job.id,
        "status": job.status,
        "total": job.total,
        "done": job.done,
        "skipped": job.skipped,
        "current_file": job.current_file,
        "percent": job.percent,
        "elapsed": job.elapsed,
        "eta": job.eta,
        "error": job.error,
    })


@api_bp.route("/jobs/<job_id>/stop", methods=["POST"])
def api_stop_job(job_id: str):
    if stop_job(job_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Job not found."}), 404


@api_bp.route("/jobs/<job_id>/stream")
def api_job_stream(job_id: str):
    """Server-Sent Events stream for real-time progress updates."""

    def generate():
        while True:
            job = get_job(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break

            payload = {
                "status": job.status,
                "total": job.total,
                "done": job.done,
                "skipped": job.skipped,
                "current_file": job.current_file,
                "percent": job.percent,
                "elapsed": job.elapsed,
                "eta": job.eta,
                "error": job.error,
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            if job.status in ("done", "stopped", "error"):
                break

            time.sleep(1)

    return Response(generate(), mimetype="text/event-stream")


@api_bp.route("/jobs/<job_id>/data")
def api_job_data(job_id: str):
    """Get processed records for a specific job from MS SQL."""
    db_config = {
        "DB_DRIVER": current_app.config["DB_DRIVER"],
        "DB_SERVER": current_app.config["DB_SERVER"],
        "DB_NAME": current_app.config["DB_NAME"],
        "DB_USER": current_app.config["DB_USER"],
        "DB_PASSWORD": current_app.config["DB_PASSWORD"],
    }
    try:
        records = get_records_by_job(db_config, job_id)
        return jsonify({"records": records, "count": len(records)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/records")
def api_all_records():
    """Get latest processed records from MS SQL."""
    limit = request.args.get("limit", 500, type=int)
    db_config = {
        "DB_DRIVER": current_app.config["DB_DRIVER"],
        "DB_SERVER": current_app.config["DB_SERVER"],
        "DB_NAME": current_app.config["DB_NAME"],
        "DB_USER": current_app.config["DB_USER"],
        "DB_PASSWORD": current_app.config["DB_PASSWORD"],
    }
    try:
        records = get_all_records(db_config, limit)
        return jsonify({"records": records, "count": len(records)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

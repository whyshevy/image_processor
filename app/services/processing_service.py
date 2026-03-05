"""Processing service — orchestrates the full image-processing pipeline.

Runs in a background thread; publishes progress via a shared state dict
so the API layer can stream it to the browser via SSE.
"""

import os
import shutil
import time
import threading
import uuid
from dataclasses import dataclass, field

from app.services.file_service import (
    ensure_unique_path,
    find_all_images,
    count_by_extension,
)
from app.services.image_service import (
    extract_image_basic_properties,
    convert_file_to_processing_jpeg,
)
from app.services.ai_service import get_openai_description_keywords
from app.services.db_service import ensure_table, insert_processed_media, check_already_processed
from app.utils.helpers import format_mmss


# --------------- In-memory job registry ---------------

@dataclass
class Job:
    id: str
    status: str = "pending"          # pending | scanning | processing | saving | done | stopped | error
    total: int = 0
    done: int = 0
    skipped: int = 0
    current_file: str = ""
    percent: int = 0
    elapsed: str = "00:00"
    eta: str = "—"
    error: str = ""
    stop_event: threading.Event = field(default_factory=threading.Event)


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs() -> list[dict]:
    with _lock:
        return [
            {"id": j.id, "status": j.status, "total": j.total, "done": j.done, "percent": j.percent}
            for j in _jobs.values()
        ]


def stop_job(job_id: str) -> bool:
    job = get_job(job_id)
    if job:
        job.stop_event.set()
        return True
    return False


# --------------- Scanning (find images) ---------------

def scan_directory(
    directory: str,
    supported_extensions: tuple[str, ...],
) -> dict:
    """Return a summary of images found in *directory*."""
    images = find_all_images(directory, supported_extensions)
    ext_counts = count_by_extension(images, supported_extensions)
    ext_summary = {ext: cnt for ext, cnt in ext_counts.items() if cnt > 0}
    return {
        "directory": directory,
        "total": len(images),
        "by_extension": ext_summary,
        "files": [os.path.relpath(p, directory) for p in images],
    }


# --------------- Main processing ---------------

def start_processing(
    src_dir: str,
    selected_files: list[str],   # relative paths from src_dir
    config: dict,
) -> str:
    """
    Kick off the processing pipeline in a background thread.
    Returns a job_id for status polling / SSE.
    """
    job_id = uuid.uuid4().hex[:12]
    job = Job(id=job_id)

    with _lock:
        _jobs[job_id] = job

    t = threading.Thread(
        target=_run_pipeline,
        args=(job, src_dir, selected_files, config),
        daemon=True,
    )
    t.start()
    return job_id


def _run_pipeline(
    job: Job,
    src_dir: str,
    selected_files: list[str],
    config: dict,
) -> None:
    try:
        _do_processing(job, src_dir, selected_files, config)
    except Exception as e:
        job.status = "error"
        job.error = str(e)


def _do_processing(
    job: Job,
    src_dir: str,
    selected_files: list[str],
    config: dict,
) -> None:
    api_key = config["OPENAI_API_KEY"]
    model = config.get("OPENAI_MODEL", "gpt-4o")
    jpeg_quality = config.get("JPEG_QUALITY", 92)
    try_rawpy = config.get("TRY_RAWPY", True)
    keywords_limit = config.get("KEYWORDS_LIMIT", 20)
    processed_folder = config["PROCESSED_FOLDER"]

    db_config = {
        "DB_DRIVER": config["DB_DRIVER"],
        "DB_SERVER": config["DB_SERVER"],
        "DB_NAME": config["DB_NAME"],
        "DB_USER": config["DB_USER"],
        "DB_PASSWORD": config["DB_PASSWORD"],
    }

    # Ensure DB table exists
    ensure_table(db_config)

    # Build work dirs
    folder_name = os.path.basename(src_dir.rstrip("/\\"))
    processing_dir = os.path.join(processed_folder, f"{folder_name}_processing")
    os.makedirs(processing_dir, exist_ok=True)

    # Prepare list
    job.status = "scanning"
    images_to_process: list[tuple[str, str, dict]] = []
    skipped = 0

    for rel in selected_files:
        if job.stop_event.is_set():
            break
        orig_path = os.path.join(src_dir, rel)
        if not os.path.isfile(orig_path):
            continue

        preprops = extract_image_basic_properties(orig_path, try_rawpy)

        # Skip if already in DB (by MD5)
        md5 = preprops.get("OriginalMD5", "")
        if md5 and check_already_processed(db_config, md5):
            skipped += 1
            continue

        rel_dir = os.path.relpath(os.path.dirname(orig_path), src_dir)
        if rel_dir == ".":
            rel_dir = ""
        dst_dir = os.path.join(processing_dir, rel_dir)
        os.makedirs(dst_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(orig_path))[0]
        proc_jpeg = ensure_unique_path(os.path.join(dst_dir, base_name + ".jpeg"))

        try:
            convert_file_to_processing_jpeg(orig_path, proc_jpeg, jpeg_quality, try_rawpy)
        except Exception as e:
            print(f"[CONVERT] Skip {orig_path}: {e}")
            continue

        images_to_process.append((orig_path, proc_jpeg, preprops))

    total = len(images_to_process)
    job.total = total
    job.skipped = skipped
    job.status = "processing"

    start_time = time.time()

    for i, (orig_path, proc_jpeg, preprops) in enumerate(images_to_process, start=1):
        if job.stop_event.is_set():
            job.status = "stopped"
            break

        fname = os.path.basename(orig_path)
        job.current_file = fname

        desc, uk_pipe, en_pipe = get_openai_description_keywords(
            proc_jpeg, api_key, model, jpeg_quality, keywords_limit,
        )

        # Insert into MS SQL
        insert_processed_media(
            db_config, job.id, os.path.basename(proc_jpeg), proc_jpeg,
            preprops, desc, uk_pipe, en_pipe, orig_path,
        )

        elapsed = time.time() - start_time
        job.done = i
        job.percent = int(round((i / max(total, 1)) * 100))
        job.elapsed = format_mmss(int(elapsed))
        if i > 1:
            avg = elapsed / i
            eta_s = int(avg * (total - i))
            job.eta = format_mmss(eta_s)

    if job.stop_event.is_set():
        shutil.rmtree(processing_dir, ignore_errors=True)
        job.status = "stopped"
        return

    # Cleanup temp processing dir
    shutil.rmtree(processing_dir, ignore_errors=True)
    job.status = "done"

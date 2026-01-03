from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from pathlib import Path
import uuid
import shutil
import json

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Anime AI Озвучка - API")

# Serve simple static frontend
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="src/static"), name="static")

@app.get("/")
def root_index():
    return FileResponse("src/static/index.html")

@app.get("/job")
def job_page():
    return FileResponse("src/static/job.html")


class UploadResponse(BaseModel):
    job_id: str
    filename: str
    status: str


def save_upload(file: UploadFile, dest: Path):
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_video(background_tasks: BackgroundTasks,
                       file: UploadFile = File(...),
                       target_language: str = Form(...),
                       translate: bool = Form(True),
                       voice_gender: str = Form("auto"),
                       add_logo: bool = Form(False),
                       logo: UploadFile = File(None),
                       logo_position: str = Form("bottom-left"),
                       ):
    # Basic validation
    if not file.content_type or not file.content_type.startswith("video"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a video")

    job_id = uuid.uuid4().hex
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    file_path = job_dir / file.filename
    save_upload(file, file_path)

    meta = {
        "job_id": job_id,
        "filename": file.filename,
        "target_language": target_language,
        "translate": translate,
        "voice_gender": voice_gender,
        "status": "queued",
    }

    if add_logo and logo is not None:
        logo_path = job_dir / f"logo_{logo.filename}"
        save_upload(logo, logo_path)
        meta["logo"] = str(logo_path)
        meta["logo_position"] = logo_position

    (job_dir / "meta.json").write_text(json.dumps(meta))

    # Enqueue background processing: prefer Celery if configured
    import os as _os
    if _os.getenv("CELERY_BROKER_URL"):
        try:
            from src.tasks import process_video_task
            process_video_task.delay(job_id, str(file_path))
            meta.setdefault("events", []).append("enqueued_via_celery")
            (job_dir / "meta.json").write_text(json.dumps(meta))
        except Exception as e:
            # fallback to background task
            background_tasks.add_task(process_video, job_id, str(file_path), meta)
    else:
        background_tasks.add_task(process_video, job_id, str(file_path), meta)

    # Return job info
    return UploadResponse(job_id=job_id, filename=file.filename, status="queued")

    return UploadResponse(job_id=job_id, filename=file.filename, status="queued")


def process_video(job_id: str, file_path: str, meta: dict):
    """Compatibility wrapper: delegate to centralized processor.process_job."""
    try:
        from src.processor import process_job
        process_job(job_id, file_path, meta)
    except Exception as e:
        job_dir = UPLOAD_DIR / job_id
        meta.setdefault("errors", {})["process_video"] = str(e)
        meta["status"] = "failed"
        (job_dir / "meta.json").write_text(json.dumps(meta))


@app.get("/api/job/{job_id}")
def get_job_status(job_id: str):
    job_dir = UPLOAD_DIR / job_id
    meta_file = job_dir / "meta.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return json.loads(meta_file.read_text())


@app.get("/api/job/{job_id}/notifications")
def get_notifications(job_id: str):
    job_dir = UPLOAD_DIR / job_id
    from src.notify import get_notifications
    return get_notifications(job_dir)


@app.get("/api/job/{job_id}/download")
def download_result(job_id: str):
    job_dir = UPLOAD_DIR / job_id
    meta_file = job_dir / "meta.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        if meta.get("s3_url"):
            return {"s3_url": meta.get("s3_url")}
    out_files = list(job_dir.glob("*_processed.mp4"))
    if not out_files:
        raise HTTPException(status_code=404, detail="Output not ready")
    return FileResponse(out_files[0], filename=out_files[0].name, media_type="video/mp4")


@app.get("/api/job/{job_id}/transcript")
def get_transcript(job_id: str):
    job_dir = UPLOAD_DIR / job_id
    tfile = job_dir / "transcript.json"
    if not tfile.exists():
        raise HTTPException(status_code=404, detail="Transcript not found or not ready")
    return json.loads(tfile.read_text())


@app.get("/api/job/{job_id}/speakers")
def get_speakers(job_id: str):
    job_dir = UPLOAD_DIR / job_id
    sfile = job_dir / "speakers.json"
    if not sfile.exists():
        raise HTTPException(status_code=404, detail="Speakers info not ready")
    return json.loads(sfile.read_text())


@app.post("/api/job/{job_id}/assign_voices")
def assign_voices(job_id: str, mapping: dict):
    """Accepts JSON like {"speaker1": {"gender":"female"}, "speaker2": "male"} or voice ids.
    Saves mapping and starts TTS re-synthesis in background.
    """
    job_dir = UPLOAD_DIR / job_id
    if not (job_dir / "meta.json").exists():
        raise HTTPException(status_code=404, detail="Job not found")
    (job_dir / "speakers_mapping.json").write_text(json.dumps(mapping, ensure_ascii=False))

    # enqueue synthesize with mapping (prefer Celery)
    import os as _os
    if _os.getenv("CELERY_BROKER_URL"):
        try:
            from src.tasks import synthesize_with_mapping_task
            synthesize_with_mapping_task.delay(job_id, mapping)
            return JSONResponse({"status": "queued_via_celery"})
        except Exception:
            # fallback to background
            background_tasks = BackgroundTasks()
            background_tasks.add_task(process_synthesize_with_mapping, job_id, str(job_dir), mapping)
            return JSONResponse({"status": "queued"}, background=background_tasks)
    else:
        background_tasks = BackgroundTasks()
        background_tasks.add_task(process_synthesize_with_mapping, job_id, str(job_dir), mapping)
        return JSONResponse({"status": "queued"}, background=background_tasks)


def process_synthesize_with_mapping(job_id: str, job_dir: str, mapping: dict):
    # Re-run synthesis with mapping
    try:
        jobd = UPLOAD_DIR / job_id
        # find original file
        meta = json.loads((jobd / "meta.json").read_text())
        original = jobd / meta.get("filename")
        from src.processor import synthesize_and_mix
        out = synthesize_and_mix(jobd, str(original), voice_gender=meta.get("voice_gender","auto"), use_translated=meta.get("translate", True), speakers_map=mapping)
        meta["status"] = "done"
        meta["output"] = str(out)
        (jobd / "meta.json").write_text(json.dumps(meta))
    except Exception as e:
        meta = json.loads((jobd / "meta.json").read_text())
        meta["status"] = "failed"
        meta.setdefault("errors", {})["synthesize_with_mapping"] = str(e)
        (jobd / "meta.json").write_text(json.dumps(meta))

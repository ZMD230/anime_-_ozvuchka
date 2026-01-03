import json
from pathlib import Path

from src.celery_app import celery_app
from src.processor import process_job, synthesize_and_mix


@celery_app.task(bind=True)
def process_video_task(self, job_id: str, file_path: str):
    job_dir = Path("data/uploads") / job_id
    meta = {}
    if (job_dir / "meta.json").exists():
        meta = json.loads((job_dir / "meta.json").read_text())
    try:
        process_job(job_id, file_path, meta)
    except Exception as e:
        meta.setdefault("errors", {})["celery_task"] = str(e)
        meta["status"] = "failed"
        (job_dir / "meta.json").write_text(json.dumps(meta))
        raise


@celery_app.task(bind=True)
def synthesize_with_mapping_task(self, job_id: str, mapping: dict):
    job_dir = Path("data/uploads") / job_id
    meta = {}
    if (job_dir / "meta.json").exists():
        meta = json.loads((job_dir / "meta.json").read_text())
    try:
        original = job_dir / meta.get("filename")
        out = synthesize_and_mix(job_dir, str(original), voice_gender=meta.get("voice_gender", "auto"), use_translated=meta.get("translate", True), speakers_map=mapping)
        meta["status"] = "done"
        meta["output"] = str(out)
        (job_dir / "meta.json").write_text(json.dumps(meta))
    except Exception as e:
        meta = json.loads((job_dir / "meta.json").read_text())
        meta["status"] = "failed"
        meta.setdefault("errors", {})["synthesize_with_mapping"] = str(e)
        (job_dir / "meta.json").write_text(json.dumps(meta))
        raise

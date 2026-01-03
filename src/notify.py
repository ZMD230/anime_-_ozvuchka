import json
from pathlib import Path
from datetime import datetime


def add_notification(job_dir: str, message: str, level: str = "info"):
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    nfile = job_dir / "notifications.json"
    if nfile.exists():
        data = json.loads(nfile.read_text())
    else:
        data = []
    entry = {
        "time": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "message": message,
    }
    data.append(entry)
    nfile.write_text(json.dumps(data, ensure_ascii=False))
    return entry


def get_notifications(job_dir: str):
    job_dir = Path(job_dir)
    nfile = job_dir / "notifications.json"
    if not nfile.exists():
        return []
    return json.loads(nfile.read_text())

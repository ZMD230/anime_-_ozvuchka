import os
from pathlib import Path

try:
    from pyannote.audio import Pipeline
except Exception:
    Pipeline = None

HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")


def diarize_audio(audio_path: str, job_dir: str):
    """Run speaker diarization using pyannote.audio Pipeline if available.
    Saves `diarization.json` containing segments with speaker labels.
    """
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    audio_path = str(audio_path)

    if Pipeline is None:
        raise RuntimeError("pyannote.audio is not installed or available")
    if not HUGGINGFACE_TOKEN:
        raise RuntimeError("HUGGINGFACE_TOKEN is required for pyannote pretrained pipelines")

    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization", use_auth_token=HUGGINGFACE_TOKEN)
    diarization = pipeline(audio_path)

    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({
            "start": float(turn.start),
            "end": float(turn.end),
            "speaker": speaker,
        })

    out = {"segments": segments}
    (job_dir / "diarization.json").write_text(str(out))
    return out

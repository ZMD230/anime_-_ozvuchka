import subprocess
from pathlib import Path
import numpy as np

try:
    import librosa
except Exception:
    librosa = None


def extract_segment(audio_path: str, start: float, end: float, out_path: str):
    # use ffmpeg to trim audio segment
    cmd = [
        "ffmpeg", "-y", "-i", str(audio_path), "-ss", str(start), "-to", str(end), "-ar", "16000", "-ac", "1", str(out_path)
    ]
    subprocess.run(cmd, check=True)


def estimate_gender_from_wav(wav_path: str):
    if librosa is None:
        return "unknown"
    y, sr = librosa.load(wav_path, sr=None)
    # Use librosa.pyin for f0 estimation if available
    try:
        f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=50, fmax=500, sr=sr)
        # f0 can be array; take median of voiced values
        voiced = f0[~np.isnan(f0)]
        if len(voiced) == 0:
            return "unknown"
        median_f0 = float(np.median(voiced))
        # Basic heuristic thresholds (Hz): female > 160, male <= 160
        return "female" if median_f0 > 160 else "male"
    except Exception:
        # fallback: use piptrack
        try:
            pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
            pitches = pitches[magnitudes > np.median(magnitudes)]
            if len(pitches) == 0:
                return "unknown"
            median_f0 = float(np.median(pitches))
            return "female" if median_f0 > 160 else "male"
        except Exception:
            return "unknown"


def detect_speaker_gender(audio_path: str, start: float, end: float, job_dir: str):
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    sample = job_dir / f"gender_sample_{int(start*1000)}_{int(end*1000)}.wav"
    extract_segment(audio_path, start, end, sample)
    return estimate_gender_from_wav(str(sample))

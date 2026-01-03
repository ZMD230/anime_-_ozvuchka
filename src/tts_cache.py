import hashlib
from pathlib import Path
import shutil

CACHE_DIR = Path("data/tts_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _make_key(text: str, voice_id: str = None, voice_gender: str = None, model: str = None):
    key_src = (text or "") + "|" + (voice_id or "") + "|" + (voice_gender or "") + "|" + (model or "")
    return hashlib.sha256(key_src.encode("utf-8")).hexdigest()


def get_cached(text: str, voice_id: str = None, voice_gender: str = None, model: str = None):
    key = _make_key(text, voice_id, voice_gender, model)
    path = CACHE_DIR / f"{key}.wav"
    if path.exists():
        return str(path)
    return None


def store_cache(src_wav: str, text: str, voice_id: str = None, voice_gender: str = None, model: str = None):
    key = _make_key(text, voice_id, voice_gender, model)
    dest = CACHE_DIR / f"{key}.wav"
    shutil.copy(src_wav, dest)
    return str(dest)

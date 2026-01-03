import os
import requests
from pathlib import Path

ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVEN_BASE = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io")
ELEVEN_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")


class ElevenTTS:
    def __init__(self, api_key: str = None, base_url: str = None, default_voice: str = None):
        self.api_key = api_key or ELEVEN_API_KEY
        self.base = base_url or ELEVEN_BASE
        self.default_voice = default_voice or ELEVEN_VOICE_ID
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set")

    def _get_default_voice(self):
        # Try to get first available voice
        url = f"{self.base}/v1/voices"
        headers = {"xi-api-key": self.api_key}
        r = requests.get(url, headers=headers)
        if r.ok:
            j = r.json()
            voices = j.get("voices", [])
            if voices:
                return voices[0].get("voice_id") or voices[0].get("id")
        return None

    def pick_voice_by_gender(self, gender: str = None):
        """Try to pick a voice that matches gender hint (best-effort)."""
        if gender is None:
            return self._get_default_voice()
        url = f"{self.base}/v1/voices"
        headers = {"xi-api-key": self.api_key}
        r = requests.get(url, headers=headers)
        if not r.ok:
            return self._get_default_voice()
        voices = r.json().get("voices", [])
        # Heuristic: look for gender words in voice name or description
        g = gender.lower()
        for v in voices:
            name = (v.get("name") or "").lower()
            if g in name:
                return v.get("voice_id") or v.get("id")
        # fallback: return first voice
        if voices:
            return voices[0].get("voice_id") or voices[0].get("id")
        return None

    def synthesize_to_wav(self, text: str, out_path: str, voice_id: str = None, model: str = None, voice_gender: str = None):
        voice = voice_id or self.default_voice or self._get_default_voice()
        if voice_gender and not voice_id:
            candidate = self.pick_voice_by_gender(voice_gender)
            if candidate:
                voice = candidate
        if not voice:
            raise RuntimeError("No voice available for ElevenLabs API")
        url = f"{self.base}/v1/text-to-speech/{voice}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/wav",
        }
        payload = {"text": text}
        if model:
            payload["model_id"] = model
        r = requests.post(url, json=payload, headers=headers, stream=True, timeout=60)
        if not r.ok:
            raise RuntimeError(f"ElevenLabs TTS error: {r.status_code} {r.text}")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return str(out_path)

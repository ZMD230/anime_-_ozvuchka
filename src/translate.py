import os
import requests

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


def translate_segments(segments, target_language: str):
    """Translate a list of segments in-place and return new list with `translated` field."""
    if not target_language:
        return segments
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not set")

    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"

    texts = [s.get("text", "") for s in segments]
    # Build form data: multiple 'q' fields
    data = {
        "target": target_language,
        "format": "text",
    }
    # requests will encode lists as multiple fields when using tuples
    payload = []
    for t in texts:
        payload.append(("q", t))
    payload.append(("target", target_language))
    payload.append(("format", "text"))

    r = requests.post(url, data=payload)
    if not r.ok:
        raise RuntimeError(f"Translation API error: {r.status_code} {r.text}")

    data = r.json()
    translations = data.get("data", {}).get("translations", [])
    if len(translations) != len(segments):
        # If mismatch, try minimal fallback: translate segment by segment
        translations = []
        for t in texts:
            r = requests.post(url, data={"q": t, "target": target_language, "format": "text"})
            if not r.ok:
                translations.append({"translatedText": ""})
            else:
                translations.append(r.json().get("data", {}).get("translations", [])[0])

    out_segments = []
    for s, tr in zip(segments, translations):
        s2 = s.copy()
        s2["translated"] = tr.get("translatedText", "")
        out_segments.append(s2)

    return out_segments

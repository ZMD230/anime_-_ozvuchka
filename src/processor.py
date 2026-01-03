import subprocess
import json
from pathlib import Path
import shutil

try:
    import whisper
except Exception as e:
    whisper = None

_model = None

def get_model(name: str = "small"):
    global _model
    if _model is None:
        if whisper is None:
            raise RuntimeError("Whisper is not installed")
        _model = whisper.load_model(name)
    return _model


def extract_audio(video_path: str, out_audio_path: str):
    out_audio_path = str(out_audio_path)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        out_audio_path,
    ]
    subprocess.run(cmd, check=True)


def transcribe_audio(audio_path: str, model_name: str = "small"):
    model = get_model(model_name)
    result = model.transcribe(str(audio_path))
    return result


def process_job(job_id: str, file_path: str, meta: dict):
    """Full processing pipeline for a job (used by Celery or sync call).
    Performs transcription, translation, diarization, gender detection and synthesis.
    """
    job_dir = Path("data/uploads") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save meta (in case it's not already saved)
    (job_dir / "meta.json").write_text(json.dumps(meta))

    # Transcription
    try:
        trans_out = transcribe_and_save(job_dir, file_path, meta.get("target_language"), meta.get("translate", True))
        meta["status"] = "transcribed"
        (job_dir / "meta.json").write_text(json.dumps(meta))
    except Exception as e:
        meta.setdefault("errors", {})["transcription"] = str(e)
        (job_dir / "meta.json").write_text(json.dumps(meta))
        raise

    # Auto-assign speakers mapping if available
    try:
        if (job_dir / "speakers.json").exists():
            s = json.loads((job_dir / "speakers.json").read_text())
            mapping = {}
            for spk, info in s.items():
                mapping[spk] = info.get("suggested_gender") or "auto"
            (job_dir / "speakers_mapping.json").write_text(json.dumps(mapping, ensure_ascii=False))
    except Exception as e:
        (job_dir / "speakers_mapping_error.txt").write_text(str(e))

    # Synthesis (may error — handle so job still ends)
    try:
        from src.notify import add_notification
        add_notification(job_dir, "Synthesis started", level="info")
        speakers_map = None
        if (job_dir / "speakers_mapping.json").exists():
            speakers_map = json.loads((job_dir / "speakers_mapping.json").read_text())
        out_video = synthesize_and_mix(job_dir, file_path, voice_gender=meta.get("voice_gender", "auto"), use_translated=meta.get("translate", True), speakers_map=speakers_map)
        meta["output"] = str(out_video)
        add_notification(job_dir, "Synthesis finished", level="info")

        # Try to upload result to S3 if configured
        try:
            from src.storage import upload_file, S3_BUCKET
            if S3_BUCKET:
                key = f"results/{job_id}/{Path(meta['output']).name}"
                upload_file(meta["output"], key)
                # save presigned URL
                from src.storage import get_presigned_url
                url = get_presigned_url(key)
                meta["s3_key"] = key
                meta["s3_url"] = url
        except Exception as e:
            # do not fail job on S3 errors — just log
            (job_dir / "s3_upload_error.txt").write_text(str(e))

    except Exception as e:
        meta.setdefault("errors", {})["tts_pipeline"] = str(e)
        # fallback copy
        out_path = job_dir / f"{Path(file_path).stem}_processed.mp4"
        shutil.copy(file_path, out_path)
        meta["output"] = str(out_path)

    meta["status"] = "done"
    (job_dir / "meta.json").write_text(json.dumps(meta))
    return meta


def synthesize_and_mix(job_dir: str, video_path: str, voice_gender: str = "auto", use_translated: bool = True, speakers_map: dict = None):
    """
    Generate TTS for (translated) segments, mix them into a single audio track and overlay onto the video.
    """
    job_dir = Path(job_dir)
    transcript_file = job_dir / ("transcript_translated.json" if use_translated and (job_dir / "transcript_translated.json").exists() else "transcript.json")
    if not transcript_file.exists():
        raise RuntimeError("Transcript not available for TTS generation")
    trans = json.loads(transcript_file.read_text())
    segments = trans.get("segments", [])

    # Prepare TTS engine with caching and parallel generation
    try:
        from src.tts import ElevenTTS
        from src.tts_cache import get_cached, store_cache
        tts = ElevenTTS()
    except Exception as e:
        raise RuntimeError(f"TTS initialization failed: {e}")

    # Build unique synthesis requests (text + voice choice)
    requests_map = {}  # key -> dict(text, voice_id, voice_gender, segments_indices)
    for i, seg in enumerate(segments):
        text = (seg.get("translated") or seg.get("text") or "").strip()
        if not text:
            continue
        # Speaker/voice resolution
        speaker = None
        if isinstance(seg.get("speakers"), list) and seg.get("speakers"):
            speaker = seg.get("speakers")[0]
        v_id = None
        v_gender = None
        if speakers_map and speaker and speaker in speakers_map:
            mv = speakers_map.get(speaker)
            if isinstance(mv, dict):
                v_id = mv.get("voice_id")
                v_gender = mv.get("gender")
            else:
                v_gender = mv
        if not v_id and not v_gender:
            # use overall voice_gender hint
            if voice_gender in ("male", "female"):
                v_gender = voice_gender

        # final key is text + chosen voice identifier (voice_id if known else voice_gender)
        key = (text, v_id or (v_gender or "auto"))
        requests_map.setdefault(key, {"text": text, "voice_id": v_id, "voice_gender": v_gender, "segments": []})
        requests_map[key]["segments"].append(i)

    # Check cache and create list of synth tasks
    synth_tasks = []  # entries needing generation: (key, data)
    for k, data in requests_map.items():
        cached = get_cached(data["text"], voice_id=data.get("voice_id"), voice_gender=data.get("voice_gender"))
        if cached:
            data["cached"] = cached
        else:
            synth_tasks.append((k, data))

    # Parallel synthesize missing items
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def synthesize_task(data):
        # attempt to pick specific voice_id if only gender provided
        v_id = data.get("voice_id")
        if not v_id and data.get("voice_gender"):
            try:
                candidate = tts.pick_voice_by_gender(data.get("voice_gender"))
                if candidate:
                    v_id = candidate
            except Exception:
                v_id = None
        # synthesize to temp path then store cache
        tmp = job_dir / f"_tmp_synth_{abs(hash(data['text'])) % (10**8)}.wav"
        tts.synthesize_to_wav(data["text"], tmp, voice_id=v_id, voice_gender=data.get("voice_gender"))
        cached = store_cache(str(tmp), data["text"], voice_id=v_id, voice_gender=data.get("voice_gender"))
        try:
            tmp.unlink()
        except Exception:
            pass
        return cached

    if synth_tasks:
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(synthesize_task, data): data for _, data in synth_tasks}
            for fut in as_completed(futures):
                data = futures[fut]
                try:
                    cached_path = fut.result()
                    data["cached"] = cached_path
                except Exception as e:
                    # log error
                    (job_dir / f"tts_task_error_{abs(hash(data['text'])) % (10**8)}.txt").write_text(str(e))

    # Map cached files to segment outputs
    tts_files = []
    for k, data in requests_map.items():
        cached = data.get("cached")
        if not cached:
            continue
        for seg_idx in data.get("segments", []):
            seg = segments[seg_idx]
            start = seg.get("start", 0)
            tts_files.append({"file": cached, "start": start, "speaker": (seg.get("speakers") or [None])[0]})

    if not tts_files:
        raise RuntimeError("No TTS segments were generated")

    # Create delayed versions and mix them
    delayed_files = []
    for idx, it in enumerate(tts_files):
        in_f = it["file"]
        delay_ms = int(float(it.get("start", 0)) * 1000)
        out_delayed = job_dir / f"tts_seg_{idx}_delayed.wav"
        # Use ffmpeg to add silence delay in ms
        cmd = [
            "ffmpeg", "-y", "-i", str(in_f), "-af", f"adelay={delay_ms}|{delay_ms}", str(out_delayed)
        ]
        subprocess.run(cmd, check=True)
        delayed_files.append(str(out_delayed))

    # save speaker->voice mapping if provided
    if speakers_map:
        (job_dir / "speakers_mapping.json").write_text(json.dumps(speakers_map, ensure_ascii=False))

    # Mix delayed files into single track
    mix_out = job_dir / "tts_mixed.wav"
    inputs = []
    filter_inputs = []
    for d in delayed_files:
        inputs += ["-i", d]
        filter_inputs.append("[{}:a]".format(len(filter_inputs)))
    # ffmpeg amix
    cmd = ["ffmpeg", "-y"] + sum([["-i", d] for d in delayed_files], []) + ["-filter_complex", f"amix=inputs={len(delayed_files)}:dropout_transition=0", str(mix_out)]
    subprocess.run(cmd, check=True)

    # Overlay audio onto original video
    out_video = job_dir / f"{Path(video_path).stem}_processed.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path), "-i", str(mix_out), "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0", "-shortest", str(out_video)
    ]
    subprocess.run(cmd, check=True)

    # Apply logo overlay if provided in meta or job folder
    try:
        meta_file = job_dir / "meta.json"
        logo_file = None
        logo_pos = None
        if meta_file.exists():
            m = json.loads(meta_file.read_text())
            logo_file = m.get("logo")
            logo_pos = m.get("logo_position")
        # fallback: search for logo_*
        if not logo_file:
            logos = list(job_dir.glob("logo_*.png")) + list(job_dir.glob("logo_*.jpg")) + list(job_dir.glob("logo_*.jpeg"))
            if logos:
                logo_file = str(logos[0])
        if logo_file:
            try:
                from src.logo import overlay_logo
                out_with_logo = job_dir / f"{Path(video_path).stem}_processed_logo.mp4"
                overlay_logo(str(out_video), logo_file, str(out_with_logo), position=logo_pos or "bottom-left")
                out_video = out_with_logo
            except Exception as e:
                # log error but continue
                (job_dir / "logo_overlay_error.txt").write_text(str(e))

    except Exception:
        pass

    return str(out_video)

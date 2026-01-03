"""Simple benchmark to measure TTS throughput using cache and parallel generation.

Usage:
  python scripts/benchmark_tts.py --n 10

If ELEVENLABS_API_KEY is not set, runs in dry-run mode (no real HTTP calls).
"""
import argparse
import time
from pathlib import Path
import os

from src.tts import ElevenTTS
from src.tts_cache import get_cached


def gen_texts(n):
    return [f"Hello, this is test sentence number {i}." for i in range(n)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=20)
    args = p.parse_args()

    texts = gen_texts(args.n)
    tts = None
    try:
        tts = ElevenTTS()
    except Exception as e:
        print("ElevenLabs not configured, running dry-run (no real synth)")

    start = time.time()
    for t in texts:
        c = get_cached(t, voice_gender='female')
        if c:
            continue
        if tts:
            tmp = Path("/tmp") / f"bench_{abs(hash(t)) % (10**8)}.wav"
            tts.synthesize_to_wav(t, tmp, voice_gender='female')
    elapsed = time.time() - start
    print(f"Processed {len(texts)} texts in {elapsed:.2f}s")


if __name__ == '__main__':
    main()

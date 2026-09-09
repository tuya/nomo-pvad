#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NomoPVAD target-speaker detection — inference example (bundled weights, self-contained).

Given an enrollment clip (target speaker) + a test clip, emit per-160ms-chunk
probabilities of "is the target currently speaking".

Usage:
    python infer.py --enroll enroll.wav --test test.wav
    python infer.py --enroll enroll.wav --test test.wav --device cuda:0 --threshold 0.7
The default weights live under weights/ — no extra download needed.
"""
import os
import sys
import time
import argparse

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from nomo_pvad import NomoPVAD, NomoPVADSession, SR, CHUNK_SAMPLES   # noqa: E402


def load_wav(path: str) -> np.ndarray:
    x, s = sf.read(path, dtype="float32")
    if x.ndim > 1:
        x = x[:, 0]
    if s != SR:
        import librosa
        x = librosa.resample(x, orig_sr=s, target_sr=SR)
    return x.astype(np.float32)


def main():
    ap = argparse.ArgumentParser(description="NomoPVAD target-speaker VAD inference")
    ap.add_argument("--enroll", required=True, help="enrollment (target speaker) wav")
    ap.add_argument("--test", required=True, help="test wav")
    ap.add_argument("--device", default="cpu", help="cpu | cuda:0")
    ap.add_argument("--threshold", type=float, default=0.7,
                    help="target decision threshold (on probability). Default 0.7 favors low "
                         "false-accept; lock / avoid-false-accept scenarios can go higher (0.8+), "
                         "high-recall / turn-taking can drop to 0.5-0.6. Tune per scenario.")
    ap.add_argument("--ckpt", default=os.path.join(HERE, "weights", "nomo_pvad.pt"))
    ap.add_argument("--eres2netv2_dir", default=None, help="ERes2NetV2 directory; leave empty to auto-download from modelscope on first run")
    ap.add_argument("--verbose", action="store_true", help="print per-chunk probability")
    ap.add_argument("--fast", action="store_true", help="skip the streaming playback pacing, return immediately (scripts / eval)")
    args = ap.parse_args()

    model = NomoPVAD(args.ckpt, args.eres2netv2_dir, device=args.device)
    sess = NomoPVADSession(model)
    sess.set_enrollment(load_wav(args.enroll))

    test = load_wav(args.test)
    n = (len(test) + CHUNK_SAMPLES - 1) // CHUNK_SAMPLES
    sec_per_chunk = CHUNK_SAMPLES / SR
    delay = 0.0 if args.fast else min(0.12, 3.0 / max(n, 1))  # bounded streaming pace (~3s total)

    # process chunk by chunk (160ms) and print live (simulate real streaming, not a one-shot pass)
    print(f"▶ streaming detection (one frame per {int(sec_per_chunk * 1000)}ms) …")
    probs = np.zeros(n, dtype=np.float32)
    is_tgt = np.zeros(n, dtype=bool)
    LIVE_W = 56  # max recent frames shown on the live line (scroll left beyond this)
    for i in range(n):
        ch = test[i * CHUNK_SAMPLES:(i + 1) * CHUNK_SAMPLES]
        if len(ch) < CHUNK_SAMPLES:
            ch = np.pad(ch, (0, CHUNK_SAMPLES - len(ch)))
        p = float(sess.process_chunk(ch))
        probs[i] = p
        is_tgt[i] = p >= args.threshold
        t = (i + 1) * sec_per_chunk
        if args.verbose:
            bar = "█" if is_tgt[i] else "·"
            print(f"  {t:6.2f}s  p={p:.2f}  {bar} {'target speaker' if is_tgt[i] else 'non-target / silence'}")
        else:
            recent = "".join("█" if is_tgt[j] else "·"
                             for j in range(max(0, i - LIVE_W + 1), i + 1))
            sys.stdout.write(f"\r  {t:5.1f}s  {recent}  ")
            sys.stdout.flush()
        if delay:
            time.sleep(delay)
    if not args.verbose:
        sys.stdout.write("\n")

    dur = len(test) / SR
    tgt_ratio = is_tgt.mean() * 100
    tgt_sec = float(is_tgt.sum()) * CHUNK_SAMPLES / SR

    # visual timeline: each cell = 160ms, █ = target speaking, · = non-target / silence; a tick every 2s
    strip = "".join("█" if is_tgt[i] else "·" for i in range(n))
    sec_per_chunk = CHUNK_SAMPLES / SR
    axis_chars = [" "] * (n + 4)
    for sec in range(0, int(dur) + 1, 2):
        pos = round(sec / sec_per_chunk)
        for k, c in enumerate(f"{sec}s"):
            if pos + k < len(axis_chars):
                axis_chars[pos + k] = c
    print()
    print("  " + "".join(axis_chars).rstrip())
    print("  " + strip)
    print("  █ target speaking     · non-target / silence")
    print()
    detected = tgt_ratio >= 20
    print(f"Result: {'✅ target speaker detected' if detected else '⚪ target speaker not detected'}"
          f" (~{tgt_sec:.1f}s of target speech, {tgt_ratio:.0f}%)")


if __name__ == "__main__":
    main()

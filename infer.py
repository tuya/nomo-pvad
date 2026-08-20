#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NomoPVAD 目标说话人检测 —— 推理示例（自带权重、自包含）。

给定 注册音(目标说话人) + 测试音，逐 160ms chunk 输出"当前是否目标在说话"的概率。

用法：
    python infer.py --enroll enroll.wav --test test.wav
    python infer.py --enroll enroll.wav --test test.wav --device cuda:0 --threshold 0.7
默认权重在 weights/ 下，无需额外下载。
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
    ap.add_argument("--enroll", required=True, help="注册音(目标说话人) wav")
    ap.add_argument("--test", required=True, help="测试音 wav")
    ap.add_argument("--device", default="cpu", help="cpu | cuda:0")
    ap.add_argument("--threshold", type=float, default=0.7,
                    help="目标判定阈值(概率口径)。默认 0.7 偏低误报;锁/防误放行场景可再高(0.8+),"
                         "高召回/turn-taking 场景可降到 0.5-0.6。按场景调。")
    ap.add_argument("--ckpt", default=os.path.join(HERE, "weights", "nomo_pvad.pt"))
    ap.add_argument("--eres2netv2_dir", default=None, help="ERes2NetV2 目录；留空则首次自动从 modelscope 下载")
    ap.add_argument("--verbose", action="store_true", help="打印逐 chunk 概率")
    ap.add_argument("--fast", action="store_true", help="跳过流式播放节奏，立即出结果(脚本/评测用)")
    args = ap.parse_args()

    model = NomoPVAD(args.ckpt, args.eres2netv2_dir, device=args.device)
    sess = NomoPVADSession(model)
    sess.set_enrollment(load_wav(args.enroll))

    test = load_wav(args.test)
    n = (len(test) + CHUNK_SAMPLES - 1) // CHUNK_SAMPLES
    sec_per_chunk = CHUNK_SAMPLES / SR
    delay = 0.0 if args.fast else min(0.12, 3.0 / max(n, 1))  # 有界流式节奏(整段约 3s)

    # 逐 160ms chunk 流式处理并实时输出（模拟真实流式，而非一次性算完）
    print(f"▶ 流式检测中（每 {int(sec_per_chunk * 1000)}ms 出一帧）…")
    probs = np.zeros(n, dtype=np.float32)
    is_tgt = np.zeros(n, dtype=bool)
    LIVE_W = 56  # 实时行最多显示最近多少帧（超出则向左滚动）
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
            print(f"  {t:6.2f}s  p={p:.2f}  {bar} {'目标说话人' if is_tgt[i] else '非目标 / 静音'}")
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

    # 直观时间轴：每格 160ms，█ = 目标说话人在说，· = 非目标 / 静音；每 2s 一个刻度
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
    print("  █ 目标说话人在说话    · 非目标 / 静音")
    print()
    detected = tgt_ratio >= 20
    print(f"结论：{'✅ 检测到目标说话人' if detected else '⚪ 未检测到目标说话人'}"
          f"（目标说话约 {tgt_sec:.1f}s，占 {tgt_ratio:.0f}%）")


if __name__ == "__main__":
    main()

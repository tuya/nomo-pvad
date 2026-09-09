# nomo-pvad — Streaming Target-Speaker Detection (Inference)

**English** | [<kbd>简体中文</kbd>](README.zh-CN.md)

Given a target speaker's **enrollment audio** and an incoming **audio stream**, nomo-pvad determines **whether the target speaker is speaking, in real time, at 160 ms intervals**. It supports applications that respond only to an enrolled speaker, including scenarios with multiple speakers and background noise. Inference operates on streaming audio chunks and supports on-device deployment.

- **Input**: enrollment audio (used to extract a d-vector speaker embedding) and a 16 kHz audio stream to analyze
- **Output**: a target-speaker probability ∈ [0, 1] for every 160 ms chunk
- Includes **inference code and sample audio**, without training code. Version `1.1` (tag `release-1.1`).

> 📄 **Technical report** (task definition, module architecture and configuration, training settings, and measured latency and accuracy): <https://tuya.com/model/doc/pvad>

> 🎧 **Online demo**: <https://tuya.com/model/demo/pvad>
>
> ⚠️ The demo includes substantial additional engineering beyond the open-source baseline in this repository (**model only, no pre/post-processing**). Those additions are not included in this release.

## Installation
```bash
# After cloning the repo, install dependencies:
pip install -r requirements.txt
```
> The nomo-pvad weights (approximately 35 MB) are bundled at `weights/nomo_pvad.pt`, so no separate download is required for these weights. The original ERes2NetV2 speaker model is downloaded automatically on first run if it is not already available locally (see [Architecture](#architecture)).

## Command-line usage
The repository includes enrollment and test audio for a quick check. The first portion of the test clip contains the target speaker and should be classified as target speech; the later portion contains a non-target speaker and should be classified as non-target speech:
```bash
python infer.py --enroll examples/enroll.wav --test examples/test.wav --verbose
```
Illustrative output (excerpt; `p` is the target-speaker probability, followed by a timeline with 160 ms resolution):
```text
▶ streaming detection (one frame per 160 ms) …
    0.16s  p=0.92  █ target speaker
    0.32s  p=0.90  █ target speaker
    ...
    2.72s  p=0.11  · non-target / silence
    2.88s  p=0.08  · non-target / silence

  0s          2s          4s
  ████████████████··········
  █ target speaking     · non-target / silence

Result: ✅ target speaker detected (≈ 2.4 s of target speech, 55%)
```
Or use your own audio:
```bash
python infer.py --enroll enroll.wav --test test.wav
# per-chunk log: --verbose ; GPU: --device cuda:0 ; threshold: --threshold 0.7
```

## Selecting the decision threshold
`process_chunk` returns the **target-speaker probability P(target) ∈ [0, 1]**. The decision threshold defines the **operating point selected for deployment** and should be adjusted to the application:

| Scenario | Suggested threshold | Trade-off |
|---|---|---|
| **Speaker-based gating / false-acceptance prevention** (high cost of false acceptance) | **0.7–0.85** | Lower false acceptance rate, slightly higher miss rate (the target speaker may occasionally need to repeat themselves); default 0.7 |
| Balanced | 0.6 | Balance between recall and false acceptance rate |
| Multi-speaker turn-taking / high recall | 0.5–0.6 | Prioritize recall while tolerating more false acceptances |

> A higher threshold makes acceptance more conservative. Streaming deployments typically also use a state machine with hysteresis, requiring N consecutive frames before changing the detection state, to reduce rapid state changes.

## Library usage
```python
from nomo_pvad import NomoPVAD, NomoPVADSession

m = NomoPVAD("weights/nomo_pvad.pt", device="cpu")   # ERes2NetV2 auto-downloads on first run
sess = NomoPVADSession(m)
sess.set_enrollment(enroll_pcm_f32_16k)          # enroll the target speaker
for chunk_f32 in stream_160ms_chunks:           # 160 ms each (2560 samples @ 16k)
    p = sess.process_chunk(chunk_f32)            # target-speaker probability [0, 1]
```

## Repository structure
```
infer.py           Command-line inference example
nomo_pvad.py       Streaming inference wrapper (enrollment → per-chunk probability)
core/              Model architecture (model + eres2netv2_backbone + film + frame_adapter)
weights/           Bundled nomo_pvad.pt weights; the original ERes2NetV2 model is downloaded on first run
examples/          Sample audio (enroll.wav + test.wav)
```

## Architecture

```
enroll (≥10s) ─► ERes2NetV2 full model (with pooling, frozen) ─► d-vector 192-d (L2-normalized)
                                                                   │  one-time; runtime only needs this vector
                                                                   ▼
stream ─► Fbank ─► ERes2NetV2 trunk ─► FiLM ─► proj ─► speech encoder ─► det decoder ─► chunk head ─► P(target)
 16kHz    80-d    pooling removed·8× ds  γ·(x+β) 1024→256   causal ×2        causal ×1     every 2 frames  every 160ms
```

| Module | Configuration | Parameters |
|---|---|---|
| Acoustic features | 80-dimensional filterbank (Fbank) features, 25 ms window / 10 ms hop, dither=0, mean subtraction over the time dimension | — |
| Speaker backbone | ERes2NetV2 (baseWidth=26, scale=2, expansion=2), final pooling removed; 8× temporal downsampling → 12.5 Hz (80 ms/frame), mean pooling over the frequency dimension, 1024-dimensional output | 13.93M |
| FiLM modulation | 192 → LayerNorm→Linear(512)→SiLU→Dropout(0.1)→Linear(2048), split into (γ̃, β), γ=1+γ̃, output `γ·(x+β)`; final layer initialized to zero → identity mapping at the start of training | 1.15M |
| Feature projection | LayerNorm(1024) + Linear(1024→256) | 0.26M |
| Speech encoder | CausalConv1d + GLU residual blocks ×2, d_model=256, kernel=7 | 1.84M |
| Detection decoder | Same residual block ×1 | 0.92M |
| Chunk classification head | Mean pooling over every 2 backbone frames (2 × 80 ms) to produce 1 chunk → LayerNorm + Linear(256) + SiLU + Dropout + Linear(2), softmax yields the target-class probability | 0.07M |
| **Total** | | **18.16M**, FP16 weights: 36.6 MB |

> The bundled `nomo_pvad.pt` contains the fine-tuned backbone. The full original ERes2NetV2 (with pooling) extracts the enrollment embedding. If enrollment happens in the cloud or during provisioning, pass the precomputed 192-dimensional vector to `sess.set_enrollment_emb(...)`. The current Python wrapper also loads the original ERes2NetV2 checkpoint during initialization, even with a precomputed embedding. For offline use, cache that model in advance or pass its local directory via `eres2netv2_dir` (CLI: `--eres2netv2_dir`); otherwise, it is downloaded automatically on first run.

**Key design choices:**
- **A single network** integrates voice activity detection (VAD), target-speaker discrimination, and temporal modeling, producing an output every 160 ms. This avoids combining separate speaker verification, VAD, and rule-based components, simplifying deployment and supporting low-latency operation.
- **FiLM speaker conditioning**: the enrollment d-vector applies an affine modulation to each frame's features instead of being concatenated at the input, preserving speaker conditioning in deeper layers. Zero initialization of the final layer makes the modulation an identity mapping at the start of training.
- **Temporal modeling with CausalConv1d + GLU residual blocks** (instead of a Conformer with a look-ahead window): training and inference share the same structure, with no reliance on truncating future frames at inference time.

## Intended use and limitations
- **Intended use**: on-device or cloud applications that respond only to the enrolled speaker, including scenarios with multiple speakers and background noise. Voiceprint enrollment requires the speaker's **informed consent**.
- **Unintended use**: monitoring or tracking without consent, or high-risk applications such as identity authentication. The model is not designed for spoofing countermeasures or liveness detection.
- **Limitations**: performance degrades with very short enrollment audio (<1 s), lossy audio transmission (e.g. Opus), mismatched recording environments, or far-field audio. Distinguishing speakers of the same gender with similar vocal timbres is a known challenge.

## License
- **Code**: Apache-2.0 (see `LICENSE`).
- **ERes2NetV2 speaker backbone**: from [3D-Speaker / ModelScope](https://github.com/modelscope/3D-Speaker) (`iic/speech_eres2netv2_sv_zh-cn_16k-common`), declared Apache-2.0 upstream.
  - `weights/nomo_pvad.pt` **contains weights fine-tuned from that backbone** (final pooling removed, all parameters fine-tuned for this task) — a derivative work, redistributed under Apache-2.0 with attribution here.
  - The **enrollment side** uses the unmodified original full model (with pooling); it is not bundled and downloads automatically from ModelScope on first run.

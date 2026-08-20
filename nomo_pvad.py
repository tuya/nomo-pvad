# -*- coding: utf-8 -*-
"""NomoPVAD 流式打分器（自包含）。

把 NomoPVAD 网络包装成「注册一次 + 逐 chunk 出目标概率」的流式接口，
仅依赖本包 core 的 build_model + modelscope ERes2NetV2（提注册 embedding）。

用法：
    m = NomoPVAD(ckpt, eres2netv2_dir, device='cpu')
    sess = NomoPVADSession(m)
    sess.set_enrollment(enroll_pcm_float32_16k)   # 注册目标说话人
    for chunk in chunks:                          # 每 160ms (2560 采样 @16k)
        prob = sess.process_chunk(chunk_float32)  # 目标说话人概率 [0,1]
    # 或离线整段：
    probs = sess.score_utterance(pcm_float32)     # 每 chunk 概率数组
"""
from __future__ import annotations

import os
import sys
import logging
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F
import torchaudio.compliance.kaldi as kaldi

logger = logging.getLogger("nomo_pvad")

#: 允许从权重文件 model_cfg 读取的架构字段白名单（其余一律忽略，防配置注入）。
#: 与 core/model.py NomoPVADNet 读取的键保持一致；eres2netv2_model_dir 由本类注入，不在此列。
_ALLOWED_CFG_KEYS = frozenset({
    "spk_embed_dim", "film_hidden", "film_dropout", "d_model",
    "adapter_kernel", "adapter_dropout", "speech_encoder_depth",
    "classifier_hidden_dim", "classifier_dropout", "num_classes",
    "decoder_depth", "eres2netv2_ckpt_filename",
})

SR = 16000
CHUNK_SAMPLES = SR * 160 // 1000      # 2560 = 160ms


def _eres2netv2_fbank(wav: torch.Tensor, sample_rate: int = SR) -> torch.Tensor:
    """80 维 fbank（25/10ms, dither=0）+ 减时间均值，与 ERes2NetV2 训练口径一致。"""
    if wav.dim() == 1:
        wav = wav.unsqueeze(0)
    wav = wav * (1 << 15)
    feat = kaldi.fbank(wav, num_mel_bins=80, frame_length=25, frame_shift=10,
                       sample_frequency=sample_rate, dither=0.0)
    return feat - feat.mean(dim=0, keepdim=True)


# ERes2NetV2 声纹骨干为第三方模型（3D-Speaker / modelscope），本仓不打包其权重；
# 首次使用时从 modelscope 官方源自动下载。
ERES2NETV2_MODELSCOPE_ID = "iic/speech_eres2netv2_sv_zh-cn_16k-common"


def _resolve_eres_dir(eres_dir: Optional[str]) -> str:
    """返回含 pretrained_eres2netv2.ckpt 的目录：本地目录 > modelscope 缓存 > 联网下载。

    已缓存时直接用缓存目录、**跳过 snapshot_download**——它是每次刷"Downloading N files"
    日志与进度条的来源；只有真没缓存的首次运行才联网下载。
    """
    ckpt = "pretrained_eres2netv2.ckpt"
    if eres_dir and os.path.isfile(os.path.join(eres_dir, ckpt)):
        return eres_dir
    # 命中 modelscope 本地缓存则静默返回（用 glob 定位，兼容不同 modelscope 版本的缓存结构）
    import glob
    name = ERES2NETV2_MODELSCOPE_ID.split("/")[-1]
    cache_root = os.environ.get("MODELSCOPE_CACHE") or \
        os.path.join(os.path.expanduser("~"), ".cache", "modelscope")
    hits = glob.glob(os.path.join(cache_root, "**", name, ckpt), recursive=True)
    if hits:
        return os.path.dirname(hits[0])
    # 未缓存：首次联网下载（此时 modelscope 的下载进度是正常且有用的）
    logger.info("首次运行：从 modelscope 下载 ERes2NetV2 声纹骨干 %s …", ERES2NETV2_MODELSCOPE_ID)
    try:
        from modelscope import snapshot_download
    except Exception:                                          # 兼容旧版 modelscope
        from modelscope.hub.snapshot_download import snapshot_download
    return snapshot_download(ERES2NETV2_MODELSCOPE_ID)


class NomoPVAD:
    """NomoPVAD 网络 + ERes2NetV2 提取器（进程内加载一次，多会话共用）。"""

    def __init__(self, ckpt: str, eres2netv2_dir: Optional[str] = None, device: str = "cpu"):
        self.device = torch.device(device)
        # 第三方 ERes2NetV2：本地有则用，否则自动从 modelscope 下载（不打包别人的权重）
        self._eres2netv2_dir = _resolve_eres_dir(eres2netv2_dir)

        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from core.model import build_model                    # noqa: E402

        # weights_only=True：只反序列化张量/基础类型，拒绝 pickle 任意对象，
        # 防被篡改的 .pt 通过 __reduce__ 执行任意代码（RCE）。
        state = torch.load(ckpt, map_location="cpu", weights_only=True)
        # model_cfg 只接受白名单内的架构字段，避免从权重文件注入任意配置（超大维度等）。
        raw_cfg = state.get("model_cfg", {}) if isinstance(state, dict) else {}
        cfg = {k: v for k, v in raw_cfg.items() if k in _ALLOWED_CFG_KEYS}
        cfg["eres2netv2_model_dir"] = self._eres2netv2_dir
        self.model = build_model(cfg)
        self.model.load_state_dict(state.get("model_state_dict", state), strict=False)
        self.model.eval().to(self.device)

        self._eres = None   # ERes2NetV2 提取器 lazy 加载
        logger.info("NomoPVAD 就绪 (device=%s)", device)

    def _ensure_eres(self):
        if self._eres is not None:
            return
        from modelscope.models.audio.sv.ERes2NetV2 import ERes2NetV2   # noqa
        m = ERes2NetV2(feat_dim=80, embed_dim=192, baseWidth=26, scale=2, expansion=2)
        ck = os.path.join(self._eres2netv2_dir, "pretrained_eres2netv2.ckpt")
        m.load_state_dict(torch.load(ck, map_location="cpu", weights_only=True), strict=False)
        m.eval().to(self.device)
        for p in m.parameters():
            p.requires_grad_(False)
        self._eres = m

    @torch.no_grad()
    def extract_emb(self, pcm_f32: np.ndarray) -> torch.Tensor:
        """注册音 → L2-归一 192 维 d-vector。"""
        self._ensure_eres()
        feat = _eres2netv2_fbank(torch.from_numpy(np.asarray(pcm_f32, dtype=np.float32))).unsqueeze(0).to(self.device)
        return F.normalize(self._eres(feat).float(), dim=-1)   # (1, 192)

    @torch.no_grad()
    def probs_on(self, spk_emb: torch.Tensor, pcm_f32: np.ndarray) -> np.ndarray:
        """给定 spk_emb 与一段音频 → 每 chunk 目标说话人概率。"""
        fb = _eres2netv2_fbank(torch.from_numpy(np.asarray(pcm_f32, dtype=np.float32))).unsqueeze(0).to(self.device)
        lens = torch.tensor([fb.shape[1]], device=self.device)
        out = self.model(spk_emb, fb, lens)
        mask = out["chunk_mask"][0].cpu().numpy()
        probs = F.softmax(out["chunk_logits"], dim=-1)[0, :, 1].cpu().numpy()
        return probs[mask]


class NomoPVADSession:
    """每连接一份：持有 spk_emb + 滑动窗，逐 chunk 出目标概率。共用 NomoPVAD。"""

    def __init__(self, model: NomoPVAD, window_sec: float = 2.4):
        self.m = model
        self.window_samples = int(SR * window_sec)
        self.spk_emb: Optional[torch.Tensor] = None
        self._buf = np.zeros(0, dtype=np.float32)

    def set_enrollment(self, pcm_f32: np.ndarray):
        """用注册音提 embedding 并复位。"""
        self.spk_emb = self.m.extract_emb(pcm_f32)
        self.reset()

    def set_enrollment_emb(self, emb_192: np.ndarray):
        """直接用预先算好的 192 维 embedding 注册并复位。"""
        e = torch.from_numpy(np.asarray(emb_192, dtype=np.float32)).reshape(1, -1)
        self.spk_emb = F.normalize(e, dim=-1).to(self.m.device)
        self.reset()

    def reset(self):
        self._buf = np.zeros(0, dtype=np.float32)

    def process_chunk(self, chunk_f32: np.ndarray) -> float:
        """逐 160ms chunk：在滑窗内跑 NomoPVAD，返回当前 chunk 的目标说话人概率。"""
        assert self.spk_emb is not None, "先 set_enrollment"
        self._buf = np.concatenate([self._buf, np.asarray(chunk_f32, dtype=np.float32)])
        if self._buf.size > self.window_samples:
            self._buf = self._buf[-self.window_samples:]
        if self._buf.size < CHUNK_SAMPLES:
            return 0.0
        probs = self.m.probs_on(self.spk_emb, self._buf)
        return float(probs[-1]) if len(probs) else 0.0

    def score_utterance(self, pcm_f32: np.ndarray) -> np.ndarray:
        """整段一次算出每 chunk 概率（离线）。"""
        assert self.spk_emb is not None, "先 set_enrollment"
        return self.m.probs_on(self.spk_emb, pcm_f32)

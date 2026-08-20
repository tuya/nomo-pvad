#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NomoPVAD 模型定义。

以注册说话人 embedding 为条件，从连续音频流中逐 160ms chunk 判定目标说话人是否在说话。
时序部分严格因果，可端侧流式。方法参考 Google Personal VAD 与 Lin et al. (Interspeech 2025)。

数据流（T = fbank 帧数, T_frame = T/8）：
    test_fbank (B, T, 80)
        │ ERes2NetV2 backbone（8x 时间下采样 + 频率 mean-pool）
        ▼
    frame_feat (B, T_frame, 1024) ──FiLM(spk_emb) 调制──► (B, T_frame, 1024)
        │ feat_proj: LayerNorm + Linear(1024 → d_model=256)
        ▼
    x (B, T_frame, 256)
        │ speech encoder: CausalFrameAdapter(depth=2)
        ▼
    enc_feat (B, T_frame, 256)
        │ det decoder(depth=1) → 每 2 帧 mean-pool 成 chunk → classifier_det
        ▼
    chunk_logits (B, N_chunks, 2)   # softmax 后取第 1 类即目标说话人概率
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from .eres2netv2_backbone import ERes2NetV2Backbone
from .frame_adapter import CausalFrameAdapter
from .film import FiLMSpeakerCond

logger = logging.getLogger(__name__)

FRAMES_PER_CHUNK = 2  # 每 2 个 ERes2NetV2 帧 (80ms) = 1 chunk (160ms)


class NomoPVADNet(nn.Module):
    """NomoPVAD 网络：backbone + FiLM + speech encoder + det decoder + 分类头。"""

    def __init__(self, config: Dict):
        """
        config 字段（除 eres2netv2_model_dir 外均带默认值）：
            eres2netv2_model_dir       : ERes2NetV2 权重目录（必填）
            eres2netv2_ckpt_filename   : 'pretrained_eres2netv2.ckpt'
            spk_embed_dim              : 192
            d_model                    : 256
            film_hidden                : 512
            film_dropout               : 0.1
            speech_encoder_depth       : 2
            decoder_depth              : 1
            adapter_kernel             : 7
            adapter_dropout            : 0.1
            classifier_hidden_dim      : 256
            classifier_dropout         : 0.1
            num_classes                : 2
        """
        super().__init__()
        self.config = config

        # ---------------- Backbone ----------------
        self.backbone = ERes2NetV2Backbone(
            model_dir=config['eres2netv2_model_dir'],
            ckpt_filename=config.get('eres2netv2_ckpt_filename', 'pretrained_eres2netv2.ckpt'),
        )
        self.backbone_output_dim = self.backbone.output_dim        # 1024

        # ---------------- 说话人融合：FiLM ----------------
        self.spk_in_dim = config.get('spk_embed_dim', 192)
        self.film = FiLMSpeakerCond(
            spk_dim=self.spk_in_dim,
            feat_dim=self.backbone_output_dim,                     # 1024
            hidden=config.get('film_hidden', 512),
            dropout=config.get('film_dropout', 0.1),
        )

        # ---------------- Feature projection (1024 → d_model) ----------------
        self.d_model = config.get('d_model', 256)
        self.feat_proj = nn.Sequential(
            nn.LayerNorm(self.backbone_output_dim),
            nn.Linear(self.backbone_output_dim, self.d_model),
        )

        # ---------------- Speech Encoder ----------------
        adapter_kernel = config.get('adapter_kernel', 7)
        adapter_dropout = config.get('adapter_dropout', 0.1)
        self.speech_encoder = CausalFrameAdapter(
            d_model=self.d_model,
            depth=config.get('speech_encoder_depth', 2),
            kernel_size=adapter_kernel,
            dropout=adapter_dropout,
        )

        # ---------------- Det Decoder + 分类头 ----------------
        cls_hidden = config.get('classifier_hidden_dim', self.d_model)
        cls_dropout = config.get('classifier_dropout', 0.1)
        num_classes = config.get('num_classes', 2)
        self.det_decoder = CausalFrameAdapter(
            d_model=self.d_model,
            depth=config.get('decoder_depth', 1),
            kernel_size=adapter_kernel,
            dropout=adapter_dropout,
        )
        self.classifier_det = nn.Sequential(
            nn.LayerNorm(self.d_model),
            nn.Linear(self.d_model, cls_hidden),
            nn.SiLU(),
            nn.Dropout(cls_dropout),
            nn.Linear(cls_hidden, num_classes),
        )

        self.frames_per_chunk = FRAMES_PER_CHUNK

        n_total = sum(p.numel() for p in self.parameters())
        logger.info(f"NomoPVADNet: d_model={self.d_model}, params={n_total/1e6:.2f}M")

    def _backbone_forward(self, fbank_e2: torch.Tensor) -> torch.Tensor:
        # backbone 严格 8x 下采样，长度补齐到 8 的倍数
        T = fbank_e2.size(1)
        pad = (self.backbone.TIME_DOWNSAMPLE - T % self.backbone.TIME_DOWNSAMPLE) \
              % self.backbone.TIME_DOWNSAMPLE
        if pad > 0:
            fbank_e2 = F.pad(fbank_e2, (0, 0, 0, pad))
        return self.backbone(fbank_e2)

    def _extract_chunks(self, x: torch.Tensor) -> torch.Tensor:
        """每 frames_per_chunk 帧 mean-pool 成 1 个 chunk。"""
        B, T, D = x.shape
        g = self.frames_per_chunk
        pad = (g - T % g) % g
        if pad > 0:
            x = F.pad(x, (0, 0, 0, pad))
        return x.view(B, -1, g, D).mean(dim=2)

    def _compute_chunk_mask(self, test_lengths: torch.Tensor, T_input: int) -> torch.Tensor:
        total_downsample = self.backbone.TIME_DOWNSAMPLE * self.frames_per_chunk
        chunk_lens = (test_lengths + total_downsample - 1) // total_downsample
        N_chunk = (T_input + total_downsample - 1) // total_downsample
        arange = torch.arange(N_chunk, device=test_lengths.device).unsqueeze(0)
        return arange < chunk_lens.unsqueeze(1)

    @torch.no_grad()
    def forward(self,
                spk_emb: torch.Tensor,
                test_fbank: torch.Tensor,
                test_lengths: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Args:
            spk_emb:      (B, 192)  L2-normalized 注册说话人 embedding
            test_fbank:   (B, T, 80) 已减时间维均值
            test_lengths: (B,)      每条样本的有效帧数
        Returns:
            {
              'chunk_logits': (B, N, 2)   每 chunk 二分类 logits（第 1 类为目标）
              'chunk_mask':   (B, N) bool 有效 chunk 掩码
            }
        """
        T_input = test_fbank.size(1)
        frame_feat = self._backbone_forward(test_fbank)            # (B, T/8, 1024)
        fused = self.film(frame_feat, spk_emb)                     # (B, T/8, 1024)
        x = self.feat_proj(fused)                                  # (B, T/8, 256)
        enc_feat = self.speech_encoder(x)                          # (B, T/8, 256)
        det_x = self.det_decoder(enc_feat)                         # (B, T/8, 256)
        chunk_logits = self.classifier_det(self._extract_chunks(det_x))  # (B, N, 2)
        chunk_mask = self._compute_chunk_mask(test_lengths, T_input)
        return {'chunk_logits': chunk_logits, 'chunk_mask': chunk_mask}


def build_model(config: Optional[Dict] = None) -> NomoPVADNet:
    return NomoPVADNet(config or {})

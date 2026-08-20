#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FiLM 说话人条件调制层。

用注册说话人 embedding 生成逐通道仿射参数 (γ, β)，调制帧级特征：
    out = γ(spk) · (feat + β(spk))
γ、β 沿时间维广播；最后一层零初始化使启动时为 identity。
"""
from __future__ import annotations

import torch
import torch.nn as nn


class FiLMSpeakerCond(nn.Module):
    """Speaker-conditioned FiLM modulation for frame-level features.

    γ(zspk), β(zspk) ∈ R^C are channel-wise modulation params,
    broadcast along time dimension.
    """

    def __init__(self,
                 spk_dim: int = 192,
                 feat_dim: int = 1024,
                 hidden: int = 512,
                 dropout: float = 0.1):
        super().__init__()
        self.spk_dim = spk_dim
        self.feat_dim = feat_dim

        self.proj = nn.Sequential(
            nn.LayerNorm(spk_dim),
            nn.Linear(spk_dim, hidden),
            nn.SiLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, 2 * feat_dim),
        )
        # 最后一层零初始化 → 启动时 γ=1, β=0，输出等于输入
        nn.init.zeros_(self.proj[-1].weight)
        nn.init.zeros_(self.proj[-1].bias)

    def forward(self,
                frame_feat: torch.Tensor,
                spk_emb: torch.Tensor) -> torch.Tensor:
        """
        Args:
            frame_feat: (B, T, C) 主信号帧级特征
            spk_emb:    (B, D_spk) 已 L2-norm 的说话人 embedding
        Returns:
            (B, T, C) FiLM 调制后特征
        """
        gb = self.proj(spk_emb)                          # (B, 2C)
        gamma_tilde, beta = gb.chunk(2, dim=-1)          # 各 (B, C)
        gamma = (1.0 + gamma_tilde).unsqueeze(1)         # (B, 1, C) 沿时间广播
        beta = beta.unsqueeze(1)                         # (B, 1, C)
        return gamma * (frame_feat + beta)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""因果 1D 卷积帧适配器（Causal Conv1d ResBlock + GLU）。

时序建模模块，输入输出均为 (B, T, D)，时间维长度不变。
每个 ResBlock = CausalConv1d(D→2D) + GLU + LayerNorm + Dropout + 残差。
时间维严格因果（仅左侧 padding），无 self-attention，天然支持流式推理
（每步只需缓存最后 kernel-1 帧）。
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class ChannelLayerNorm1d(nn.Module):
    """对 (B, C, T) 输入做沿 channel 维的 LayerNorm（每个时间步独立归一化）。

    与 nn.GroupNorm(1, C) 的区别：
        GroupNorm(1) 沿 (C, T) 一起算 mean/var → **破坏因果性**（用到未来帧统计）
        ChannelLayerNorm1d 只沿 C 算 mean/var → 严格因果

    实现等价于 nn.LayerNorm(C)，但作用维度通过 transpose 处理。
    """

    def __init__(self, num_channels: int, eps: float = 1e-5):
        super().__init__()
        self.norm = nn.LayerNorm(num_channels, eps=eps)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # (B, C, T) → (B, T, C) → LayerNorm(C) → (B, C, T)
        x = x.transpose(1, 2).contiguous()
        x = self.norm(x)
        x = x.transpose(1, 2).contiguous()
        return x


class CausalConv1dResBlock(nn.Module):
    """因果 1D Conv ResBlock（带 GLU）。

    数据流：
        x (B, D, T)
          → 左 pad (kernel-1)  → CausalConv1d(D → 2D, k)
          → GLU (沿 channel 切半)        → (B, D, T)
          → ChannelLayerNorm（每帧独立沿 channel 维归一化，严格因果）
          → Dropout
          → x + residual
        → ReLU
        → return (B, D, T)
    """

    def __init__(self,
                 d_model: int,
                 kernel_size: int = 7,
                 dropout: float = 0.1):
        super().__init__()
        assert kernel_size >= 1
        self.kernel_size = kernel_size
        self.left_pad = kernel_size - 1
        self.conv = nn.Conv1d(
            in_channels=d_model,
            out_channels=2 * d_model,   # GLU 需要 2x channel
            kernel_size=kernel_size,
            padding=0,                  # 自行因果 pad
            bias=True,
        )
        self.norm = ChannelLayerNorm1d(d_model)
        self.drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, D, T)
        Returns:
            out: (B, D, T)
        """
        residual = x
        x = F.pad(x, (self.left_pad, 0))             # 仅左 pad → 严格因果
        x = self.conv(x)                              # (B, 2D, T)
        x = F.glu(x, dim=1)                           # (B, D, T)
        x = self.norm(x)
        x = self.drop(x)
        return F.relu(x + residual, inplace=False)


class CausalFrameAdapter(nn.Module):
    """3 层 Causal 1D Conv ResBlock 堆叠。"""

    def __init__(self,
                 d_model: int = 256,
                 depth: int = 3,
                 kernel_size: int = 7,
                 dropout: float = 0.1):
        super().__init__()
        self.d_model = d_model
        self.depth = depth
        self.blocks = nn.ModuleList([
            CausalConv1dResBlock(d_model=d_model,
                                 kernel_size=kernel_size,
                                 dropout=dropout)
            for _ in range(depth)
        ])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, T, D)
        Returns:
            out: (B, T, D)
        """
        x = x.transpose(1, 2).contiguous()           # (B, D, T)
        for blk in self.blocks:
            x = blk(x)
        x = x.transpose(1, 2).contiguous()           # (B, T, D)
        return x

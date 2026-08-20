#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ERes2NetV2 backbone 封装。

复用 modelscope 预训练 ERes2NetV2，砍掉末端 pooling / seg 层，暴露帧级特征：
  - 输入 fbank: (B, T, 80) @ 10ms hop，已沿时间维减均值（ERes2NetV2 训练口径）
  - 内部时间下采样 8x → 帧率 12.5Hz（80ms/帧），频率维 mean-pool
  - 输出 frame features: (B, T/8, 1024)；每 2 帧 = 1 个 160ms chunk

推理阶段随模型一起 eval，不修改 backbone 权重。
"""
from __future__ import annotations
import os
import logging

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


def _try_import_modelscope_eres2netv2():
    """兼容不同 modelscope 版本的模块路径，返回 ERes2NetV2 类。"""
    try:
        from modelscope.models.audio.sv.ERes2NetV2 import ERes2NetV2
        return ERes2NetV2
    except Exception:
        pass
    try:
        from modelscope.models.audio.sv.eres2netv2 import ERes2NetV2
        return ERes2NetV2
    except Exception:
        pass
    return None


class ERes2NetV2Backbone(nn.Module):
    """ERes2NetV2 backbone（去 pool 版本），输出帧级特征 (B, T/8, 1024)。"""

    # ERes2NetV2 标准版超参（与 modelscope ckpt 匹配）
    EXPECTED_FEAT_DIM = 80
    EXPECTED_EMBED_DIM = 192
    EXPECTED_BASE_WIDTH = 26
    EXPECTED_SCALE = 2
    EXPECTED_EXPANSION = 2
    M_CHANNELS = 64
    TIME_DOWNSAMPLE = 8       # 总时间下采样比（layer2/3/4 各 stride=2）

    def __init__(self,
                 model_dir: str,
                 ckpt_filename: str = 'pretrained_eres2netv2.ckpt'):
        """
        Args:
            model_dir: ERes2NetV2 ckpt 所在目录
            ckpt_filename: ckpt 文件名
        """
        super().__init__()
        self.model_dir = os.path.abspath(model_dir)
        ckpt_path = os.path.join(self.model_dir, ckpt_filename)
        if not os.path.exists(ckpt_path):
            raise FileNotFoundError(f"ERes2NetV2 ckpt 不存在: {ckpt_path}")

        ERes2NetV2 = _try_import_modelscope_eres2netv2()
        if ERes2NetV2 is None:
            raise ImportError("未找到 modelscope ERes2NetV2 定义，请 `pip install modelscope`。")
        net = ERes2NetV2(
            feat_dim=self.EXPECTED_FEAT_DIM,
            embed_dim=self.EXPECTED_EMBED_DIM,
            baseWidth=self.EXPECTED_BASE_WIDTH,
            scale=self.EXPECTED_SCALE,
            expansion=self.EXPECTED_EXPANSION,
        )
        # weights_only=True：拒绝 pickle 任意对象反序列化，防被篡改的 ckpt 执行任意代码。
        state = torch.load(ckpt_path, map_location='cpu', weights_only=True)
        net.load_state_dict(state, strict=False)

        # 只保留 trunk（conv1/bn1/layer1-4/layer3_ds/fuse34），砍掉 pool/seg
        self.conv1 = net.conv1
        self.bn1 = net.bn1
        self.layer1 = net.layer1
        self.layer2 = net.layer2
        self.layer3 = net.layer3
        self.layer4 = net.layer4
        self.layer3_ds = net.layer3_ds
        self.fuse34 = net.fuse34

        self.output_dim = self.M_CHANNELS * 8 * self.EXPECTED_EXPANSION   # 64*8*2 = 1024
        logger.info(f"ERes2NetV2Backbone: output_dim={self.output_dim}, "
                    f"time_downsample={self.TIME_DOWNSAMPLE}x")

    def _trunk_forward(self, fbank: torch.Tensor) -> torch.Tensor:
        """ERes2NetV2 trunk 前向（到 fuse_out34，不进 pool）。

        Args:
            fbank: (B, T, 80) 已减时间维均值
        Returns:
            fuse_out34: (B, 1024, F'=10, T'=T/8)
        """
        x = fbank.permute(0, 2, 1)        # (B, T, F) → (B, F, T)
        x = x.unsqueeze_(1)               # (B, 1, F, T)
        out = F.relu(self.bn1(self.conv1(x)))
        out1 = self.layer1(out)
        out2 = self.layer2(out1)
        out3 = self.layer3(out2)
        out4 = self.layer4(out3)
        out3_ds = self.layer3_ds(out3)
        return self.fuse34(out4, out3_ds)  # (B, 1024, 10, T/8)

    def forward(self, fbank_eres2netv2: torch.Tensor) -> torch.Tensor:
        """整段前向。

        Args:
            fbank_eres2netv2: (B, T, 80) 已减时间维均值
        Returns:
            frame_features: (B, T/8, 1024)  频率维 mean-pool，帧率 12.5Hz
        """
        fuse_out34 = self._trunk_forward(fbank_eres2netv2)   # (B, C, F', T')
        return fuse_out34.mean(dim=2).transpose(1, 2)        # (B, T', C)

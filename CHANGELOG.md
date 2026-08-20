# Changelog

本文件记录 nomo-pvad 的所有重要变更。
格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

版本号为两段 `X.Y`，对应 tag `release-X.Y`：
- **X**：破坏性变更（Python API 不兼容，或旧权重无法被新代码加载）
- **Y**：其余一切变更（新能力、bug 修复、文档、依赖、**权重更新**）

## [Unreleased]

## [1.0] - 2026-08-19

首个公开发布版本。

### Added
- 流式目标说话人检测推理实现：注册音提 d-vector + 逐 160ms chunk 输出目标说话人概率。
- `infer.py` 命令行工具，支持 `--verbose` 逐帧输出、`--fast` 跳过流式节奏、`--threshold` 自定义阈值、`--device` 选择 CPU/GPU。
- 预训练权重 `weights/nomo_pvad.pt`（35MB）随仓分发，clone 即可运行。
- 示例音频 `examples/enroll.wav`、`examples/test.wav`。
- 许可与来源声明：`LICENSE`(Apache-2.0)、`THIRD_PARTY_NOTICES.md`、`weights/WEIGHTS_LICENSE.md`。

### Model
- 网络：ERes2NetV2 骨干（去末端 pooling、全参微调）+ FiLM 条件调制 + 因果流式解码器。
- 骨干内部时间下采样 8x → 帧率 12.5Hz（80ms/帧）。
- 输出为概率 `P(target) ∈ [0,1]`，**判定阈值由部署方按场景选取**，默认 `0.7`。
  各场景推荐值见 README「阈值按场景调」一节。
- 权重 sha256 见 `weights/CHECKSUMS.txt`。

### Security
- 所有 `torch.load` 使用 `weights_only=True`，拒绝 pickle 任意对象反序列化。
- 从 checkpoint 读取的 `model_cfg` 走字段白名单，防配置注入。
- `requirements.txt` 全部依赖锁定版本范围。

[Unreleased]: https://github.com/tuya/nomo-pvad/compare/release-1.0...HEAD
[1.0]: https://github.com/tuya/nomo-pvad/releases/tag/release-1.0

# 第三方组件与许可

本项目（nomo-pvad）在 Apache License 2.0 下发布（见 `LICENSE`）。项目使用/衍生了以下第三方组件，特此声明并致谢。

## ERes2NetV2 声纹骨干

- **来源**：3D-Speaker（ModelScope）— https://github.com/modelscope/3D-Speaker
- **模型**：`iic/speech_eres2netv2_sv_zh-cn_16k-common`
- **上游许可**：Apache License 2.0
- **上游 NOTICE**：上游仓库根目录**未提供** `NOTICE` 文件（截至 2026-08 核实），故本项目无需随附上游 NOTICE。
- **使用方式**：
  - **注册侧**：运行时从 ModelScope 自动下载**未经修改的完整原始模型**（含 pooling），本仓库**不打包**其权重。
  - **推理主干**：`weights/nomo_pvad.pt` 中包含由该骨干**微调而来**的权重（去除末端 pooling 层、在本任务上全参微调），属其衍生作品，依 Apache-2.0 再分发并在此署名（另见 `weights/WEIGHTS_LICENSE.md`）。

## 运行时依赖

`torch`、`torchaudio`、`numpy`、`soundfile`、`librosa`、`modelscope` —— 各依赖遵循其各自的开源许可（多为 BSD / MIT / Apache-2.0），版本约束见 `requirements.txt`。

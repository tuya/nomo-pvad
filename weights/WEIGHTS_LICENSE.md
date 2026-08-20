# 权重许可与来源（weights/nomo_pvad.pt）

- **许可**：Apache License 2.0（与本项目代码一致，见根目录 `LICENSE`）。
- **内容**：nomo-pvad 网络权重 + 由 ERes2NetV2 声纹骨干微调而来的主干权重（去除末端 pooling、本任务全参微调）。
- **衍生声明**：微调主干部分为 [3D-Speaker / ERes2NetV2](https://github.com/modelscope/3D-Speaker)（`iic/speech_eres2netv2_sv_zh-cn_16k-common`，Apache-2.0）的衍生作品，依 Apache-2.0 再分发并署名，详见根目录 `THIRD_PARTY_NOTICES.md`。
- **注册侧原始模型不含在此**：注册用的完整原始 ERes2NetV2（含 pooling）由 ModelScope 运行时自动下载，本仓库不打包。
- **安全提示**：请仅从官方渠道获取本权重文件。加载已使用 `torch.load(..., weights_only=True)`，拒绝任意对象反序列化；请勿改用 `weights_only=False` 加载来路不明的 `.pt` 文件。

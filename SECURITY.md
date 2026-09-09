# 安全策略 / Security Policy

## 支持的版本

本项目采用两段版本号 `X.Y`（tag `release-X.Y`），**不设维护分支**。
安全修复只在**最新版本**上发布，请始终使用最新的 `release-X.Y`。

| 版本 | 是否支持 |
|---|---|
| 最新 `release-X.Y` | ✅ |
| 其余历史版本 | ❌ 请升级 |

## 上报漏洞

**请勿通过公开 issue 上报安全漏洞。**

- 首选：在本仓库 **Security → Report a vulnerability** 提交私密报告（GitHub Private Vulnerability Reporting）。
- 备选：发邮件至 **guanhw@tuya.com** 或 **lepei.cheng@tuya.com**，标题注明 `[nomo-pvad]`。

我们的响应目标：

| 阶段 | 时限 |
|---|---|
| 确认收到 | 3 个工作日内 |
| 初步影响评估 | 10 个工作日内 |
| 修复发布 | 视严重程度，高危目标 30 日内 |

修复发布后我们会在 CHANGELOG 中致谢报告者（如你希望匿名请说明）。

## 模型权重安全（重要）

本仓库分发二进制模型权重 `weights/nomo_pvad.pt`。PyTorch 的 `.pt` 文件基于 pickle，
**加载不受信任的 `.pt` 文件等同于执行任意代码**。因此：

1. **只从官方渠道获取权重**：本仓库对应 `release-X.Y` 标签下的 `weights/` 目录。
   不要使用第三方镜像、网盘或转发的权重文件。
2. **务必校验完整性**：

   ```bash
   cd weights && shasum -a 256 -c CHECKSUMS.txt
   ```

   每个版本的 SHA-256 记录在对应标签下的 `weights/CHECKSUMS.txt`。当前发布流程只创建标签，不上传 Release 附件。
3. **本项目所有 `torch.load` 均使用 `weights_only=True`**，拒绝 pickle 任意对象反序列化。
   若你 fork 本项目，**请勿改为 `weights_only=False`**——这会重新引入远程代码执行风险。
   推送前由贡献者和维护者在本地验证；GitHub 不再自动运行 CI 检查。
4. 从 checkpoint 读取的模型配置 `model_cfg` 走**字段白名单**，防止被篡改的权重文件注入异常架构参数。

## 非安全问题

模型识别不准、误报漏报、阈值调不好——这些是**效果问题**不是安全漏洞，
请走公开 issue，并附上 Python/torch 版本、音频采样率与可复现命令。

## 范围说明

本仓库仅含**推理代码**。第三方依赖（torch、torchaudio、modelscope 等）的漏洞请上报至其各自上游项目；
ERes2NetV2 声纹骨干来自 [3D-Speaker](https://github.com/modelscope/3D-Speaker)，
其自身问题请上报至上游（另见 `THIRD_PARTY_NOTICES.md`）。

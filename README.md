# nomo-pvad — 流式目标说话人检测（推理）

给定目标说话人的注册音 + 音频流，**逐 160ms 实时判断"当前是否目标说话人在说话"**。
用于设备端"只听主人说话"、多人 + 噪声下只放行注册目标。chunk 级流式，可端侧部署。

- **输入**：注册音（提 d-vector）+ 待测音频流（16kHz）
- **输出**：每 160ms chunk 的目标说话人概率 ∈ [0,1]
- 本包含**推理代码 + 示例音频**（不含训练代码），版本 `1.0`（对应 tag `release-1.0`）。

> 📄 **详细技术报告**（任务定义、逐模块架构与配置、训练设置、延迟与精度实测）：<https://tuya.com/model/doc/pvad>

> 🎧 **在线体验 Demo**：<https://tuya.com/model/demo/pvad>
>
> ⚠️ 该 demo 在本仓开源基线（**纯模型、无前后处理**）之外，另叠加了大量工程实现，这些不在开源范围内。

## 安装
```bash
# 克隆本仓库后，安装依赖：
pip install -r requirements.txt
```
> nomo-pvad 权重（约 35MB）已随仓库一并提供，位于 `weights/nomo_pvad.pt`，clone 下来即可直接运行；ERes2NetV2 声纹骨干首次运行自动下载。

## 命令行
自带一对示例音频，可直接验证（前段=目标说话人 → 判「目标」，后段=非目标 → 判「非目标」）：
```bash
python infer.py --enroll examples/enroll.wav --test examples/test.wav --verbose
```
示例输出（节选；`p` 为目标说话人概率，末尾是逐 160ms 的时间轴）：
```text
▶ 流式检测中（每 160ms 出一帧）…
    0.16s  p=0.92  █ 目标说话人
    0.32s  p=0.90  █ 目标说话人
    ...
    2.72s  p=0.11  · 非目标 / 静音
    2.88s  p=0.08  · 非目标 / 静音

  0s          2s          4s
  ████████████████··········
  █ 目标说话人在说话    · 非目标 / 静音

结论：✅ 检测到目标说话人（目标说话约 2.4s，占 55%）
```
或用自己的音频：
```bash
python infer.py --enroll 注册音.wav --test 测试音.wav
# 逐 chunk 打印: --verbose ；GPU: --device cuda:0 ；阈值: --threshold 0.7
```

## 阈值按场景调（重要）
模型 `process_chunk` 输出的是**概率 P(target)∈[0,1]**，判定阈值是**部署方按业务选的操作点**，
不同场景不同值：

| 场景 | 建议阈值 | 取舍 |
|---|---|---|
| **声纹锁 / 防误放行**（误报代价高） | **0.7–0.85** | 低误报，漏报略升（本人偶尔多说一句），默认 0.7 |
| 均衡 | 0.6 | 召回/误报折中 |
| 多人 turn-taking / 高召回 | 0.5–0.6 | 抢召回，容忍更多误报 |

> 阈值越高越保守（拒识更严）；流式部署通常再叠加状态机迟滞（连续 N 帧才翻转）进一步压抖动。

## 作为库调用
```python
from nomo_pvad import NomoPVAD, NomoPVADSession

m = NomoPVAD("weights/nomo_pvad.pt", device="cpu")   # ERes2NetV2 首次自动下载
sess = NomoPVADSession(m)
sess.set_enrollment(enroll_pcm_f32_16k)          # 注册目标说话人
for chunk in stream_160ms_chunks:                # 每 160ms (2560 采样 @16k)
    p = sess.process_chunk(chunk_f32)            # 目标说话人概率 [0,1]
```

## 目录
```
infer.py           命令行推理示例
nomo_pvad.py     流式推理封装（注册 → 逐 chunk 概率）
core/              模型架构（model + eres2netv2_backbone + film + frame_adapter）
weights/           nomo-pvad 权重 nomo_pvad.pt（已随仓库提供；ERes2NetV2 骨干首次运行自动下载）
examples/          示例音频（enroll.wav + test.wav）
```

## 架构

```
注册音(≥10s) ─► ERes2NetV2 完整模型(含 pooling, 冻结) ─► d-vector 192 维(L2 归一)
                                                            │  一次性；运行时只需这个向量
                                                            ▼
音频流 ─► Fbank ─► ERes2NetV2 主干 ─► FiLM ─► 投影 ─► speech encoder ─► det decoder ─► chunk 头 ─► P(target)
 16kHz    80 维    去 pooling·8× 下采样  γ·(x+β)  1024→256   因果 ×2         因果 ×1      每 2 帧      每 160ms
```

| 模块 | 配置 | 参数量 |
|---|---|---|
| 前端特征 | Fbank 80 维，25ms 窗 / 10ms 移，dither=0，减时间维均值 | — |
| 声纹骨干 | ERes2NetV2（baseWidth=26, scale=2, expansion=2），去末端 pooling；时间 8× 下采样 → 12.5Hz（80ms/帧），频率维 mean-pool，输出 1024 维 | 13.93M |
| FiLM 调制 | 192 → LayerNorm→Linear(512)→SiLU→Dropout(0.1)→Linear(2048)，切分为 (γ̃, β)，γ=1+γ̃，输出 `γ·(x+β)`；末层零初始化 → 启动时即 identity | 1.15M |
| 特征投影 | LayerNorm(1024) + Linear(1024→256) | 0.26M |
| Speech encoder | CausalConv1d + GLU 残差块 ×2，d_model=256，kernel=7 | 1.84M |
| Det decoder | 同上 ×1 | 0.92M |
| Chunk 检测头 | 每 2 个骨干帧（2×80ms）mean-pool 成 1 chunk → LayerNorm + Linear(256) + SiLU + Dropout + Linear(2)，softmax 取目标类 | 0.07M |
| **合计** | | **18.16M**，fp16 权重 36.6MB |

> 随仓库分发的 `nomo_pvad.pt` 已包含微调后的骨干，主推理链路不依赖联网。首次运行自动下载的是**注册侧**的完整 ERes2NetV2（含 pooling），仅在本机做注册时需要；若注册在云端或配网阶段完成，设备端只需保存那个 192 维向量。

**设计要点：**
- **单一网络**同时完成 VAD + 目标说话人判别 + 时序建模，逐 160ms 输出——无需"声纹 + VAD + 规则"三件套拼装，部署简单、延迟低。
- **FiLM 声纹条件化**：用注册 d-vector 对每帧特征做仿射调制，而非在输入端拼接——条件在深层不会被稀释。末层零初始化让训练从 identity 起步。
- **时序建模用 CausalConv1d + GLU 残差块**（而非带右看窗的 Conformer）：训练与推理结构一致，不靠推理时截断未来帧。

## 用途与局限
- **预期**：设备端 / 云端"只听主人说话"、多人 + 噪声场景只放行注册目标；需**用户知情同意**注册本人声纹。
- **非预期**：未经同意的监听 / 追踪；用于身份鉴权等高风险场景（本模型非为反欺诈 / 活体设计）。
- **局限**：短注册（<1s）、有损链路（如 Opus）、跨环境 / 远场下性能下降；同性别相近音色为已知难点。

## 许可
- **代码**：Apache-2.0（见 `LICENSE`）。
- **ERes2NetV2 声纹骨干**：来自 [3D-Speaker / modelscope](https://github.com/modelscope/3D-Speaker)（`iic/speech_eres2netv2_sv_zh-cn_16k-common`），上游声明为 Apache-2.0。
  - `weights/nomo_pvad.pt` 中**包含由该骨干微调而来的权重**（去除末端 pooling 层、在本任务上全参微调），属其衍生作品，依 Apache-2.0 再分发并在此署名。
  - **注册侧**使用的是未经修改的完整原始模型（含 pooling），本仓不打包，首次运行时从 modelscope 自动下载。


# 贡献指南

感谢关注 nomo-pvad。本文说明分支、提交、PR 与发版的约定。

## 开始之前

- 提交前请先开 issue 讨论，避免重复劳动或方向不符。
- 本仓库**只含推理代码**，不接受训练代码相关的 PR。
- 涉及**模型权重变更**的 PR 请先在 issue 中讨论——需要配套的指标数据与阈值影响说明。

## 分支模型

只有两条长期分支：

| 分支 | 定位 |
|---|---|
| `master` | **默认分支**。发布分支；合入后自动打 tag |
| `dev` | 集成分支。所有开发在此汇聚 |

```
feat/xxx ──┐
fix/xxx  ──┼── PR ──► dev ── PR(release) ──► master ──自动──► tag release-X.Y
docs/xxx ──┘
```

**外部贡献者请一律把 PR 提向 `dev`，不要提向 `master`。**

### 分支命名

`<type>/<简短描述>`，全小写 kebab-case，关联 issue 时后缀编号：

| 前缀 | 用途 |
|---|---|
| `feat/` | 新能力，如 `feat/onnx-export` |
| `fix/` | Bug 修复，如 `fix/short-audio-padding-42` |
| `perf/` | 性能优化 |
| `docs/` | 仅文档 |
| `refactor/` `test/` `chore/` `ci/` | 其余 |
| `model/` | 权重更新专用 |

分支合并后请及时删除。

## 提交信息

采用 [Conventional Commits](https://www.conventionalcommits.org/)，正文用英文：

```
<type>(<scope>): <subject 命令式、≤50 字符、句尾无标点>

<body：解释「为什么」这么改，而不是复述「改了什么">

Closes #<issue>
Signed-off-by: Your Name <you@example.com>
```

- `type` ∈ `feat` `fix` `perf` `docs` `refactor` `test` `chore` `ci` `revert`
- `scope` ∈ `core` `infer` `weights` `examples` `deps` `docs`

### DCO 签名（必需）

本项目使用 [Developer Certificate of Origin](https://developercertificate.org/)。
每个提交必须带 `Signed-off-by`，用 `-s` 自动添加：

```bash
git commit -s -m "fix(infer): handle audio shorter than one chunk"
```

忘记签名时补签：`git commit --amend -s --no-edit`（多个提交用 `git rebase --signoff`）。

## Pull Request

1. 从 `dev` 拉分支开发；
2. 本地跑通：
   ```bash
   ruff check .
   python infer.py --enroll examples/enroll.wav --test examples/test.wav --fast
   ```
3. 提 PR 到 `dev`，填写 PR 模板中的检查项；
4. 推送前在本地完成验证；GitHub 不再重复运行 lint、扫描或推理检查，维护者 review 后合并；
5. 短期分支 → `dev` 使用 **Squash and merge**，squash 后的标题需符合 Conventional Commits。
6. 维护者的 `dev` → `master` release PR 使用 **Merge commit**；发布验收后将 `master` 合回 `dev`，保留共同历史。

### 请勿在 PR 中包含

- 任何内部域名、IP、内网链接、密钥凭据；
- 把 `torch.load(..., weights_only=True)` 改为 `weights_only=False`；
- 未经讨论的权重文件替换；
- 与 PR 主题无关的格式化改动。

## 版本与发版

维护者可按 [GitHub 发布操作手册](RELEASING.md) 中的命令直接执行。

版本号两段 `X.Y`，对应 tag `release-X.Y`：

- **X**：破坏性变更（Python API 不兼容，或旧权重无法被新代码加载）
- **Y**：其余一切变更，**包括 bug 修复**（不设 patch 段，1.0 之后的修复即 1.1）

发版由维护者操作：

1. 在本地验证改动，然后推送到 `dev`；GitHub 不重复运行 lint、扫描或推理检查。
2. 准备新版本时同步更新 `VERSION`、`CHANGELOG.md`、`README.md` 和 `README.zh-CN.md`。英文为默认 README，两份文档保留语言切换链接。
3. 仅当权重变化时更新 `weights/CHECKSUMS.txt`，并在 CHANGELOG 的 `### Model` 中说明指标和阈值影响。
4. 使用 Merge commit 将 `dev` 合并到 `master`，可通过 PR 或维护者本地合并后推送。
5. `release.yml` 读取 `VERSION`，自动在该提交上创建 annotated tag `release-X.Y`。标签已存在则成功跳过，绝不移动或删除已有标签。
6. 核实标签指向预期发布提交，然后将 `master` 合回 `dev`。

工作流只负责打 tag，不创建 GitHub Release 页面或上传附件。源码、权重和文档均保留在对应标签的仓库内容中。

新版本必须递增 `VERSION`；版本号未变时不会创建新标签。可在 Actions 对 `master` 手动重新运行 `release`，已有标签保持不变。

若分支保护仍要求已删除的 `lint`、`no-internal-refs`、`smoke-infer`，应移除这些必需检查，避免 PR 永久等待。维护者直接推送须符合仓库权限设置；使用 Merge commit 时不能要求线性历史。

## 行为准则

参与本项目即表示你同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 许可

提交贡献即表示你同意你的贡献以 [Apache License 2.0](LICENSE) 授权发布。

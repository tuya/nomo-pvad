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
| `master` | **默认分支**。始终等于最新可发布版本，合入即自动发版 |
| `dev` | 集成分支。所有开发在此汇聚 |

```
feat/xxx ──┐
fix/xxx  ──┼── PR ──► dev ── PR(release) ──► master ──自动──► tag release-X.Y + Release
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
4. 需要 CI 三个检查项全绿（`lint`、`no-internal-refs`、`smoke-infer`）；维护者会 review 后合并；
5. 合并方式为 **Squash and merge**，squash 后的标题需符合 Conventional Commits。

### 请勿在 PR 中包含

- 任何内部域名、IP、内网链接、密钥凭据（CI 有 `no-internal-refs` 检查项拦截）；
- 把 `torch.load(..., weights_only=True)` 改为 `weights_only=False`（安全红线，CI 拦截）；
- 未经讨论的权重文件替换；
- 与 PR 主题无关的格式化改动。

## 版本与发版

版本号两段 `X.Y`，对应 tag `release-X.Y`：

- **X**：破坏性变更（Python API 不兼容，或旧权重无法被新代码加载）
- **Y**：其余一切变更，**包括 bug 修复**（不设 patch 段，1.0 之后的修复即 1.1）

发版由维护者操作：更新 `VERSION` 与 `CHANGELOG.md` → 提 `dev` → `master` 的 release PR →
合入后 CI 自动打 tag 并创建 Release。**贡献者与维护者都不要手动打 tag。**

## 行为准则

参与本项目即表示你同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 许可

提交贡献即表示你同意你的贡献以 [Apache License 2.0](LICENSE) 授权发布。

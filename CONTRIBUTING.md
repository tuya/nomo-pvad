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
| `master` | **默认分支**。发布分支；合入后自动打 tag 并发布 Release |
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
   python scripts/smoke_infer.py
   python scripts/check_release.py
   python -m unittest discover -s tests -v
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

版本号两段 `X.Y`，对应 tag `release-X.Y`：

- **X**：破坏性变更（Python API 不兼容，或旧权重无法被新代码加载）
- **Y**：其余一切变更，**包括 bug 修复**（不设 patch 段，1.0 之后的修复即 1.1）

发版由维护者操作：

1. 在 `dev` 准备变更，同步更新 `VERSION`、`CHANGELOG.md`、`README.md` 和 `README.zh-CN.md`。英文为默认 README，两份文档须保留相互跳转的语言链接。
2. 仅当权重变化时更新 `weights/CHECKSUMS.txt`，并在 CHANGELOG 的 `### Model` 中说明指标和阈值影响。
3. 将 `dev` 合并到 `master`，可通过 release PR 或维护者本地合并后推送。推送前本地验证版本高于目标分支及已有正式标签，CHANGELOG 须精确匹配该版本。
4. 使用 **Merge commit** 合入。`release.yml` 不运行开发 CI，只校验发布元数据及权重一致性，然后创建 tag 和 Release 草稿。
5. 自动上传权重和校验和，下载两份附件并核对字节内容，成功后公开 Release。
6. 核实 tag 指向本次合并提交、两份附件与仓库一致，以及双语文档链接可用。
7. 将 `master` 合回 `dev`（直接快进或通过同步 PR 的 Merge commit，依分支保护设置操作）。

**贡献者与维护者都不要手动打 tag，不得移动或删除已发布标签。**

若发布中断，在 Actions 中对 `master` 重新运行 `release` 工作流。已有 tag 必须指向本次发布提交；工作流会补建缺少的 Release、补传缺少的附件。已有附件必须与当前提交一致，否则停止并要求人工排查，不覆盖附件。已有完整 Release 仅校验，不重复发布。若 `master` 已推进，应运行当前提交的工作流；版本对应的 tag 已指向其他提交时必须递增版本。

若分支保护仍要求已删除的 `lint`、`no-internal-refs`、`smoke-infer`，应移除这些必需检查，避免 PR 永久等待。可保留 PR 规则；维护者直接推送须符合仓库权限设置。release PR 使用 Merge commit，不能要求线性历史。

## 行为准则

参与本项目即表示你同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 许可

提交贡献即表示你同意你的贡献以 [Apache License 2.0](LICENSE) 授权发布。

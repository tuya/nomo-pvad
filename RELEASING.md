# GitHub 发布操作手册

当前流程：**本地验证 → 推送 dev → 合并 master → 自动打 tag → 验收 → 回流 dev**。

GitHub 不运行 lint、源码扫描或推理 CI。`.github/workflows/release.yml` 只读取 `VERSION` 并创建 annotated tag，不创建 GitHub Release 页面，也不上传附件。已有标签成功跳过，绝不移动或删除。

## 1. 进入公开仓工作副本

以下以维护者的 `~/nomo-pvad-public` 为例；如果目录不同，请替换路径。必须使用指向公开 GitHub 仓库的工作副本，不要将其他仓库的历史合并进来。

```bash
cd ~/nomo-pvad-public
git remote -v
git status --short
git fetch origin --tags
git switch dev
git pull --ff-only origin dev
```

确认 `origin` 指向 `git@github.com:tuya/nomo-pvad.git`，并先处理未提交改动。SSH 登录可用 `ssh -T git@github.com` 检查；提示认证成功但不提供 shell 属于正常结果。直接 Git 推送不需要 GitHub CLI 登录。

## 2. 准备下一版本

以下示例为 **1.1 → 1.2**。在本地完成实际代码验证后，同步修改：

| 文件 | 更新内容 |
|---|---|
| `VERSION` | 单行 `1.2`，只用 `X.Y` 两段数字 |
| `CHANGELOG.md` | 新增 `## [1.2] - YYYY-MM-DD`，写明变更并更新底部版本链接 |
| `README.md` | 英文版本号及 `release-1.2` 标签名 |
| `README.zh-CN.md` | 同步中文说明、版本号及标签名，保留双向语言切换 |
| `weights/CHECKSUMS.txt` | 仅换权重时更新 SHA-256，并在 CHANGELOG 说明模型与阈值影响 |

提交前查看差异，只暂存本次发布需要的文件。下面列出版本文档；有代码改动时，另外按文件路径暂存。

```bash
git diff
git add VERSION CHANGELOG.md README.md README.zh-CN.md
git diff --cached --check
git diff --cached --stat
git commit -s -m "release: 1.2"
git push origin dev
```

推送 `dev` 不会触发 CI 或创建标签。

## 3. 合并到 master

维护者可在本地使用 Merge commit 合并，再推送；也可在 GitHub 提 `dev → master` 的 PR，选择 **Create a merge commit**。

```bash
git switch master
git pull --ff-only origin master
git merge --no-ff --signoff dev -m "release: 1.2"
git push origin master
```

如有冲突，先解决并确认结果再推送；不要强推。若仓库要求通过 PR 合并，则按仓库规则完成 PR，不绕过保护。

## 4. 验收自动标签

打开 [GitHub Actions 的 release 工作流](https://github.com/tuya/nomo-pvad/actions/workflows/release.yml)，确认本次 `master` 提交对应的运行成功。

```bash
git fetch origin --tags
git show --no-patch release-1.2
git rev-parse 'release-1.2^{commit}'
git rev-parse master
```

首次发布该版本时，最后两条命令应输出相同的提交 SHA。源码、权重和文档均可从对应标签读取，例如 [release-1.1](https://github.com/tuya/nomo-pvad/tree/release-1.1)。无需检查 Release 附件。

标签是发布时的固定快照。后续维护提交可能使 `master` 领先于旧标签；重新运行工作流不会把旧标签移到最新提交。要发布新快照，必须递增 `VERSION`。

## 5. 回流 dev

无人同时推进 `dev` 时，可直接快进到本次 `master`：

```bash
git switch dev
git merge --ff-only master
git push origin dev
git fetch origin
git rev-parse origin/master origin/dev
```

最后两个 SHA 应相同。若 `dev` 已有其他人推送的新提交，先拉取并合并 `master`，解决冲突后正常推送，不强行覆盖远端。

## 常见情况

- **工作流成功但没有新标签**：`VERSION` 对应的标签已存在；这是预期的成功跳过。下一版请递增版本。
- **工作流失败，标签尚未创建**：查看 Actions 中的错误，修正格式或权限后，在 `release` 页选择 Run workflow，分支选 `master`。
- **标签已存在**：保持不变。重跑只会跳过；发现发布内容问题时用新版本修复。
- **PR 等待已删除的 CI**：从分支保护的必需检查中移除 `lint`、`no-internal-refs`、`smoke-infer`。Merge commit 与“要求线性历史”不能同时启用。
- **自动推 tag 被拒绝**：工作流已声明 `contents: write`；确认组织策略允许该权限，且标签规则允许 GitHub Actions 创建 `release-*`。

当前已发布标签包括 `release-1.0` 和 `release-1.1`。下次正式发布从 `1.2` 开始，不重建或移动旧标签。

## 变更说明

<!-- 这个 PR 做了什么、为什么需要 -->

关联 issue: Closes #

## 变更类型

- [ ] `feat` 新能力
- [ ] `fix` Bug 修复
- [ ] `perf` 性能优化
- [ ] `docs` 仅文档
- [ ] `model` **模型权重更新**
- [ ] 其他（refactor / test / chore / ci）

## 检查项

- [ ] 普通 PR 提向 `dev`；维护者 release PR 为 `dev` → `master`，使用 Merge commit
- [ ] 提交已 DCO 签名（`git commit -s`）
- [ ] 提交信息符合 Conventional Commits
- [ ] 本地已跑通 `ruff check .`
- [ ] 本地已跑通 `python scripts/smoke_infer.py`
- [ ] **不含**任何内部域名 / IP / 内网链接 / 密钥凭据
- [ ] **未**将 `torch.load(..., weights_only=True)` 改为 `weights_only=False`
- [ ] 已更新 `CHANGELOG.md`；发版时同步 `VERSION` 及中英文 README

## 若变更了模型权重，请补充

- [ ] 已更新 `weights/CHECKSUMS.txt`
- [ ] `CHANGELOG.md` 已补 `### Model` 小节
- 指标变化（EER / 延迟）：
- **业务阈值是否需要重新标定**：<!-- 若是，README「阈值按场景调」的推荐值也要同步改 -->

## 兼容性

- [ ] 向后兼容
- [ ] **破坏性变更**（Python API 不兼容，或旧权重无法被新代码加载 → 需进位 X）

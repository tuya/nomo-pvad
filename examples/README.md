# 示例音频

用于快速验证 nomo-pvad：

```bash
python infer.py --enroll examples/enroll.wav --test examples/test.wav --verbose
```

- `enroll.wav` — 目标说话人（说话人 A）的注册音。
- `test.wav` — 前段为目标说话人 A（另一句话），后段为非目标说话人 B。
  预期：前段判为「目标」，后段判为「非目标」。

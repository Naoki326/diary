# 闸门1·原型：一天照片 → 时间线日记（THROWAWAY）

> **一次性原型，勿投入生产。** 回答 issue #2 的问题：AI 整理出的日记是否产出
> 「值得回忆」的价值？上限/下限在哪？验证完即冻结，决策进地图，代码不迁移。

## 用法（一条命令）

```bash
# photo_dir 里放一天的 50–200 张照片（jpg/png/heic 均可，按 EXIF 时间排序）
python3 prototype/gate1-diary/diary.py <photo_dir> [--date 2026-10-03]
```

默认跑两档智谱模型对比：`glm-5.3-flash`（上限档，0.8 元/百万输入 tok）和
`glm-4.6v-flash`（免费下限档）。API key 运行时从 `~/.pi/agent/models.json`
的 `zai-pro` 读取，不落盘。

产物在 `out/<日期>-<时间>/`：

- `diary-<model>.md` —— 每档模型的日记成稿
- `captions-<model>.md` —— 每档模型的逐张打标（质量对照用）
- `report.md` —— token/成本台账（闸门 1 要看真实账单）
- `index.html` —— 照片 + 打标 + 各档日记的对照页（浏览器打开）

## 已知边界（2026-10-07 冒烟结论）

- `glm-4.6v-flashx`（0.15 元/M）在本 key 上报 `1113 余额不足`，账户充值后可
  `--models glm-5.3-flash,glm-4.6v-flashx,glm-4.6v-flash` 加为第三档。
- 图片 token 化差异大：5.3-flash ≈ 2300 tok/张，4.6v-flash ≈ 356 tok/张
  （长边 1280px），成本模型按实际 usage 记账，不按张。
- 打标阶段关 thinking；日记阶段开 thinking（叙事质量是评价对象）。
- 素材打标薄弱时模型会「轻想象」脑补细节（壁纸冒烟测试即脑补出厨房场景），
  真实照片下这个倾向是闸门 1 的核心评分维度。

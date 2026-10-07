# 调研：多模态 AI 供应商能力与价格（lifelogging 管线）

- Issue: #4
- 分支: `research/ai-vendors`
- 调研日期: 2026-10-07（全部价格以当日抓取的官方定价页为准；汇率折算按 **1 USD ≈ 7.2 CNY 假设**，仅用于汇总参考）
- 方法: 仅用 curl（每请求 --max-time 15）抓官方定价页；SPA/需登录页面抓不到的一律标「未能核实」，不引用二手价格。

## TL;DR（结论先行）

1. **批量图片打标（成本大头）首选国内低价视觉模型**：智谱 GLM-4.6V-FlashX（0.15 元/百万输入 token）与阿里 qwen3-vl-flash（0.15 元/百万输入 token，≤32K 档）同价且都极便宜；qwen-vl-plus（0.8 元/M）作备选。**每用户每天 100–500 张照片的打标成本约 0.02–1.03 元/日，即每月约 0.6–31 元**（纯图片输入 token，不含 prompt/输出）。
2. **批量执行用阿里 Batch API**：官方明确 Batch 5 折且「不受限流限制」，是批量打标的最优执行通道（来源：限流页 + 视觉文档）。
3. **日记/Vlog 文案生成**：智谱 GLM-4-Flash 系免费、GLM-4.1V-Thinking-Flash（64K 上下文）免费，可零成本承接轻量文案；质量档用 GLM-4.5V / qwen3-vl 系按 token 付费即可，单次成本分币级。
4. **图像生成**：通义万相 wanx2.0-t2i-turbo 0.04 元/张是地板价；Gemini 2.5 Flash Image（nano banana）$0.039/张（≈0.28 元）适合人物一致性要求高的宫格/海报，但官方已公告 deprecated（2026-10-02 关停，需迁移 Gemini 3.1 Flash Image）。**火山即梦/Seedream 价格未能核实**（定价页需登录，curl 不可达）。
5. **国际线（Gemini/OpenAI）从中国大陆不可直连**：Gemini API 官方支持区域页抓取结果不含中国大陆（0 次匹配）；OpenAI 平台同判。走国际线必须自备海外网络/代理，合规与稳定性自担，本项目如实标注不推荐作默认链路。
6. **每用户每月总成本区间（打标 + 每周 2–3 次生成任务）：约 2–35 元人民币（国内线）；国际线约 $0.5–6（≈4–43 元）**，明细见下文表格。

---

## 1. 批量图片理解/打标

### 1.1 阿里通义 Qwen-VL（百炼，华北2/北京，元/百万 Token）

来源: 阿里云百炼计费页 <https://help.aliyun.com/zh/model-studio/billing-for-model-studio>；图片 token 规则与多图上限: <https://help.aliyun.com/zh/model-studio/vision>；限流: <https://help.aliyun.com/zh/model-studio/rate-limit>

| 模型 | 输入（元/百万tok） | 输出（元/百万tok） | 备注 |
|---|---|---|---|
| qwen-vl-max | 1.6 | 4.0 | 无阶梯计价 |
| qwen-vl-plus | 0.8 | 2.0 | 无阶梯计价 |
| qwen3-vl-flash | 0.15（≤32K 档） | 1.5 | 32K–128K 档 0.3/3；128K–256K 档 0.6/6 |
| （国际站 qwen-vl-max） | 5.871 | 23.486 | 国际部署贵 ~3.7 倍，本项目应用国内站 |

- **图片如何计 token**：32×32 像素/patch，一张图 token ≈ max_pixels/32/32；默认 max_pixels 约 1,310,720–2,621,440（模型而异），即**单图默认约 1,280–2,560 token**（来源：vision 文档，含各模型默认值与上限 16,777,216）。
- **上下文能放多少张图**：Qwen3-VL/Qwen-VL 系 URL 或本地路径传图**最多 256 张**，Base64 最多 250 张；新版 Qwen3.7/3.8 系最多 **2048 张**；同时受模型图文总 token 上限约束；请求体 ≤64MB（来源：vision 文档「图片数量限制」节）。
- **限流（北京，主账号维度，超限 1 分钟内自动恢复）**：qwen-vl-max / qwen-vl-plus 1,200 RPM、1,000,000 TPM；qwen3-vl-flash / qwen3-vl-plus 3,000 RPM、5,000,000 TPM；**Batch API 调用不受限流限制**（来源：限流页）。qwen3.8-max/flash 采用按月消费档位的动态软限流。
- **Batch 折扣**：大规模非实时图像任务官方推荐 OpenAI 兼容-Batch（文件输入），**50% 成本折扣**（来源：vision 文档「异步与批量处理」节）。
- 参考延迟（官方实测，单张 2480×3508 默认参数）：qwen-vl-max ≈12s，qwen-vl-plus ≈8s（来源：vision 文档「响应速度与模型选型」节）。

### 1.2 火山引擎豆包视觉理解 —— **未能核实**

- 官方定价入口（文档站 SPA，curl 抓取无正文；精确单价需登录控制台核对）：<https://www.volcengine.com/docs/82379/1099320>
- 结论：**豆包视觉理解（doubao-vision / doubao-seed 系列）图片输入单价未能核实**，不做引用。如需纳入成本模型，后续由有火山账号的同学补数。

### 1.3 智谱 GLM-4V 系（元/百万 Token）

来源: 智谱开放平台 API 定价（markdown 版）<https://docs.bigmodel.cn/cn/guide/start/pricing.md>（控制台版 <https://open.bigmodel.cn/pricing> 为 JS 渲染，curl 不可读；.md 版为官方文档域，视为 primary）

| 模型 | 上下文 | 输入（元/百万tok） | 输出（元/百万tok） |
|---|---|---|---|
| GLM-4.6V | [0,32K) / [32K,128K) | 1 / 2 | 3 / 6 |
| GLM-4.6V-FlashX | [0,32K) / [32K,128K) | 0.15 / 0.3 | 1.5 / 3 |
| GLM-4.6V-Flash | — | **免费** | **免费** |
| GLM-4.5V | [0,32K) / [32K,64K) | 2 / 4 | 6 / 12 |
| GLM-4V-Flash | 4K | 免费 | 免费 |
| GLM-4.1V-Thinking-Flash | 64K | 免费 | 免费 |

- GLM-4.5V：106B MoE（激活 12B），官方称同级开源多模态 SOTA，支持图像/视频/文件输入、深度思考（来源：模型页 <https://docs.bigmodel.cn/cn/guide/models/vlm/glm-4.5v>）。
- 智谱侧图片 token 化规则（每图多少 token）未在定价页给出：**未能核实**，成本表按与 Qwen 同量级（1,280–2,560 tok/图）估算并标注。

### 1.4 Google Gemini 2.x（美元/百万 Token）

来源: <https://ai.google.dev/gemini-api/docs/pricing>（2026-10-07 抓取）

| 模型 | 输入 $/1M（text/image/video） | 输出 $/1M | Batch 输入 $/1M |
|---|---|---|---|
| Gemini 2.5 Flash | 0.30 | 2.50 | 0.15 |
| Gemini 2.5 Flash-Lite | 0.10 | 0.40 | （未抓取到，未核实） |
| Gemini 2.5 Pro | 1.25（≤200K）/ 2.50（>200K） | 10 / 15 | （同页有 Batch 节，未逐项摘录） |

- Gemini 图片 token 数（如 ~258 tok/小图）出自官方 vision 文档另一页，**本轮未核实**，成本表用区间估。
- **中国大陆可用性**：官方支持区域页抓取结果不含 China（<https://ai.google.dev/gemini-api/docs/available-regions>，grep "china" 0 次匹配）→ 大陆无法直连，需海外网络。

### 1.5 OpenAI GPT-4o / GPT-4o-mini（美元/百万 Token）

来源: <https://platform.openai.com/docs/pricing>（SSR 数据，2026-10-07 抓取；openai.com/pricing 为营销页，以平台文档为准）

| 模型 | 输入 $/1M | 缓存输入 $/1M | 输出 $/1M | Batch 输入/输出 $/1M |
|---|---|---|---|---|
| gpt-4o | 2.50 | 1.25 | 10.00 | — |
| gpt-4o-mini | 0.15 | 0.075 | 0.60 | 0.075 / 0.30 |
| gpt-4.1-mini | 0.40 | 0.10 | 1.60 | — |
| gpt-4.1-nano | 0.10 | 0.025 | 0.40 | — |

- 图片按输入 token 计费（vision tile 计算规则页未在本轮核实，按每图约 500–3,000 token 区间粗估）。
- **中国大陆可用性**：OpenAI 不向中国大陆提供服务（不支持大陆直连，公开常识；具体官方公告未逐一核实）。风险自担，不推荐默认链路。

---

## 2. 日记 / Vlog 文案生成

- **零成本档**：智谱 GLM-4-Flash-250414（128K 上下文，免费）、GLM-4.1V-Thinking-Flash（64K，免费，可直接吃图+文生成文案）、GLM-4.6V-Flash（免费）（来源：智谱定价页，URL 同 1.3）。
- **付费档**：qwen3-vl-flash 0.15/1.5 元/M、GLM-4.6V 1/3 元/M——单篇日记（几千 token 输入+千 token 输出）成本 <0.01 元（来源同上）。
- 结论：文案生成成本可忽略，**瓶颈在视觉理解而非文本生成**。

## 3. 图像生成（漫画 / 宫格图 / 海报）

### 3.1 通义万相（百炼，元/张，仅输出计费）

来源: <https://help.aliyun.com/zh/model-studio/billing-for-model-studio>（「万相文生图」节）

| 模型 | 输出单价 | 免费额度（90 天内） |
|---|---|---|
| wan2.6-t2i | 0.20 元/张 | 50 张 |
| wan2.5-t2i-preview | 0.20 元/张 | 50 张 |
| wan2.2-t2i-flash | 0.14 元/张 | 100 张 |
| wanx2.1-t2i-turbo | 0.14 元/张 | 500 张 |
| wanx2.0-t2i-turbo | **0.04 元/张** | 500 张 |
| wan2.5-i2i-preview（图生图/改图） | 0.20 元/张 | 50 张 |
| wanx2.1-imageedit | 0.14 元/张 | 500 张 |

- 漫画风格化效果、人物一致性：官方定价页不含效果结论，**口碑未验证**（需后续用 issue 里的样图实测）。

### 3.2 火山即梦 / Seedream —— **未能核实**

- 定价需登录火山控制台/文档 SPA（curl 不可达），单张价格**未能核实**。官方入口：<https://www.volcengine.com/product/doubao>（图像生成 Seedream 系列）。

### 3.3 Gemini 图像生成（nano banana）

来源: <https://ai.google.dev/gemini-api/docs/pricing>

- Gemini 2.5 Flash Image（nano banana，`gemini-2.5-flash-image`）：文本输入同 2.5 Flash（$0.30/1M）；**输出 $0.039/张**（1024×1024 图 = 1,290 token，$30/1M image token）；Batch 输出 **$0.0195/张**。
- 官方模型定位原文："A native image generation model, optimized for speed, flexibility, and contextual understanding"（同页）。人物一致性/漫画风格口碑：**未验证**（社区口碑好但属二手信息，不引）。
- ⚠️ 官方公告：2.5 Flash Image **deprecated，2026-10-02 关停**，需迁移 Gemini 3.1 Flash Image / 3.1 Flash Lite Image（同页 Warning 原文）——选型时直接按 3.1 系评估（3.1 价格未在本轮抓取，未核实）。
- 中国大陆不可直连（同 1.4）。

### 3.4 智谱 CogView（附）

- CogView-4：0.06 元/次（Batch 0.03 元/次）；CogView-3-Flash：免费（来源：智谱定价页，URL 同 1.3）。适合当免费兜底。

---

## 4. 成本模型：每用户每日/每月

假设：**每天 100–500 张照片 × 每张 1 次视觉理解调用**；单图消耗按 1,280–2,560 输入 token（阿里默认 max_pixels 区间；智谱/国际线无官方单图 token 数，按同量级估）+ 输出按 ~100 tok 忽略级；生成任务 **每周 2–3 次、每次 4–10 张**（月 32–120 张）。USD 按 7.2 折算（假设值）。

### 4.1 视觉理解（打标）成本

| 方案 | 每千张纯图输入成本 | 每日（100–500 张） | **每月（30 天）** |
|---|---|---|---|
| qwen3-vl-flash（0.15 元/M） | 0.19–0.38 元 | 0.02–0.19 元 | **0.6–5.8 元** |
| qwen-vl-plus（0.8 元/M） | 1.02–2.05 元 | 0.10–1.03 元 | **3.1–30.7 元** |
| qwen-vl-max（1.6 元/M） | 2.05–4.10 元 | 0.21–2.05 元 | **6.1–61.4 元** |
| 上述 × Batch 5 折 | — | 减半 | **3–31 元（vl-plus/max 档）** |
| GLM-4.6V-FlashX（0.15 元/M） | 0.19–0.38 元 | 0.02–0.19 元 | **0.6–5.8 元** |
| GLM-4.6V（1 元/M） | 1.28–2.56 元 | 0.13–1.28 元 | **3.8–38.4 元** |
| GLM-4.1V-Thinking-Flash / 4.6V-Flash / 4V-Flash | 免费 | 0 | **0 元**（限流政策未核实，免费层通常有 RPM/并发限制） |
| Gemini 2.5 Flash（$0.30/M，估 258–1,290 tok/图，未核实） | $0.08–0.39（0.6–2.8 元） | $0.008–0.20 | **$0.2–5.8（1.7–42 元）** |
| Gemini Batch（$0.15/M） | 减半 | 减半 | **$0.1–2.9（0.9–21 元）** |
| GPT-4o-mini（$0.15/M，估 500–3,000 tok/图，粗估） | $0.075–0.45（0.5–3.2 元） | $0.008–0.22 | **$0.2–6.8（1.7–49 元）** |
| 火山豆包视觉 | **未能核实** | 未能核实 | 未能核实 |

### 4.2 生成任务成本（月 32–120 张）

| 方案 | 单张 | 每月（32–120 张） |
|---|---|---|
| wanx2.0-t2i-turbo | 0.04 元 | **1.3–4.8 元** |
| wan2.2-t2i-flash / wanx2.1-t2i-turbo | 0.14 元 | 4.5–16.8 元 |
| wan2.6-t2i / wan2.5-i2i | 0.20 元 | 6.4–24 元 |
| CogView-4 / CogView-3-Flash | 0.06 元 / 免费 | 1.9–7.2 元 / 0 元 |
| Gemini 2.5 Flash Image（Batch） | $0.0195（0.14 元） | $0.62–2.34（4.5–16.8 元） |
| 即梦/Seedream | **未能核实** | 未能核实 |

### 4.3 每用户总成本区间（打标 + 生成）

| 线路 | 每日 | 每月 |
|---|---|---|
| 国内线·经济（GLM-Flash 免费 + wanx2.0-turbo） | ≈ 0–0.2 元 | **≈ 1–7 元** |
| 国内线·均衡（qwen3-vl-flash/gl-4.6v-flashx + wan flash，Batch） | 0.1–0.5 元 | **≈ 3–20 元** |
| 国内线·质量（qwen-vl-max + wan2.6） | 0.5–3 元 | **≈ 13–85 元** |
| 国际线（Gemini Batch 打标 + nano banana Batch 生成，需海外网络） | $0.01–0.3 | **≈ $0.5–8（4–58 元）** |

**给成本模型 ticket 的口径**：按「均衡档」每用户每月 **约 3–20 元人民币** 做预算基准；重度用户上限约 85 元/月。

## 5. 风险与未验证项清单

- [ ] 火山豆包视觉理解 + 即梦/Seedream 全部价格：**未能核实**（SPA/需登录），需控制台人工核对。
- [ ] 智谱图片 token 化规则、免费模型限流政策：未核实。
- [ ] Gemini 单图 token 数（258/1290）与 3.1 Flash Image 价格：未核实。
- [ ] OpenAI vision tile token 规则：未核实（用区间粗估）。
- [ ] 漫画风格化/人物一致性效果：所有厂商均未实测，建议开 spike 用统一 prompt 集评测（万相 wan2.6 vs Seedream vs nano banana）。
- [ ] 大陆访问国际线的合规/稳定性：如实标注「不可直连」，未评估代理方案。

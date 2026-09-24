# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

现有代码已确定技术栈：静态 HTML/CSS/原生 JS 单页 + Python 抓取脚本（fetch_data.py）+ 本地 data.json，无框架、无后端。部署形态未定：可能保持本地运行，也可能放云服务器（Docker 或简单静态托管），属于未决事项。

## Users

个人自用为主（开发者本人），用来快速查看主流大模型 API 定价并估算调用成本。用户同时明确要求 UI 要做得好看——这是一个需要兼顾实用与视觉审美的个人工具。中文界面。

## Product Purpose

做"各渠道的大模型价格"对比工具：同一个模型（如 deepseek-flash）在**官方**有一个价格，在**其他 API 渠道商**（中转/聚合平台）也有各自的价格，全部接入对比。当前先做好 5 家官方渠道（OpenAI / Anthropic / Google / DeepSeek / xAI），并留下可扩展接口，之后可批量导入更多渠道商。另有**订阅计划（coding plan 类）**统计页，独立分页。也是用户的练手学习项目。

## Positioning

区别于直接浏览 llmrates / pi.dev / OpenRouter：以**模型为中心、渠道为维度**组织价格（一个模型看多个渠道的价格对比），中文界面，官方命名统一（旧名自动归一），DeepSeek 峰谷计价，附带订阅计划统计——是"看得懂、能比渠道、能算账"的个人价格雷达。

## Operating Context

- 数据流：llmrates API → fetch_data.py（Python 抓取，无跨域限制）→ data.json（模型→渠道→价格）+ plans.json（订阅计划）→ HTML 渲染。
- 两个页面：`index.html` 价格目录（pi.dev 风格：按厂商分组、上下文窗口、输入/输出/缓存价、搜索筛选、明暗切换）；`plans.html` 订阅计划统计。
- 运行方式：本地 `python -m http.server 8000` 或 VS Code Live Server 打开 `index.html`；先运行 `python fetch_data.py` 生成 data.json。
- API 不可用时脚本自动回退到内置参考价，页面永不白屏。
- 北京时间峰谷判断：工作日 9:00–12:00、14:00–18:00 为 DeepSeek 高峰（×2），周末全天谷价。

## Capabilities and Constraints

- 数据模型：**模型 → 渠道 → 价格**。每个模型下有 channels 数组（官方 + 未来第三方渠道），每渠道有自己的货币、输入/输出/缓存价、峰谷倍率。
- 当前渠道：5 家官方（OpenAI / Anthropic / Google / DeepSeek / xAI），13 个模型；schema 预留多渠道扩展。
- 官方命名：模型按官方 API ID 展示（deepseek-flash、gpt-5.4、claude-opus-5、gemini-3.8-flash、grok-4.6），旧名归一到新名。
- 官方通知：页面顶部展示官方迁移/下线提示（当前为 DeepSeek 模型迁移通知）。
- 订阅计划页：独立 plans.json，按订阅项统计（名称/厂商/价格/周期/分类）。
- 价格货币：DeepSeek 官方人民币（¥），其余厂商美元（$），每渠道独立货币。
- 硬约束：中文界面；无框架纯静态可部署；数据来自 llmrates，价格为实时/官方参考价。
- 未决事项：部署形态（本地 / Docker / 静态托管）；第三方渠道商接入清单；订阅计划的完整数据。

## Brand Commitments

产品名 "LLM Price Radar"。中文界面为明确要求。无既定的品牌色、字体或视觉资产约束（用户表示视觉可以大胆重来，但要好 UI）。

## Evidence on Hand

- 现有实现：`llm-price-radar-v3.html`（当前视觉，待重设计）、`fetch_data.py`、`data.json`（13/13 实时命中）。
- 官方通知文本（DeepSeek 模型迁移）已收录进 notices。
- 无价格历史数据；无商业性声明（价格为 llmrates/官方公开数据，页面标注"仅作个人参考"）。

## Product Principles

1. 数据驱动、来源透明：价格来自 llmrates/官方，页面如实标注数据状态（实时/部分/回退）。
2. 官方为准：模型命名与定价口径跟随官方最新。
3. 一页看完、立刻能算账：信息密度优先，但必须可读、好看（个人向工具也值得精心设计）。
4. 稳健兜底：API 不可用时不白屏，始终有数据可看。
5. 保持简单可部署：无框架、无后端，任何静态托管都能跑。

## Accessibility & Inclusion

个人自用工具，无产品级无障碍合规要求；但中文可读性、深色模式支持（现有版本已有 prefers-color-scheme）应作为良好实践保留。

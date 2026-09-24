# 历史 README（Pages 改造前；当前说明见仓库根目录）

个人使用的 LLM 模型价格对比与成本估算工具。**纯静态单页应用，数据全内嵌，双击 `index.html` 即可用，离线可用，0 网络请求。**

当前规模：**344 个模型 / 36 个订阅计划 / 10 家厂商 / 23 个官方来源**（快照 2026-09-24）。

## 文件结构

```
llm-price-radar/
├── index.html              ★ 主应用（单文件，数据内嵌，双击打开）
├── data.json               模型 API 数据（344 模型，与 index 内嵌同步）
├── plans.json              订阅计划数据（36 计划，与 index 内嵌同步）
├── llm-price-manifest.json AI 可读数据索引（结构、口径、来源、counts）
├── fetch_prices.py         ★ 官方定价抓取（唯一脚本：抓取+解析+入库）
├── sync_data.py            手动确认的少量数据入库
├── import_xlsx.py          xlsx 采集表批量导入（预览/写库双模式）
└── docs/
    ├── CHANGELOG.md        变更日志
    ├── fetch-report-*.md   官方定价抓取报告（含价格差异）
    ├── fetch-parsed/       官方解析结果明细（parsed-<日期>.json）
    ├── fetch-snapshots/    官方页抓取快照（fetch_prices.py 每次生成）
    ├── data-expansion-2026-09-21.md   数据扩展调研（参考合并版）
    ├── 待查证-2026-09-21.md           9 项冲突查证记录
    ├── ui-plan.md          UI 设计规划
    ├── joyehuang-blog-research.md   博客调研
    ├── archive/            历史备份（旧 PRODUCT、旧版 UI 等）
    ├── preview/            界面截图存档
    └── vendor-icons/       厂商 Logo SVG 备份（已内嵌进 index）
```

## 功能一览

- **5 个视图**：模型 API / Coding Plan / 我的关注 / 试算记录 / 来源
- **模型目录**：搜索（⌘K / Esc 清除）、供应商筛选、A-Z 排序（默认）/ 价格排序、按厂商分组折叠
- **模型详情**：多计费档位、五维成本试算（输入/缓存读取/缓存写入/输出/存储）、试算保存恢复
- **订阅计划**：36 个计划，**GLM / MiniMax / Qoder 支持国际/国内价格切换**（分组级控制）
- **地区切换**：国际/国内双币种切换，排序/分组/比较/试算全程跟随当前地区
- **对比**：勾选最多 3 项并排比较（同币种同类型校验）
- **导出**：CSV 导出当前筛选结果
- **离线**：全部数据内嵌 `<script type="application/json">`；数据用 `regions` 结构支持双币种

## 数据口径

- 价格为**原币种 / 百万 tokens**（模型）与**常规月付**（订阅），不做汇率换算
- 缓存维度分读取/写入/存储；`null` 表示官方未单列，**不等于免费**
- DeepSeek 为人民币分时计价（高峰/空闲）；其余厂商美元为主
- 双币种模型/套餐用 `regions{国际,国内}` 结构，切换器在分组标题
- 每条数据带 `source` 指向官方定价页，快照日期见页面顶部（自动更新）

## 数据维护（一条命令）

```
python fetch_prices.py            # 抓取全部官方源 + 解析 + 差异报告（不写库）
python fetch_prices.py --apply    # 抓取 + 解析 + 自动入库
python fetch_prices.py openai     # 只处理指定来源（substring 匹配）
```

**覆盖 11 个官方源**：
- 静态 HTML 解析（6）：OpenAI / Anthropic / xAI / DeepSeek / 智谱（国内）/ Google（网络受限环境标 FAIL）
- 文档站 .md（3）：Kimi / MiniMax（按量计费）/ 阿里云百炼（只收 qwen 自家模型）
- 纯 JS SPA 无接口（2）：火山引擎 / Z.AI → 报告标注，数据由 xlsx/人工维护

**--apply 自动入库规则**：
- 价格变更 → 覆盖（保留 contextWindow 等字段）；新增模型 → 自动收
- 跳过：免费模型、噪音变体（-us/-region/-0309）、价格一致、**输出<输入疑似列错位**
- 文档站国内价 → 自动合并进 `regions` 模型的国内档（不破坏国际/国内切换）
- 自动更新 `snapshot` 时间戳；自动补全缺失的来源记录

**辅助工具**（手动/批量场景）：
- `sync_data.py`：少量已确认数据入库（改 `VERIFIED_MODELS`/`VERIFIED_PLANS` 后运行）
- `import_xlsx.py`：xlsx 采集表批量导入（`--apply` 写库，DeepSeek CNY 口径保护）

## 本地存储键（localStorage）

| 键 | 内容 |
|---|---|
| `llmpr-stars` | 星标关注（模型/套餐 id） |
| `llmpr-plan-region` | 各厂商国际/国内选择 |
| `llmpr-collapsed` | 分组折叠状态（按视图隔离） |
| `llmpr-mvp-records` | 试算记录（最近 20 条，含地区，恢复时还原） |

## 已知设计约定

- **当前地区币种**用 `curCur()`（regions 计划取当前切换地区，其余取顶层 `currency`）；`baseCur()` 仅用于显示混币种组（如 `CNY/USD`）
- 双 region 计划（GLM/MiniMax/Qoder）的 `currency/price/quota/note/source` 在 `regions` 内，顶层缺失属预期；代码用 `planCur()/curCur()` 归一化读取
- 地区切换 / 恢复试算 / 比较都会**重新校验比较项**（`revalidateCompare()`），币种变化自动移除跨币种比较
- **搜索/筛选/价格排序激活时分组自动展开**；搜索中主动折叠仅本次生效（`searchFold` 内存态，条件变化即重置）
- 窄屏（≤900px）详情是弹窗，带 id 的链接会自动打开

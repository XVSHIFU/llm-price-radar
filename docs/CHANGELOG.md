# 变更日志

## 2026-09-24 · 项目整理：清理 + README 重写

### 清理

- 删除：`__pycache__`、临时文件 `tmp.txt`、旧快照 `fetch-snapshots-js/`、旧解析 `fetch-parsed/parsed-2026-09-23.json`、旧报告（09-21/09-23）
- 归档：`PRODUCT.md` → `docs/archive/PRODUCT-old.md`（内容过时：fetch_data/llmrates/13模型/channels 结构）
- `llm-price-manifest.json` 更新：models 344 / plans 36 / sources 23 / providers 10 / snapshot 2026-09-24

### README 重写

- 数据规模：344 模型 / 36 计划 / 10 厂商 / 23 来源
- 功能：A-Z 排序、地区切换（GLM/MiniMax/Qoder）、试算保存恢复、比较同币种校验
- 数据维护：`fetch_prices.py` 一条命令 + --apply 规则（含列错位保护、regions 合并、来源自动补全）
- 设计约定：curCur/planCur 归一化、revalidateCompare、searchFold 搜索折叠、窄屏弹窗

## 2026-09-23 · 合并为唯一脚本 fetch_prices.py + 全量修复

### 合并

- fetch_official.py / fetch_js_pages.py / price_parsers.py / fetch_data.py 全部合并进 **`fetch_prices.py`**（已删除旧脚本）
- 一条命令：`python fetch_prices.py [--apply] [来源]`

### 覆盖 11 个官方源

- 静态 HTML 解析（6）：OpenAI / Anthropic / xAI / DeepSeek / 智谱国内 / Google（备用，网络受限环境标 FAIL）
- 文档站 .md（3）：Kimi（DocTable）/ MiniMax 按量计费（markdown）/ 阿里云百炼（JSX 表格，**只收 qwen 自家**）
- 纯 JS SPA 无接口（2）：火山引擎 / Z.AI → 报告标注，数据由 xlsx/人工维护

### 重大修复

- **阿里云 .md 是全市场价目**（含第三方托管 DeepSeek/Kimi/GLM 等），曾污染官方模型（deepseek-v4-pro、kimi-k3、glm-4.x/5.3 被覆盖为阿里云价）
- 修复：阿里云解析加 qwen 前缀过滤（只收自家）；清理 220 个第三方托管模型；恢复 DeepSeek/Kimi/智谱官方模型
- 修复空 id 模型（阿里云表格"参见模型列表"行）导致 boot 报"价格快照无法读取"
- 模型 87→344（10 家厂商）；官方模型数据正确性经最终 --apply 验证（变更 5/新增 3/跳过 311）

### 最终 --apply 实测

- 11 源全部处理：8 家解析成功、Google 网络受限、火山/Z.AI 标 SPA
- 阿里云 qwen 系 251 个（含批次/缓存变体），其余厂商与库内一致

## 2026-09-23 · fetch_js_pages 举一反三：探测各站 llms.txt/.md 接口

### 探测结论（几乎所有文档站都有纯文本接口）

| 站 | llms.txt | 页面 .md | 接入 |
|---|---|---|---|
| Kimi | ✅ | ✅ | ✅ 4 模型 |
| MiniMax 国内 | ✅ | ✅ | ✅ 10 模型 |
| MiniMax 国际 | ✅ | ✅ | 待接 |
| 阿里云百炼 | ✅ 230KB | ✅ 892KB（JSX 表格） | ✅ 473 模型（含全部变体） |
| DeepSeek | ✅ | ✅ | 已有静态解析器 |
| 智谱 bigmodel | ✅ | ✅ | 已有静态解析器 |
| 火山引擎 | ✅ | ❌（.md 返回 HTML） | 待探 |
| Z.AI | ✅ | 定价页 URL 待找 | 待探 |

### 新增：阿里云百炼接入

- `.md` 为 JSX `<table>` 格式 → 新增 `parse_jsx_table` 解析器
- 解析 473 个模型（Qwen 全系 + 托管 DeepSeek + 语音，含模式/版本/阶梯变体）
- 注意：473 个太杂（Batch/缓存/多版本/阶梯行），不建议全量入库，按需筛选主版本

## 2026-09-23 · fetch_js_pages 重写为纯 python（去浏览器依赖）

### 原因

- 旧方案用 agent-browser 渲染 JS 页，每页 1-2 分钟，全量 10 分钟+ 且经常超时卡死
- 发现 Kimi / MiniMax 均为 **Mintlify 文档站**：每页有 `.md` 纯文本版本（/docs/llms.txt 索引），python 直接 GET 秒级完成

### 重写内容

- `fetch_js_pages.py` → 纯 python（urllib），无 agent-browser 依赖
- 支持两种表格式：DocTable JSON（Kimi）+ 普通 markdown 表格（MiniMax）
- 列映射 / HTML 标签清理 / 五折价取最后数字 / 同 id 多档合并 / 非 token 计费过滤
- 实测：Kimi 4 个（K3 ¥20/¥100、K2.7-Code、HighSpeed、K2.6）+ MiniMax 10 个（M2 全系含缓存、M3 双档）秒级解析
- MiniMax 正确定价页：`docs/guides/pricing-paygo.md`（按量计费，原 guides/pricing 是语音包页）

## 2026-09-23 · fetch_official 支持 --apply 全自动入库

### 用法

- `python fetch_official.py --parse --apply`：抓取 → 解析 → **自动入库**

### 自动入库规则

- 价格变更 → 覆盖库内同 id 模型（保留 contextWindow/family 等额外字段）
- 新增模型 → 自动收；**跳过**：免费模型（无价格）、噪音变体（-us/-region/-0309 等）
- 智谱国内解析（glm-5-3-cn 等）→ 自动合并进库内 regions 模型的国内档（ID_ALIAS）
- 价格一致 → 跳过不动（保留库内版本）

### 本次 --apply 结果（模型 65→87）

- 智谱：4 个 regions 国内档更新（glm-4.7 ¥2/¥8、glm-5.3 ¥8/¥28、flash ¥0.8/¥2.8、flashx ¥2/¥7）+ 22 个国内模型新增（5.2/5.1/5/5-Turbo/4-Plus/视觉/OCR 等）
- OpenAI/Claude/DeepSeek/xAI：价格一致全部跳过（官方页验证库内数据无变化）
- 跳过：免费模型 6（4.7-Flash/4-Flash/Z1-Flash 等）+ grok-4.20 噪音变体 3
- 浏览器实测：智谱 28 个模型正常，目录 87 个模型

## 2026-09-23 · 官方定价页自动解析器（多厂商脚本化取数）

### 新增脚本

- **`price_parsers.py`**：官方定价页解析器（标准模型格式输出）
  - 静态可解析：Anthropic（platform.claude.com 五列完整表）/ OpenAI / xAI / DeepSeek / 智谱 bigmodel.cn（32 个）
  - JS 渲染后解析：Kimi 中国站（fetch_js_pages 渲染文本）
- **`fetch_official.py --parse`**：抓取 → 解析 → 与 data.json 差异报告（价格变更/新增/缺失）
- **`fetch_js_pages.py`**：JS 渲染页抓取（agent-browser 渲染后取文本）

### 验证结果（15 页抓 14，解析 64 模型）

- OpenAI/Anthropic/DeepSeek/xAI：解析价与库内**全部一致**（此前校准/入库数据正确性得到官方页验证）
- Anthropic 官方表含缓存写 5m/1h 双档 + 命中倍率注记（0.025×/0.05×/0.1×）
- 智谱国内全系 32 个新增候选（GLM-5.2/5.1/5/4-Plus/视觉/OCR 等）
- 发现并入库新模型 10 个：gpt-6-sol/luna、claude-opus-4.1/4、sonnet-4、haiku-3.5、grok-4.7/4.20×3

### 产出物

- `docs/fetch-parsed/parsed-*.json`（解析明细）、`docs/fetch-snapshots-js/`（渲染文本）
- 报告：`docs/fetch-report-*.md`（含价格差异）

## 2026-09-21 · Anthropic 官方全系校准（platform.claude.com pricing 页）

### 数据源升级

- 直接抓取官方定价页 `platform.claude.com/docs/en/about-claude/pricing`，解析出完整价格表（输入 / 缓存写5m / 缓存写1h / 缓存读 / 输出 五列）
- 此前采集报告误判该页"缓存三维度未单列"，实际官方有完整 5m/1h 缓存写档

### Anthropic 7 → 14 个模型（全部官方校准）

- 新增：Opus 5.5（$4/$20，缓存命中 0.05×）、Opus 4.7/4.6/4.5、Sonnet 4.5、Fable 5 / Mythos 5（缓存命中 0.1×）
- 校准：Opus 4.8 / Sonnet 4.6 / Mythos 5.1 补齐缓存写 5m/1h 双档（此前 write 缺失）
- 保留：Opus 5 / Sonnet 5 / Haiku 4.5 / Fable 5.1 等（与官方一致，已确认）
- 缓存命中倍率入备注：Fable/Mythos 5.1 = 0.025×、Opus 5.5 = 0.05×、其余 0.1×
- 官方注记：Sonnet 5 的 $2/$10 为发布时介绍价，后续可能调整
- 模型 48→55；浏览器实测 Anthropic 组 14 个模型正常

## 2026-09-21 · 模型补全 23→48（GLM/豆包/Qwen3 全系入库）

### 新增模型 25 个（数据来自用户 xlsx 官方采集）

- **智谱 GLM 全系（6）**：glm-4.5/4.6（单国际）、glm-4.7/5.3/5.3-flash/5.3-flashx（regions 国际+国内）；新增智谱官方图标（Lobe Icons Zhipu）
- **火山引擎豆包全系（6）**：seed-1.6/1.8/2.0-code/2.0-pro/2.1-turbo/evolving（国内单币种，含 2.1-pro/seed-code 共 8 个）
- **阿里云 Qwen3（3）**：qwen3-coder-plus（4 档含长上下文惩罚价）/qwen3-max/qwen3.8-max
- **Google（3）**：gemini-3.6-flash/3.7-flash（与 3.8 同价 $0.75/$3.75）/3.1-pro-preview（双档）
- **MiniMax（3，regions）**：M2.1/M2.5（统一价）/M3（含 >512K 翻倍档）
- **xAI（1）**：grok-4.3（双档）；**Anthropic（3）**：Opus 4.8/Sonnet 4.6/Mythos 5.1
- 厂商 8→10、模型 23→48；manifest counts 同步

### 实测

- 智谱组切换国内：GLM-4.7 ¥2/¥8、GLM-5.3 ¥8/¥28、Flash ¥0.8/¥2.8、FlashX ¥2/¥7（4.5/4.6 国内未列保持美元）
- 豆包全系 8 个、Qwen3 3 个全部展示；图标齐全无占位
- 截图：`docs/preview/models-48-full.png`

## 2026-09-21 · 模型视图双区域切换（订阅同款 regions）

### 数据：模型 regions 化

- **Kimi K3**：kimi-k3-intl + kimi-k3-cn 合并 → `kimi-k3` regions{国际 $3/$15, 国内 ¥20/¥100}
- **MiniMax M2.7**：→ `minimax-m2.7` regions{国际 $0.30/$1.20（含 highspeed）, 国内 ¥2.1/¥8.4}
- **MiniMax M2**：→ `minimax-m2` regions{国际 $0.30/$1.20, 国内 ¥2.1/¥8.4}
- 模型顶层保留国际价（兼容 isModel/draft/详情）；模型数 24→23
- 仅对**官方明确双价**的模型做 regions（K2.6/K2.7 Code 国际价来源存疑，保持国内单币种）

### UI：模型视图组标题切换器 + 渲染适配

- 组标题切换器从订阅视图扩展到模型视图（有双币种模型的组显示国际/国内按钮）
- 新增 `regionOf/mRates/mCur` 辅助；`rate()` 按当前区域取档位（tier 越界自动保护）
- 列表、详情页（档位/单位/价格）、成本计算器、比较视图、CSV 导出的币种全部跟随区域
- 实测：MiniMax 组 $0.30→¥2.10 全组切换；Moonshot 组 K3 $3/$15→¥20/¥100（K2.6/K2.7 保持国内价）；详情页档位数/单位/计算器币种同步
- 截图：`docs/preview/models-region-switch.png`

## 2026-09-21 · 切换按钮统一 + 模型视图按厂商整合

### 按钮缩小统一

- 国际/国内切换按钮：24×46px（12px 字 + 4/14 padding）→ **18×38px**（10px 字 + 1/9 padding），与折叠箭头（18px）高度一致，消除"一大一小"
- 组标题与行内切换按钮尺寸统一（font 10px，padding 1px 9px）

### 模型视图按厂商整合

- 分组规则统一：模型视图也改为**按厂商分组**（不再按币种拆组）
  - MiniMax：CNY/USD · 2 个模型（M2 国内 + M2.7 国际 合并一组）
  - Moonshot：CNY/USD · 4 个模型（K3 国内/国际 + K2.7 Code + K2.6 合并一组）
- 组标题币种显示支持多币种：组内混币种时显示 `CNY/USD`（dispCur 逻辑更新）
- 订阅视图不受影响（有 regions 的组仍显示当前切换币种）；默认折叠 + A-Z 排序保持

### 截图

- `docs/preview/smaller-region-btn.png`（切换按钮缩小）
- `docs/preview/models-vendor-group.png`（模型视图按厂商整合）

## 2026-09-21 · 双区域切换推广（智谱同款 regions 结构）

### 数据：regions 双区域化

- **MiniMax Token Plan**（Plus/Max/Ultra）：国际 $22/$55/$132 ↔ 国内 ¥49/¥119/¥469
- **Qoder**（Pro/Pro+/Ultra）：国际 $20/$60/$200 ↔ 国内 ¥59/¥169/¥559；旧 cn/intl 6 个 id 合并为 3 个 regions id + Teams（qoder-teams，仅国际）
- 与 GLM 同款 `regions{国际,国内}` 结构；plans 总数 39→36
- Kimi 国内人民币价未核实，暂不做双区域

### UI：订阅视图按厂商分组

- Coding Plan 视图改为**按厂商分组**（一家一组），组标题带国际/国内切换器；阿里云 5 个套餐（Qoder 3 双区 + Teams + 百炼）合成一组
- 模型 API 视图保持币种分组（模型为单币种不同条目，不适配切换）
- 切换效果实测：阿里云 Qoder ¥59/¥169/¥559、Teams 保持 $40、百炼保持 ¥200；MiniMax ¥49/¥119/¥469
- 默认折叠 + A-Z 排序保持；截图存 `docs/preview/region-switch-minimax-{cn,usd}.png`

## 2026-09-21 · 目录 A-Z 排序 + 默认折叠

### 排序

- 默认排序改为 **A-Z**（原为数据原始顺序），下拉文案同步改为「A-Z」
- 规则：厂商按名称排序（英文按字母；中文按拼音首字母映射后插入对应位置，如 阿里云→A、火山引擎→H、腾讯→T、字节→Z），组内模型/套餐按名称 A-Z
- 例：Anthropic → 阿里云 → DeepSeek → Google → 火山引擎 → MiniMax → Moonshot → OpenAI → 腾讯 → xAI → Z.AI → 字节
- 保留币种分组（USD/CNY 同厂商相邻）；「输入价 ↑ / 输出价 ↑ / 月费 ↑」等价格排序不变

### 折叠

- 分组**默认折叠**（首次访问全部折叠，点击标题/箭头展开）
- 展开/折叠状态仍持久化到 `llmpr-collapsed`：用户手动操作过的组保持用户选择
- 修复首次点击展开无效的问题（未存状态时按"默认折叠"参与切换）

### 截图

- `docs/preview/az-collapsed-models.png`（模型视图默认折叠）
- `docs/preview/az-expanded-anthropic.png`（展开 Anthropic 组）

## 2026-09-21 · 数据入库 + 抓取脚本（参考合并 · 已回填查证）

### 数据入库（模型 13→24，计划 16→39）

- **新增模型 11 个**：grok-4.6（双档+缓存读）、grok-build-0.1、grok-4.5；Kimi K3 国内/国际、K2.7 Code、K2.6；MiniMax M2.7 国际/M2 国内；Doubao Seed 2.1 Pro / Seed Code
- **新增订阅 23 个**：Kimi Code 新套餐 $19/39/99/199、Qoder 国内 ¥59/169/559 + 国际 $20/60/200/40、CodeBuddy $10/40、TRAE $3/10/30/100、SuperGrok $30/100/300、Google AI Pro/Ultra 5×/20×
- **修正**：GLM 国际 Pro $72→$80、Max $160→$168（人工查证）；国内 ¥118/¥538/¥1,078 确认正确
- 三方同步：index.html 内嵌 + data.json + plans.json（content_hash 重算）

### 新增脚本

- `sync_data.py`：已查证数据入库同步（VERIFIED_* → 三方同步 + hash）
- `import_xlsx.py`：xlsx 采集表导入器（预览/--apply 双模式；CNY 口径保护）
- `fetch_official.py`：官方定价页抓取器（快照 + 可达性报告，不覆盖数据）
- 首次抓取：14 页可达 12 页（Google/Claude 网络失败，可重试）
- README 新增「数据维护工作流」；旧 fetch_data.py 标记停用

## 2026-09-21 · GLM 国际价修正（人工查证回填）

### 数据修正

- **GLM Coding Plan 国际价**：Pro $72→**$80**、Max $160→**$168**（Lite $18 不变），依据 z.ai 官方购买页（2026-09-21 人工查证）
- 同步更新 `index.html` 内嵌 plan-data、`plans.json`（content_hash/updated_at 重算）
- GLM 国内价 ¥118/¥538/¥1,078 **确认正确，无需改**（bigmodel.cn 购买页验证，推翻此前"调价至 49/149/469"的未证实报道）

### 新增调研文档

- `docs/data-expansion-2026-09-21.md`：参考合并版（合并用户 txt 报告 + xlsx 结构化库，回填 9 项查证结论）
- `docs/待查证-2026-09-21.md`：9 项冲突查证记录（6 项结案 / 3 项部分未核：Gemini 3.5 价格、GLM-5.3-Flash 促销有效期、Kimi 人民币订阅价、TRAE 国内人民币价）

### 查证要点

- TRAE 连续月付 $3/$10/$30/$100（Pro+ 存在）；xlsx 的 $20/$60/$200 与现售页不符
- SuperGrok $30/$100/$300 官方购买页证实（原二手价转正）
- MiniMax 国际新购 $22/$55/$132；$20/$50/$120 为存量签约价
- Kimi 新套餐（Go/Plus/Pro/Max $19/$39/$99/$199）无周限额；旧套餐（Andante 等）仍有周额度
- xAI US 端点 ×1.1 为官方规则（仅 grok-4.6 适用）

## 2026-09-21 · 区域切换、界面微调、按厂商折叠

### Z.AI 国际/国内切换（分组级）

- 切换器定位于 Z.AI 分组标题行内、供应商名之后、币种文字之前
- 币种文字跟随切换：`国内 → CNY · 3 个套餐`（¥118/¥538/¥1,078），分组位置不跳动（基准币种锁定）
- 切换状态持久化（`llmpr-plan-region`），刷新后保持
- 排查结论：前一会话记录的"点击不生效"为自动化测试假象（元素在视口外，点击坐标落空），代码本身无 bug

### 顺带修复（GLM 双 region 计划顶层字段缺失导致）

1. 分组标题 `undefined` 币种 → 新增 `baseCur()` 归一化
2. 币种筛选下 GLM 计划消失 → 筛选/排序改用 `baseCur`
3. CSV 导出 GLM 行空值 → 改用 `planCur(x)`
4. 比较视图对 GLM 显示异常 → 同上
5. 详情页"来源待补充" → `source` 从 region 内读取，并显示当前区域标签
6. 非默认排序大组时切换器错挂第一个供应商 → `groupRegionSwitch` 精准识别组内双 region 供应商（`|` 连接，逐一设置）

### 界面调整（用户需求）

- 移除"全部币种"筛选下拉（8 处相关代码全清，残留 0）
- 顶部导航栏变窄：高度 88→62px，品牌字号 21→19px，徽标 39→31px
- 按厂商折叠：点击分组标题折叠/展开该厂商所有行，箭头旋转指示，
  键盘可达（aria-expanded + 焦点保持），状态持久化且模型/计划视图隔离

### 工作区整理

- `gpt-ui-mvp.html`（GPT 原版备份）与 `_move_switch.py`（已执行的一次性迁移脚本）→ `docs/archive/`
- 清理临时文件，新增本 README 与 CHANGELOG

### 数据同步

- `plans.json`：12 条 → 16 条，与 index 内嵌一致
- `llm-price-manifest.json`：counts.plans=16，描述更新

## 2026-09-20 · 数据官方化（前次会话）

- 19→16 个计划：ChatGPT Pro 5×/20×、Claude Max 5×/20× 拆档
- GLM 国际/国内双 region 数据结构（`regions: {国际, 国内}`）
- 厂商 Lobe Icons 真实 Logo 内嵌（8 家）

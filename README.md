# LLM Price Radar · 价格工作台

[打开网站](https://xvshifu.github.io/llm-price-radar/) · [更新与部署](https://github.com/XVSHIFU/llm-price-radar/actions/workflows/pages.yml)

原生 HTML/CSS/JavaScript 模型 API 与 Coding Plan 价格目录。支持搜索、原币种比较、地区/档位切换、五维成本试算、关注、试算记录和 CSV 导出。数据内嵌，下载 `index.html` 后可离线打开。无需服务器或数据库。

## 发布与自动更新

- 推送 `main`：测试、构建、部署仓库内的数据，不重新抓取。
- 每天北京时间 **08:37**（UTC 00:37）：抓取、校验、保存数据版本、部署。
- 手动更新：Actions → **Update prices and deploy Pages** → **Run workflow**。勾选 `refresh` 时抓取，取消时只部署。
- 抓取报告、快照和待核对候选位于该次运行的 **Artifacts → fetch-report-…**，保留 30 天；摘要有逐源状态和价格差异。
- 通过校验的数据由机器人提交回 `main`；同一 workflow 直接部署，不依赖机器人提交触发下一次工作流。
- 全部来源失败、校验或构建失败时不部署，线上保留上一版。部分来源失败时只更新可验证的记录，其余保留旧数据。网页“来源”视图显示各来源状态。
- 每次部署只上传 `dist/` 内的 HTML、JSON、manifest 和 `.nojekyll`，不将脚本、抓取报告或历史备份作为网站文件发布。

GitHub 定时任务是尽力调度，可能延迟；公开仓库长期无活动（60 天）可能停用定时工作流，可在 Actions 重新启用。失败通知由个人 GitHub Actions 通知设置控制。正常访问网站需要网络；已下载的单文件不依赖联网。

## 自动更新边界

来源解析器是适配官方页面的规则，并非官方结构化 API。页面改版、反爬、网络限制都可能影响抓取。自动更新仅针对**已存在且供应商、来源、币种、计费档位能精确匹配**的记录：

- 比较所有档位的 input/output/read/write/storage，保留来源、注释、上下文等元数据。
- 地区报价只更新匹配地区；国际和国内不能互相覆盖。
- 新模型、档位变化、缺失已有单价、价格超出 0.25–4 倍范围或涉及零价格的变化：输出待核对候选，不直接覆盖。
- 匹配规则较保守，成功解析不等于所有解析结果都已采用。人工确认后修改 `data.json` 再发布。
- Google 等来源仍可能无法解析；火山引擎、Z.AI SPA 和订阅计划当前需要人工维护。
- `snapshot` 是**原始基准快照**，不是全库最近核验时间；`source_status` 记录抓取状态，模型/地区的 `last_checked_at` 只在对应记录通过校验时更新。
- 当前价格仍继承项目原始数据，本次工程改造不代表所有历史价格已经重新核验。

## 本地使用与开发

Python 3.12+。抓取、构建和 Python 测试只用标准库；前端检查需要 Node.js。

```sh
python -m unittest discover -s tests -v
python build_site.py --sync
node tests/check_frontend.cjs
python build_site.py
python -m http.server 8000 --directory dist
```

浏览器打开 `http://localhost:8000`。也可以直接打开根目录的 `index.html`。

```sh
python fetch_prices.py               # 预览报告，不改价格库
python fetch_prices.py openai        # 只抓取指定来源
python fetch_prices.py --apply       # 应用通过校验的变化并同步网页
```

报告写入 `reports/`，不会提交到 Git。使用 UTC 时间戳，路径相对于脚本所在目录，Windows/Linux 均可运行。

## 数据与代码结构

| 文件 | 用途 |
|---|---|
| `data.json` / `plans.json` | 唯一权威数据源，人工编辑这里 |
| `index.html` | 界面代码与便携离线页面；内嵌 JSON 由构建器生成 |
| `price_data.py` | 数据校验、稳定 hash、安全 JSON 内嵌、统一发布 |
| `build_site.py` | `--sync` 同步本地文件；默认构建 `dist/` |
| `fetch_prices.py` | 官方来源抓取、解析、报告 |
| `update_prices.py` | 保守合并与待人工核对记录 |
| `llm-price-manifest.json` | 自动生成的 AI 可读索引，路径适配 Pages 子目录 |
| `tests/` | 更新/发布及前端逻辑回归检查 |
| `import_xlsx.py` | 可选的人工 Excel 导入器，先预览再 `--apply` |
| `sync_data.py` | 历史覆盖表，直接执行已停用，防止倒灌旧数据 |
| `repair_sources.py` | 原始导入数据缺失来源引用的一次性修复，无价格更改 |

Excel 导入前安装 `python -m pip install -r requirements-import.txt`。它不在定时任务中运行。未知厂商需要先补充官方来源；导入仍应核对模型 ID 和地区，不能直接用第三方采集数据覆盖线上数据。

`content_hash` 是去掉自身 hash 字段后，按键排序、无多余空格、UTF-8 JSON 的 SHA-256；不将旧 hash 递归算入新 hash。

关注与试算仅保存在当前浏览器的 localStorage，不上传 GitHub，不跨设备同步。从本地文件切换到 Pages 域名后，不会自动迁移旧的浏览器记录。

## 首次配置与回滚

### Google 抓取范围

`google_prices.py` 只读取英文官方页的 Standard 付费 token 表；不采集 Batch、Flex、Priority、音频专用、图像生成或工具调用价格。支持明确的文本价格、上下文长度分档、`through` / `starting` 日期条件，以及独立的缓存存储费（美元 / 百万 token·小时）。日期按 UTC 判断。

未知条件、缺失档位或歧义价格会跳过该模型，保留旧数据；解析数量不代表官网全量模型覆盖。新模型和与库内标签不一致的档位仍进入 `reports/review.json`。跨年价格标签会变化，因此需人工核对后迁移，避免新价格配上旧日期说明。连接采用有限的退避重试，不绕过 TLS 校验。

离线回归：`python -m unittest discover -s tests -p test_google.py -v`。在线预览：`python fetch_prices.py google`（不加 `--apply` 不改价格库）。

## Pages 配置

仓库 Settings → Pages → Source 选择 **GitHub Actions**。工作流需要写入仓库数据和部署 Pages 的权限，已在 YAML 中按 job 声明，无需配置个人 token 或 SSH 密钥。

恢复旧数据：在 Git 中撤销有问题的数据提交，再推送 `main`；或者恢复所需版本的 `data.json` / `plans.json`，运行 `python build_site.py --sync` 后提交。不要仅重跑旧的 Actions run 来回滚，本工作流始终检出最新 `main`。

自定义域名需要在 Pages 设置中绑定并配置 DNS；默认 `github.io` 地址支持 HTTPS。

详细约束：[GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)、[Actions 定时任务](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

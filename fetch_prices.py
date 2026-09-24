# -*- coding: utf-8 -*-
"""官方定价抓取 · 唯一脚本（纯 python，无浏览器）。

覆盖全部官方定价源，一条命令抓取 → 解析 → 入库：

  python fetch_prices.py                 # 抓取 + 解析 + 差异报告（不写库）
  python fetch_prices.py --apply         # 抓取 + 解析 + 自动入库
  python fetch_prices.py openai          # 只处理指定来源（substring 匹配 id）

来源分三类：
  - html  静态可解析的官方定价页（OpenAI/Anthropic/xAI/DeepSeek/智谱/Google）
  - md    Mintlify 文档站 .md 定价文档（Kimi/MiniMax/阿里云百炼）
  - spa   纯 JS 渲染、无静态数据接口（火山引擎/Z.AI）→ 标注，数据由 xlsx/人工维护

--apply 入库规则：
  - 已有模型的同币种、同档位价格变更 → 校验后更新，保留元数据
  - 新模型、档位变化、缺失单价、异常变动 → 报告待人工核对，不覆盖
  - 智谱国内解析（glm-5-3-cn）→ 合并进库内 regions 模型国内档
  - 价格一致 → 跳过

输出：reports/fetch-report-<日期>.md（报告）+ reports/parsed/（解析明细）
"""

import os
import re
import sys
import json
import time
import http.cookiejar
from html import unescape
import urllib.request
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pathlib import Path
from price_data import atomic_write, read_json, publish
from update_prices import merge_candidates

ROOT = str(Path(__file__).resolve().parent)
SNAPSHOT_DIR = ROOT + "/reports/snapshots"
PARSED_DIR = ROOT + "/reports/parsed"
REPORT = ROOT + "/reports/fetch-report-%s.md"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36",
           "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}

# ============================================================
# 工具函数
# ============================================================
def _text(html):
    t = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.S)
    t = re.sub(r'<style[^>]*>.*?</style>', ' ', t, flags=re.S)
    t = re.sub(r'<[^>]+>', ' ', t)
    return re.sub(r'\s+', ' ', t)


def _f(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


class PricingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep bounded, query-free redirect diagnostics (never log session tokens)."""
    def __init__(self):
        self.hops = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        self.hops.append(f'{code} {target.scheme}://{target.netloc}{target.path}')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, timeout=25, retries=2):
    last = None
    for _ in range(retries + 1):
        if _:
            time.sleep(min(2 ** (_ - 1), 4))
        try:
            redirects = PricingRedirectHandler()
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), redirects)
            req = urllib.request.Request(url, headers=HEADERS)
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                try:
                    return resp.status, raw.decode("utf-8")
                except UnicodeDecodeError:
                    return resp.status, raw.decode("utf-8", errors="replace")
        except Exception as e:
            last = RuntimeError(f'{type(e).__name__}: request failed after redirects: '
                                + ' -> '.join(redirects.hops[-8:])) if redirects.hops else e
    raise last


# ============================================================
# 静态 HTML 解析器
# ============================================================
def parse_anthropic(html):
    """Read named columns, never infer price meaning from page-wide position."""
    aliases = {'name': 'model', 'model': 'model', 'input': 'input',
               'output': 'output', '5m writes': 'write5m', '1h writes': 'write1h',
               'hits and refreshes': 'read'}
    models = {}
    for table in re.findall(r'<table\b[^>]*>(.*?)</table>', html, re.S | re.I):
        columns = None
        for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', table, re.S | re.I):
            headers = re.findall(r'<th\b[^>]*>(.*?)</th>', row, re.S | re.I)
            if headers:
                # A full-width "Additional models" section is not a new schema.
                if len(headers) == 1 and re.search(r'<th\b[^>]*colspan=["\x27]?6\b', row, re.I):
                    continue
                keys = [aliases.get(unescape(_text(h)).strip().lower()) for h in headers]
                columns = keys if len(keys) == 6 and set(keys) == set(aliases.values()) else None
                continue
            cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)
            if columns is None or len(cells) != len(columns):
                continue
            values = dict(zip(columns, [unescape(_text(c)).strip() for c in cells]))
            name = re.match(r'Claude\s+([A-Za-z]+\s+\d+(?:\.\d+)*)\b', values['model'])
            if not name:
                continue
            prices = {}
            for key in ('input', 'output', 'write5m', 'write1h', 'read'):
                matches = re.findall(r'\$(\d+(?:\.\d+)?)\s*/\s*MTok\b', values[key])
                if len(matches) == 1 and values[key].count('$') == 1:
                    prices[key] = float(matches[0])
            if len(prices) != 5:
                continue
            mid = 'claude-' + name[1].lower().replace(' ', '-')
            model = {'id': mid, 'name': 'Claude ' + name[1], 'provider': 'Anthropic', 'currency': 'USD',
                     'rates': [{'label': label, 'input': prices['input'], 'output': prices['output'],
                                'read': prices['read'], 'write': prices[key]}
                               for label, key in [('缓存保留 5 分钟', 'write5m'), ('缓存保留 1 小时', 'write1h')]],
                     'notes': ['来源 platform.claude.com/docs/en/about-claude/pricing。']}
            if mid in models and models[mid]['rates'] != model['rates']:
                raise ValueError('Anthropic conflicting price rows: ' + mid)
            models[mid] = model
    return list(models.values())


def parse_openai(html):
    """developers.openai.com/api/docs/pricing：模型 + 8 价（短/长 × in/read/write/out），取标准档。"""
    t = _text(html)
    pat = re.compile(
        r'(gpt-[\w.-]+)\s+\$([\d.]+)\s+\$([\d.]+)\s+\$([\d.]+)\s+\$([\d.]+)\s+'
        r'\$([\d.]+)\s+\$([\d.]+)\s+\$([\d.]+)\s+\$([\d.]+)')
    seen, out = set(), []
    for m in pat.finditer(t):
        mid = m.group(1)
        if mid in seen:
            continue
        seen.add(mid)
        out.append({'id': mid, 'name': mid.upper().replace('.', '-'), 'provider': 'OpenAI', 'currency': 'USD',
                    'rates': [
                        {'label': 'Short context · 标准', 'input': _f(m.group(2)), 'output': _f(m.group(5)),
                         'read': _f(m.group(3)), 'write': _f(m.group(4))},
                        {'label': 'Long context · 标准', 'input': _f(m.group(6)), 'output': _f(m.group(9)),
                         'read': _f(m.group(7)), 'write': _f(m.group(8))}],
                    'notes': ['来源 developers.openai.com/api/docs/pricing（标准处理档）。']})
    return out


def parse_xai(html):
    """docs.x.ai/developers/pricing：模型 + 6 价（短/长 × in/read/out）。"""
    t = _text(html)
    pat = re.compile(
        r'(grok-[\w.-]+)\b[^$]*?\$([\d.]+)\s+\$([\d.]+)\s+\$([\d.]+)\s+'
        r'\$([\d.]+)\s+\$([\d.]+)\s+\$([\d.]+)')
    seen, out = set(), []
    for m in pat.finditer(t):
        mid = m.group(1)
        if mid in seen:
            continue
        seen.add(mid)
        out.append({'id': mid, 'name': mid.replace('-', ' ').title(), 'provider': 'xAI', 'currency': 'USD',
                    'rates': [
                        {'label': '标准 · 短上下文', 'input': _f(m.group(2)), 'output': _f(m.group(4)),
                         'read': _f(m.group(3)), 'write': None},
                        {'label': '标准 · 长上下文', 'input': _f(m.group(5)), 'output': _f(m.group(7)),
                         'read': _f(m.group(6)), 'write': None}],
                    'notes': ['来源 docs.x.ai/developers/pricing。']})
    return out


def parse_deepseek(html):
    """api-docs.deepseek.com：人民币两模型列（flash/v4-pro）峰谷价。"""
    t = _text(html)
    def grab(p):
        m = re.search(p, t)
        return [_f(x) for x in m.groups()] if m else None
    hit = grab(r'缓存命中[）)]\s*空闲时段\s*([\d.]+)元\s*([\d.]+)元\s*高峰时段\s*([\d.]+)元\s*([\d.]+)元')
    miss = grab(r'缓存未命中[）)]\s*空闲时段\s*([\d.]+)元\s*([\d.]+)元\s*高峰时段\s*([\d.]+)元\s*([\d.]+)元')
    out = grab(r'百万tokens输出\s*空闲时段\s*([\d.]+)元\s*([\d.]+)元\s*高峰时段\s*([\d.]+)元\s*([\d.]+)元')
    if not (hit and miss and out):
        return []
    def model(i, mid, name):
        return {'id': mid, 'name': name, 'provider': 'DeepSeek', 'currency': 'CNY',
                'rates': [
                    {'label': '高峰时段 · 北京时间', 'input': miss[i + 2], 'output': out[i + 2], 'read': hit[i + 2], 'write': None},
                    {'label': '空闲时段 · 北京时间', 'input': miss[i], 'output': out[i], 'read': hit[i], 'write': None}],
                'notes': ['来源 api-docs.deepseek.com（人民币原价，未换算）。']}
    return [model(0, 'deepseek-flash', 'DeepSeek Flash'),
            model(1, 'deepseek-v4-pro', 'DeepSeek V4 Pro')]


def parse_zhipu_cn(html):
    """docs.bigmodel.cn/cn/guide/start/pricing：GLM-X 档位 输入 输出 缓存存储 缓存命中。"""
    t = _text(html)
    pat = re.compile(
        r'(GLM-[\w.-]+)\s+((?:(?!GLM-|模型介绍|New|Hot).){0,60}?)\s+'
        r'(\d+(?:\.\d+)?|免费)\s+(\d+(?:\.\d+)?|免费)\s+限时免费\s+(\d+(?:\.\d+)?|不支持|免费)')
    seen, out = set(), []
    for m in pat.finditer(t):
        raw = m.group(1)
        mid = raw.lower() if raw.lower().startswith('glm') else 'glm-' + raw.lower()
        mid = mid.replace('.', '-') + '-cn'
        if mid in seen:
            continue
        seen.add(mid)
        inp = None if m.group(3) == '免费' else _f(m.group(3))
        o = None if m.group(4) == '免费' else _f(m.group(4))
        hit = None if m.group(5) in ('不支持', '免费') else _f(m.group(5))
        out.append({'id': mid, 'name': raw, 'provider': '智谱', 'currency': 'CNY',
                    'rates': [{'label': '标准 · ' + (m.group(2) or '标准'), 'input': inp, 'output': o,
                               'read': hit, 'write': None}],
                    'notes': ['国内 bigmodel.cn 官方页。']})
    return out


def parse_google(html, today=None):
    from google_prices import parse_google as parse_standard_prices
    return parse_standard_prices(html, today=today)


# ============================================================
# 文档站 .md 解析
# ============================================================
def parse_doc_table(md):
    """DocTable（rows={[...]}）→ (表头, 数据行) 列表。"""
    tables = []
    for m in re.finditer(r'columns=\{\s*\[(.*?)\]\s*\}.*?rows=\{\s*\[(.*?)\]\s*\}', md, re.S | re.I):
        cm, rm = m.groups()
        cols = re.findall(r'title:\s*"([^"]+)"', cm)
        try:
            rows = json.loads("[" + rm.rstrip().rstrip(",") + "]")
        except json.JSONDecodeError:
            continue
        if cols and rows and isinstance(rows[0], list):
            tables.append([cols] + rows)
    return tables


def parse_md_table(md):
    """普通 markdown 表格（| 分隔）。"""
    tables, cur = [], []
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("|"):
            cells = [c.strip().replace("**", "") for c in line.strip("|").split("|")]
            if set(cells) <= {"-", ":", ":---", "---", ":--", ":---:"}:
                continue
            cur.append(cells)
        else:
            if len(cur) >= 2:
                tables.append(cur)
            cur = []
    if len(cur) >= 2:
        tables.append(cur)
    return tables


def parse_jsx_table(md):
    """JSX <table> HTML（阿里云百炼 .md）。"""
    tables = []
    for tm in re.finditer(r'<table[^>]*>(.*?)</table>', md, re.S):
        rows = []
        for rm in re.finditer(r'<tr[^>]*>(.*?)</tr>', tm.group(1), re.S):
            cells = []
            for cm in re.finditer(r'<(th|td)[^>]*>(.*?)</\1>', rm.group(1), re.S):
                txt = re.sub(r'<[^>]+>', '', cm.group(2))
                cells.append(re.sub(r'\s+', ' ', txt).strip())
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def md_tables_to_models(tables, col_map, provider, model_filter=None):
    by_id = {}
    for rows in tables:
        if not rows:
            continue
        header = [str(h).strip() for h in rows[0]]
        idx = {}
        for field, kw in col_map.items():
            for i, h in enumerate(header):
                if kw in h:
                    idx[field] = i
                    break
        if "model" not in idx:
            continue
        for r in rows[1:]:
            if len(r) <= idx["model"]:
                continue
            model = re.sub(r'<[^>]+>', '', str(r[idx["model"]]))
            model = re.sub(r'<br\s*/?>|\*$', ' ', model).strip()
            model = re.split(r'[（(]', model)[0].strip()
            if not model:
                continue
            if model_filter and not re.match(model_filter, model):
                continue  # 只收指定前缀（如阿里云只收 qwen 自家）
            def cell(field):
                i = idx.get(field)
                if i is None or i >= len(r):
                    return None
                v = str(r[i]).strip().replace("¥", "").replace(",", "").replace("%", "")
                if not v or v in ("—", "-", "未找到", "null", "免费", "不支持", "永久五折", ""):
                    return None
                nums = re.findall(r'[\d]+\.?[\d]*', v)
                return float(nums[-1]) if nums else None
            inp = cell("input") or cell("input_miss")
            o = cell("output")
            if inp is None and o is None:
                continue
            tier = re.search(r'(≤\s*\d+[kK]|>\s*\d+[kK])', model)
            label = "标准 · " + tier.group(1).replace(" ", "") if tier else "标准"
            mid = re.sub(r'[^A-Za-z0-9.-]+', '-', model.lower()).strip('-')
            mid = re.sub(r'-{2,}', '-', mid)
            if not mid:
                continue
            rate = {'label': label, 'input': inp, 'output': o,
                    'read': cell("read"), 'write': cell("write") or cell("write5m")}
            if mid in by_id:
                rs = by_id[mid]["rates"]
                for i, e in enumerate(rs):
                    if e["label"] == label:
                        rs[i] = rate
                        break
                else:
                    rs.append(rate)
            else:
                by_id[mid] = {'id': mid, 'name': model, 'provider': provider, 'currency': 'CNY',
                              'rates': [rate], 'notes': ["来源 Mintlify .md 定价文档。"]}
    return list(by_id.values())


# ============================================================
# 来源清单
# ============================================================
SOURCES = [
    # ---- 静态 HTML（解析器） ----
    ("openai-api",  "OpenAI · API 定价", "https://developers.openai.com/api/docs/pricing", "html", parse_openai, None),
    ("claude-api",  "Anthropic · API 定价", "https://platform.claude.com/docs/en/about-claude/pricing", "html", parse_anthropic, None),
    ("xai-api",     "xAI · API 定价", "https://docs.x.ai/developers/pricing", "html", parse_xai, None),
    ("deepseek-api", "DeepSeek · 模型与价格", "https://api-docs.deepseek.com/zh-cn/quick_start/pricing", "html", parse_deepseek, None),
    ("zhipu-api",   "智谱 · GLM API 定价（国内）", "https://docs.bigmodel.cn/cn/guide/start/pricing", "html", parse_zhipu_cn, None),
    ("google-api",  "Google · Gemini API 定价", "https://ai.google.dev/gemini-api/docs/pricing?hl=en", "html", parse_google, None),
    # ---- 文档站 .md（格式, 列映射, 厂商） ----
    ("kimi-api", "Moonshot Kimi · API 定价", "https://platform.kimi.com/docs/pricing/chat.md", "md", None,
     ("doc_table", {"model": "模型", "input_miss": "未命中", "read": "命中", "write5m": "5min",
                    "write1h": "1h", "output": "输出"}, "Moonshot")),
    ("minimax-api", "MiniMax · API 定价（按量计费）", "https://platform.minimaxi.com/docs/guides/pricing-paygo.md", "md", None,
     ("md_table", {"model": "模型", "input": "输入", "output": "输出", "read": "缓存读取", "write": "缓存写入"}, "MiniMax")),
    ("aliyun-api", "阿里云百炼 · 模型定价", "https://help.aliyun.com/zh/model-studio/model-pricing.md", "md", None,
     ("jsx_table", {"model": "模型 ID", "input": "输入单价", "read": "缓存命中输入单价", "output": "输出单价"}, "阿里云", r"qwen")),
    # ---- 纯 JS SPA（无静态接口，数据由 xlsx/人工维护） ----
    ("volcengine-api", "火山引擎方舟 · API 定价", "https://docs.volcengine.com/docs/82379/1544106", "spa", None, None),
    ("zai-api", "Z.AI · API 定价", "https://z.ai/pricing", "spa", None, None),
]


SOURCE_DEFS = {
    "aliyun-api": {"name": "阿里云百炼 · 模型定价", "url": "https://help.aliyun.com/zh/model-studio/model-pricing", "scope": "Qwen 全系人民币价与缓存"},
    "codebuddy-plan": {"name": "腾讯 CodeBuddy · 订阅", "url": "https://intl.cloud.tencent.com/zh/document/product/1256/77270", "scope": "Pro/Team 月费与积分"},
    "glm-api": {"name": "智谱 · GLM API 定价（国际）", "url": "https://docs.z.ai/pricing", "scope": "GLM 国际站美元价"},
    "google-plan": {"name": "Google · AI 订阅", "url": "https://one.google.com/ai-premium", "scope": "AI Pro/Ultra 月费与存储"},
    "kimi-plan": {"name": "Moonshot Kimi Code · 订阅", "url": "https://www.kimi.com/membership/pricing", "scope": "Kimi Code 新套餐（国际美元）"},
    "qoder-plan": {"name": "通义 Qoder · 订阅", "url": "https://help.aliyun.com/zh/lingma/billing-description", "scope": "Qoder 国际/国内 Credits 套餐"},
    "trae-plan": {"name": "TRAE · 订阅", "url": "https://www.trae.ai/pricing", "scope": "Lite/Pro/Pro+/Ultra 连续月付"},
    "xai-plan": {"name": "xAI · SuperGrok 订阅", "url": "https://grok.com/plans", "scope": "SuperGrok/Plus/Heavy 月费"},
}


# ============================================================
# --apply 入库
# ============================================================
ID_ALIAS = {"glm-4-7-cn": "glm-4.7", "glm-5-3-cn": "glm-5.3",
            "glm-5-3-flash-cn": "glm-5.3-flash", "glm-5-3-flashx-cn": "glm-5.3-flashx"}
NOISE_SUFFIX = ("-us", "-region", "-usonlyinference", "-0309-reasoning", "-0309-non-reasoning", "-multi-agent-0309")


def apply_changes(parsed_all, statuses=None):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data, changes, pending = merge_candidates(read_json(ROOT + "/data.json"), parsed_all, now)
    # Snapshot remains the original baseline. Individual records carry their own timestamps.
    source_status = data.setdefault("source_status", {})
    for sid, status in (statuses or {}).items():
        previous = source_status.get(sid, {})
        source_status[sid] = {**previous, **status, "last_attempt": now}
        if status["status"] == "parsed":
            source_status[sid]["last_parsed"] = now
            source_status[sid]["review_count"] = sum(p["source"] == sid for p in pending)
    publish(data, read_json(ROOT + "/plans.json"), ROOT)
    return changes, pending


# ============================================================
# 主流程
# ============================================================
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if any(a in sys.argv for a in ("--help", "-h")):
        print(__doc__)
        return
    do_apply = "--apply" in sys.argv
    only = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    os.makedirs(PARSED_DIR, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    parsed_all = {}
    rows = []
    statuses = {}
    previous_status = read_json(ROOT + "/data.json").get("source_status", {})
    todo = [s for s in SOURCES if not only or only in s[0]]
    if not todo:
        raise SystemExit("没有匹配的来源：" + str(only))
    for i, (sid, name, url, kind, parser, md_cfg) in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {name} ...", flush=True)
        if kind == "spa":
            statuses[sid] = {"status": "manual", "message": "需要人工维护"}
            rows.append({"name": name, "status": "SPA", "parsed": None, "note": "纯 JS 渲染，无静态数据接口"})
            print(f"  SPA 无接口（数据由 xlsx/人工维护）", flush=True)
            continue
        try:
            status, body = fetch(url)
            if kind == "html":
                parsed = parser(body) or []
            else:
                fmt, col_map, prov, model_filter = md_cfg if len(md_cfg) == 4 else (*md_cfg, None)
                tables = (parse_doc_table(body) if fmt == "doc_table"
                          else parse_jsx_table(body) if fmt == "jsx_table" else parse_md_table(body))
                parsed = md_tables_to_models(tables, col_map, prov, model_filter)
            if not parsed:
                raise ValueError("页面已获取，但解析结果为空；保留旧数据")
            ids = [m["id"] for m in parsed]
            if len(ids) != len(set(ids)):
                raise ValueError("解析结果包含重复模型 ID")
            previous_count = previous_status.get(sid, {}).get("count", 0)
            if previous_count and len(parsed) < previous_count * 0.5:
                raise ValueError("解析数量较上次减少超过一半；保留该来源旧数据")
            with open(f"{SNAPSHOT_DIR}/{sid}.html", "w", encoding="utf-8") as f:
                f.write(body)
            parsed_all[sid] = parsed
            statuses[sid] = {"status": "parsed", "count": len(parsed)}
            rows.append({"name": name, "status": f"OK {status}", "parsed": len(parsed),
                         "note": ""})
            print(f"  OK 解析 {len(parsed)} 个模型", flush=True)
        except Exception as e:
            statuses[sid] = {"status": "failed", "message": str(e)[:200]}
            rows.append({"name": name, "status": f"FAIL {type(e).__name__}", "parsed": 0,
                         "note": str(e)[:70]})
            print(f"  FAIL {type(e).__name__}: {e}", flush=True)

    pfile = f"{PARSED_DIR}/parsed-{date}.json"
    atomic_write(pfile, json.dumps(parsed_all, ensure_ascii=False, indent=2))

    lines = [f"# 官方定价抓取报告 · {date}", "",
             "| 来源 | 状态 | 解析模型 | 备注 |", "|---|---|---|---|"]
    total = 0
    for r in rows:
        total += r["parsed"] or 0
        lines.append(f"| {r['name']} | {r['status']} | {r['parsed'] if r['parsed'] is not None else '—'} | {r['note']} |")
    lines.append("")
    lines.append(f"**共解析 {total} 个模型**（明细存 `{pfile}`）")

    if parsed_all:
        if do_apply:
            changes, pending = apply_changes(parsed_all, statuses)
        else:
            _, changes, pending = merge_candidates(read_json(ROOT + "/data.json"), parsed_all,
                                                    datetime.now(timezone.utc).isoformat(timespec="seconds"))
        lines += ["", "## 价格差异" + ("（已应用通过校验的项）" if do_apply else "（预览，未写库）"), ""]
        lines += [f"- {c['id']} / {c.get('region') or '默认'}：{json.dumps(c['before'], ensure_ascii=False)} → {json.dumps(c['after'], ensure_ascii=False)}" for c in changes]
        lines += ["", f"## 待人工核对（{len(pending)} 项，未自动覆盖）", ""]
        lines += [f"- {p['id']}：{p['reason']}" for p in pending]
        atomic_write(Path(ROOT) / "reports/review.json", json.dumps(pending, ensure_ascii=False, indent=2))
        print(f"变更 {len(changes)} 项，待核对 {len(pending)} 项")

    atomic_write(REPORT % date, "\n".join(lines) + "\n")
    print("报告：", REPORT % date)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write("\n".join(lines)[:50000] + "\n")
    if not parsed_all:
        raise SystemExit("所有来源均未成功解析；不发布，保留线上旧版。")
    failed = [sid for sid, value in statuses.items() if value["status"] == "failed"]
    if failed:
        print("::warning::部分来源失败，保留对应旧数据：" + ", ".join(failed))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""xlsx 采集数据导入器（官方采集表 → 数据入库）。

读取 LLM_price_radar_<日期>.xlsx 的「API价格」表，按 (厂商, 精确型号, 市场) 归并成
index.html 内嵌的 rates 结构，然后合并进 data.json / index.html 内嵌。

用法：
  python import_xlsx.py 文件.xlsx            # 预览：只生成候选清单 + 报告，不改库
  python import_xlsx.py 文件.xlsx --apply    # 确认无误后写库

规则：
  - 同一 (厂商,型号) 的多档行合并为一个模型的 rates[]，label 用「输入上下文档位」。
  - 市场（国际/美国端点/中国大陆）不同的同型号 → 拆成独立模型 id（如 kimi-k3-cn / kimi-k3-intl）。
  - 缓存 read/write/storage 为 null 的行保持 null（官方未单列 ≠ 免费）。
  - 已存在的同 id 模型将被覆盖（以本次 xlsx 为准）；id 生成规则见 gen_id()。
  - 币种取该市场行币种；DeepSeek 国内人民币行照录（不做换算）。
"""

import sys
import re
import json
import openpyxl
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from price_data import publish, read_json
from repair_sources import SOURCES

ROOT = str(Path(__file__).resolve().parent)
INDEX = ROOT + "/index.html"
DATA_JSON = ROOT + "/data.json"

VENDOR_NORM = {
    "智谱 / z.ai": "智谱", "智谱": "智谱", "z.ai": "智谱",
    "阿里云百炼": "阿里云", "火山引擎": "火山引擎",
}
MARKET_TAG = {
    "国际 / global": "intl", "国际": "intl", "国际 z.ai": "intl", "国际美元报价": "intl",
    "国际 gemini developer api": "intl", "gemini developer api": "intl",
    "国际 / global 美国端点": "us", "美国区域端点": "us", "us-only inference": "us",
    "中国大陆": "cn", "中国大陆 bigmodel.cn": "cn", "中国大陆 platform.minimaxi.com": "cn",
    "中国内地 / 北京": "cn", "国内": "cn", "中国": "cn",
    "支持的数据驻留区域端点": "region",
}


def col(row, name):
    """xlsx 行按表头取值；找不到返回 None。"""
    for k, v in row.items():
        if k and k.strip() == name:
            return v
    return None


def norm_vendor(v):
    if not v:
        return "Unknown"
    key = str(v).strip().lower()
    return VENDOR_NORM.get(key, str(v).strip())


def norm_market(m):
    if not m:
        return "intl"
    key = str(m).strip().lower()
    return MARKET_TAG.get(key, re.sub(r"[^a-z]", "", key) or "intl")


VENDOR_PREFIX = {
    "xai": "grok", "moonshot": "kimi", "智谱": "glm", "阿里云": "qwen",
    "火山引擎": "doubao", "minimax": "minimax", "openai": "gpt",
    "anthropic": "claude", "google": "gemini", "deepseek": "deepseek",
}


def gen_id(vendor, model, market):
    """id：厂商-型号-市场。型号已带厂商前缀则不重复前缀；市场只有国际时省略后缀。"""
    mid = re.sub(r"[^a-z0-9.-]", "", str(model).lower()).replace(".", "-")
    pfx = VENDOR_PREFIX.get(vendor.lower())
    base = mid if pfx and mid.startswith(pfx) else (pfx or re.sub(r"[^a-z0-9]", "", vendor.lower())[:6]) + "-" + mid
    return base if market == "intl" else "%s-%s" % (base, market)


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_rows(ws):
    header = {}
    for i, c in enumerate(ws[1]):
        header[i] = c.value.strip() if c.value else ""
    rows = []
    for r in ws.iter_rows(min_row=2):
        d = {}
        for i, c in enumerate(r):
            if i in header and header[i]:
                d[header[i]] = c.value
        if col(d, "记录ID"):
            rows.append(d)
    return rows


def build_candidates(rows):
    """按 (厂商,型号,市场) 归并行 → 模型候选 dict 列表。"""
    groups = defaultdict(list)
    for d in rows:
        vendor = norm_vendor(col(d, "厂商"))
        model = col(d, "精确型号")
        if not model:
            continue
        market = norm_market(col(d, "市场/部署区域"))
        groups[(vendor, str(model), market)].append(d)

    models = []
    for (vendor, model, market), grp in groups.items():
        rates = []
        notes = []
        currency = None
        for d in grp:
            cur = col(d, "币种") or currency
            if cur:
                currency = str(cur).upper()
            tier = col(d, "输入上下文档位") or "标准"
            label = ("%s · %s" % (str(tier), { "intl": "国际", "cn": "国内", "us": "US端点" }.get(market, market)))
            rates.append({
                "label": label,
                "input": fnum(col(d, "输入 / 百万tokens")),
                "output": fnum(col(d, "输出 / 百万tokens")),
                "read": fnum(col(d, "缓存read / 百万tokens")),
                "write": fnum(col(d, "缓存write / 百万tokens")),
                "storage": fnum(col(d, "缓存storage / 百万token·小时")),
            })
            remark = col(d, "备注") or ""
            if remark:
                notes.append(str(remark))
        rates = [r for r in rates if r["input"] is not None or r["output"] is not None]
        if not rates:
            continue
        # 同档位去重（US 端点 ×1.1 行可能与标准行档位相同）
        seen = set()
        dedup = []
        for r in rates:
            key = (r["input"], r["output"], r["read"])
            if key not in seen:
                seen.add(key)
                dedup.append(r)
        models.append({
            "id": gen_id(vendor, model, market),
            "name": "%s %s%s" % (vendor, model, { "intl": "", "cn": "（国内）", "us": "（US 端点）" }.get(market, "")),
            "provider": vendor,
            "currency": currency or "USD",
            "family": vendor,
            "source": ("zhipu-api" if (currency or "USD") == "CNY" else "glm-api") if vendor == "智谱" else SOURCES.get(vendor, "imported"),
            "rates": dedup,
            "notes": list(dict.fromkeys(notes))[:4],
        })
    models.sort(key=lambda m: m["id"])
    return models


def extract_script(s, tag):
    m = re.search(r'<script id="%s" type="application/json">(.*?)</script>' % tag, s, re.S)
    return m.group(1), m.start(1), m.end(1)


def apply(candidates):
    md = read_json(DATA_JSON)
    by_id = {m["id"]: m for m in md["models"]}
    added, overwritten, skipped = [], [], []
    for m in candidates:
        old = by_id.get(m["id"])
        # 保护：现有模型是官方人民币口径（如 DeepSeek 官方 CNY），
        # 不被 xlsx 的美元采集行覆盖，避免破坏口径一致性。
        if old and old.get("currency") == "CNY" and m.get("currency") != "CNY":
            skipped.append("%s (%s 已存在 CNY 口径，跳过 USD 候选)" % (m["id"], m["id"]))
            continue
        # Imported records need an explicit official source before publishing.
        if m.get("source") == "imported":
            skipped.append(m["id"] + "（请先为候选记录填写官方 source，再导入）")
            continue
        if m["id"] in by_id:
            overwritten.append(m["id"])
        else:
            added.append(m["id"])
        by_id[m["id"]] = m
    md["models"] = list(by_id.values())
    md["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    publish(md, read_json(Path(ROOT) / "plans.json"), ROOT)
    return added, overwritten, skipped


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    do_apply = "--apply" in sys.argv

    wb = openpyxl.load_workbook(path, data_only=True)
    api_sheet = None
    for ws in wb.worksheets:
        if "api" in ws.title.lower() or "价格" in ws.title:
            api_sheet = ws
            break
    if api_sheet is None:
        print("未找到「API价格」表，可用的表：", [w.title for w in wb.worksheets])
        sys.exit(1)

    rows = parse_rows(api_sheet)
    candidates = build_candidates(rows)

    print("== 解析 %d 行 → %d 个模型 ==" % (len(rows), len(candidates)))
    for m in candidates:
        r0 = m["rates"][0]
        print("  %-28s %-5s in=%s out=%s (%d 档)" % (
            m["id"], m["currency"], r0["input"], r0["output"], len(m["rates"])))

    if not do_apply:
        print("\n预览模式：未写库。确认无误后加 --apply 再跑。")
        return

    added, overwritten, skipped = apply(candidates)
    print("\n已写库：新增 %d 个模型，覆盖 %d 个模型，跳过 %d 个" % (len(added), len(overwritten), len(skipped)))
    if added:
        print("新增:", added)
    if overwritten:
        print("覆盖:", overwritten)
    if skipped:
        print("跳过（口径保护）:", skipped)


if __name__ == "__main__":
    main()

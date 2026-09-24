"""Shared validation and deterministic publishing for the static catalogue."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parent
PRICE_KEYS = ("input", "output", "read", "write", "storage")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".radar-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(payload):
    value = copy.deepcopy(payload)
    value.pop("content_hash", None)
    if isinstance(value.get("_meta"), dict):
        value["_meta"].pop("content_hash", None)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_rates(rates):
    if not isinstance(rates, list) or not rates:
        raise ValueError("rates must be a non-empty list")
    labels = set()
    for rate in rates:
        label = rate.get("label")
        if not isinstance(label, str) or not label.strip() or label in labels:
            raise ValueError(f"Missing or duplicate rate label: {label!r}")
        labels.add(label)
        for key in PRICE_KEYS:
            value = rate.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise ValueError(f"Invalid {key} price: {value!r}")


def validate(models, plans):
    sources = models.get("sources", [])
    source_ids = {s["id"] for s in sources}
    if len(source_ids) != len(sources):
        raise ValueError("Duplicate source IDs")
    for source in sources:
        if not re.match(r"^https?://[^/\s]+", source.get("url", "")):
            raise ValueError(f"Invalid source URL: {source['id']}")
    ids = set()
    for kind, entries in (("model", models.get("models")), ("plan", plans.get("plans"))):
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"Empty {kind} catalogue")
        for entry in entries:
            mid = entry.get("id")
            if not mid or mid in ids:
                raise ValueError(f"Missing or duplicate ID: {mid}")
            ids.add(mid)
            if not entry.get("name") or not entry.get("provider"):
                raise ValueError(f"Missing name/provider: {mid}")
            regions = entry.get("regions", {})
            variants = ([entry] if kind == "model" or not regions else []) + list(regions.values())
            for variant in variants:
                if variant.get("currency") not in ("USD", "CNY"):
                    raise ValueError(f"Invalid currency: {mid}")
                if variant.get("source", entry.get("source")) not in source_ids:
                    raise ValueError(f"Unknown source: {mid}")
                if kind == "model":
                    try:
                        validate_rates(variant.get("rates"))
                    except ValueError as exc:
                        raise ValueError(f"{mid}: {exc}") from exc
                else:
                    price = variant.get("price")
                    if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price < 0:
                        raise ValueError(f"Invalid subscription price: {mid}")


def embedded_json(payload):
    # HTML's script parser recognizes </script> even inside a JSON string.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")


def render_html(template, models, plans):
    for tag, payload in (("model-data", models), ("plan-data", plans)):
        pattern = rf'(<script id="{tag}" type="application/json">).*?(</script>)'
        template, count = re.subn(pattern, lambda m: m[1] + embedded_json(payload) + m[2], template, flags=re.S)
        if count != 1:
            raise ValueError(f"Expected one script#{tag}; found {count}")
    return template


def manifest(models, plans):
    return {
        "version": "1.0", "name": "llm-price-radar",
        "description": "模型 API 与订阅计划价格目录；原币种，未做汇率换算。",
        "instructions": "相对 URL 以本 manifest 所在目录为基准。价格来自多批快照；snapshot 不是全库最近核验日期。模型单价为每百万 token，storage 为每百万 token·小时；null 不等于免费。regions 为独立地区报价。source 对应 sources。content_hash 为去掉自身 hash 字段后的规范 JSON SHA-256。source_status 提供逐来源抓取状态；套餐由人工维护。",
        "snapshot": models.get("snapshot"),
        "plans_snapshot": plans.get("_meta", {}).get("snapshot"),
        "endpoints": {"data_url": "./data.json", "plans_url": "./plans.json", "manifest_url": "./llm-price-manifest.json"},
        "counts": {"models": len(models["models"]), "plans": len(plans["plans"]),
                   "sources": len(models["sources"]), "providers": len({m["provider"] for m in models["models"]})},
        "sources": models["sources"],
        "source_status": models.get("source_status", {}),
        "content_hashes": {"models": models["content_hash"], "plans": plans["_meta"]["content_hash"]},
    }


def publish(models, plans, output=ROOT, template=None):
    """Prepare/validate everything before writing. Pages deploys dist as one artifact."""
    models, plans = copy.deepcopy(models), copy.deepcopy(plans)
    validate(models, plans)
    models["content_hash"] = digest(models)
    plans.setdefault("_meta", {})["content_hash"] = digest(plans)
    if template is None:
        template = (ROOT / "index.html").read_text(encoding="utf-8")
    files = {"index.html": render_html(template, models, plans), "data.json": models,
             "plans.json": plans, "llm-price-manifest.json": manifest(models, plans)}
    for name, value in files.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        atomic_write(Path(output) / name, text)


# -*- coding: utf-8 -*-
"""数据入库同步脚本（2026-09-21 参考合并 + 人工查证定案）。

职责：
  1. 把 VERIFIED_MODELS / VERIFIED_PLANS（已查证定案数据）合并进
     index.html 内嵌 model-data / plan-data（按 id 覆盖或追加）。
  2. 同步写出 data.json / plans.json（结构完全一致）。
  3. 重算 content_hash（sha256 原始 JSON）、updated_at。

用法：python sync_data.py
以后新增确认数据：往 VERIFIED_MODELS / VERIFIED_PLANS 追加条目，再跑一次。
来源口径：docs/data-expansion-2026-09-21.md（参考合并版 · 已回填查证）。
"""

import json
import re
from datetime import datetime
from pathlib import Path
from price_data import publish, read_json

ROOT = str(Path(__file__).resolve().parent)
INDEX = ROOT + "/index.html"
DATA_JSON = ROOT + "/data.json"
PLANS_JSON = ROOT + "/plans.json"

# ============================================================
# 已查证定案 · 新增模型（rates 结构，与 index.html 内嵌一致）
# 依据：xlsx API 价格表（官方采集）+ 人工查证回填
# ============================================================
VERIFIED_MODELS = [
    # ---------- xAI ----------
    {
        "id": "grok-4.6", "name": "Grok 4.6", "provider": "xAI", "currency": "USD", "family": "Grok",
        "source": "xai-api",
        "rates": [
            {"label": "标准 · [0,200K)", "input": 2, "output": 6, "read": 0.5, "write": None},
            {"label": "标准 · [200K,500K]", "input": 4, "output": 12, "read": 1, "write": None},
        ],
        "notes": [
            "官方 docs.x.ai：达到 200K 后整次请求按长档计费；缓存读取已单列。",
            "US 区域端点按全球费率 ×1.1（官方规则，当前官方仅对 grok-4.6 提供 US 端点）。",
            "缓存 write/storage 官方未单列，不等于免费；服务端工具调用另计费。",
        ],
    },
    {
        "id": "grok-build-0.1", "name": "Grok Build 0.1", "provider": "xAI", "currency": "USD", "family": "Grok",
        "source": "xai-api",
        "rates": [
            {"label": "标准 · [0,200K)", "input": 1, "output": 2, "read": 0.2, "write": None},
            {"label": "标准 · [200K,256K]", "input": 2, "output": 4, "read": 0.4, "write": None},
        ],
        "notes": ["grok-code-fast-1 的官方迁移目标模型。", "缓存 write/storage 未单列。"],
    },
    {
        "id": "grok-4.5", "name": "Grok 4.5", "provider": "xAI", "currency": "USD", "family": "Grok",
        "source": "xai-api",
        "rates": [{"label": "标准 · [0,200K)", "input": 2, "output": 6, "read": 0.3, "write": None}],
        "notes": ["缓存 write/storage 未单列。"],
    },
    # ---------- Moonshot Kimi（官方 platform.kimi.com / platform.kimi.ai） ----------
    {
        "id": "kimi-k3", "name": "Kimi K3", "provider": "Moonshot", "currency": "USD", "family": "Kimi",
        "source": "kimi-api",
        "rates": [
            {"label": "标准 · 国际站", "input": 3, "output": 15, "read": 0.3, "write": 3},
        ],
        "regions": {
            "国际": {"currency": "USD", "rates": [{"label": "标准 · 国际站", "input": 3, "output": 15, "read": 0.3, "write": 3}]},
            "国内": {"currency": "CNY", "rates": [{"label": "标准 · 中国站", "input": 20, "output": 100, "read": 2, "write": 20}]},
        },
        "notes": [
            "官方中国站 platform.kimi.com 人民币价；国际站 platform.kimi.ai 美元价。",
            "缓存写 TTL 5min（¥20/$3），TTL 1h 翻倍（¥40/$6）；上下文 1,048,576。",
        ],
    },
    {
        "id": "kimi-k2.7-code-cn", "name": "Kimi K2.7 Code", "provider": "Moonshot", "currency": "CNY", "family": "Kimi",
        "source": "kimi-api",
        "rates": [
            {"label": "标准 · 中国站", "input": 6.5, "output": 27, "read": 1.3, "write": None},
            {"label": "HighSpeed · 中国站", "input": 13, "output": 54, "read": 2.6, "write": None},
        ],
        "notes": ["上下文 262,144。", "HighSpeed 为加速档，同模型价格 ×2。"],
    },
    {
        "id": "kimi-k2.6-cn", "name": "Kimi K2.6", "provider": "Moonshot", "currency": "CNY", "family": "Kimi",
        "source": "kimi-api",
        "rates": [
            {"label": "标准 · 中国站", "input": 6.5, "output": 27, "read": 1.1, "write": None},
        ],
        "notes": ["上下文 262,144。"],
    },
    # ---------- MiniMax（官方 platform.minimaxi.com / platform.minimax.io，M 系列统一价） ----------
    {
        "id": "minimax-m2.7", "name": "MiniMax M2.7", "provider": "MiniMax", "currency": "USD", "family": "MiniMax",
        "source": "minimax-api",
        "rates": [
            {"label": "标准 · 国际站", "input": 0.3, "output": 1.2, "read": 0.06, "write": 0.375},
            {"label": "HighSpeed · 国际站", "input": 0.6, "output": 2.4, "read": None, "write": None},
        ],
        "regions": {
            "国际": {"currency": "USD", "rates": [
                {"label": "标准 · 国际站", "input": 0.3, "output": 1.2, "read": 0.06, "write": 0.375},
                {"label": "HighSpeed · 国际站", "input": 0.6, "output": 2.4, "read": None, "write": None},
            ]},
            "国内": {"currency": "CNY", "rates": [
                {"label": "标准 · 中国站", "input": 2.1, "output": 8.4, "read": 0.21, "write": 2.625},
            ]},
        },
        "notes": ["M 系列统一价：国际 $0.30/$1.20，国内 ¥2.1/¥8.4。", "缓存 storage 官方未单列。"],
    },
    {
        "id": "minimax-m2", "name": "MiniMax M2", "provider": "MiniMax", "currency": "USD", "family": "MiniMax",
        "source": "minimax-api",
        "rates": [
            {"label": "标准 · 国际站", "input": 0.3, "output": 1.2, "read": None, "write": None},
        ],
        "regions": {
            "国际": {"currency": "USD", "rates": [
                {"label": "标准 · 国际站", "input": 0.3, "output": 1.2, "read": None, "write": None},
            ]},
            "国内": {"currency": "CNY", "rates": [
                {"label": "标准 · 中国站", "input": 2.1, "output": 8.4, "read": 0.21, "write": 2.625},
            ]},
        },
        "notes": ["国际 $0.30/$1.20（M 系列统一价）；国内 ¥2.1/¥8.4。", "缓存 storage 未单列。"],
    },
    # ---------- 火山引擎豆包（官方 volcengine ark 定价） ----------
    {
        "id": "doubao-seed-2.1-pro", "name": "Doubao Seed 2.1 Pro", "provider": "火山引擎", "currency": "CNY", "family": "Doubao",
        "source": "volcengine-api",
        "rates": [
            {"label": "标准", "input": 6, "output": 30, "read": 1.2, "write": None},
        ],
        "notes": ["缓存存储 ¥0.017/百万 token·小时。", "豆包全系（1.6/1.8/2.0-code/2.0-pro/2.1-turbo/evolving）见采集表。"],
    },
    {
        "id": "doubao-seed-code", "name": "Doubao Seed Code", "provider": "火山引擎", "currency": "CNY", "family": "Doubao",
        "source": "volcengine-api",
        "rates": [
            {"label": "输入 ≤ 32K", "input": 1.2, "output": 8, "read": 0.24, "write": None},
            {"label": "32K < 输入 ≤ 128K", "input": 1.4, "output": 12, "read": None, "write": None},
            {"label": "128K < 输入 ≤ 256K", "input": 2.8, "output": 16, "read": None, "write": None},
        ],
        "notes": ["编程模型，兼容 Anthropic API / TRAE。", "缓存存储 ¥0.017/百万 token·小时。"],
    },
    # ---------- 智谱 GLM（官方 z.ai / bigmodel.cn） ----------
    {
        "id": "glm-4.5", "name": "GLM-4.5", "provider": "智谱", "currency": "USD", "family": "GLM",
        "source": "glm-api",
        "rates": [{"label": "标准 · 国际站", "input": 0.6, "output": 2.2, "read": 0.11, "write": None}],
        "notes": ["国际 z.ai $0.6/$2.2；国内 bigmodel.cn 未列该精确型号。", "缓存 storage 限免截止日期未列。"],
    },
    {
        "id": "glm-4.6", "name": "GLM-4.6", "provider": "智谱", "currency": "USD", "family": "GLM",
        "source": "glm-api",
        "rates": [{"label": "标准 · 国际站", "input": 0.6, "output": 2.2, "read": 0.11, "write": None}],
        "notes": ["国际 z.ai $0.6/$2.2；国内 bigmodel.cn 未列该精确型号。"],
    },
    {
        "id": "glm-4.7", "name": "GLM-4.7", "provider": "智谱", "currency": "USD", "family": "GLM",
        "source": "glm-api",
        "rates": [{"label": "标准 · 国际站", "input": 0.6, "output": 2.2, "read": 0.11, "write": None}],
        "regions": {
            "国际": {"currency": "USD", "rates": [{"label": "标准 · 国际站", "input": 0.6, "output": 2.2, "read": 0.11, "write": None}]},
            "国内": {"currency": "CNY", "rates": [{"label": "标准 · [0,32K)", "input": 2, "output": 8, "read": 0.4, "write": None}]},
        },
        "notes": ["国内另有 [32K,200K) ¥3/¥14、¥4/¥16 档（此处列基础档）。"],
    },
    {
        "id": "glm-5.3", "name": "GLM-5.3", "provider": "智谱", "currency": "USD", "family": "GLM",
        "source": "glm-api",
        "rates": [{"label": "标准 · 国际站", "input": 1.4, "output": 4.4, "read": 0.26, "write": None}],
        "regions": {
            "国际": {"currency": "USD", "rates": [{"label": "标准 · 国际站", "input": 1.4, "output": 4.4, "read": 0.26, "write": None}]},
            "国内": {"currency": "CNY", "rates": [{"label": "标准 · 国内", "input": 8, "output": 28, "read": 2, "write": None}]},
        },
        "notes": ["缓存 storage 限免截止日期未列；write 未单列 ≠ 免费。"],
    },
    {
        "id": "glm-5.3-flash", "name": "GLM-5.3 Flash", "provider": "智谱", "currency": "USD", "family": "GLM",
        "source": "glm-api",
        "rates": [{"label": "标准 · 国际站", "input": 0.15, "output": 0.5, "read": 0.03, "write": None}],
        "regions": {
            "国际": {"currency": "USD", "rates": [{"label": "标准 · 国际站", "input": 0.15, "output": 0.5, "read": 0.03, "write": None}]},
            "国内": {"currency": "CNY", "rates": [{"label": "标准 · 国内", "input": 0.8, "output": 2.8, "read": 0.23, "write": None}]},
        },
        "notes": ["国内 FAQ 另报限时 5 折 ¥0.4/¥1.4，有效期未核实（待查证 #8），此处列标准价。"],
    },
    {
        "id": "glm-5.3-flashx", "name": "GLM-5.3 FlashX", "provider": "智谱", "currency": "USD", "family": "GLM",
        "source": "glm-api",
        "rates": [{"label": "标准 · 国际站", "input": 0.37, "output": 1.25, "read": 0.075, "write": None}],
        "regions": {
            "国际": {"currency": "USD", "rates": [{"label": "标准 · 国际站", "input": 0.37, "output": 1.25, "read": 0.075, "write": None}]},
            "国内": {"currency": "CNY", "rates": [{"label": "标准 · 国内", "input": 2, "output": 7, "read": 0.57, "write": None}]},
        },
        "notes": ["缓存 storage 限免截止日期未列。"],
    },
    # ---------- 火山引擎豆包全系（国内单币种） ----------
    {
        "id": "doubao-seed-1.6", "name": "Doubao Seed 1.6", "provider": "火山引擎", "currency": "CNY", "family": "Doubao",
        "source": "volcengine-api",
        "rates": [
            {"label": "输入 ≤ 32K", "input": 0.8, "output": 2, "read": 0.16, "write": None},
            {"label": "32K < 输入 ≤ 128K", "input": 1.2, "output": 16, "read": None, "write": None},
            {"label": "128K < 输入 ≤ 256K", "input": 2.4, "output": 24, "read": None, "write": None},
        ],
        "notes": ["缓存存储 ¥0.017/百万 token·小时。"],
    },
    {
        "id": "doubao-seed-1.8", "name": "Doubao Seed 1.8", "provider": "火山引擎", "currency": "CNY", "family": "Doubao",
        "source": "volcengine-api",
        "rates": [
            {"label": "输入 ≤ 32K", "input": 0.8, "output": 2, "read": 0.16, "write": None},
            {"label": "32K < 输入 ≤ 128K", "input": 1.2, "output": 16, "read": None, "write": None},
            {"label": "128K < 输入 ≤ 256K", "input": 2.4, "output": 24, "read": None, "write": None},
        ],
        "notes": ["缓存存储 ¥0.017/百万 token·小时。"],
    },
    {
        "id": "doubao-seed-2.0-code", "name": "Doubao Seed 2.0 Code", "provider": "火山引擎", "currency": "CNY", "family": "Doubao",
        "source": "volcengine-api",
        "rates": [
            {"label": "输入 ≤ 32K", "input": 3.2, "output": 16, "read": 0.64, "write": None},
            {"label": "32K < 输入 ≤ 128K", "input": 4.8, "output": 24, "read": None, "write": None},
            {"label": "128K < 输入 ≤ 256K", "input": 9.6, "output": 48, "read": None, "write": None},
        ],
        "notes": ["缓存存储 ¥0.017/百万 token·小时。"],
    },
    {
        "id": "doubao-seed-2.0-pro", "name": "Doubao Seed 2.0 Pro", "provider": "火山引擎", "currency": "CNY", "family": "Doubao",
        "source": "volcengine-api",
        "rates": [
            {"label": "输入 ≤ 32K", "input": 3.2, "output": 16, "read": 0.64, "write": None},
            {"label": "32K < 输入 ≤ 128K", "input": 4.8, "output": 24, "read": None, "write": None},
            {"label": "128K < 输入 ≤ 256K", "input": 9.6, "output": 48, "read": None, "write": None},
        ],
        "notes": ["缓存存储 ¥0.017/百万 token·小时。"],
    },
    {
        "id": "doubao-seed-2.1-turbo", "name": "Doubao Seed 2.1 Turbo", "provider": "火山引擎", "currency": "CNY", "family": "Doubao",
        "source": "volcengine-api",
        "rates": [{"label": "标准 · [0,256K]", "input": 3, "output": 15, "read": 0.6, "write": None}],
        "notes": ["缓存存储 ¥0.017/百万 token·小时。"],
    },
    {
        "id": "doubao-seed-evolving", "name": "Doubao Seed Evolving", "provider": "火山引擎", "currency": "CNY", "family": "Doubao",
        "source": "volcengine-api",
        "rates": [{"label": "标准 · [0,1024K]", "input": 6, "output": 30, "read": 1.2, "write": None}],
        "notes": ["缓存存储 ¥0.017/百万 token·小时。"],
    },
    # ---------- 阿里云 Qwen3（国内单币种） ----------
    {
        "id": "qwen3-coder-plus", "name": "Qwen3 Coder Plus", "provider": "阿里云", "currency": "CNY", "family": "Qwen",
        "source": "aliyun-api",
        "rates": [
            {"label": "输入 ≤ 32K", "input": 4, "output": 16, "read": 0.8, "write": None},
            {"label": "32K < 输入 ≤ 128K", "input": 6, "output": 24, "read": 1.2, "write": None},
            {"label": "128K < 输入 ≤ 256K", "input": 10, "output": 40, "read": 2, "write": None},
            {"label": "256K < 输入 ≤ 1M", "input": 20, "output": 200, "read": 4, "write": None},
        ],
        "notes": ["编程模型；256K-1M 档输出 ¥200 为长上下文惩罚性定价。"],
    },
    {
        "id": "qwen3-max", "name": "Qwen3 Max", "provider": "阿里云", "currency": "CNY", "family": "Qwen",
        "source": "aliyun-api",
        "rates": [
            {"label": "输入 ≤ 32K", "input": 2.5, "output": 10, "read": 0.5, "write": None},
            {"label": "32K < 输入 ≤ 128K", "input": 4, "output": 16, "read": 0.8, "write": None},
            {"label": "128K < 输入 ≤ 256K", "input": 7, "output": 28, "read": 1.4, "write": None},
        ],
        "notes": [],
    },
    {
        "id": "qwen3.8-max", "name": "Qwen3.8 Max", "provider": "阿里云", "currency": "CNY", "family": "Qwen",
        "source": "aliyun-api",
        "rates": [{"label": "标准 · [0,1M]", "input": 12, "output": 36, "read": None, "write": None}],
        "notes": [],
    },
    # ---------- Google Gemini 3.x 补齐（单 USD） ----------
    {
        "id": "gemini-3.6-flash", "name": "Gemini 3.6 Flash", "provider": "Google", "currency": "USD", "family": "Gemini",
        "source": "google-api",
        "rates": [{"label": "标准", "input": 0.75, "output": 3.75, "read": 0.075, "write": None, "storage": 0.5}],
        "notes": ["与 3.8 Flash 同为 $0.75/$3.75；缓存存储 $0.5/M·h。"],
    },
    {
        "id": "gemini-3.7-flash", "name": "Gemini 3.7 Flash", "provider": "Google", "currency": "USD", "family": "Gemini",
        "source": "google-api",
        "rates": [{"label": "标准", "input": 0.75, "output": 3.75, "read": 0.075, "write": None, "storage": 0.5}],
        "notes": ["与 3.8 Flash 同为 $0.75/$3.75；缓存存储 $0.5/M·h。"],
    },
    {
        "id": "gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro Preview", "provider": "Google", "currency": "USD", "family": "Gemini",
        "source": "google-api",
        "rates": [
            {"label": "提示词 ≤ 200K", "input": 2, "output": 12, "read": 0.2, "write": None},
            {"label": "提示词 > 200K", "input": 4, "output": 18, "read": 0.4, "write": None},
        ],
        "notes": ["Preview 型号。"],
    },
    # ---------- MiniMax M2.1 / M2.5 / M3（regions） ----------
    {
        "id": "minimax-m2.1", "name": "MiniMax M2.1", "provider": "MiniMax", "currency": "USD", "family": "MiniMax",
        "source": "minimax-api",
        "rates": [{"label": "标准 · 国际站", "input": 0.3, "output": 1.2, "read": 0.06, "write": 0.375}],
        "regions": {
            "国际": {"currency": "USD", "rates": [{"label": "标准 · 国际站", "input": 0.3, "output": 1.2, "read": 0.06, "write": 0.375}]},
            "国内": {"currency": "CNY", "rates": [{"label": "标准 · 中国站", "input": 2.1, "output": 8.4, "read": 0.21, "write": 2.625}]},
        },
        "notes": ["M 系列统一价。"],
    },
    {
        "id": "minimax-m2.5", "name": "MiniMax M2.5", "provider": "MiniMax", "currency": "USD", "family": "MiniMax",
        "source": "minimax-api",
        "rates": [{"label": "标准 · 国际站", "input": 0.3, "output": 1.2, "read": 0.06, "write": 0.375}],
        "regions": {
            "国际": {"currency": "USD", "rates": [{"label": "标准 · 国际站", "input": 0.3, "output": 1.2, "read": 0.06, "write": 0.375}]},
            "国内": {"currency": "CNY", "rates": [{"label": "标准 · 中国站", "input": 2.1, "output": 8.4, "read": 0.21, "write": 2.625}]},
        },
        "notes": ["M 系列统一价。"],
    },
    {
        "id": "minimax-m3", "name": "MiniMax M3", "provider": "MiniMax", "currency": "USD", "family": "MiniMax",
        "source": "minimax-api",
        "rates": [
            {"label": "标准 · 国际 ≤512K", "input": 0.3, "output": 1.2, "read": 0.06, "write": 0.375},
            {"label": "标准 · 国际 >512K", "input": 0.6, "output": 2.4, "read": 0.12, "write": None},
        ],
        "regions": {
            "国际": {"currency": "USD", "rates": [
                {"label": "标准 · 国际 ≤512K", "input": 0.3, "output": 1.2, "read": 0.06, "write": 0.375},
                {"label": "标准 · 国际 >512K", "input": 0.6, "output": 2.4, "read": 0.12, "write": None},
            ]},
            "国内": {"currency": "CNY", "rates": [
                {"label": "标准 · 国内 ≤512K", "input": 2.1, "output": 8.4, "read": 0.42, "write": None},
                {"label": "标准 · 国内 >512K", "input": 4.2, "output": 16.8, "read": 0.84, "write": None},
            ]},
        },
        "notes": ["M3 旗舰；>512K 超长档翻倍。"],
    },
    # ---------- xAI / Anthropic（Anthropic 全系来自官方 platform.claude.com/docs/en/about-claude/pricing） ----------
    {
        "id": "grok-4.3", "name": "Grok 4.3", "provider": "xAI", "currency": "USD", "family": "Grok",
        "source": "xai-api",
        "rates": [
            {"label": "标准 · [0,200K)", "input": 1.25, "output": 2.5, "read": 0.2, "write": None},
            {"label": "标准 · [200K,500K]", "input": 2.5, "output": 5, "read": 0.4, "write": None},
        ],
        "notes": ["旧型号迁移目标 grok-build-0.1；旧 slug 按 4.3 价格计费。"],
    },
    {
        "id": "claude-opus-5.5", "name": "Claude Opus 5.5", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 4, "output": 20, "read": 0.2, "write": 5},
            {"label": "缓存保留 1 小时", "input": 4, "output": 20, "read": 0.2, "write": 8},
        ],
        "notes": ["官方缓存命中 0.05× 基价（$4×0.05=$0.2）。"],
    },
    {
        "id": "claude-opus-5", "name": "Claude Opus 5", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 5, "output": 25, "read": 0.5, "write": 6.25},
            {"label": "缓存保留 1 小时", "input": 5, "output": 25, "read": 0.5, "write": 10},
        ],
        "notes": ["缓存命中 0.1× 基价（$5×0.1=$0.5）。"],
    },
    {
        "id": "claude-opus-4.8", "name": "Claude Opus 4.8", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 5, "output": 25, "read": 0.5, "write": 6.25},
            {"label": "缓存保留 1 小时", "input": 5, "output": 25, "read": 0.5, "write": 10},
        ],
        "notes": ["官方表确认 5m/1h 缓存写价；Opus 5 现售。"],
    },
    {
        "id": "claude-opus-4.7", "name": "Claude Opus 4.7", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 5, "output": 25, "read": 0.5, "write": 6.25},
            {"label": "缓存保留 1 小时", "input": 5, "output": 25, "read": 0.5, "write": 10},
        ],
        "notes": ["官方表确认 5m/1h 缓存写价。"],
    },
    {
        "id": "claude-opus-4.6", "name": "Claude Opus 4.6", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 5, "output": 25, "read": 0.5, "write": 6.25},
            {"label": "缓存保留 1 小时", "input": 5, "output": 25, "read": 0.5, "write": 10},
        ],
        "notes": ["官方表确认 5m/1h 缓存写价。"],
    },
    {
        "id": "claude-opus-4.5", "name": "Claude Opus 4.5", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 5, "output": 25, "read": 0.5, "write": 6.25},
            {"label": "缓存保留 1 小时", "input": 5, "output": 25, "read": 0.5, "write": 10},
        ],
        "notes": ["官方表确认 5m/1h 缓存写价。"],
    },
    {
        "id": "claude-sonnet-5", "name": "Claude Sonnet 5", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 2, "output": 10, "read": 0.2, "write": 2.5},
            {"label": "缓存保留 1 小时", "input": 2, "output": 10, "read": 0.2, "write": 4},
        ],
        "notes": ["官方注：$2/$10 为发布时介绍价（introductory pricing），后续可能调整。"],
    },
    {
        "id": "claude-sonnet-4.6", "name": "Claude Sonnet 4.6", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 3, "output": 15, "read": 0.3, "write": 3.75},
            {"label": "缓存保留 1 小时", "input": 3, "output": 15, "read": 0.3, "write": 6},
        ],
        "notes": ["Sonnet 5 现售。"],
    },
    {
        "id": "claude-sonnet-4.5", "name": "Claude Sonnet 4.5", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 3, "output": 15, "read": 0.3, "write": 3.75},
            {"label": "缓存保留 1 小时", "input": 3, "output": 15, "read": 0.3, "write": 6},
        ],
        "notes": ["官方表确认。"],
    },
    {
        "id": "claude-haiku-4.5", "name": "Claude Haiku 4.5", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 1, "output": 5, "read": 0.1, "write": 1.25},
            {"label": "缓存保留 1 小时", "input": 1, "output": 5, "read": 0.1, "write": 2},
        ],
        "notes": ["官方表确认。"],
    },
    {
        "id": "claude-fable-5.1", "name": "Claude Fable 5.1", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 10, "output": 50, "read": 0.25, "write": 12.5},
            {"label": "缓存保留 1 小时", "input": 10, "output": 50, "read": 0.25, "write": 20},
        ],
        "notes": ["官方缓存命中 0.025× 基价（$10×0.025=$0.25）。"],
    },
    {
        "id": "claude-fable-5", "name": "Claude Fable 5", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 10, "output": 50, "read": 1, "write": 12.5},
            {"label": "缓存保留 1 小时", "input": 10, "output": 50, "read": 1, "write": 20},
        ],
        "notes": ["Fable 5 缓存命中 0.1× 标准（区别于 5.1 的 0.025×）。"],
    },
    {
        "id": "claude-mythos-5.1", "name": "Claude Mythos 5.1", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 10, "output": 50, "read": 0.25, "write": 12.5},
            {"label": "缓存保留 1 小时", "input": 10, "output": 50, "read": 0.25, "write": 20},
        ],
        "notes": ["官方缓存命中 0.025× 基价；limited availability。"],
    },
    {
        "id": "claude-mythos-5", "name": "Claude Mythos 5", "provider": "Anthropic", "currency": "USD", "family": "Claude",
        "source": "claude-api",
        "rates": [
            {"label": "缓存保留 5 分钟", "input": 10, "output": 50, "read": 1, "write": 12.5},
            {"label": "缓存保留 1 小时", "input": 10, "output": 50, "read": 1, "write": 20},
        ],
        "notes": ["Mythos 5 缓存命中 0.1× 标准；limited availability。"],
    },
    {
        "id": "gpt-6-sol", "name": "GPT-6-SOL", "provider": "OpenAI", "currency": "USD",
        "source": "",
        "rates": [
                {"label": "Short context · 标准", "input": 2.0, "output": 10.0, "read": 0.2, "write": 2.5},
                {"label": "Long context · 标准", "input": 4.0, "output": 15.0, "read": 0.4, "write": 5.0}
        ],
        "notes": ["来源 developers.openai.com/api/docs/pricing（取标准处理档；Fast/Batch/Flex 档未取）。"],
    },
    {
        "id": "gpt-6-luna", "name": "GPT-6-LUNA", "provider": "OpenAI", "currency": "USD",
        "source": "",
        "rates": [
                {"label": "Short context · 标准", "input": 0.1, "output": 0.5, "read": 0.01, "write": 0.125},
                {"label": "Long context · 标准", "input": 0.2, "output": 0.75, "read": 0.02, "write": 0.25}
        ],
        "notes": ["来源 developers.openai.com/api/docs/pricing（取标准处理档；Fast/Batch/Flex 档未取）。"],
    },
    {
        "id": "claude-opus-4.1", "name": "Claude Opus 4.1", "provider": "Anthropic", "currency": "USD",
        "source": "",
        "rates": [
                {"label": "缓存保留 5 分钟", "input": 15.0, "output": 75.0, "read": 1.5, "write": 18.75},
                {"label": "缓存保留 1 小时", "input": 15.0, "output": 75.0, "read": 1.5, "write": 30.0}
        ],
        "notes": ["来源 platform.claude.com/docs/en/about-claude/pricing。"],
    },
    {
        "id": "claude-opus-4", "name": "Claude Opus 4", "provider": "Anthropic", "currency": "USD",
        "source": "",
        "rates": [
                {"label": "缓存保留 5 分钟", "input": 15.0, "output": 75.0, "read": 1.5, "write": 18.75},
                {"label": "缓存保留 1 小时", "input": 15.0, "output": 75.0, "read": 1.5, "write": 30.0}
        ],
        "notes": ["来源 platform.claude.com/docs/en/about-claude/pricing。"],
    },
    {
        "id": "claude-sonnet-4", "name": "Claude Sonnet 4", "provider": "Anthropic", "currency": "USD",
        "source": "",
        "rates": [
                {"label": "缓存保留 5 分钟", "input": 3.0, "output": 15.0, "read": 0.3, "write": 3.75},
                {"label": "缓存保留 1 小时", "input": 3.0, "output": 15.0, "read": 0.3, "write": 6.0}
        ],
        "notes": ["来源 platform.claude.com/docs/en/about-claude/pricing。"],
    },
    {
        "id": "claude-haiku-3.5", "name": "Claude Haiku 3.5", "provider": "Anthropic", "currency": "USD",
        "source": "",
        "rates": [
                {"label": "缓存保留 5 分钟", "input": 0.8, "output": 4.0, "read": 0.08, "write": 1.0},
                {"label": "缓存保留 1 小时", "input": 0.8, "output": 4.0, "read": 0.08, "write": 1.6}
        ],
        "notes": ["来源 platform.claude.com/docs/en/about-claude/pricing。"],
    },
    {
        "id": "grok-4.7", "name": "Grok 4.7", "provider": "xAI", "currency": "USD",
        "source": "",
        "rates": [
                {"label": "标准 · 短上下文", "input": 2.0, "output": 6.0, "read": 0.5, "write": None},
                {"label": "标准 · 长上下文", "input": 4.0, "output": 12.0, "read": 1.0, "write": None}
        ],
        "notes": ["来源 docs.x.ai/developers/pricing。"],
    },
    {
        "id": "grok-4.20-multi-agent-0309", "name": "Grok 4.20 Multi Agent 0309", "provider": "xAI", "currency": "USD",
        "source": "",
        "rates": [
                {"label": "标准 · 短上下文", "input": 1.25, "output": 2.5, "read": 0.2, "write": None},
                {"label": "标准 · 长上下文", "input": 2.5, "output": 5.0, "read": 0.4, "write": None}
        ],
        "notes": ["来源 docs.x.ai/developers/pricing。"],
    },
    {
        "id": "grok-4.20-0309-reasoning", "name": "Grok 4.20 0309 Reasoning", "provider": "xAI", "currency": "USD",
        "source": "",
        "rates": [
                {"label": "标准 · 短上下文", "input": 1.25, "output": 2.5, "read": 0.2, "write": None},
                {"label": "标准 · 长上下文", "input": 2.5, "output": 5.0, "read": 0.4, "write": None}
        ],
        "notes": ["来源 docs.x.ai/developers/pricing。"],
    },
    {
        "id": "grok-4.20-0309-non-reasoning", "name": "Grok 4.20 0309 Non Reasoning", "provider": "xAI", "currency": "USD",
        "source": "",
        "rates": [
                {"label": "标准 · 短上下文", "input": 1.25, "output": 2.5, "read": 0.2, "write": None},
                {"label": "标准 · 长上下文", "input": 2.5, "output": 5.0, "read": 0.4, "write": None}
        ],
        "notes": ["来源 docs.x.ai/developers/pricing。"],
    }
]

# ============================================================
# 已查证定案 · 新增订阅计划
# 依据：txt 采集报告 + xlsx 订阅表 + 人工查证回填
# ============================================================
VERIFIED_PLANS = [
    # ---------- Kimi Code 新套餐（国际，无周限额） ----------
    {"id": "kimi-code-plus",  "name": "Kimi Code Plus",  "provider": "Moonshot", "currency": "USD", "price": 19,  "kind": "Kimi Code 订阅", "quota": "5 小时滚动 + 月度共享额度", "tools": "Kimi Code", "note": "新套餐无每周额度限制。支持 K3；Pro 起 1M 上下文及 HighSpeed。", "source": "kimi-plan", "region": "国际"},
    {"id": "kimi-code-pro",   "name": "Kimi Code Pro",   "provider": "Moonshot", "currency": "USD", "price": 39,  "kind": "Kimi Code 订阅", "quota": "5 小时滚动 + 月度共享额度", "tools": "Kimi Code", "note": "新套餐无每周额度限制。", "source": "kimi-plan", "region": "国际"},
    {"id": "kimi-code-max",   "name": "Kimi Code Max",   "provider": "Moonshot", "currency": "USD", "price": 99,  "kind": "Kimi Code 订阅", "quota": "5 小时滚动 + 月度共享额度", "tools": "Kimi Code", "note": "新套餐无每周额度限制。", "source": "kimi-plan", "region": "国际"},
    {"id": "kimi-code-ultra", "name": "Kimi Code Ultra", "provider": "Moonshot", "currency": "USD", "price": 199, "kind": "Kimi Code 订阅", "quota": "5 小时滚动 + 月度共享额度", "tools": "Kimi Code", "note": "新套餐无每周额度限制。", "source": "kimi-plan", "region": "国际"},
    # ---------- Qoder 国内+国际（regions 双区域，同 GLM 切换） ----------
    {"id": "qoder-pro",    "name": "Qoder Pro",     "provider": "阿里云", "kind": "Qoder 订阅", "tools": "Qoder", "regions": {"国际": {"currency": "USD", "price": 20,  "quota": "2,000 Credits / 月",  "note": "半价活动已于 2026-04-30 结束，当前标准价。", "source": "qoder-plan"}, "国内": {"currency": "CNY", "price": 59,  "quota": "2,000 Credits / 月",  "note": "Credits 按模型消耗，不等于请求数。", "source": "qoder-plan"}}},
    {"id": "qoder-plus",   "name": "Qoder Pro+",    "provider": "阿里云", "kind": "Qoder 订阅", "tools": "Qoder", "regions": {"国际": {"currency": "USD", "price": 60,  "quota": "6,000 Credits / 月",  "note": "半价活动已于 2026-04-30 结束。", "source": "qoder-plan"}, "国内": {"currency": "CNY", "price": 169, "quota": "6,000 Credits / 月",  "note": "Credits 按模型消耗，不等于请求数。", "source": "qoder-plan"}}},
    {"id": "qoder-ultra",  "name": "Qoder Ultra",   "provider": "阿里云", "kind": "Qoder 订阅", "tools": "Qoder", "regions": {"国际": {"currency": "USD", "price": 200, "quota": "20,000 Credits / 月", "note": "半价活动已于 2026-04-30 结束。", "source": "qoder-plan"}, "国内": {"currency": "CNY", "price": 559, "quota": "20,000 Credits / 月", "note": "Credits 按模型消耗，不等于请求数。", "source": "qoder-plan"}}},
    {"id": "qoder-teams",  "name": "Qoder Teams",   "provider": "阿里云", "currency": "USD", "price": 40, "kind": "Qoder 订阅", "quota": "3,000 Credits / 坐席·月", "tools": "Qoder", "note": "团队公共池；无国内对应档。", "source": "qoder-plan", "region": "国际"},
    # ---------- 腾讯 CodeBuddy（官方文档） ----------
    {"id": "codebuddy-pro",  "name": "CodeBuddy Pro",  "provider": "腾讯", "currency": "USD", "price": 10, "kind": "CodeBuddy 订阅", "quota": "1,000 积分 / 月", "tools": "CodeBuddy", "note": "年付 $96（折合 $8/月）。积分当月有效、不累积结转。", "source": "codebuddy-plan", "region": "国际"},
    {"id": "codebuddy-team", "name": "CodeBuddy Team", "provider": "腾讯", "currency": "USD", "price": 40, "kind": "CodeBuddy 订阅", "quota": "1,000 积分 / 坐席·月", "tools": "CodeBuddy", "note": "年付 $480/坐席（$40/月）。团队公共池。", "source": "codebuddy-plan", "region": "国际"},
    # ---------- TRAE（连续月付，官方定价页） ----------
    {"id": "trae-lite",     "name": "TRAE Lite",     "provider": "字节", "currency": "USD", "price": 3,   "kind": "TRAE 订阅", "quota": "连续月付", "tools": "TRAE", "note": "含 $5 基础用量 + bonus。单买一月 $4.5。", "source": "trae-plan", "region": "国际"},
    {"id": "trae-pro",      "name": "TRAE Pro",      "provider": "字节", "currency": "USD", "price": 10,  "kind": "TRAE 订阅", "quota": "连续月付", "tools": "TRAE", "note": "SOLO 模式包含在 Pro 内，不单独收费。单买一月 $15。", "source": "trae-plan", "region": "国际"},
    {"id": "trae-pro-plus", "name": "TRAE Pro+",     "provider": "字节", "currency": "USD", "price": 30,  "kind": "TRAE 订阅", "quota": "连续月付", "tools": "TRAE", "note": "更高额度。单买一月 $45。", "source": "trae-plan", "region": "国际"},
    {"id": "trae-ultra",    "name": "TRAE Ultra",    "provider": "字节", "currency": "USD", "price": 100, "kind": "TRAE 订阅", "quota": "连续月付", "tools": "TRAE", "note": "最高档。单买一月 $150。", "source": "trae-plan", "region": "国际"},
    # ---------- xAI SuperGrok（官方购买页证实） ----------
    {"id": "supergrok",        "name": "SuperGrok",        "provider": "xAI", "currency": "USD", "price": 30,  "kind": "SuperGrok 订阅", "quota": "Grok 4.6 + 编码工具", "tools": "grok.com / iOS / Android", "note": "官方购买页证实（2026-09-21）。", "source": "xai-plan", "region": "国际"},
    {"id": "supergrok-plus",   "name": "SuperGrok Plus",   "provider": "xAI", "currency": "USD", "price": 100, "kind": "SuperGrok 订阅", "quota": "更高用量", "tools": "grok.com / iOS / Android", "note": "1080p 视频、优先访问、Grok Build。", "source": "xai-plan", "region": "国际"},
    {"id": "supergrok-heavy",  "name": "SuperGrok Heavy",  "provider": "xAI", "currency": "USD", "price": 300, "kind": "SuperGrok 订阅", "quota": "Grok Build agent、Grok 4 Heavy", "tools": "grok.com / iOS / Android", "note": "官方购买页证实（2026-09-21）。", "source": "xai-plan", "region": "国际"},
    # ---------- Google AI Pro / Ultra ----------
    {"id": "google-ai-pro",        "name": "Google AI Pro",      "provider": "Google", "currency": "USD", "price": 19.99, "kind": "Google AI 订阅", "quota": "5TB 存储 · Gemini 用量 4×", "tools": "Gemini App / Code Assist / CLI", "note": "含 Gemini Code Assist 与 Gemini CLI。", "source": "google-plan", "region": "国际"},
    {"id": "google-ai-ultra-5x",   "name": "Google AI Ultra 5×", "provider": "Google", "currency": "USD", "price": 99.99, "kind": "Google AI 订阅", "quota": "20TB 存储起 · 用量 5×", "tools": "Gemini App / Code Assist / CLI", "note": "I/O 2026 新入口价。", "source": "google-plan", "region": "国际"},
    {"id": "google-ai-ultra-20x",  "name": "Google AI Ultra 20×", "provider": "Google", "currency": "USD", "price": 200,   "kind": "Google AI 订阅", "quota": "用量 20×", "tools": "Gemini App / Code Assist / CLI", "note": "原 $250 降至 $200。", "source": "google-plan", "region": "国际"},
]


# ============================================================
# 同步逻辑
# ============================================================
def extract_script(s, tag):
    m = re.search(r'<script id="%s" type="application/json">(.*?)</script>' % tag, s, re.S)
    if not m:
        raise RuntimeError("找不到 script#" + tag)
    return m.group(1), m.start(1), m.end(1)


def merge_models(existing, additions):
    by_id = {m["id"]: m for m in existing}
    added, updated = [], []
    for m in additions:
        if m["id"] in by_id:
            updated.append(m["id"])
        else:
            added.append(m["id"])
        by_id[m["id"]] = m
    return list(by_id.values()), added, updated


def merge_plans(existing, additions):
    by_id = {p["id"]: p for p in existing}
    added, updated = [], []
    for p in additions:
        if p["id"] in by_id:
            updated.append(p["id"])
        else:
            added.append(p["id"])
        by_id[p["id"]] = p
    return list(by_id.values()), added, updated


def main():
    raise SystemExit("此脚本保存的是历史人工覆盖表，已停用直接执行，避免覆盖较新数据。请修改 data.json / plans.json 后运行 python build_site.py --sync。")


def apply_historical_overrides():
    """Legacy migration, deliberately excluded from the CLI and scheduled workflow."""
    with open(INDEX, encoding="utf-8") as f:
        html = f.read()

    # ---- model-data ----
    raw_md, a, b = extract_script(html, "model-data")
    md = json.loads(raw_md)
    md["models"], added_m, updated_m = merge_models(md["models"], VERIFIED_MODELS)

    # 补充 source 条目（若新 source 未登记）
    known_sources = {s["id"] for s in md.get("sources", [])}
    extra_sources = {
        "xai-api":        {"id": "xai-api", "name": "xAI · API 定价", "url": "https://docs.x.ai/developers/pricing", "scope": "模型价格与缓存读取；US 端点 ×1.1"},
        "kimi-api":       {"id": "kimi-api", "name": "Moonshot Kimi · API 定价", "url": "https://platform.kimi.com/docs/pricing/chat", "scope": "中国站人民币价与国际站美元价"},
        "minimax-api":    {"id": "minimax-api", "name": "MiniMax · API 定价", "url": "https://platform.minimaxi.com/docs/guides/pricing", "scope": "国内 M 系列人民币价与国际站美元价"},
        "volcengine-api": {"id": "volcengine-api", "name": "火山引擎方舟 · API 定价", "url": "https://docs.volcengine.com/docs/82379/1544106", "scope": "豆包全系人民币价与缓存"},
    }
    for sid, spec in extra_sources.items():
        if sid not in known_sources:
            md["sources"].append(spec)

    md["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    md["snapshot"] = datetime.now().strftime("%Y-%m-%d")
    new_raw_md = json.dumps(md, ensure_ascii=False, separators=(",", ":"))
    from price_data import digest
    md_hash = digest(md)
    # 保留原始缩进结构：将 updated_at/content_hash 重算
    md["content_hash"] = md_hash
    new_raw_md = json.dumps(md, ensure_ascii=False, separators=(",", ":"))

    # ---- plan-data ----
    raw_pd, c, d = extract_script(html, "plan-data")
    pd = json.loads(raw_pd)
    pd["plans"], added_p, updated_p = merge_plans(pd["plans"], VERIFIED_PLANS)
    pd["_meta"]["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    pd["_meta"]["content_hash"] = digest(pd)
    new_raw_pd = json.dumps(pd, ensure_ascii=False, separators=(",", ":"))

    # 写回 index.html
    publish(md, pd, ROOT)

    print("== 同步完成 ==")
    print("模型新增:", added_m)
    print("模型覆盖:", updated_m)
    print("计划新增:", added_p)
    print("计划覆盖:", updated_p)
    print("data.json models:", len(md["models"]), "| plans.json plans:", len(pd["plans"]))
    print("content_hash 已重算：model=%s... plan=%s..." % (md["content_hash"][:8], pd["_meta"]["content_hash"][:8]))


if __name__ == "__main__":
    main()

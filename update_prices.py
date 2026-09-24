"""Conservative price merging: never infer a new billing tier from a loose parser."""
import copy
from price_data import PRICE_KEYS, validate_rates

ALIASES = {"glm-4-7-cn": "glm-4.7", "glm-5-3-cn": "glm-5.3",
           "glm-5-3-flash-cn": "glm-5.3-flash", "glm-5-3-flashx-cn": "glm-5.3-flashx"}


def merge_rates(old, new):
    validate_rates(new)
    # These are heuristically parsed tables, so labels and dimensions must agree.
    before = {r["label"]: r for r in old}
    after = {r["label"]: r for r in new}
    if before.keys() != after.keys():
        raise ValueError("计费档位发生变化，需要核对上下文/缓存/峰谷口径")
    merged = []
    for label, prior in before.items():
        incoming = after[label]
        result = dict(prior)
        for key in PRICE_KEYS:
            value, previous = incoming.get(key), prior.get(key)
            if value is None and previous is not None:
                raise ValueError(f"解析缺失已有单价：{label}/{key}")
            if value is not None:
                if previous is not None and value != previous:
                    if previous == 0 or value == 0 or not 0.25 <= value / previous <= 4:
                        raise ValueError(f"价格变化超出自动更新范围：{label}/{key}")
                result[key] = value
        merged.append(result)
    return merged


def merge_candidates(data, parsed_all, now):
    result = copy.deepcopy(data)
    models = {m["id"]: m for m in result["models"]}
    changes, pending = [], []
    for sid, candidates in parsed_all.items():
        for candidate in candidates:
            mid = ALIASES.get(candidate["id"], candidate["id"])
            old = models.get(mid)
            try:
                if old is None:
                    raise ValueError("新模型，需要先核对模型 ID、币种和计费口径")
                if old["provider"] != candidate["provider"]:
                    raise ValueError("供应商不一致")
                region = None
                target = old
                if old.get("regions"):
                    matches = [(k, v) for k, v in old["regions"].items() if v["currency"] == candidate["currency"]]
                    if len(matches) != 1:
                        raise ValueError("无法唯一匹配地区")
                    region, target = matches[0]
                if target["currency"] != candidate["currency"]:
                    raise ValueError("币种不一致")
                original_source = target.get("source", old.get("source"))
                if original_source != sid and not (sid == "zhipu-api" and region == "国内" and original_source == "glm-api"):
                    raise ValueError("来源不一致")
                rates = merge_rates(target["rates"], candidate["rates"])
                if rates != target["rates"]:
                    changes.append({"id": mid, "source": sid, "region": region,
                                    "before": copy.deepcopy(target["rates"]), "after": rates})
                    target["rates"] = rates
                    target["price_updated_at"] = now
                    result["updated_at"] = now
                    # Root rates remain compatible with the international default.
                    if region == "国际":
                        old["rates"] = copy.deepcopy(rates)
                target["last_checked_at"] = now
            except (ValueError, KeyError, TypeError) as exc:
                pending.append({"id": mid, "source": sid, "reason": str(exc), "candidate": candidate})
    return result, changes, pending

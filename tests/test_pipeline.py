import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import io
import os

from price_data import ROOT, digest, publish, read_json, render_html, validate
from update_prices import merge_candidates


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.data = read_json(ROOT / "data.json")
        self.plans = read_json(ROOT / "plans.json")
        self.model = copy.deepcopy(next(m for m in self.data["models"] if m["id"] == "claude-sonnet-5"))
        self.source = self.model["source"]

    def merge(self, candidate):
        return merge_candidates(self.data, {self.source: [candidate]}, "2026-09-24T00:00:00+00:00")

    def test_baseline_valid(self):
        validate(self.data, self.plans)

    def test_cache_only_and_second_tier_changes(self):
        candidate = copy.deepcopy(self.model)
        candidate["rates"][0]["read"] *= 1.1
        candidate["rates"][1]["write"] *= 1.1
        result, changes, pending = self.merge(candidate)
        changed = next(m for m in result["models"] if m["id"] == candidate["id"])
        self.assertEqual(changed["rates"], candidate["rates"])
        self.assertEqual(len(changes), 1)
        self.assertEqual(pending, [])

    def test_parser_cannot_drop_notes_source_or_metadata(self):
        candidate = {k: copy.deepcopy(self.model[k]) for k in ("id", "provider", "currency", "rates")}
        candidate["notes"] = ["generic parser note"]
        candidate["rates"][0]["input"] *= 1.1
        result, _, pending = self.merge(candidate)
        changed = next(m for m in result["models"] if m["id"] == candidate["id"])
        self.assertEqual(changed["source"], self.model["source"])
        self.assertEqual(changed["notes"], self.model["notes"])
        self.assertEqual(pending, [])

    def test_missing_cache_or_tier_keeps_entire_model(self):
        for mutation in (lambda m: m["rates"][0].update(read=None), lambda m: m["rates"].pop()):
            candidate = copy.deepcopy(self.model)
            mutation(candidate)
            result, changes, pending = self.merge(candidate)
            self.assertEqual(result, self.data)
            self.assertEqual(changes, [])
            self.assertEqual(len(pending), 1)

    def test_wrong_currency_and_outlier_rejected(self):
        for mutation in (lambda m: m.update(currency="CNY"), lambda m: m["rates"][0].update(input=99999)):
            candidate = copy.deepcopy(self.model)
            mutation(candidate)
            result, changes, pending = self.merge(candidate)
            self.assertEqual(result, self.data)
            self.assertEqual(changes, [])
            self.assertTrue(pending)

    def test_region_update_does_not_touch_international_prices(self):
        original = next(m for m in self.data["models"] if m["id"] == "minimax-m2.7")
        candidate = {"id": original["id"], "provider": original["provider"],
                     "currency": "CNY", "rates": copy.deepcopy(original["regions"]["国内"]["rates"])}
        candidate["rates"][0]["output"] *= 1.1
        result, changes, pending = merge_candidates(self.data, {"minimax-api": [candidate]}, "test")
        changed = next(m for m in result["models"] if m["id"] == original["id"])
        self.assertEqual(changed["regions"]["国际"], original["regions"]["国际"])
        self.assertEqual(changed["rates"], original["rates"])
        self.assertEqual(changed["regions"]["国内"]["rates"], candidate["rates"])
        self.assertEqual(len(changes), 1)
        self.assertFalse(pending)

    def test_new_model_goes_to_review(self):
        candidate = copy.deepcopy(self.model)
        candidate["id"] = "unknown-new-model"
        result, _, pending = self.merge(candidate)
        self.assertEqual(result, self.data)
        self.assertEqual(len(pending), 1)

    def test_partial_update_does_not_claim_new_baseline(self):
        candidate = copy.deepcopy(self.model)
        candidate["rates"][0]["input"] *= 1.1
        result, _, _ = self.merge(candidate)
        self.assertEqual(result["snapshot"], self.data["snapshot"])
        self.assertEqual(next(m for m in result["models"] if m["id"] == "deepseek-flash"),
                         next(m for m in self.data["models"] if m["id"] == "deepseek-flash"))

    def test_hash_is_stable_and_tracks_payload(self):
        value = copy.deepcopy(self.data)
        initial = digest(value)
        value["content_hash"] = "old"
        self.assertEqual(digest(value), initial)
        value["models"][0]["rates"][0]["input"] += 1
        self.assertNotEqual(digest(value), initial)

    def test_html_safe_json_round_trip(self):
        data = copy.deepcopy(self.data)
        data["models"][0]["notes"] = ['</script><script>alert("x")</script>']
        html = render_html((ROOT / "index.html").read_text(encoding="utf-8"), data, self.plans)
        raw = re.search(r'<script id="model-data" type="application/json">(.*?)</script>', html, re.S)[1]
        self.assertEqual(json.loads(raw), data)
        self.assertNotIn('<script>alert', html)

    def test_build_publishes_only_public_files_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            publish(self.data, self.plans, tmp)
            paths = list(Path(tmp).iterdir())
            self.assertEqual({p.name for p in paths}, {"index.html", "data.json", "plans.json", "llm-price-manifest.json"})
            initial = {p.name: p.read_bytes() for p in paths}
            publish(self.data, self.plans, tmp)
            self.assertEqual(initial, {p.name: p.read_bytes() for p in paths})
            manifest = read_json(Path(tmp) / "llm-price-manifest.json")
            self.assertEqual(manifest["counts"]["models"], len(self.data["models"]))
            self.assertEqual(manifest["endpoints"]["data_url"], "./data.json")

    def test_invalid_catalog_does_not_overwrite_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            publish(self.data, self.plans, tmp)
            before = (Path(tmp) / "index.html").read_bytes()
            broken = copy.deepcopy(self.data)
            broken["models"][0]["rates"][0]["input"] = float("nan")
            with self.assertRaises(ValueError):
                publish(broken, self.plans, tmp)
            self.assertEqual(before, (Path(tmp) / "index.html").read_bytes())

    def test_failed_fetch_retains_data_and_generates_report(self):
        import fetch_prices
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "data.json").write_text(json.dumps(self.data), encoding="utf-8")
            before = (folder / "data.json").read_bytes()
            with patch.multiple(fetch_prices, ROOT=tmp, SNAPSHOT_DIR=tmp + "/snapshots",
                                PARSED_DIR=tmp + "/parsed", REPORT=tmp + "/report-%s.md"), \
                 patch.object(fetch_prices, "SOURCES", [("test", "Test", "https://example.com", "html", lambda h: [], None)]), \
                 patch.object(fetch_prices, "fetch", return_value=(200, "empty page")), \
                 patch("sys.argv", ["fetch_prices.py", "--apply"]), patch("sys.stdout", io.StringIO()), \
                 patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}):
                with self.assertRaises(SystemExit):
                    fetch_prices.main()
            self.assertEqual(before, (folder / "data.json").read_bytes())
            self.assertIn("FAIL", next(folder.glob("report-*.md")).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

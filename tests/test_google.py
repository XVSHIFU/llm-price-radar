import unittest
from datetime import date
from fetch_prices import parse_google


def page(inp, out, cache, model='gemini-3.8-flash'):
    rows = ''.join(f'<tr><td>{label}</td><td>Free of charge</td><td>{value}</td></tr>'
                   for label, value in [('Input price', inp), ('Output price', out), ('Context caching price', cache)])
    return f'<h2>{model}</h2><code>{model}</code><h3>Standard</h3><table><tr><th></th><th>Free Tier</th><th>Paid Tier, per 1M tokens in USD</th></tr>{rows}</table><h3>Batch</h3><table>{rows}</table>'


class GoogleTests(unittest.TestCase):
    def test_current_dated_prices_and_storage(self):
        h = page('$0.75 through December 31, 2026.<br>$1.50 starting January 1, 2027.',
                 '$3.75 through December 31, 2026.<br>$7.50 starting January 1, 2027.',
                 '$0.075 through December 31, 2026.<br>$0.15 starting January 1, 2027.<br>$0.50 / 1,000,000 tokens per hour (storage price) through December 31, 2026.<br>$1.00 / 1,000,000 tokens per hour (storage price) starting January 1, 2027.')
        now = parse_google(h, today=date(2026, 12, 31))[0]['rates'][0]
        self.assertEqual((now['input'], now['output'], now['read'], now['storage']), (.75, 3.75, .075, .5))
        future = parse_google(h, today=date(2027, 1, 1))[0]['rates'][0]
        self.assertEqual((future['input'], future['output'], future['storage']), (1.5, 7.5, 1))
        self.assertNotEqual(now['label'], future['label'])

    def test_context_tiers(self):
        h = page('$1.25, prompts <= 200k tokens<br>$2.50, prompts > 200k tokens',
                 '$10, prompts &lt;= 200k<br>$15, prompts > 200k',
                 '$0.125, prompts <= 200k<br>$0.25, prompts > 200k<br>$4.50 / 1,000,000 tokens per hour (storage price)', 'gemini-2.5-pro')
        rates = parse_google(h)[0]['rates']
        self.assertEqual([r['input'] for r in rates], [1.25, 2.5])
        self.assertEqual([r['storage'] for r in rates], [4.5, 4.5])

    def test_text_not_audio(self):
        h = page('$0.10 (text / image / video)<br>$0.30 (audio)', '$0.40',
                 '$0.01 (text / image / video)<br>$0.03 (audio)<br>$1.00 / 1,000,000 tokens per hour (storage price)')
        r = parse_google(h)[0]['rates'][0]
        self.assertEqual((r['input'], r['read'], r['storage']), (.1, .01, 1))
        self.assertEqual(r['label'], 'Standard · 文本')

    def test_ambiguous_and_missing_standard_fail_closed(self):
        self.assertEqual(parse_google(page('$1 special offer', '$2', '$0.1')), [])
        self.assertEqual(parse_google(page('$1', '$2', '$0.1').replace('Standard', 'Priority')), [])
        self.assertEqual(parse_google(page('$1<br>$2', '$3', '$0.1')), [])

    def test_future_only_prices_and_missing_paid_header_rejected(self):
        self.assertEqual(parse_google(page('$1 starting January 1, 2027.', '$2', '$0.1'), today=date(2026, 9, 24)), [])
        self.assertEqual(parse_google(page('$1', '$2', '$0.1').replace('Paid Tier, per 1M tokens in USD', 'Paid Tier per request')), [])

    def test_duplicate_sections_are_not_silently_selected(self):
        h = page('$1', '$2', '$0.1')
        with self.assertRaises(ValueError):
            parse_google(h + h)

    def test_missing_context_tier_rejects_entire_model(self):
        h = page('$1, prompts <= 200k<br>$2, prompts > 200k', '$3, prompts <= 200k', '$0.1')
        self.assertEqual(parse_google(h), [])

    def test_date_rollover_requires_review_not_stale_label_update(self):
        from update_prices import merge_candidates
        h = page('$1 through December 31, 2026.<br>$2 starting January 1, 2027.', '$3', '$0.1')
        old = parse_google(h, today=date(2026, 12, 31))[0]
        old['source'] = 'google-api'
        data = {'models': [old]}
        new = parse_google(h, today=date(2027, 1, 1))
        result, changes, pending = merge_candidates(data, {'google-api': new}, 'test')
        self.assertEqual(result, data)
        self.assertEqual(changes, [])
        self.assertEqual(len(pending), 1)

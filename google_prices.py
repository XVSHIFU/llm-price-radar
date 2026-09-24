"""Conservative parser for Google's English Standard paid token tables.

Unknown price qualifiers fail closed. Storage is USD / million tokens / hour,
never a cache-write price. Explicit dates are interpreted on a UTC date boundary.
"""
import re
from datetime import datetime, timezone
from html.parser import HTMLParser


class CellText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ('br', 'p', 'div'):
            self.parts.append(' ')


def text(html):
    parser = CellText()
    parser.feed(html)
    return re.sub(r'\s+', ' ', ''.join(parser.parts)).strip()


def amounts(cell, today):
    value = text(cell)
    if value.lower() == 'not available':
        return []
    if not value.startswith('$'):
        raise ValueError('Unknown price cell')
    result = []
    for part in value.split('$')[1:]:
        match = re.fullmatch(r'(\d+(?:\.\d+)?)(.*)', part.strip())
        if not match:
            raise ValueError('Unknown amount')
        price, qualifier = float(match[1]), match[2].strip()
        period = None
        dates = re.search(r'\b(through|starting) ([A-Z][a-z]+ \d{1,2}, \d{4})\.?$', qualifier)
        if dates:
            boundary = datetime.strptime(dates[2], '%B %d, %Y').date()
            if (dates[1] == 'through' and today > boundary) or (dates[1] == 'starting' and today < boundary):
                continue
            period = (dates[1], boundary.isoformat())
            qualifier = qualifier[:dates.start()].strip()
        storage = qualifier == '/ 1,000,000 tokens per hour (storage price)'
        dimension = ''
        if storage:
            dimension = 'storage'
        elif qualifier in ('(text / image / video)', '(text, image, video)', '(text)'):
            dimension = 'text'
        elif qualifier == '(audio)':
            dimension = 'audio'
        elif qualifier:
            context = re.fullmatch(r',\s*prompts\s*(<=|≤|>)\s*(\d+)k(?: tokens)?', qualifier, re.I)
            if not context:
                raise ValueError('Unknown price qualifier: ' + qualifier)
            dimension = ('≤' if context[1] in ('<=', '≤') else '>') + ' ' + context[2] + 'K'
        result.append((dimension, price, period))
    return result


def parse_google(html, today=None):
    today = today or datetime.now(timezone.utc).date()
    models = {}
    seen = set()
    for block in re.split(r'<h2\b[^>]*>', html, flags=re.I)[1:]:
        code = re.search(r'<code\b[^>]*>\s*(gemini-[\w.-]+)\s*</code>', block, re.I)
        if not code:
            continue
        mid = code[1]
        if mid in seen:
            raise ValueError('Duplicate Google model section: ' + mid)
        seen.add(mid)
        sections = re.split(r'<h3\b[^>]*>', block, flags=re.I)[1:]
        standard = [s for s in sections if text(s.split('</h3>', 1)[0]) == 'Standard']
        if len(standard) != 1:
            continue
        table = re.search(r'<table\b[^>]*>(.*?)</table>', standard[0], re.S | re.I)
        if not table:
            continue
        try:
            rows = re.findall(r'<tr\b[^>]*>(.*?)</tr>', table[1], re.S | re.I)
            headers = [text(c) for c in re.findall(r'<th\b[^>]*>(.*?)</th>', rows[0], re.S | re.I)]
            paid = [i for i, h in enumerate(headers) if h == 'Paid Tier, per 1M tokens in USD']
            if len(paid) != 1:
                continue
            fields = {}
            for row in rows[1:]:
                cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)
                if not cells:
                    continue
                title = text(cells[0])
                key = ('input' if title in ('Input price', 'Input price (text, image, video)') else
                       'output' if title in ('Output price', 'Output price (including thinking tokens)') else
                       'read' if title == 'Context caching price' else None)
                if key:
                    if key in fields or len(cells) != len(headers):
                        raise ValueError('Ambiguous row')
                    fields[key] = amounts(cells[paid[0]], today)
            if set(fields) != {'input', 'output', 'read'}:
                continue
            dimensions = {d for d, _, _ in fields['input'] if d != 'audio'}
            if not dimensions or ('storage' in dimensions):
                continue
            rates = []
            for dimension in sorted(dimensions, key=lambda d: (not d.startswith('≤'), d)):
                rate = {'write': None}
                periods = set()
                for key, items in fields.items():
                    candidates = [(v, p) for d, v, p in items if d == dimension or d == '']
                    if key == 'read' and not items:
                        rate[key] = None
                        continue
                    if len(candidates) != 1:
                        raise ValueError('Ambiguous or missing tier')
                    rate[key], period = candidates[0]
                    if period:
                        periods.add(period)
                stores = [(v, p) for d, v, p in fields['read'] if d == 'storage']
                if len(stores) > 1:
                    raise ValueError('Ambiguous storage')
                rate['storage'] = stores[0][0] if stores else None
                if stores and stores[0][1]:
                    periods.add(stores[0][1])
                if len(periods) > 1:
                    raise ValueError('Mixed effective dates')
                label = 'Standard · 文本' if dimension == 'text' else '提示词 ' + dimension if dimension else 'Standard'
                if periods:
                    kind, boundary = next(iter(periods))
                    label = ('Standard · ' + boundary[:4] + ' 年内' if not dimension and kind == 'through' and boundary.endswith('-12-31')
                             else label + ' · ' + ('截至 ' if kind == 'through' else '自 ') + boundary)
                rate['label'] = label
                rates.append(rate)
            model = {'id': mid, 'name': mid, 'provider': 'Google', 'currency': 'USD', 'rates': rates,
                     'notes': ['Google Standard paid tier; storage per million tokens per hour.']}
            models[mid] = model
        except (ValueError, IndexError):
            # Unsupported modalities/conditions must never become guessed prices.
            continue
    return list(models.values())

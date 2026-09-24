import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from fetch_prices import fetch, parse_anthropic


class SourceTests(unittest.TestCase):
    def table(self, columns, values):
        return '<table><tr>' + ''.join('<th>' + c + '</th>' for c in columns) + '</tr><tr>' + ''.join('<td>' + v + '</td>' for v in values) + '</tr></table>'

    def test_anthropic_current_columns_and_description(self):
        html = self.table(
            ['Name', 'Input', 'Output', '5m writes', '1h writes', 'Hits and refreshes'],
            ['Claude Sonnet 5 <span>Description</span>', '$2 / MTok', '$10 / MTok', '$2.50 / MTok', '$4 / MTok', '$0.20 / MTok'])
        models = parse_anthropic(html)
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]['rates'], [
            {'label': '缓存保留 5 分钟', 'input': 2, 'output': 10, 'read': .2, 'write': 2.5},
            {'label': '缓存保留 1 小时', 'input': 2, 'output': 10, 'read': .2, 'write': 4}])

    def test_anthropic_reordered_columns(self):
        html = self.table(
            ['Model', 'Input', '5m writes', '1h writes', 'Hits and refreshes', 'Output'],
            ['Claude Opus 5', '$5 / MTok', '$6.25 / MTok', '$10 / MTok', '$0.50 / MTok', '$25 / MTok'])
        self.assertEqual(parse_anthropic(html)[0]['rates'][0]['output'], 25)

    def test_anthropic_section_header_keeps_column_mapping(self):
        html = self.table(
            ['Name', 'Input', 'Output', '5m writes', '1h writes', 'Hits and refreshes'],
            ['Claude Opus 5', '$5 / MTok', '$25 / MTok', '$6.25 / MTok', '$10 / MTok', '$0.50 / MTok'])
        html = html.replace('</tr><tr>', '</tr><tr><th colspan="6">Additional models</th></tr><tr>')
        self.assertEqual(len(parse_anthropic(html)), 1)

    def test_anthropic_unknown_headers_and_ambiguous_prices_rejected(self):
        self.assertEqual(parse_anthropic(self.table(['Model', 'Input', 'Output'], ['Claude Opus 5', '$5', '$25'])), [])
        html = self.table(
            ['Name', 'Input', 'Output', '5m writes', '1h writes', 'Hits and refreshes'],
            ['Claude Sonnet 5', '$2 / MTok or $3 / MTok', '$10 / MTok', '$2.50 / MTok', '$4 / MTok', '$.20 / MTok'])
        self.assertEqual(parse_anthropic(html), [])

    def test_fetch_preserves_cookie_across_redirect(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get('Cookie') == 'session=ok':
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'pricing')
                else:
                    self.send_response(302)
                    self.send_header('Set-Cookie', 'session=ok; Path=/')
                    self.send_header('Location', '/pricing')
                    self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertEqual(fetch(f'http://127.0.0.1:{server.server_port}/pricing', retries=0), (200, 'pricing'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

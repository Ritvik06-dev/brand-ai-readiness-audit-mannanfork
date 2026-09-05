#!/usr/bin/env python3
"""Fixture server - stdlib http.server serving declarative single-condition
scenarios for the fixture suite (Phase 5, GAMEPLAN 8 / INDEPENDENT_REVIEW 8.4).

A scenario is a dict:
  {
    "name": str,
    "site_type": str,                 # passed to the collector
    "robots": {"status": 200|404|503, "body": str},
    "pages": {path: {"status": int, "headers": {k: v}, "body": str}},
    "missing_path": {"status": int, "body": str},   # unknown paths (soft-404 tests)
    "ua_rules": {token_substring: {"status": int, "headers": {...}}},  # WAF differential
    "sitemap_body": str,              # served at /sitemap.xml (lastmod scenarios)
  }

start(scenario) binds 127.0.0.1 on an ephemeral port and returns (server, url).
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_handler(scenario):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # silence
            pass

        def _resolve(self):
            path = self.path.split("?")[0]
            ua = self.headers.get("User-Agent", "") or ""
            for token, rule in (scenario.get("ua_rules") or {}).items():
                if token.lower() in ua.lower():
                    return (rule["status"], rule.get("headers", {}),
                            rule.get("body", "<html><body>challenge</body></html>"))
            if path == "/robots.txt":
                r = scenario["robots"]
                return (r["status"], {"Content-Type": "text/plain"}, r["body"])
            if path == "/sitemap.xml" and scenario.get("sitemap_body"):
                host = self.headers.get("Host", "127.0.0.1")
                return (200, {"Content-Type": "application/xml"},
                        scenario["sitemap_body"].replace("{HOST}", host))
            page = scenario["pages"].get(path)
            if page:
                return (page["status"], page.get("headers", {}), page["body"])
            miss = scenario["missing_path"] or {"status": 404, "body": "<html><body>404</body></html>"}
            return (miss["status"], {"Content-Type": "text/html"}, miss["body"])

        def _serve(self, include_body):
            status, headers, body = self._resolve()
            body_bytes = body.encode("utf-8")
            self.send_response(status)
            headers = dict(headers)
            headers.setdefault("Content-Type", "text/html; charset=utf-8")
            headers["Content-Length"] = str(len(body_bytes) if include_body else 0)
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            if include_body and self.command != "HEAD":
                self.wfile.write(body_bytes)

        def do_GET(self):
            self._serve(True)

        def do_HEAD(self):
            self._serve(False)

    return Handler


def start(scenario):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(scenario))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, "http://127.0.0.1:%d/" % server.server_address[1]


def stop(server):
    server.shutdown()
    server.server_close()

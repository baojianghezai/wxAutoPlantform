# -*- coding: utf-8 -*-
"""临时 mock n8n waitUrl 接收器：记录 POST 到 mock_received.jsonl。验证后可删。"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode("utf-8", "replace")
        with open("server/mock_received.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"path": self.path, "body": body}, ensure_ascii=False) + "\n")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"code":0}')

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 9000), H).serve_forever()

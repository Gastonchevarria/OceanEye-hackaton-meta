#!/usr/bin/env python3
"""
Pure Static Read-Only File Server for sentinel.oceaneye-ai.com (docs/ bundle only).
Zero backend APIs, zero environment file loading, zero OpenAPI/Swagger endpoints.
"""
import http.server
import os
import socketserver
from pathlib import Path

DOCS_DIR = Path("/home/hermes001/OceanEye-hackaton-meta/docs").resolve()
PORT = 8095


class SafeStaticHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)

    def end_headers(self):
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive, nosnippet")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean in ("/app", "/app/", "/app/index.html"):
            return str(DOCS_DIR / "app.html")
        return super().translate_path(path)

    def do_GET(self):
        clean = self.path.split("?", 1)[0]
        if clean == "/robots.txt":
            body = b"User-agent: *\nDisallow: /\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if clean.startswith("/.") or clean.startswith("/api") or clean in ("/docs", "/openapi.json", "/redoc"):
            self.send_error(404, "Not Found")
            return
        return super().do_GET()

    def log_message(self, format, *args):
        return


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    os.chdir(DOCS_DIR)
    with ReusableTCPServer(("127.0.0.1", PORT), SafeStaticHandler) as httpd:
        httpd.serve_forever()

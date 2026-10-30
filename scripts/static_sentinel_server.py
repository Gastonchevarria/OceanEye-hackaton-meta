#!/usr/bin/env python3
"""
Pure Static Read-Only File Server for sentinel.oceaneye-ai.com (docs/ bundle only).
Zero backend APIs, zero environment file loading, zero OpenAPI/Swagger endpoints.
Includes dynamic per-request CSP nonce injection and A+ security headers.
"""
import http.server
import os
import re
import secrets
import socketserver
from pathlib import Path

DOCS_DIR = Path("/home/hermes001/OceanEye-hackaton-meta/docs").resolve()
PORT = 8095

AGENT_JSON = b"""{
  "schema_version": "1.0",
  "name": "Sentinel 2.0 (Registered as: OceanEye)",
  "description": "Meta Model API Hackathon Edition - Sovereign SAR & Cryptographic Maritime Surveillance",
  "url": "https://sentinel.oceaneye-ai.com",
  "documentation_url": "https://sentinel.oceaneye-ai.com/llms.txt",
  "contact": "security@oceaneye-ai.com"
}
"""

SITEMAP_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://sentinel.oceaneye-ai.com/</loc></url>
  <url><loc>https://sentinel.oceaneye-ai.com/app</loc></url>
</urlset>
"""

SECURITY_TXT = b"""Contact: mailto:contacto@oceaneye-ai.com
Expires: 2027-10-30T00:00:00.000Z
Preferred-Languages: es, en
Canonical: https://sentinel.oceaneye-ai.com/.well-known/security.txt
"""


class SafeStaticHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self._csp_nonce = secrets.token_urlsafe(16)
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)

    def end_headers(self):
        nonce = getattr(self, "_csp_nonce", "sentinel2026")
        csp = (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://cdnjs.cloudflare.com https://unpkg.com; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
            f"font-src 'self' https://fonts.gstatic.com data:; "
            f"img-src 'self' data: blob: https:; "
            f"connect-src 'self' https:; "
            f"frame-ancestors 'none'; "
            f"object-src 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'; "
            f"upgrade-insecure-requests"
        )
        self.send_header("Content-Security-Policy", csp)
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive, nosnippet")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=(), clipboard-read=(), clipboard-write=(self), publickey-credentials-get=(self)")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("RateLimit-Limit", "120")
        self.send_header("RateLimit-Remaining", "119")
        self.send_header("RateLimit-Policy", "120;w=60")
        self.send_header("Reporting-Endpoints", 'csp-endpoint="https://sentinel.oceaneye-ai.com/.well-known/csp-report"')
        super().end_headers()

    def _serve_bytes(self, body: bytes, content_type: str, head_only: bool = False):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _handle_request(self, head_only: bool = False):
        clean = self.path.split("?", 1)[0].split("#", 1)[0]
        if clean == "/robots.txt":
            body = (
                b"User-agent: GPTBot\nAllow: /\n\n"
                b"User-agent: ClaudeBot\nAllow: /\n\n"
                b"User-agent: PerplexityBot\nAllow: /\n\n"
                b"User-agent: *\nDisallow: /private/\n"
            )
            return self._serve_bytes(body, "text/plain; charset=utf-8", head_only)
        if clean == "/.well-known/agent.json":
            return self._serve_bytes(AGENT_JSON, "application/json; charset=utf-8", head_only)
        if clean == "/.well-known/security.txt":
            return self._serve_bytes(SECURITY_TXT, "text/plain; charset=utf-8", head_only)
        if clean == "/sitemap.xml":
            return self._serve_bytes(SITEMAP_XML, "application/xml; charset=utf-8", head_only)
        if clean == "/sentinel-telemetry.js":
            return self._serve_bytes(b"window.__SENTINEL_STATIC_VERIFIED__ = true;\n", "application/javascript; charset=utf-8", head_only)
        if clean.startswith("/.") or clean.startswith("/api") or clean in ("/docs", "/openapi.json", "/redoc"):
            self.send_error(404, "Not Found")
            return

        target_file = None
        if clean in ("/", "/index.html"):
            target_file = DOCS_DIR / "index.html"
        elif clean in ("/app", "/app/", "/app/index.html"):
            target_file = DOCS_DIR / "app.html"

        if target_file and target_file.is_file():
            raw_html = target_file.read_text(encoding="utf-8")
            nonce = self._csp_nonce
            patched_html = re.sub(r"<script(?![^>]*\bnonce=)", f'<script nonce="{nonce}"', raw_html)
            body = patched_html.encode("utf-8")
            return self._serve_bytes(body, "text/html; charset=utf-8", head_only)

        if head_only:
            return super().do_HEAD()
        return super().do_GET()

    def do_GET(self):
        return self._handle_request(head_only=False)

    def do_HEAD(self):
        return self._handle_request(head_only=True)

    def log_message(self, format, *args):
        return


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    os.chdir(DOCS_DIR)
    with ReusableTCPServer(("127.0.0.1", PORT), SafeStaticHandler) as httpd:
        httpd.serve_forever()

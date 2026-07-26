from __future__ import annotations

import argparse
import http.client
import json
import os
import posixpath
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlparse


HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
UNSAFE_ENCODED_PATH_OCTET = re.compile(r"%(?:00|25|2e|2f|5c)", re.IGNORECASE)
MALFORMED_PERCENT_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


class TunnelProxy(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int, upstream_port: int, public_base_file: Path, allowlist_path: Path):
        super().__init__(("127.0.0.1", port), TunnelProxyHandler)
        policy = _load_json(allowlist_path)
        if policy.get("schema") != "pf07.tunnel-route-allowlist.v1":
            raise ValueError("unsupported route allowlist")
        self.upstream_port = upstream_port
        self.public_base_file = public_base_file
        self.public_routes = tuple(policy["public_routes"])
        self.denied_routes = tuple(policy["denied_routes"])
        marker = os.environ.get("PF07_TUNNEL_PROXY_MARKER", "")
        if not re.fullmatch(r"[0-9a-f]{64}", marker):
            raise ValueError("trusted tunnel marker is unavailable")
        self.trusted_marker = marker

    def public_bases(self) -> tuple[str, str]:
        value = _load_json(self.public_base_file)
        public_base = str(value["public_base"]).rstrip("/")
        local_base = str(value["local_base"]).rstrip("/")
        if not public_base.startswith("https://") or not local_base.startswith("http://127.0.0.1:"):
            raise ValueError("invalid tunnel base identity")
        return public_base, local_base

    @staticmethod
    def _matches(path: str, rule: dict[str, Any]) -> bool:
        target = str(rule.get("path", ""))
        kind = rule.get("match")
        if kind == "exact":
            return path == target
        if kind != "prefix" or not target.startswith("/"):
            return False
        if target.endswith("/"):
            return path.startswith(target)
        return path == target or path.startswith(target + "/")

    def canonical_route(self, path: str, query: str = "") -> str | None:
        try:
            query_fields = parse_qsl(query, keep_blank_values=True, max_num_fields=100)
        except ValueError:
            return None
        if any(
            key.casefold() == "rest_route" or key.casefold().startswith("rest_route[")
            for key, _ in query_fields
        ):
            return None
        if not path.startswith("/") or len(path) > 8192:
            return None
        decoded = path
        for _ in range(4):
            if (
                "\x00" in decoded
                or "\\" in decoded
                or MALFORMED_PERCENT_ESCAPE.search(decoded)
                or UNSAFE_ENCODED_PATH_OCTET.search(decoded)
            ):
                return None
            try:
                next_value = unquote(decoded, errors="strict")
            except UnicodeDecodeError:
                return None
            if next_value == decoded:
                break
            decoded = next_value
        else:
            return None
        segments = decoded.split("/")
        if any(segment in {".", ".."} for segment in segments):
            return None
        normalized = posixpath.normpath(decoded)
        if not normalized.startswith("/"):
            return None
        if decoded.endswith("/") and not normalized.endswith("/"):
            normalized += "/"
        matches: list[tuple[int, bool]] = []
        matches.extend((len(str(rule["path"])), True) for rule in self.public_routes if self._matches(normalized, rule))
        matches.extend((len(str(rule["path"])), False) for rule in self.denied_routes if self._matches(normalized, rule))
        if not matches:
            return None
        longest = max(length for length, _ in matches)
        if not all(allowed for length, allowed in matches if length == longest):
            return None
        canonical_path = quote(normalized, safe="/-._~!$&'()*+,;=:@")
        return canonical_path + (f"?{query}" if query else "")

    def route_allowed(self, path: str, query: str = "") -> bool:
        return self.canonical_route(path, query) is not None


class TunnelProxyHandler(BaseHTTPRequestHandler):
    server: TunnelProxy
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _deny(self) -> None:
        payload = b"PF07 tunnel route not found.\n"
        self.send_response(HTTPStatus.NOT_FOUND)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _proxy(self) -> None:
        parsed = urlparse(self.path)
        upstream_target = self.server.canonical_route(parsed.path, parsed.query)
        if upstream_target is None:
            self._deny()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        if length < 0 or length > 32 * 1024 * 1024:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        body = self.rfile.read(length) if length else None
        public_base, local_base = self.server.public_bases()
        public_host = urlparse(public_base).netloc
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP | {"host", "content-length", "accept-encoding"}
            and key.lower() not in {"forwarded", "x-real-ip", "x-oddroom-private-admin"}
            and not key.lower().startswith("x-forwarded-")
            and not key.lower().startswith("x-pf07-")
        }
        headers.update(
            {
                "Host": f"127.0.0.1:{self.server.upstream_port}",
                "Accept-Encoding": "identity",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": public_host,
                "X-PF07-Tunnel-Policy": "store-and-protected-admin-only",
                "X-PF07-Trusted-Proxy": self.server.trusted_marker,
            }
        )
        upstream = http.client.HTTPConnection("127.0.0.1", self.server.upstream_port, timeout=60)
        try:
            upstream.request(self.command, upstream_target, body=body, headers=headers)
            response = upstream.getresponse()
            payload = response.read()
            content_type = response.getheader("Content-Type", "")
            if any(token in content_type.lower() for token in ("text/", "json", "javascript", "xml")):
                local_https = "https://" + urlparse(local_base).netloc
                for source, destination in (
                    (local_base, public_base),
                    (local_https, public_base),
                    (quote(local_base, safe=""), quote(public_base, safe="")),
                    (quote(local_https, safe=""), quote(public_base, safe="")),
                ):
                    payload = payload.replace(source.encode("utf-8"), destination.encode("utf-8"))
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                lower = key.lower()
                if lower in HOP_BY_HOP | {"content-length", "content-encoding"}:
                    continue
                if lower == "location":
                    value = value.replace(local_base, public_base).replace(
                        "https://" + urlparse(local_base).netloc,
                        public_base,
                    )
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except (ConnectionError, TimeoutError, OSError, http.client.HTTPException):
            self.send_error(HTTPStatus.BAD_GATEWAY, "PF07 local storefront unavailable")
        finally:
            upstream.close()

    do_GET = _proxy
    do_HEAD = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_PATCH = _proxy
    do_DELETE = _proxy
    do_OPTIONS = _proxy


def main() -> int:
    parser = argparse.ArgumentParser(description="PF07 allowlisted tunnel reverse proxy")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--upstream-port", type=int, required=True)
    parser.add_argument("--public-base-file", type=Path, required=True)
    parser.add_argument("--route-allowlist", type=Path, required=True)
    args = parser.parse_args()
    server = TunnelProxy(args.port, args.upstream_port, args.public_base_file, args.route_allowlist)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

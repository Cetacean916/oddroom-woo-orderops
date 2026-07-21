from __future__ import annotations

import argparse
import hmac
import json
import secrets
import socket
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .core import (
    LauncherError,
    backup,
    configure_connected,
    controlled_update,
    credentials,
    diagnostics,
    export_evidence,
    package_root,
    preflight,
    recover,
    reset_demo,
    restore,
    restart,
    selected_locale,
    set_demo_scenario,
    set_locale,
    set_mode,
    start,
    status,
    stop,
    tunnel_off,
    tunnel_on,
    tunnel_status,
    uninstall,
)


class HubServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], token: str):
        super().__init__(address, HubHandler)
        self.session_token = token
        self.ui_root = package_root() / "launcher" / "ui"


class HubHandler(BaseHTTPRequestHandler):
    server: HubServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _headers(self, status_code: int, content_type: str, length: int) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        self.end_headers()

    def _bytes(self, value: bytes, content_type: str, status_code: int = 200) -> None:
        self._headers(status_code, content_type, len(value))
        self.wfile.write(value)

    def _json(self, value: Any, status_code: int = 200) -> None:
        payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self._bytes(payload, "application/json; charset=utf-8", status_code)

    def _authorized(self) -> bool:
        provided = self.headers.get("X-PF07-Hub-Token", "")
        return bool(provided) and hmac.compare_digest(provided, self.server.session_token)

    def _request_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise LauncherError("Invalid request length.") from error
        if length < 0 or length > 4096:
            raise LauncherError("Request body is too large.")
        if length == 0:
            return {}
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LauncherError("Request body must be valid JSON.") from error
        if not isinstance(value, dict):
            raise LauncherError("Request body must be a JSON object.")
        return value

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            suffix = "en" if selected_locale() == "en_US" else "ko"
            html = (self.server.ui_root / f"index.{suffix}.html").read_text(encoding="utf-8")
            html = html.replace("__PF07_SESSION_TOKEN__", self.server.session_token)
            self._bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/app.css":
            self._bytes((self.server.ui_root / "app.css").read_bytes(), "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._bytes((self.server.ui_root / "app.js").read_bytes(), "text/javascript; charset=utf-8")
            return
        if path == "/fonts/PretendardVariable.woff2":
            self._bytes((self.server.ui_root / "fonts" / "PretendardVariable.woff2").read_bytes(), "font/woff2")
            return
        if path == "/brand-symbol.svg":
            symbol = package_root() / "payload" / "oddroom-orderops" / "assets" / "images" / "brand" / "symbol.svg"
            self._bytes(symbol.read_bytes(), "image/svg+xml")
            return
        if path == "/api/status":
            self._json(status())
            return
        if path == "/api/preflight":
            self._json(preflight())
            return
        if path == "/api/diagnostics":
            if not self._authorized():
                self._json({"error": "hub session authorization required"}, HTTPStatus.FORBIDDEN)
                return
            self._json(diagnostics())
            return
        if path == "/api/tunnel-status":
            if not self._authorized():
                self._json({"error": "hub session authorization required"}, HTTPStatus.FORBIDDEN)
                return
            self._json(tunnel_status())
            return
        if path == "/api/credentials":
            if not self._authorized():
                self._json({"error": "hub session authorization required"}, HTTPStatus.FORBIDDEN)
                return
            self._json(credentials())
            return
        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if not self._authorized():
            self._json({"error": "hub session authorization required"}, HTTPStatus.FORBIDDEN)
            return
        path = urlparse(self.path).path
        try:
            if path == "/api/start":
                self._json(start())
                return
            if path == "/api/stop":
                self._json(stop())
                return
            if path == "/api/restart":
                self._json(restart())
                return
            if path == "/api/recover":
                self._json(recover())
                return
            if path == "/api/open-prerequisite":
                self._json(preflight(open_installer=True))
                return
            if path == "/api/evidence-export":
                self._json(export_evidence())
                return
            if path == "/api/backup":
                body = self._request_json()
                self._json(backup(None, str(body.get("passphrase", ""))))
                return
            if path == "/api/restore":
                body = self._request_json()
                self._json(
                    restore(
                        str(body.get("archive", "")),
                        str(body.get("passphrase", "")),
                        str(body.get("confirmation", "")),
                    )
                )
                return
            if path == "/api/update":
                body = self._request_json()
                self._json(
                    controlled_update(
                        str(body.get("predecessor", "")),
                        str(body.get("confirmation", "")),
                    )
                )
                return
            if path == "/api/tunnel-on":
                body = self._request_json()
                self._json(
                    tunnel_on(
                        str(body.get("confirmation", "")),
                        str(body.get("config", "")) or None,
                        str(body.get("provider", "cloudflared")),
                        str(body.get("executable", "")) or None,
                    )
                )
                return
            if path == "/api/tunnel-off":
                body = self._request_json()
                self._json(tunnel_off(str(body.get("confirmation", ""))))
                return
            if path == "/api/uninstall":
                body = self._request_json()
                self._json(
                    uninstall(
                        str(body.get("confirmation", "")),
                        str(body.get("data_choice", "")),
                    )
                )
                return
            if path == "/api/locale":
                body = self._request_json()
                self._json(set_locale(str(body.get("locale", ""))))
                return
            if path == "/api/mode":
                body = self._request_json()
                self._json(set_mode(str(body.get("mode", ""))))
                return
            if path == "/api/connected-setup":
                body = self._request_json()
                self._json(configure_connected({key: str(value) for key, value in body.items()}))
                return
            if path == "/api/scenario":
                body = self._request_json()
                self._json(set_demo_scenario(str(body.get("scenario", ""))))
                return
            if path == "/api/reset":
                body = self._request_json()
                self._json(reset_demo(str(body.get("confirmation", ""))))
                return
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except LauncherError as error:
            self._json({"error": str(error)}, HTTPStatus.CONFLICT)
        except Exception as error:
            self._json({"error": f"Unexpected launcher failure: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _select_hub_port(requested: int | None) -> int:
    if requested is not None:
        if not 1024 <= requested <= 65535:
            raise LauncherError("Hub port must be between 1024 and 65535.")
        if not _port_available(requested):
            raise LauncherError(f"Hub port {requested} is already in use.")
        return requested
    for port in range(19070, 19080):
        if _port_available(port):
            return port
    raise LauncherError("No free loopback port was found for the launch hub.")


def main() -> int:
    parser = argparse.ArgumentParser(prog="pf07-hub", description="OFFSET OrderOps graphical launch hub")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        port = _select_hub_port(args.port)
        server = HubServer(("127.0.0.1", port), secrets.token_urlsafe(32))
        url = f"http://127.0.0.1:{port}/"
        print(f"PF07_HUB_URL={url}", flush=True)
        if not args.no_browser:
            threading.Timer(0.35, lambda: webbrowser.open(url, new=2)).start()
        server.serve_forever(poll_interval=0.25)
        return 0
    except KeyboardInterrupt:
        return 0
    except (LauncherError, OSError) as error:
        print(f"PF07 hub error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

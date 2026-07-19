"""Authenticated localhost bridge from NanoClaw's container to the Windows CLI."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTAINER_ROOT = "/workspace/extra/pe-scraper"
ALLOWED_COMMANDS = {
    "ask",
    "discover",
    "doctor",
    "export",
    "heartbeat",
    "init-db",
    "research",
    "reset-stale",
    "run",
    "run-firm",
    "status",
}
MAX_BODY_BYTES = 64 * 1024


def _translate_path(value: str) -> str:
    if value == CONTAINER_ROOT:
        return str(PROJECT_ROOT)
    prefix = f"{CONTAINER_ROOT}/"
    if value.startswith(prefix):
        relative = PurePosixPath(value.removeprefix(prefix))
        return str(PROJECT_ROOT.joinpath(*relative.parts))
    return value


class BridgeHandler(BaseHTTPRequestHandler):
    server: "BridgeServer"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path != "/healthz":
            self._send_json(404, {"error": "not found"})
            return
        self._send_json(200, {"status": "ok"})

    def do_POST(self) -> None:
        if self.path != "/run":
            self._send_json(404, {"error": "not found"})
            return

        supplied = self.headers.get("x-pe-scraper-token", "")
        if not hmac.compare_digest(supplied, self.server.token):
            self._send_json(401, {"error": "unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_BYTES:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(length))
            args = payload.get("args")
            if not isinstance(args, list) or not args or len(args) > 64:
                raise ValueError("args must be a non-empty list")
            if not all(isinstance(arg, str) and len(arg) <= 4096 and "\0" not in arg for arg in args):
                raise ValueError("invalid argument")
            if args[0] not in ALLOWED_COMMANDS:
                raise ValueError(f"unsupported command: {args[0]}")
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": str(exc)})
            return

        translated = [_translate_path(arg) for arg in args]
        command = [
            sys.executable,
            "-c",
            "from pescraper.cli import app; app()",
            *translated,
        ]
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"

        try:
            completed = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=4 * 60 * 60,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self._send_json(
                504,
                {
                    "returncode": 124,
                    "stdout": exc.stdout or "",
                    "stderr": exc.stderr or "",
                    "error": "command timed out",
                },
            )
            return

        self._send_json(
            200,
            {
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], token: str) -> None:
        super().__init__(address, BridgeHandler)
        self.token = token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--token-file", required=True, type=Path)
    args = parser.parse_args()

    token = args.token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise SystemExit("bridge token is missing or too short")

    BridgeServer((args.host, args.port), token).serve_forever()


if __name__ == "__main__":
    main()

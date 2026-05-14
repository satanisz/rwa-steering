from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .calculator import RwaCalculator, dumps_json, load_core_csv


class RwaRequestHandler(BaseHTTPRequestHandler):
    calculator: RwaCalculator

    server_version = "RestrictedRwaBackend/1.0"

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler.
        path = urlparse(self.path).path
        if path in {"/", "/health"}:
            self._send_json(
                {
                    "status": "ok",
                    "service": "restricted-rwa-backend",
                    "endpoints": [
                        "GET /health",
                        "GET /reference/nccr",
                        "GET /countries",
                        "POST /calculate",
                    ],
                }
            )
            return
        if path == "/reference/nccr":
            self._send_json(self.calculator.nccr_mapping)
            return
        if path == "/countries":
            self._send_json(self.calculator.countries)
            return
        self._send_json({"error": f"Unknown endpoint {path}"}, status=404)

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler.
        path = urlparse(self.path).path
        if path != "/calculate":
            self._send_json({"error": f"Unknown endpoint {path}"}, status=404)
            return

        try:
            payload = self._read_json()
            rows = payload.get("core_info")
            if not isinstance(rows, list):
                raise ValueError("JSON body must contain core_info as a list of records")
            include_trace = bool(payload.get("include_trace", False))
            projection_date = payload.get("projection_date")
            result = self.calculator.calculate_batch(
                rows,
                include_trace=include_trace,
                projection_date=projection_date,
            )
            self._send_json(result)
        except Exception as exc:  # noqa: BLE001 - transport layer returns JSON errors.
            self._send_json({"error": str(exc)}, status=400)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = dumps_json(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_server(
    host: str,
    port: int,
    nccr_mapping_path: str | Path,
    country_info_path: str | Path,
) -> ThreadingHTTPServer:
    calculator = RwaCalculator.from_files(nccr_mapping_path, country_info_path)

    class Handler(RwaRequestHandler):
        pass

    Handler.calculator = calculator
    return ThreadingHTTPServer((host, port), Handler)


def calculate_file(
    core_path: str | Path,
    country_path: str | Path,
    nccr_path: str | Path,
    include_trace: bool = False,
    projection_date: str | None = None,
) -> dict[str, Any]:
    calculator = RwaCalculator.from_files(nccr_path, country_path)
    return calculator.calculate_batch(
        load_core_csv(core_path),
        include_trace=include_trace,
        projection_date=projection_date,
    )

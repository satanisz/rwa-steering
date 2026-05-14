from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .calculator import RwaCalculator, dumps_json, load_core_csv


class RwaRequestHandler(BaseHTTPRequestHandler):
    """Restricted stdlib HTTP adapter around `RwaCalculator`.

    This exists for environments where FastAPI/ASGI dependencies are not
    available. New integrations should prefer the FastAPI app, but this handler
    remains useful for minimal runtime and compatibility checks.
    """

    calculator: RwaCalculator

    server_version = "RestrictedRwaBackend/1.0"

    def do_GET(self) -> None:
        """Handle health and reference-data GET endpoints."""
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

    def do_POST(self) -> None:
        """Handle JSON batch calculation requests."""
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
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)

    def log_message(self, format: str, *args: Any) -> None:
        """Silence default stdlib request logging for cleaner CLI output."""
        return

    def _read_json(self) -> dict[str, Any]:
        """Read and validate the request body as a JSON object."""
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _send_json(self, payload: Any, status: int = 200) -> None:
        """Write a JSON response with stable calculator serialisation."""
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
    """Build a restricted stdlib HTTP server with a preloaded calculator."""
    calculator = RwaCalculator.from_files(nccr_mapping_path, country_info_path)

    class Handler(RwaRequestHandler):
        """Request handler bound to the calculator created for this server."""

    Handler.calculator = calculator
    return ThreadingHTTPServer((host, port), Handler)


def calculate_file(
    core_path: str | Path,
    country_path: str | Path,
    nccr_path: str | Path,
    include_trace: bool = False,
    projection_date: str | None = None,
) -> dict[str, Any]:
    """Calculate RWA for CSV file inputs in restricted CLI mode."""
    calculator = RwaCalculator.from_files(nccr_path, country_path)
    return calculator.calculate_batch(
        load_core_csv(core_path),
        include_trace=include_trace,
        projection_date=projection_date,
    )

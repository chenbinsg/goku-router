"""Structured (JSON) logging setup.

Converts uvicorn's access/error logs and app logs into single-line JSON objects so
log collectors (k8s/Fluent Bit/Cloud Logging) can parse one record per line —
matching the `llm_trace` records emitted by the provider layer.

Enabled by default; set LOG_FORMAT=text to keep uvicorn's plain-text logs (handy
for local dev readability).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime


def _ts(created: float) -> str:
    return datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class RoutineAccessFilter(logging.Filter):
    """Drop routine probe/UI reads before formatting; retain unexpected results."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access" or not isinstance(record.args, tuple) or len(record.args) != 5:
            return True
        _, method, full_path, _, status = record.args
        if method not in ("GET", "HEAD") or not isinstance(full_path, str):
            return True
        try:
            status = int(status)
        except (TypeError, ValueError):
            return True
        path = full_path.partition("?")[0]
        if path == "/health":
            return status != 200
        if path == "/":
            return status != 307  # RedirectResponse's expected /console/ redirect
        if path in ("/console", "/console/") or path.startswith("/console/assets/"):
            return not (200 <= status < 300 or status == 304)
        return True


class JsonLogFormatter(logging.Formatter):
    """Render each LogRecord as one JSON line.

    uvicorn.access records carry their fields in record.args as
    (client_addr, method, full_path, http_version, status_code) — we expand those
    into structured keys instead of a pre-formatted string.
    """

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, object] = {
            "ts": _ts(record.created),
            "level": record.levelname,
            "logger": record.name,
        }

        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5:
            client_addr, method, full_path, http_version, status_code = record.args
            out.update({
                "log": "access",
                "client": client_addr,
                "method": method,
                "path": full_path,
                "http_version": http_version,
                "status": status_code,
            })
        else:
            out["msg"] = record.getMessage()

        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            out["stack"] = self.formatStack(record.stack_info)

        return json.dumps(out, ensure_ascii=False, default=str)


def setup_logging() -> None:
    """Install the JSON formatter on the root + uvicorn loggers.

    Called at import time of app.main (after uvicorn's own configure_logging), so it
    overrides uvicorn's defaults and covers access logs, error logs and tracebacks.
    Access filtering applies to both JSON and text logging.
    """
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RoutineAccessFilter) for f in access_logger.filters):
        access_logger.addFilter(RoutineAccessFilter())

    if os.getenv("LOG_FORMAT", "json").lower() != "json":
        return

    handler = logging.StreamHandler()  # stdout/stderr; one record per line
    handler.setFormatter(JsonLogFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    # uvicorn keeps its own handlers + propagate=False; replace them so its lines
    # also go through the JSON formatter exactly once.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False

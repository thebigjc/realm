from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from prometheus_client import Counter, Gauge, Histogram, CONTENT_TYPE_LATEST
from prometheus_client import generate_latest
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn

log = logging.getLogger(__name__)


# Type alias for PEP 3333 start_response
StartResponse = Callable[..., Callable[[bytes], Any]]


# Metrics definitions
blizzard_request_seconds: Histogram = Histogram(
    "blizzard_request_seconds",
    "Latency of Blizzard API requests",
    labelnames=("endpoint", "method", "status", "outcome"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
blizzard_requests_total: Counter = Counter(
    "blizzard_requests_total",
    "Total Blizzard API requests",
    labelnames=("endpoint", "method", "status", "outcome"),
)

# Discord metrics
discord_connected = Gauge(
    "discord_connected",
    "Whether the Discord bot is connected (1) or not (0)",
)
discord_messages_sent_total = Counter(
    "discord_messages_sent_total",
    "Total number of messages sent to Discord",
    labelnames=("channel",),
)
discord_send_seconds = Histogram(
    "discord_send_seconds",
    "Latency to send a message to Discord",
    labelnames=("channel",),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
discord_command_invocations_total = Counter(
    "discord_command_invocations_total",
    "Number of slash command invocations",
    labelnames=("command", "status"),
)

discord_ws_latency_seconds = Gauge(
    "discord_ws_latency_seconds",
    "Discord gateway websocket latency in seconds",
)

discord_message_send_errors_total = Counter(
    "discord_message_send_errors_total",
    "Number of Discord message send failures",
    labelnames=("channel",),
)

# Realm status: per realm name/slug up(1)/down(0)
realm_up = Gauge(
    "realm_up",
    "Realm availability by realm name/slug",
    labelnames=("realm",),
)


def update_realm_gauges(status_by_realm: dict[str, bool]) -> None:
    for name, is_up in status_by_realm.items():
        try:
            realm_up.labels(realm=name).set(1.0 if is_up else 0.0)
        except Exception:
            log.exception("Failed to update realm gauge for %s", name)


# --- Health & readiness tracking -------------------------------------------------
@dataclass
class _HealthState:
    start_time: float
    last_poll_success: float | None
    last_poll_error: float | None
    consecutive_failures: int
    last_discord_connect: float | None
    last_discord_disconnect: float | None

    def as_dict(self) -> dict[str, Any]:  # for JSON-ish response
        now = time.time()
        return {
            "uptime_seconds": int(now - self.start_time),
            "last_poll_success_age": None if self.last_poll_success is None else int(now - self.last_poll_success),
            "last_poll_error_age": None if self.last_poll_error is None else int(now - self.last_poll_error),
            "consecutive_failures": self.consecutive_failures,
            "last_discord_connect_age": None if self.last_discord_connect is None else int(now - self.last_discord_connect),
            "last_discord_disconnect_age": None if self.last_discord_disconnect is None else int(now - self.last_discord_disconnect),
        }


_health = _HealthState(
    start_time=time.time(),
    last_poll_success=None,
    last_poll_error=None,
    consecutive_failures=0,
    last_discord_connect=None,
    last_discord_disconnect=None,
)

# Tunables (could be env-driven later):
_MAX_CONSECUTIVE_FAILURES_FOR_READY = 5  # beyond this, report unhealthy
_MAX_POLL_STALENESS_SECONDS = 900  # if no success in last 15m, unhealthy


def note_poll_success() -> None:
    _health.last_poll_success = time.time()
    _health.consecutive_failures = 0


def note_poll_error() -> None:
    _health.last_poll_error = time.time()
    _health.consecutive_failures += 1


def note_discord_connect() -> None:
    _health.last_discord_connect = time.time()


def note_discord_disconnect() -> None:
    _health.last_discord_disconnect = time.time()


def health_status() -> tuple[bool, dict[str, Any]]:
    """Return (is_healthy, details). Conservative readiness logic to avoid flapping.

    Healthy if:
      - At least one successful poll has occurred
      - Last success not too stale
      - Consecutive failures below threshold
    Discord connectivity is informational; bot can still run degraded if disconnected.
    """
    now = time.time()
    details = _health.as_dict()
    # No successful poll yet: not ready but liveness OK
    if _health.last_poll_success is None:
        return False, {"status": "starting", **details}
    # Staleness check
    if (now - _health.last_poll_success) > _MAX_POLL_STALENESS_SECONDS:
        return False, {"status": "stale", **details}
    if _health.consecutive_failures > _MAX_CONSECUTIVE_FAILURES_FOR_READY:
        return False, {"status": "failing", **details}
    return True, {"status": "ok", **details}


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def _metrics_app(environ: Mapping[str, Any], start_response: StartResponse) -> list[bytes]:
    """Minimal WSGI app that serves Prometheus metrics and a /health endpoint.

    /metrics -> Prometheus exposition
    /health  -> JSON-ish health summary (text/plain) with HTTP 200 or 503
    """
    path = environ.get("PATH_INFO", "")
    if path == "/metrics":
        try:
            data = generate_latest()
            start_response("200 OK", [("Content-Type", CONTENT_TYPE_LATEST)])
            return [data]
        except Exception as e:
            log.exception("Error generating metrics: %s", e)
            start_response("500 Internal Server Error", [("Content-Type", "text/plain")])
            return [b"error"]
    elif path == "/health":
        try:
            ok, info = health_status()
            body = ("healthy" if ok else "unhealthy") + "\n" + " ".join(f"{k}={v}" for k, v in info.items())
            code = "200 OK" if ok else "503 Service Unavailable"
            start_response(code, [("Content-Type", "text/plain")])
            return [body.encode("utf-8")]
        except Exception:
            log.exception("Error building health response")
            start_response("500 Internal Server Error", [("Content-Type", "text/plain")])
            return [b"error"]
    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"not found"]


def start_metrics_server(host: str = "0.0.0.0", port: int = 9090) -> None:
    """Start a simple WSGI HTTP server exposing /metrics in a background thread."""
    def _run() -> None:
        try:
            with make_server(host, port, _metrics_app, server_class=_ThreadingWSGIServer) as httpd:
                log.info("Metrics server listening on %s:%s", host, port)
                httpd.serve_forever()
        except Exception:
            log.exception("Metrics server failed")

    t = threading.Thread(target=_run, name="metrics-server", daemon=True)
    t.start()

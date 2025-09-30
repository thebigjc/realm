from __future__ import annotations

import os
import logging
from typing import Optional, Protocol

try:
    import sentry_sdk  # type: ignore
except Exception:  # pragma: no cover - if not installed
    sentry_sdk = None  # type: ignore

log = logging.getLogger(__name__)


def init_sentry(*, dsn: Optional[str] = None, environment: Optional[str] = None) -> None:
    """Initialize Sentry if a DSN is provided.

    Reads DSN from argument or SENTRY_DSN env var. Optional configuration:
      - SENTRY_TRACES_SAMPLE_RATE (float, default 0.0)
      - SENTRY_PROFILES_SAMPLE_RATE (float, default 0.0)
      - SENTRY_ENVIRONMENT overrides `environment` parameter
    """
    if dsn is None:
        dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    if sentry_sdk is None:
        log.warning("SENTRY_DSN provided but sentry-sdk not installed; skipping Sentry init")
        return
    traces_sample_rate = _float_env("SENTRY_TRACES_SAMPLE_RATE", 0.0)
    profiles_sample_rate = _float_env("SENTRY_PROFILES_SAMPLE_RATE", 0.0)
    env = os.getenv("SENTRY_ENVIRONMENT", environment or os.getenv("ENV", "production"))
    release = os.getenv("SENTRY_RELEASE")  # allow manual override
    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=env,
            release=release,
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            # Integrations: httpx & asyncio auto-instrumentation are picked up automatically.
        )
        log.info("Sentry initialized env=%s traces_sample_rate=%s profiles_sample_rate=%s", env, traces_sample_rate, profiles_sample_rate)
    except Exception:
        log.exception("Failed to initialize Sentry")


def _float_env(name: str, default: float) -> float:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return float(v)
    except Exception:
        return default


class _ConfigLike(Protocol):  # minimal structural typing for tagging
    region: str
    locale: str
    poll_interval_seconds: int


def set_sentry_context(config: _ConfigLike) -> None:
    """Attach useful tags to Sentry scope if enabled.

    Accepts Config-like object (duck typed) with region, locale, poll_interval_seconds.
    """
    if sentry_sdk is None:
        return
    try:
        from sentry_sdk import configure_scope  # type: ignore

        with configure_scope() as scope:
            for key in ("region", "locale"):
                if hasattr(config, key):
                    scope.set_tag(key, getattr(config, key))
            if hasattr(config, "poll_interval_seconds"):
                scope.set_tag("poll_interval_seconds", getattr(config, "poll_interval_seconds"))
    except Exception:
        # Never crash the app on Sentry tagging
        log.debug("Failed to set Sentry scope context", exc_info=True)

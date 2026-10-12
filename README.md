# WoW Realm Status Discord Bot

A Discord bot that periodically checks US World of Warcraft realm availability and posts when the number of available realms changes. Built with Python and uv.

## Quick start

1. Set environment variables (see below)
2. Install dependencies with uv
3. Run either the one-shot BNET check or the Discord bot

### Env vars
- `BNET_CLIENT_ID`
- `BNET_CLIENT_SECRET`
- `DISCORD_BOT_TOKEN`
- `DISCORD_CHANNEL_ID` (integer)
- Optional: `REGION` (default `us`), `LOCALE` (`en_US`), `POLL_INTERVAL_SECONDS` (default `300`), `STATE_FILE_PATH` (default `./data/state.json`)
- `MIN_CHANGE_THRESHOLD` (default `10`): Minimum number of realms that must change status before posting to Discord. Filters out minor flaps (1-7 realms going down briefly) while still alerting on maintenance windows (100+ realms). Set to `1` for the old behavior (post on any change).
- Observability (optional):
	- `SENTRY_DSN` (enable Sentry error reporting; store as Fly secret: `flyctl secrets set SENTRY_DSN=...`)
	- `SENTRY_TRACES_SAMPLE_RATE` (float 0.0–1.0, default 0.0; set small value like `0.05` if you want performance tracing)
	- `SENTRY_PROFILES_SAMPLE_RATE` (float 0.0–1.0, default 0.0; enable only if needed—profiling adds overhead)
	- `SENTRY_ENVIRONMENT` (override environment tag, default derived from `ENV` or `production`)
	- `SENTRY_RELEASE` (explicit release identifier; otherwise leave unset)

### Using uv

```bash
# install deps
uv sync

# run tests
uv run pytest -q

# one-shot BNET status (prints, updates state file)
uv run wow-realm-bnet

# run the Discord bot
uv run python -m realm_bot.main
```

## Notes
- First run saves a baseline snapshot and does not post.
- The bot uses the Connected Realm index and per-id details to compute status counts.
- Poll interval defaults to 5 minutes; adjust via `POLL_INTERVAL_SECONDS`.
- A lightweight metrics & health HTTP server runs (if metrics enabled) on `METRICS_HOST:METRICS_PORT` exposing `/metrics` and `/health`.

### Health endpoint

`/health` returns `200 OK` with a short text body when the bot is considered healthy, otherwise `503 Service Unavailable`.

Readiness logic (anti-flap):
1. At least one successful poll must have completed.
2. The last successful poll must be within 15 minutes (staleness threshold).
3. Fewer than 5 consecutive poll failures.

If any condition fails, status becomes `starting`, `stale`, or `failing` and the endpoint returns `503` so an orchestrator can optionally restart. Discord connectivity is informational (a temporary gateway disconnect will not mark the bot unhealthy unless polls also fail/stall).

Sample response body (text/plain):

```
healthy
 status=ok uptime_seconds=732 last_poll_success_age=41 consecutive_failures=0 last_discord_connect_age=60
```

On failure you might see:

```
unhealthy
 status=failing uptime_seconds=910 last_poll_success_age=905 consecutive_failures=6
```

You can point Fly.io HTTP health checks at `/health` instead of `/metrics` to avoid treating a temporarily stalled metrics scrape as a fatal error. Tune thresholds by editing `_MAX_CONSECUTIVE_FAILURES_FOR_READY` or `_MAX_POLL_STALENESS_SECONDS` in `realm_bot/metrics.py` if needed.

### Troubleshooting: DNS failures inside the container
- Try setting explicit DNS servers via compose. Add `DNS1` and optionally `DNS2` to your `.env`:
	- `DNS1=1.1.1.1`, `DNS2=1.0.0.1` (or your NAS/router DNS, e.g., `192.168.1.1`).
- Recreate the container after changing DNS:
	- `docker compose up -d --force-recreate`
- Alternative: use host networking to inherit the NAS DNS directly (uncomment `network_mode: host` in compose). Note this exposes ports directly on the host namespace.
- On Synology, if DNS still fails, check global Docker DNS settings under Container Manager → Settings → Daemon → DNS Server, then restart Docker and the container.

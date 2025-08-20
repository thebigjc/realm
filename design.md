# WoW Realm Status Discord Bot – Design

## Summary
A Python Discord bot that periodically checks US World of Warcraft realm availability and posts to a channel only when the number of available realms changes. It also includes the count of realms in each state on every change.

- "Available" realms = realms whose connected realm status is UP (see Definitions).
- Initial scope: Retail US only. Extendable to other regions/Classic later.
- Runtime: laptop first; later deploy on Fly.io. Package/deps managed with uv.

## Definitions
- Realm: a named realm (e.g., "Illidan"). In the API, realms belong to a connected realm.
- Connected Realm: a group of one or more realms that share a population. Status is reported at the connected-realm level.
- Available: status.type == "UP" for the connected realm. Every member realm of an UP connected realm counts as available.
- States: We’ll report counts per status value observed from the API (at minimum UP and DOWN; may include IN_MAINTENANCE or others). Unknown values get bucketed as OTHER to avoid crashes.

## External APIs

### Authentication
- Flow: OAuth2 client credentials.
- Token endpoint (Non-China regions): `https://oauth.battle.net/token` (global for us/eu/kr/tw). China uses `https://www.battlenet.com.cn/oauth/token`.
- Auth: HTTP Basic with `client_id:client_secret`; form body `grant_type=client_credentials`.
- Scopes: Not required for public WoW Game Data APIs when using client credentials.
- Token reuse: Cache token in-process until `expires_in` and refresh proactively.

### WoW Game Data API (Retail)
- Host (US): `https://us.api.blizzard.com`
- Namespace for dynamic data: `dynamic-us` (send as header `Battlenet-Namespace: dynamic-us` or query param `?namespace=dynamic-us`).
- Locale: `en_US` (as `?locale=en_US`).
- Primary endpoint/approach:
  - Prefer the Connected Realm Search API to minimize per-ID requests:
    - `GET /data/wow/search/connected-realm?namespace=dynamic-us&orderby=id&_page=N&locale=en_US`
    - In practice, search responses generally include `status` and `realms` for connected realms; if they do not in a given region/build, fall back below.
    - Paginate over pages until no results.
  - Alternative (fallback, guaranteed fields):
    - `GET /data/wow/connected-realm/index` (list of IDs), then `GET /data/wow/connected-realm/{id}` for each to obtain `status` and `realms`.
    - If used, perform bounded concurrency and respect rate limits.

### Discord Bot API
- Library: `discord.py` 2.x (async). No privileged intents needed since we’re only sending messages, not reading member/message content.
- Rate limits: We’ll post at most once per poll interval, and only on change, which is safely within Discord limits.

## Behavior
- Poll Battle.net at a configurable interval (default 5 minutes).
- Build counts by mapping connected realm `status.type` to the number of member realms in its `realms` array.
- Compute `available_count = sum(realms) for connected_realms where status.type == "UP"`.
- Compare `available_count` to the last observed value. If changed, post to Discord channel:
  - Message includes: new available count, previous count, and counts per status for context.
- Persist last observed counts locally so restarts do not spam (JSON file on disk). First run with no prior state will not post; it just stores a baseline.

### Example message
```
Realm availability changed
- Available (UP): 237 (was 236)
- DOWN: 3 (was 4)
- IN_MAINTENANCE: 0 (was 0)
Total realms: 240 • 2025-08-09 14:20 UTC
```

## Configuration
Environment variables (works locally and on Fly.io):
- `BNET_CLIENT_ID`: Battle.net client id (required)
- `BNET_CLIENT_SECRET`: Battle.net client secret (required)
- `DISCORD_BOT_TOKEN`: Discord bot token (required)
- `DISCORD_CHANNEL_ID`: Channel ID to post into (required)
- `REGION`: Defaults to `us` (future: `eu`, `kr`, `tw`)
- `LOCALE`: Defaults to `en_US`
- `POLL_INTERVAL_SECONDS`: Defaults to `300`
- `STATE_FILE_PATH`: Defaults to `./data/state.json`

## Architecture
- `config.py`: Load/validate env vars, provide sensible defaults.
- `blizzard_client.py`:
  - Handles OAuth token acquisition/caching.
  - Provides `fetch_connected_realms()` using the Search API with pagination.
  - Structured return: list of { status: "UP"|..., realm_count: int, realms: [realm slugs/names] } at the connected-realm granularity.
- `realm_tracker.py`:
  - Converts connected-realm results into per-realm status counts.
  - Computes `available_count` (UP) and `status_counts` dict.
  - Load/save last snapshot from state file.
  - Diff function that returns whether to post, and a small struct for message rendering.
- `discord_bot.py`:
  - `on_ready` schedules a background task that runs the poll loop.
  - Posts a single message when diff triggers. Includes robust error logging.
  - Graceful shutdown cleanup.
- `main.py`:
  - Entry point wiring config, clients, and bot.

### Data model
- Snapshot JSON stored as:
```json
{
  "available_count": 237,
  "status_counts": {"UP": 237, "DOWN": 3},
  "total": 240,
  "timestamp": "2025-08-09T14:18:00Z"
}
```

## Error Handling & Resilience
- Token errors: Retry with exponential backoff; stop after a bounded number and log.
- HTTP errors >= 500: retry with backoff. 429: respect `Retry-After` if provided.
- Network timeouts: short connect/read timeouts (e.g., 5s/15s), with retries.
- Discord errors/rate limits: rely on discord.py built-in handling; still avoid frequent posts.
- Unexpected status values: map to `OTHER` bucket.
- Persist baseline before posting to avoid spamming on restarts.

## Performance & Efficiency
- Use the Search API with `fields=status,realms` to avoid per-ID fetches.
- Keep a single Async HTTP client with connection pooling (httpx.AsyncClient).
- Poll at a conservative interval (>= 5 minutes) to respect Battle.net rate limits.
- Optional future optimization: store page-level ETags and send `If-None-Match` to skip unchanged pages. If all pages return 304, skip processing entirely.

## Local Development (uv)
- Python 3.12 recommended.
- Dependencies: `discord.py`, `httpx[http2]`, `pydantic`, `python-dotenv` (optional), `tenacity` (optional for retries).
- Run:
  1. Set env vars (see Configuration).
  2. `uv run python -m realm_bot.main`

## Deployment to Fly.io
- Containerize with a slim Python base image. Install uv and resolve deps at build time.
- Provide `fly.toml` with a single process. Set secrets: `BNET_CLIENT_ID`, `BNET_CLIENT_SECRET`, `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`.
- Persistent state: Either ephemeral (no baseline across restarts) or mount a small volume for the state file. If ephemeral, bot won’t post until the first change after each restart.

## Testing
- Unit tests for:
  - Parsing and counting logic with canned API payloads (UP, DOWN, mixed, unknown status).
  - Diff function deciding when to post and creating the correct message body.
- Integration smoke test (manual): invoke `fetch_connected_realms()` and print counts.

## Security & Compliance
- Do not log secrets or full tokens.
- Respect API Terms and rate limits; keep polling moderate.
- Discord bot guidelines: only post in the configured channel, no privileged intents, handle disconnects gracefully.

## Future Enhancements
- Support EU/KR/TW and retail/classic via configurable namespaces (e.g., `dynamic-classic-us`).
- Admin slash commands to query current counts or toggle verbosity.
- Include `has_queue` breakdown (available-but-queued vs available-no-queue) if useful.
- Webhook or slash-command trigger for on-demand checks.
- ETag-based change detection to reduce API calls.
- Metrics export (Prometheus) and alert thresholds.

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

### Troubleshooting: DNS failures inside the container
- Try setting explicit DNS servers via compose. Add `DNS1` and optionally `DNS2` to your `.env`:
	- `DNS1=1.1.1.1`, `DNS2=1.0.0.1` (or your NAS/router DNS, e.g., `192.168.1.1`).
- Recreate the container after changing DNS:
	- `docker compose up -d --force-recreate`
- Alternative: use host networking to inherit the NAS DNS directly (uncomment `network_mode: host` in compose). Note this exposes ports directly on the host namespace.
- On Synology, if DNS still fails, check global Docker DNS settings under Container Manager → Settings → Daemon → DNS Server, then restart Docker and the container.

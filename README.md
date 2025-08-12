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

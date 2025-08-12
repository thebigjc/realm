from __future__ import annotations

import asyncio

from .blizzard_client import BlizzardClient
from .config import Config
from .realm_tracker import StateStore, compute_counts, diff_snapshots, format_message, make_snapshot
from dotenv import load_dotenv


async def run_once() -> int:
    # Load .env from project root if present
    load_dotenv()
    cfg = Config.load(allow_missing_discord=True)
    state = StateStore(cfg.state_file_path)
    client = BlizzardClient(
        region=cfg.region,
        locale=cfg.locale,
        client_id=cfg.bnet_client_id,
        client_secret=cfg.bnet_client_secret,
    )
    try:
        connected_realms = await client.fetch_all_connected_realms()
        available, status_counts, total = compute_counts(connected_realms)
        curr = make_snapshot(available, status_counts, total)
        prev = state.load()
        d = diff_snapshots(prev, curr)

        # Always print current status in a human-friendly way
        print(format_message(d))

        # Update state file unconditionally to set baseline or advance it
        state.save(curr)
        return 0
    finally:
        await client.aclose()


def main() -> None:
    raise SystemExit(asyncio.run(run_once()))

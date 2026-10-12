from __future__ import annotations

import asyncio
from collections import Counter

from dotenv import load_dotenv

from .blizzard_client import BlizzardClient
from .config import Config
from .models import parse_connected_realms


async def run_once() -> int:
    load_dotenv()
    cfg = Config.load(allow_missing_discord=True)
    client = BlizzardClient(
        region=cfg.region,
        locale=cfg.locale,
        client_id=cfg.bnet_client_id,
        client_secret=cfg.bnet_client_secret,
    )
    try:
        connected_realms = await client.fetch_all_connected_realms()
        models = parse_connected_realms(connected_realms)
        counts: Counter[str] = Counter()
        total_realms = 0
        for cr in models:
            for realm in cr.realms:
                category = realm.category_type() or realm.category_label() or "UNKNOWN"
                counts[category] += 1
                total_realms += 1

        if not counts:
            print("No realms returned from API")
            return 1

        print("Realm counts by category:")
        for category in sorted(counts.keys()):
            print(f"- {category}: {counts[category]}")
        print(f"Total realms counted: {total_realms}")
        return 0
    finally:
        await client.aclose()


def main() -> None:
    raise SystemExit(asyncio.run(run_once()))

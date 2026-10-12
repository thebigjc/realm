from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Set, cast

from dotenv import load_dotenv

from .blizzard_client import BlizzardClient
from .config import Config


def _unique_realm_hrefs(connected_realms: Sequence[Dict[str, Any]]) -> List[str]:
    hrefs: List[str] = []
    seen: Set[str] = set()
    for cr in connected_realms:
        realms = cr.get("realms")
        if not isinstance(realms, list):
            continue
        for realm in realms:
            if not isinstance(realm, Mapping):
                continue
            realm_dict = cast(Mapping[str, Any], realm)
            key_obj = realm_dict.get("key")
            href = None
            if isinstance(key_obj, Mapping):
                key_mapping = cast(Mapping[str, Any], key_obj)
                key_href = key_mapping.get("href")
                if isinstance(key_href, str):
                    href = key_href
            if not href and isinstance(realm_dict.get("href"), str):
                href = realm_dict.get("href")
            if isinstance(href, str) and href not in seen:
                seen.add(href)
                hrefs.append(href)
    return hrefs


async def run_once(output: Path, detail_limit: int) -> int:
    load_dotenv()
    cfg = Config.load(allow_missing_discord=True)
    client = BlizzardClient(
        region=cfg.region,
        locale=cfg.locale,
        client_id=cfg.bnet_client_id,
        client_secret=cfg.bnet_client_secret,
    )
    try:
        connected_realms: List[Dict[str, Any]] = await client.fetch_all_connected_realms()
        detail_records: List[Dict[str, Any]] = []

        if detail_limit > 0:
            hrefs = _unique_realm_hrefs(connected_realms)
            for href in hrefs[:detail_limit]:
                try:
                    detail_records.append(await client.fetch_realm_detail_by_href(href))
                except Exception as exc:  # pragma: no cover - best-effort fetch
                    detail_records.append({"href": href, "error": str(exc)})

        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(connected_realms),
            "connected_realms": connected_realms,
            "realm_details": detail_records,
        }

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"Dumped {len(connected_realms)} connected realms to {output}")
        if detail_records:
            print(f"Included {len(detail_records)} realm detail records")
        return 0
    finally:
        await client.aclose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dump raw World of Warcraft realm data")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./data/connected_realms_dump.json"),
        help="Path to write the raw JSON dump",
    )
    parser.add_argument(
        "--realm-details",
        type=int,
        default=0,
        help="Number of individual realm detail documents to fetch (costly)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(run_once(args.output, max(args.realm_details, 0))))

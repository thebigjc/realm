from __future__ import annotations

import asyncio
import logging
import os

from .blizzard_client import BlizzardClient
from .config import Config
from .discord_bot import RealmStatusBot
from .realm_tracker import StateStore
from dotenv import load_dotenv


def setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    
    # Reduce noise from HTTP libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    # Keep discord.py logs at INFO but can be reduced if needed
    # logging.getLogger("discord").setLevel(logging.WARNING)


async def amain():
    setup_logging()
    # Load .env if present
    load_dotenv()
    cfg = Config.load()
    if not cfg.discord_bot_token or (cfg.discord_channel_id is None and cfg.discord_channel_ids is None):
        raise RuntimeError(
            "DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID are required for bot mode. Use the CLI for BNET-only runs."
        )

    blizzard = BlizzardClient(
        region=cfg.region,
        locale=cfg.locale,
        client_id=cfg.bnet_client_id,
        client_secret=cfg.bnet_client_secret,
    )
    state = StateStore(cfg.state_file_path)

    bot = RealmStatusBot(config=cfg, blizzard=blizzard, state=state)
    try:
        await bot.start(cfg.discord_bot_token)
    finally:
        await bot.close()


def main():
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

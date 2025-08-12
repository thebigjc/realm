from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _env_str(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v is not None and v != "" else default


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    bnet_client_id: str
    bnet_client_secret: str
    discord_bot_token: Optional[str]
    discord_channel_id: Optional[int]
    region: str = "us"
    locale: str = "en_US"
    poll_interval_seconds: int = 300
    state_file_path: str = "./data/state.json"

    @staticmethod
    def load(allow_missing_discord: bool = False) -> "Config":
        client_id = _env_str("BNET_CLIENT_ID")
        client_secret = _env_str("BNET_CLIENT_SECRET")
        discord_token = _env_str("DISCORD_BOT_TOKEN")
        channel_id_str = _env_str("DISCORD_CHANNEL_ID")

        # Always require BNET creds
        if not client_id or not client_secret:
            missing = [n for n, v in (("BNET_CLIENT_ID", client_id), ("BNET_CLIENT_SECRET", client_secret)) if not v]
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

        region = _env_str("REGION", "us") or "us"
        locale = _env_str("LOCALE", "en_US") or "en_US"
        poll = _env_int("POLL_INTERVAL_SECONDS", 300)
        state_path = _env_str("STATE_FILE_PATH", "./data/state.json") or "./data/state.json"

        channel_id: Optional[int] = None
        if channel_id_str:
            try:
                channel_id = int(channel_id_str)
            except ValueError:
                raise RuntimeError("DISCORD_CHANNEL_ID must be an integer")

        if not allow_missing_discord:
            # Require Discord creds in bot mode
            if not discord_token or channel_id is None:
                missing = [
                    n for n, v in (("DISCORD_BOT_TOKEN", discord_token), ("DISCORD_CHANNEL_ID", channel_id_str)) if not v
                ]
                raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

        return Config(
            bnet_client_id=client_id,
            bnet_client_secret=client_secret,
            discord_bot_token=discord_token,
            discord_channel_id=channel_id,
            region=region,
            locale=locale,
            poll_interval_seconds=poll,
            state_file_path=state_path,
        )

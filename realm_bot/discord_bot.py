from __future__ import annotations

import asyncio
import contextlib
import logging

import discord

from .blizzard_client import BlizzardClient
from .config import Config
from .realm_tracker import StateStore, compute_counts, diff_snapshots, format_message, make_snapshot


log = logging.getLogger(__name__)


class RealmStatusBot(discord.Client):
    _channel: discord.abc.MessageableChannel | None
    _poll_task: asyncio.Task[None] | None

    def __init__(self, *, config: Config, blizzard: BlizzardClient, state: StateStore):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.config = config
        self.blizzard = blizzard
        self.state = state
        # Lazy-resolved channel and background task
        self._channel = None
        self._poll_task = None

    async def setup_hook(self) -> None:
        # Start background task once bot is ready
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")

    async def _poll_loop(self):
        try:
            while not self.is_closed():
                # Resolve channel lazily
                if self._channel is None and self.config.discord_channel_id is not None:
                    ch = self.get_channel(self.config.discord_channel_id)
                    if ch is None:
                        try:
                            ch = await self.fetch_channel(self.config.discord_channel_id)
                        except Exception as e:
                            log.error("Failed to fetch channel %s: %s", self.config.discord_channel_id, e)
                            await asyncio.sleep(30)
                            continue
                    self._channel = ch  # type: ignore[assignment]

                connected_realms = await self.blizzard.fetch_all_connected_realms()
                available, status_counts, total = compute_counts(connected_realms)
                current = make_snapshot(available, status_counts, total)
                previous = self.state.load()

                d = diff_snapshots(previous, current)
                if previous is None:
                    # Save baseline without posting
                    self.state.save(current)
                    log.info("Baseline saved: %s available of %s", current.available_count, current.total)
                elif d.should_post:
                    msg = format_message(d)
                    try:
                        await self._channel.send(msg)  # type: ignore[union-attr]
                    except Exception as e:
                        log.error("Failed to send message: %s", e)
                    else:
                        self.state.save(current)
                        log.info("Posted update and saved snapshot")

                await asyncio.sleep(max(30, int(self.config.poll_interval_seconds)))
        except Exception as e:
            log.exception("poll loop error: %s", e)

    async def close(self) -> None:
        try:
            if self._poll_task is not None:
                self._poll_task.cancel()
                with contextlib.suppress(Exception):
                    await self._poll_task
            await self.blizzard.aclose()
        finally:
            await super().close()

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

import discord
from discord.ext import commands
from discord import app_commands

from .blizzard_client import BlizzardClient
from .config import Config
from .realm_tracker import StateStore, compute_counts, diff_snapshots, format_message, make_snapshot


log = logging.getLogger(__name__)


class RealmCommands(commands.Cog):
    def __init__(self, bot: "RealmStatusBot"):
        self.bot = bot

    @app_commands.command(name="realm", description="Get current WoW realm status")
    async def realm(self, interaction: discord.Interaction):
        """Get current realm status (private response)"""
        try:
            snap = self.bot.state.load()
            if snap is None:
                await interaction.response.send_message(
                    "No cached state available. Please try again later.",
                    ephemeral=True,
                )
                return
            d = diff_snapshots(None, snap)
            await interaction.response.send_message(format_message(d), ephemeral=True)
        except Exception as e:
            log.exception("Failed to handle cached status request: %s", e)
            await interaction.response.send_message("Failed to read cached state; try again later.", ephemeral=True)


class RealmStatusBot(commands.Bot):
    _channel: discord.abc.MessageableChannel | None
    _poll_task: asyncio.Task[None] | None

    def __init__(self, *, config: Config, blizzard: BlizzardClient, state: StateStore):
        intents = discord.Intents.default()
        # Required to read message content in on_message handlers
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.config = config
        self.blizzard = blizzard
        self.state = state
        # Lazy-resolved channel and background task
        self._channel = None
        self._poll_task = None

    async def setup_hook(self) -> None:
        # Load Cog with slash commands
        await self.add_cog(RealmCommands(self))

        # Prefer fast guild-specific sync if DISCORD_COMMAND_GUILD is set
        guild_id = os.getenv("DISCORD_COMMAND_GUILD")
        if guild_id:
            try:
                gid = int(guild_id)
                guild = discord.Object(id=gid)
                # Ensure local tree is built for the guild
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                log.info(f"Synced {len(synced)} slash commands to guild {gid}")
            except Exception:
                log.exception("Failed to guild-sync commands; falling back to global sync")
                synced = await self.tree.sync()
                log.info(f"Synced {len(synced)} global slash commands")
        else:
            # Global sync can take time to propagate
            synced = await self.tree.sync()
            log.info(f"Synced {len(synced)} global slash commands")
        # Start background task once bot is ready
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")

    # Slash commands now live in the RealmCommands Cog above

    async def _poll_loop(self):
        try:
            while not self.is_closed():
                # Resolve channels lazily (support single or multiple IDs)
                if (self._channel is None) and (self.config.discord_channel_ids is not None):
                    # Resolve and cache a list of MessageableChannel objects
                    resolved: list[discord.abc.MessageableChannel] = []
                    for cid in self.config.discord_channel_ids:
                        ch = self.get_channel(cid)
                        if ch is None:
                            try:
                                ch = await self.fetch_channel(cid)
                            except Exception as e:
                                log.error("Failed to fetch channel %s: %s", cid, e)
                                # If one channel fetch fails, skip it and continue; don't block entirely
                                continue
                        # Append resolved channel
                        resolved.append(ch)  # type: ignore[arg-type]
                    # Keep a single channel reference for backward compatibility if only one
                    if len(resolved) == 1:
                        self._channel = resolved[0]  # type: ignore[assignment]
                    elif len(resolved) > 1:
                        # Store list on instance for multi-channel posting
                        # mypy: dynamic attribute assignment
                        setattr(self, "_channels", resolved)

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
                        # If multiple channels configured, send to each; else use single cached channel
                        channels = getattr(self, "_channels", None)
                        if channels:
                            for ch in channels:
                                try:
                                    await ch.send(msg)
                                except Exception as e:
                                    log.error("Failed to send message to %s: %s", getattr(ch, "id", "?"), e)
                        elif self._channel is not None:
                            await self._channel.send(msg)  # type: ignore[union-attr]
                        else:
                            log.warning("No Discord channel configured to post updates")
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

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
from .metrics import (
    discord_connected,
    discord_messages_sent_total,
    discord_send_seconds,
    discord_command_invocations_total,
    update_realm_gauges,
    discord_ws_latency_seconds,
    discord_message_send_errors_total,
    note_poll_success,
    note_poll_error,
    note_discord_connect,
    note_discord_disconnect,
)
from .models import parse_connected_realms


log = logging.getLogger(__name__)


class RealmCommands(commands.Cog):
    def __init__(self, bot: "RealmStatusBot"):
        self.bot = bot

    @app_commands.command(name="realm", description="Get current WoW realm status")
    async def realm(self, interaction: discord.Interaction):
        """Get current realm status (private response)"""
        try:
            discord_command_invocations_total.labels(command="realm", status="started").inc()
            snap = self.bot.state.load()
            if snap is None:
                await interaction.response.send_message(
                    "No cached state available. Please try again later.",
                    ephemeral=True,
                )
                discord_command_invocations_total.labels(command="realm", status="no_cache").inc()
                return
            d = diff_snapshots(None, snap)
            await interaction.response.send_message(format_message(d), ephemeral=True)
            discord_command_invocations_total.labels(command="realm", status="success").inc()
        except Exception as e:
            log.exception("Failed to handle cached status request: %s", e)
            await interaction.response.send_message("Failed to read cached state; try again later.", ephemeral=True)
            discord_command_invocations_total.labels(command="realm", status="error").inc()


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
        try:
            discord_connected.set(1)
        except Exception:
            pass
        try:
            note_discord_connect()
        except Exception:
            pass

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

                poll_ok = False
                try:
                    connected_realms = await self.blizzard.fetch_all_connected_realms()
                    available, status_counts, total = compute_counts(connected_realms)
                    current = make_snapshot(available, status_counts, total)
                    previous = self.state.load()
                    poll_ok = True
                except Exception as e:
                    log.exception("Poll failure: %s", e)
                    try:
                        note_poll_error()
                    except Exception:
                        pass
                    await asyncio.sleep(10)
                    continue

                # Build per-realm up map using typed models
                status_by_realm: dict[str, bool] = {}
                for cr in parse_connected_realms(connected_realms):
                    up = cr.is_up()
                    for label in cr.realm_labels():
                        status_by_realm[label] = up
                update_realm_gauges(status_by_realm)

                d = diff_snapshots(previous, current, self.config.min_change_threshold)
                if poll_ok:
                    try:
                        note_poll_success()
                    except Exception:
                        pass
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
                                    from time import perf_counter
                                    t0 = perf_counter()
                                    await ch.send(msg)
                                    dt = perf_counter() - t0
                                    chan_label = str(getattr(ch, "id", "?"))
                                    discord_messages_sent_total.labels(channel=chan_label).inc()
                                    discord_send_seconds.labels(channel=chan_label).observe(dt)
                                except Exception as e:
                                    log.error("Failed to send message to %s: %s", getattr(ch, "id", "?"), e)
                                    chan_label = str(getattr(ch, "id", "?"))
                                    discord_message_send_errors_total.labels(channel=chan_label).inc()
                        elif self._channel is not None:
                            from time import perf_counter

                            t0 = perf_counter()
                            await self._channel.send(msg)  # type: ignore[union-attr]
                            dt = perf_counter() - t0
                            chan_label = str(getattr(self._channel, "id", "?"))  # type: ignore[union-attr]
                            discord_messages_sent_total.labels(channel=chan_label).inc()
                            discord_send_seconds.labels(channel=chan_label).observe(dt)
                        else:
                            log.warning("No Discord channel configured to post updates")
                    except Exception as e:
                        log.error("Failed to send message: %s", e)
                        # Count generic send failure when channel not available
                        discord_message_send_errors_total.labels(channel="unknown").inc()
                    else:
                        self.state.save(current)
                        log.info("Posted update and saved snapshot")

                await asyncio.sleep(max(30, int(self.config.poll_interval_seconds)))
                # Update websocket latency gauge each iteration
                try:
                    lat = float(self.latency) if getattr(self, "latency", None) is not None else 0.0
                    discord_ws_latency_seconds.set(lat)
                except Exception:
                    pass
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
            try:
                discord_connected.set(0)
            except Exception:
                pass
            try:
                note_discord_disconnect()
            except Exception:
                pass
            await super().close()

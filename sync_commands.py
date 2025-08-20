#!/usr/bin/env python3
"""
Simple CLI to sync Discord slash commands
Usage: python sync_commands.py [guild_id]
"""
import asyncio
import os
import sys
from dotenv import load_dotenv
import discord
from discord.ext import commands

async def sync_commands(guild_id=None):
    load_dotenv()
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("Error: DISCORD_BOT_TOKEN not found in environment")
        return
    
    # Create a minimal bot just for syncing
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    # Add the app command to match the main bot
    @discord.app_commands.command(name="realm", description="Get current WoW realm status")
    async def realm_status(interaction: discord.Interaction):
        await interaction.response.send_message("Command registered successfully!", ephemeral=True)
    
    bot.tree.add_command(realm_status)
    
    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user}")
        print(f"Commands in tree: {len(bot.tree.get_commands())}")
        
        try:
            if guild_id:
                # Sync to specific guild
                guild = discord.Object(id=int(guild_id))
                synced = await bot.tree.sync(guild=guild)
                print(f"✅ Synced {len(synced)} commands to guild {guild_id}")
            else:
                # Sync globally
                synced = await bot.tree.sync()
                print(f"✅ Synced {len(synced)} commands globally")
                
        except Exception as e:
            print(f"❌ Failed to sync: {e}")
        finally:
            await bot.close()
    
    await bot.start(token)

def main():
    guild_id = sys.argv[1] if len(sys.argv) > 1 else None
    
    if guild_id:
        print(f"Syncing commands to guild {guild_id}...")
    else:
        print("Syncing commands globally...")
    
    asyncio.run(sync_commands(guild_id))

if __name__ == "__main__":
    main()
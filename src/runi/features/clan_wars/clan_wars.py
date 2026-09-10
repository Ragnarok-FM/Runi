import time
from typing import Optional, TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from runi.utils import log

from .resources import RESOURCES, DEFAULT_RATES, SCORING_RESOURCES, MEMBERS_PER_PAGE, STALE_AFTER_SECONDS, AUTO_REFRESH_SECONDS
from .views import PanelView

if TYPE_CHECKING:
    from runi.main import RuniClient


def _relative_time(ts: float) -> str:
    if ts <= 0:
        return "never"

    delta = time.time() - ts
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)} minutes ago"
    if delta < 86400:
        return f"{int(delta // 3600)} hours ago"
    return f"{int(delta // 86400)} days ago"


class ClanWars(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot
        self.current_page: dict[int, int] = {}   # guild_id -> zero-indexed page
        self.auto_refresh.start()

    def cog_unload(self):
        self.auto_refresh.cancel()

    async def cog_load(self):
        # Re-register the persistent view so buttons survive bot restarts.
        self.bot.add_view(PanelView(self.bot))

    def shift_page(self, guild_id: int, direction: int) -> None:
        self.current_page[guild_id] = max(0, self.current_page.get(guild_id, 0) + direction)

    # ── Panel rendering ──────────────────────────────────────────────────────

    def _format_member_row(self, rank: int, entry: dict) -> str:
        name = entry.get("display_name", f"Unknown ({entry['user_id']})")

        stale = "⚠️ " if entry["updated_at"] and (time.time() - entry["updated_at"]) > STALE_AFTER_SECONDS else ""
        header = f"`#{rank}` **{name}** {stale}— {entry['points']:,.0f} pts (Updated {_relative_time(entry['updated_at'])})"

        parts = []
        for key, meta in RESOURCES.items():
            amount = entry["resources"].get(key, 0)
            token = f":{meta['emoji']}:"
            parts.append(f"{token} {amount:,}")

        return f"{header}\n└ {' | '.join(parts)}"

    def _format_totals(self, data: dict) -> str:
        lines = [f"🏆 **Total Points:** {data['total_points']:,.0f} pts", ""]
        for key, meta in RESOURCES.items():
            token = f":{meta['emoji']}:"
            total = data["totals"].get(key, 0)
            if meta["has_points"]:
                pts = total * data["rates"].get(key, 0)
                lines.append(f"• {token} **{meta['label']}:** {total:,} ({pts:,.0f} pts)")
            else:
                lines.append(f"• {token} **{meta['label']}:** {total:,}")
        return "\n".join(lines)

    async def render_panel_embed(self, guild: discord.Guild) -> discord.Embed:
        data = await self.bot.db.get_clan_war_leaderboard(guild.id, DEFAULT_RATES)

        # Attach display names now (requires the guild object, not available in the DB layer)
        for entry in data["members"]:
            member = guild.get_member(entry["user_id"])
            entry["display_name"] = member.display_name if member else f"Unknown ({entry['user_id']})"

        page = self.current_page.get(guild.id, 0)
        total_pages = max(1, (len(data["members"]) + MEMBERS_PER_PAGE - 1) // MEMBERS_PER_PAGE)
        page = min(page, total_pages - 1)
        self.current_page[guild.id] = page

        start = page * MEMBERS_PER_PAGE
        page_members = data["members"][start:start + MEMBERS_PER_PAGE]

        rows = [
            self._format_member_row(start + i + 1, entry)
            for i, entry in enumerate(page_members)
        ]
        if not rows:
            rows = ["No submissions yet this cycle — use the buttons below to add yours!"]

        content = "\n\n".join(rows) + "\n\n" + self._format_totals(data)

        newest_update = max((m["updated_at"] for m in data["members"]), default=0)
        timestamp_label = f"Newest update: {_relative_time(newest_update)}" if newest_update else "No submissions yet"

        return self.bot.embed_renderer.render("clan_war_panel", {
            "content": content,
            "page": page + 1,
            "total_pages": total_pages,
            "refresh_minutes": AUTO_REFRESH_SECONDS // 60,
            "timestamp_label": timestamp_label,
        })

    async def refresh_panel(self, guild_id: int) -> None:
        panel = await self.bot.db.get_clan_war_panel(guild_id)
        if not panel:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        channel = guild.get_channel(panel["channel_id"])
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        try:
            message = await channel.fetch_message(panel["message_id"])
        except discord.NotFound:
            log.error(f"Clan Wars panel message missing in guild {guild_id} — needs re-setup via /resourcepanel setup")
            return
        except discord.HTTPException as exc:
            log.error(f"Failed to fetch Clan Wars panel message in guild {guild_id}: {exc}")
            return

        embed = await self.render_panel_embed(guild)
        try:
            await message.edit(embed=embed, view=PanelView(self.bot))
        except discord.HTTPException as exc:
            log.error(f"Failed to edit Clan Wars panel in guild {guild_id}: {exc}")

    @tasks.loop(seconds=AUTO_REFRESH_SECONDS)
    async def auto_refresh(self):
        for guild_id in list(self.bot.guild_ids):
            try:
                await self.refresh_panel(guild_id)
            except Exception as exc:
                log.error(f"Auto-refresh failed for guild {guild_id}: {exc}")

    @auto_refresh.before_loop
    async def before_auto_refresh(self):
        await self.bot.wait_until_ready()

    # ── /resourcepanel setup (admin) ─────────────────────────────────────────
    resourcepanel = app_commands.Group(name="resourcepanel", description="Manage the Clan Wars panel.")

    @resourcepanel.command(name="setup", description="[Admin] Post the live Clan Wars panel in this channel.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def resourcepanel_setup(self, interaction: discord.Interaction):
        guild = interaction.guild
        assert guild is not None
        channel = interaction.channel
        assert isinstance(channel, (discord.TextChannel, discord.Thread))

        await interaction.response.defer(ephemeral=True)

        placeholder_embed = self.bot.embed_renderer.render("clan_war_panel", {
            "content": "Setting up...",
            "page": 1,
            "total_pages": 1,
            "refresh_minutes": AUTO_REFRESH_SECONDS // 60,
            "timestamp_label": "No submissions yet",
        })
        message = await channel.send(embed=placeholder_embed, view=PanelView(self.bot))

        await self.bot.db.set_clan_war_panel(guild.id, channel.id, message.id)
        self.current_page[guild.id] = 0
        await self.refresh_panel(guild.id)

        embed = self.bot.embed_renderer.render("clan_war_panel_created", {})
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /setresourcepoints (admin) ───────────────────────────────────────────
    @app_commands.command(name="setresourcepoints", description="[Admin] Change the points-per-unit rate for a resource.")
    @app_commands.describe(resource="Which resource to update.", points="New points-per-unit value.")
    @app_commands.choices(resource=[
        app_commands.Choice(name=meta["label"], value=key)
        for key, meta in RESOURCES.items() if meta["has_points"]
    ])
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def setresourcepoints(self, interaction: discord.Interaction, resource: app_commands.Choice[str], points: float):
        guild = interaction.guild
        assert guild is not None

        await self.bot.db.set_resource_rate(guild.id, resource.value, points)
        await self.refresh_panel(guild.id)

        embed = self.bot.embed_renderer.render("clan_war_rate_updated", {
            "resource": RESOURCES[resource.value]["label"],
            "points": points,
        })
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /resetwar (admin) ─────────────────────────────────────────────────────
    @app_commands.command(name="resetwar", description="[Admin] Clear all submitted resources for a new clan war cycle.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def resetwar(self, interaction: discord.Interaction):
        guild = interaction.guild
        assert guild is not None

        await self.bot.db.reset_clan_war(guild.id)
        self.current_page[guild.id] = 0
        await self.refresh_panel(guild.id)

        embed = self.bot.embed_renderer.render("clan_war_reset", {})
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Error handling for admin-only slash commands ─────────────────────────
    async def _admin_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, app_commands.MissingPermissions):
            embed = self.bot.embed_renderer.render("error_missing_admin_permissions", {})
            await interaction.response.send_message(embed=embed, ephemeral=True, delete_after=6)
        else:
            log.error(f"Clan Wars command error: {error}")
            raise error

    resourcepanel_setup.error(_admin_error)
    setresourcepoints.error(_admin_error)
    resetwar.error(_admin_error)


async def setup(bot: 'RuniClient'):
    await bot.add_cog(ClanWars(bot))

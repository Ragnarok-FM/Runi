import time
from typing import Optional, TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from runi.utils import log

from .resources import RESOURCES, DEFAULT_RATES, CONVERT_PER, SCORING_RESOURCES, MEMBERS_PER_PAGE, STALE_AFTER_SECONDS, AUTO_REFRESH_SECONDS, find_member_clan
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
        self.current_page: dict[int, int] = {}   # clan_id -> zero-indexed page
        self.auto_refresh.start()

    def cog_unload(self):
        self.auto_refresh.cancel()

    async def cog_load(self):
        # A single generic persistent view covers every clan's panel — the
        # buttons resolve which clan they apply to dynamically (see views.py),
        # so nothing clan-specific needs registering here, even for clans
        # created after this bot restart.
        self.bot.add_view(PanelView(self.bot))

    def shift_page(self, clan_id: int, direction: int) -> None:
        self.current_page[clan_id] = max(0, self.current_page.get(clan_id, 0) + direction)

    # ── Panel rendering ──────────────────────────────────────────────────────

    def _format_member_row(self, rank: int, entry: dict, rates: dict) -> str:
        name = entry.get("display_name", f"Unknown ({entry['user_id']})")

        stale = "⚠️ " if entry["updated_at"] and (time.time() - entry["updated_at"]) > STALE_AFTER_SECONDS else ""
        header = f"`#{rank}` **{name}** {stale}— {entry['points']:,.0f} pts (Updated `{_relative_time(entry['updated_at'])}`)"

        parts = []
        for key, meta in RESOURCES.items():
            amount = entry["resources"].get(key, 0)
            name_part = f":{meta['emoji']}:" if meta["show_emoji"] else f"{meta['label']}:"
            if meta["converted_label"]:
                converted = entry["converted"].get(key, 0)
                pts = converted * rates.get(key, 0)
                parts.append(f"{name_part} `{amount:,}` → `{converted:,}` {meta['converted_label']} (`{pts:,.0f}` pts)")
            elif meta["has_points"]:
                pts = amount * rates.get(key, 0)
                parts.append(f"{name_part} `{amount:,}` (`{pts:,.0f}` pts)")
            else:
                parts.append(f"{name_part} `{amount:,}`")

        return f"{header}\n└ {' | '.join(parts)}"

    def _format_totals(self, data: dict) -> str:
        lines = ["📊 **Clan Totals**", f"🏆 **Total Points:** `{data['total_points']:,.0f}` pts", ""]
        for key, meta in RESOURCES.items():
            total = data["totals"].get(key, 0)
            name_part = f":{meta['emoji']}:" if meta["show_emoji"] else f"**{meta['label']}:**"
            if meta["converted_label"]:
                converted = data["totals_converted"].get(key, 0)
                pts = converted * data["rates"].get(key, 0)
                lines.append(f"• {name_part} `{total:,}` → `{converted:,}` {meta['converted_label']} (`{pts:,.0f}` pts)")
            elif meta["has_points"]:
                pts = total * data["rates"].get(key, 0)
                lines.append(f"• {name_part} `{total:,}` (`{pts:,.0f}` pts)")
            else:
                lines.append(f"• {name_part} `{total:,}`")
        return "\n".join(lines)

    async def render_panel_embed(self, guild: discord.Guild, clan: dict) -> discord.Embed:
        clan_id = clan["clan_id"]
        data = await self.bot.db.get_clan_war_leaderboard(clan_id, DEFAULT_RATES, CONVERT_PER)

        # Attach display names now (requires the guild object, not available in the DB layer)
        for entry in data["members"]:
            member = guild.get_member(entry["user_id"])
            entry["display_name"] = member.display_name if member else f"Unknown ({entry['user_id']})"

        page = self.current_page.get(clan_id, 0)
        total_pages = max(1, (len(data["members"]) + MEMBERS_PER_PAGE - 1) // MEMBERS_PER_PAGE)
        page = min(page, total_pages - 1)
        self.current_page[clan_id] = page

        start = page * MEMBERS_PER_PAGE
        page_members = data["members"][start:start + MEMBERS_PER_PAGE]

        rows = [
            self._format_member_row(start + i + 1, entry, data["rates"])
            for i, entry in enumerate(page_members)
        ]
        if not rows:
            rows = ["No submissions yet this cycle — use the buttons below to add yours!"]

        content = "\n\n".join(rows) + "\n\n" + self._format_totals(data)

        newest_update = max((m["updated_at"] for m in data["members"]), default=0)
        timestamp_label = f"Newest update: {_relative_time(newest_update)}" if newest_update else "No submissions yet"

        return self.bot.embed_renderer.render("clan_war_panel", {
            "clan_name": clan["name"],
            "content": content,
            "page": page + 1,
            "total_pages": total_pages,
            "refresh_minutes": AUTO_REFRESH_SECONDS // 60,
            "timestamp_label": timestamp_label,
        })

    async def refresh_panel(self, clan_id: int) -> None:
        clan = await self.bot.db.get_clan(clan_id)
        if not clan:
            return

        panel = await self.bot.db.get_clan_war_panel(clan_id)
        if not panel:
            return

        guild = self.bot.get_guild(clan["guild_id"])
        if not guild:
            return

        channel = guild.get_channel(panel["channel_id"])
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        try:
            message = await channel.fetch_message(panel["message_id"])
        except discord.NotFound:
            log.error(f"Clan Wars panel message missing for clan '{clan['name']}' (id {clan_id}) — needs re-setup via /resourcepanel setup")
            return
        except discord.HTTPException as exc:
            log.error(f"Failed to fetch Clan Wars panel message for clan '{clan['name']}': {exc}")
            return

        embed = await self.render_panel_embed(guild, clan)
        try:
            await message.edit(embed=embed, view=PanelView(self.bot))
        except discord.HTTPException as exc:
            log.error(f"Failed to edit Clan Wars panel for clan '{clan['name']}': {exc}")

    @tasks.loop(seconds=AUTO_REFRESH_SECONDS)
    async def auto_refresh(self):
        for guild_id in list(self.bot.guild_ids):
            try:
                clans = await self.bot.db.get_clans(guild_id)
            except Exception as exc:
                log.error(f"Auto-refresh: failed to list clans for guild {guild_id}: {exc}")
                continue

            for clan in clans:
                try:
                    await self.refresh_panel(clan["clan_id"])
                except Exception as exc:
                    log.error(f"Auto-refresh failed for clan '{clan['name']}' (id {clan['clan_id']}): {exc}")

    @auto_refresh.before_loop
    async def before_auto_refresh(self):
        await self.bot.wait_until_ready()

    # ── Shared clan-selector autocomplete (used by 3 admin commands below) ────
    async def _clan_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        guild = interaction.guild
        if guild is None:
            return []
        clans = await self.bot.db.get_clans(guild.id)
        return [
            app_commands.Choice(name=c["name"], value=c["clan_id"])
            for c in clans if current.lower() in c["name"].lower()
        ][:25]

    # ── /register (admin) ────────────────────────────────────────────────────
    @app_commands.command(name="register", description="[Admin] Register a new clan and the Discord role that identifies its members.")
    @app_commands.describe(
        clan="Display name for this clan (shown on their panel).",
        role="The Discord role that identifies this clan's members.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def register(self, interaction: discord.Interaction, clan: str, role: discord.Role):
        guild = interaction.guild
        assert guild is not None

        clan_id = await self.bot.db.register_clan(guild.id, clan, role.id)

        if clan_id is None:
            embed = self.bot.embed_renderer.render("clan_role_already_registered", {"role": role.mention})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = self.bot.embed_renderer.render("clan_registered", {
            "name": clan,
            "role": role.mention,
        })
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /resourcepanel setup (admin) ─────────────────────────────────────────
    resourcepanel = app_commands.Group(name="resourcepanel", description="Manage the Clan Wars panel.")

    @resourcepanel.command(name="setup", description="[Admin] Post a clan's live Clan Wars panel in this channel.")
    @app_commands.describe(clan="Which registered clan this panel is for.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def resourcepanel_setup(self, interaction: discord.Interaction, clan: int):
        guild = interaction.guild
        assert guild is not None
        channel = interaction.channel
        assert isinstance(channel, (discord.TextChannel, discord.Thread))

        clan_row = await self.bot.db.get_clan(clan)
        if not clan_row or clan_row["guild_id"] != guild.id:
            embed = self.bot.embed_renderer.render("clan_not_found", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        placeholder_embed = self.bot.embed_renderer.render("clan_war_panel", {
            "clan_name": clan_row["name"],
            "content": "Setting up...",
            "page": 1,
            "total_pages": 1,
            "refresh_minutes": AUTO_REFRESH_SECONDS // 60,
            "timestamp_label": "No submissions yet",
        })
        message = await channel.send(embed=placeholder_embed, view=PanelView(self.bot))

        clan_id = clan_row["clan_id"]
        await self.bot.db.set_clan_war_panel(clan_id, channel.id, message.id)
        self.current_page[clan_id] = 0
        await self.refresh_panel(clan_id)

        embed = self.bot.embed_renderer.render("clan_war_panel_created", {"clan_name": clan_row["name"]})
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /myresources ──────────────────────────────────────────────────────────
    @app_commands.command(name="myresources", description="See your own submitted Clan Wars resources (only visible to you).")
    async def myresources(self, interaction: discord.Interaction):
        guild = interaction.guild
        assert guild is not None
        member = interaction.user

        clans = await self.bot.db.get_clans(guild.id)
        clan = find_member_clan(member, clans) if isinstance(member, discord.Member) else None

        if clan is None:
            embed = self.bot.embed_renderer.render("clan_war_no_role", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        data = await self.bot.db.get_clan_war_leaderboard(clan["clan_id"], DEFAULT_RATES, CONVERT_PER)

        rank = None
        entry = None
        for i, m in enumerate(data["members"]):
            if m["user_id"] == interaction.user.id:
                rank = i + 1
                entry = m
                break

        if entry is None:
            embed = self.bot.embed_renderer.render("clan_war_no_submissions", {})
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        entry["display_name"] = interaction.user.display_name
        row = self._format_member_row(rank, entry, data["rates"])

        embed = self.bot.embed_renderer.render("clan_war_my_resources", {
            "content": row,
        })
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /setresourcepoints (admin) ───────────────────────────────────────────
    @app_commands.command(name="setresourcepoints", description="[Admin] Change the points-per-unit rate for a resource, for one clan.")
    @app_commands.describe(clan="Which clan's rate to change.", resource="Which resource to update.", points="New points-per-unit value.")
    @app_commands.choices(resource=[
        app_commands.Choice(name=meta["label"], value=key)
        for key, meta in RESOURCES.items() if meta["has_points"]
    ])
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def setresourcepoints(self, interaction: discord.Interaction, clan: int, resource: app_commands.Choice[str], points: float):
        guild = interaction.guild
        assert guild is not None

        clan_row = await self.bot.db.get_clan(clan)
        if not clan_row or clan_row["guild_id"] != guild.id:
            embed = self.bot.embed_renderer.render("clan_not_found", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await self.bot.db.set_resource_rate(clan, resource.value, points)
        await self.refresh_panel(clan)

        embed = self.bot.embed_renderer.render("clan_war_rate_updated", {
            "resource": RESOURCES[resource.value]["label"],
            "points": points,
        })
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /resetwar (admin) ─────────────────────────────────────────────────────
    @app_commands.command(name="resetwar", description="[Admin] Clear all submitted resources for one clan's new war cycle.")
    @app_commands.describe(clan="Which clan to reset.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def resetwar(self, interaction: discord.Interaction, clan: int):
        guild = interaction.guild
        assert guild is not None

        clan_row = await self.bot.db.get_clan(clan)
        if not clan_row or clan_row["guild_id"] != guild.id:
            embed = self.bot.embed_renderer.render("clan_not_found", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await self.bot.db.reset_clan_war(clan)
        self.current_page[clan] = 0
        await self.refresh_panel(clan)

        embed = self.bot.embed_renderer.render("clan_war_reset", {})
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Error handling for admin-only slash commands ─────────────────────────
    async def _admin_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, app_commands.MissingPermissions):
            embed = self.bot.embed_renderer.render("error_missing_admin_permissions", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            log.error(f"Clan Wars command error: {error}")
            raise error

    register.error(_admin_error)
    resourcepanel_setup.error(_admin_error)
    setresourcepoints.error(_admin_error)
    resetwar.error(_admin_error)

    resourcepanel_setup.autocomplete("clan")(_clan_autocomplete)
    setresourcepoints.autocomplete("clan")(_clan_autocomplete)
    resetwar.autocomplete("clan")(_clan_autocomplete)


async def setup(bot: 'RuniClient'):
    await bot.add_cog(ClanWars(bot))

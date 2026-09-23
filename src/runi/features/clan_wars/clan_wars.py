import time
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from runi.utils import log

from .resources import RESOURCES, DEFAULT_RATES, CONVERT_PER, SCORING_RESOURCES, MEMBERS_PER_PAGE, STALE_AFTER_SECONDS, AUTO_REFRESH_SECONDS, find_member_clan, WAR_RESET_TIME, WAR_RESET_WEEKDAY, WAR_RESET_TIMEZONE
from .views import PanelView

if TYPE_CHECKING:
    from runi.main import RuniClient


def _ordinal_day(day: int) -> str:
    """Returns a day number with its ordinal suffix, e.g. 1 -> '1st', 23 -> '23rd', 11 -> '11th'."""
    if 11 <= (day % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


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
        self.weekly_war_reset.start()

    def cog_unload(self):
        self.auto_refresh.cancel()
        self.weekly_war_reset.cancel()

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

    async def render_report_pages(self, guild: discord.Guild, clan: dict) -> list[discord.Embed]:
        """
        Builds a static, read-only snapshot of a clan's current standings —
        one embed per page of members, covering every member (unlike the
        live panel, this never depends on self.current_page). Meant to be
        posted as a final report right before a cycle resets.
        """
        clan_id = clan["clan_id"]
        data = await self.bot.db.get_clan_war_leaderboard(clan_id, DEFAULT_RATES, CONVERT_PER)

        for entry in data["members"]:
            member = guild.get_member(entry["user_id"])
            entry["display_name"] = member.display_name if member else f"Unknown ({entry['user_id']})"

        total_pages = max(1, (len(data["members"]) + MEMBERS_PER_PAGE - 1) // MEMBERS_PER_PAGE)

        pages = []
        for page in range(total_pages):
            start = page * MEMBERS_PER_PAGE
            page_members = data["members"][start:start + MEMBERS_PER_PAGE]

            rows = [
                self._format_member_row(start + i + 1, entry, data["rates"])
                for i, entry in enumerate(page_members)
            ]
            if not rows:
                rows = ["No submissions this cycle."]

            content = "\n\n".join(rows)
            if page == total_pages - 1:
                # Totals only once, at the end, rather than repeated on
                # every static message (unlike the live panel, where
                # repeating it on every page makes sense since a viewer
                # might land on any page first).
                content += "\n\n" + self._format_totals(data)

            embed = self.bot.embed_renderer.render("clan_war_report", {
                "clan_name": clan["name"],
                "content": content,
                "page": page + 1,
                "total_pages": total_pages,
            })
            pages.append(embed)

        return pages

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

        try:
            channel = await guild.fetch_channel(panel["channel_id"])
        except discord.NotFound:
            log.error(f"Clan Wars panel channel/thread missing for clan '{clan['name']}' (id {clan_id}) — needs re-setup via /resourcepanel setup")
            return
        except discord.HTTPException as exc:
            log.error(f"Failed to fetch Clan Wars panel channel for clan '{clan['name']}': {exc}")
            return

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

    # ── Weekly war cycle automation ──────────────────────────────────────────
    # Every Monday at 02:01 Europe/Stockholm (one minute after the in-game
    # day reset that starts the new war), for every clan that has a Forum
    # channel configured: post a final report in that cycle's thread, reset
    # the clan's resources, lock the old thread, and open a fresh one.
    @tasks.loop(time=WAR_RESET_TIME)
    async def weekly_war_reset(self):
        now = datetime.now(WAR_RESET_TIMEZONE)
        if now.weekday() != WAR_RESET_WEEKDAY:
            return

        for guild_id in list(self.bot.guild_ids):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            try:
                clans = await self.bot.db.get_clans(guild_id)
            except Exception as exc:
                log.error(f"Weekly war reset: failed to list clans for guild {guild_id}: {exc}")
                continue

            for clan in clans:
                if not clan["forum_channel_id"]:
                    continue  # this clan hasn't configured a forum yet — skip automation for it
                try:
                    await self._run_weekly_reset_for_clan(guild, clan)
                except Exception as exc:
                    log.error(f"Weekly war reset failed for clan '{clan['name']}' (id {clan['clan_id']}): {exc}")

    @weekly_war_reset.before_loop
    async def before_weekly_war_reset(self):
        await self.bot.wait_until_ready()

    async def _run_weekly_reset_for_clan(self, guild: discord.Guild, clan: dict) -> None:
        clan_id = clan["clan_id"]

        # 1. Post the final report in the CURRENT (about-to-be-retired)
        #    thread, using the data as it stands right before the reset.
        old_panel = await self.bot.db.get_clan_war_panel(clan_id)
        old_thread: Optional[discord.Thread] = None

        if old_panel:
            try:
                old_channel = await guild.fetch_channel(old_panel["channel_id"])
                if isinstance(old_channel, discord.Thread):
                    old_thread = old_channel
            except discord.HTTPException as exc:
                log.error(f"Weekly reset: couldn't fetch old thread for clan '{clan['name']}': {exc}")

        if old_thread:
            try:
                report_pages = await self.render_report_pages(guild, clan)
                for embed in report_pages:
                    await old_thread.send(embed=embed)
            except discord.HTTPException as exc:
                log.error(f"Weekly reset: failed to post report for clan '{clan['name']}': {exc}")
        else:
            log.warn(f"Weekly reset: no existing thread found for clan '{clan['name']}' — skipping report, proceeding to reset")

        # 2. Reset the clan's resources for the new cycle.
        await self.bot.db.reset_clan_war(clan_id)
        self.current_page[clan_id] = 0

        # 3. Lock the old thread now that its cycle is over.
        if old_thread:
            try:
                await old_thread.edit(locked=True)
            except discord.HTTPException as exc:
                log.error(f"Weekly reset: failed to lock old thread for clan '{clan['name']}': {exc}")

        # 4. Create a new forum thread for the new cycle, locked from the
        #    start — members only ever need to click buttons, never post.
        try:
            forum_channel = await guild.fetch_channel(clan["forum_channel_id"])
        except discord.HTTPException as exc:
            log.error(f"Weekly reset: couldn't fetch forum channel for clan '{clan['name']}': {exc}")
            return

        if not isinstance(forum_channel, discord.ForumChannel):
            log.error(f"Weekly reset: configured channel for clan '{clan['name']}' is not a Forum channel — cannot create new thread")
            return

        now = datetime.now(WAR_RESET_TIMEZONE)
        thread_name = f"{now:%B} {_ordinal_day(now.day)}, {now:%Y}"

        placeholder_embed = self.bot.embed_renderer.render("clan_war_panel", {
            "clan_name": clan["name"],
            "content": "Setting up...",
            "page": 1,
            "total_pages": 1,
            "refresh_minutes": AUTO_REFRESH_SECONDS // 60,
            "timestamp_label": "No submissions yet",
        })

        try:
            result = await forum_channel.create_thread(name=thread_name, embed=placeholder_embed, view=PanelView(self.bot))
        except discord.HTTPException as exc:
            log.error(f"Weekly reset: failed to create new thread for clan '{clan['name']}': {exc}")
            return

        new_thread = result.thread
        new_message = result.message

        try:
            await new_thread.edit(locked=True)
        except discord.HTTPException as exc:
            log.error(f"Weekly reset: failed to lock new thread for clan '{clan['name']}': {exc}")

        await self.bot.db.set_clan_war_panel(clan_id, new_thread.id, new_message.id)
        await self.refresh_panel(clan_id)

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
    @app_commands.command(name="register", description="[Admin] Register a clan, its role, and (optionally) its Forum channel.")
    @app_commands.describe(
        clan="Display name for this clan (shown on their panel).",
        role="The Discord role that identifies this clan's members.",
        forum="The Forum channel where a new thread is posted each weekly war cycle. Re-run /register to set/change this later.",
    )
    @app_commands.default_permissions(administrator=True)
    async def register(self, interaction: discord.Interaction, clan: str, role: discord.Role, forum: Optional[discord.ForumChannel] = None):
        guild = interaction.guild
        assert guild is not None

        clan_id, was_new = await self.bot.db.register_clan(guild.id, clan, role.id, forum.id if forum else None)

        embed = self.bot.embed_renderer.render("clan_registered" if was_new else "clan_updated", {
            "name": clan,
            "role": role.mention,
            "forum": forum.mention if forum else "*(unchanged — none set yet if this is a new clan)*",
        })
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /resourcepanel setup (admin) ─────────────────────────────────────────
    resourcepanel = app_commands.Group(name="resourcepanel", description="Manage the Clan Wars panel.")

    @resourcepanel.command(name="setup", description="[Admin] Post a clan's live Clan Wars panel in this channel.")
    @app_commands.describe(clan="Which registered clan this panel is for.")
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

    # ── Error handling for admin-managed slash commands ──────────────────────
    # Permission enforcement is now fully delegated to Discord's own native
    # per-command role permissions (Server Settings → Integrations → Runi),
    # so MissingPermissions can no longer be raised by our own code here —
    # Discord rejects the interaction before it ever reaches this bot.
    async def _command_error(self, interaction: discord.Interaction, error: Exception):
        log.error(f"Clan Wars command error: {error}")
        raise error

    register.error(_command_error)
    resourcepanel_setup.error(_command_error)
    setresourcepoints.error(_command_error)
    resetwar.error(_command_error)

    resourcepanel_setup.autocomplete("clan")(_clan_autocomplete)
    setresourcepoints.autocomplete("clan")(_clan_autocomplete)
    resetwar.autocomplete("clan")(_clan_autocomplete)


async def setup(bot: 'RuniClient'):
    await bot.add_cog(ClanWars(bot))

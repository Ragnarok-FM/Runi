import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from runi.utils import log

from runi.config import (
    WAR_RESET_TIMEZONE,
    WAR_RESET_WEEKDAY,
    WAR_RESET_TIME,
    CLAN_WARS_AUTO_REFRESH_SECONDS,
    CLAN_WARS_STALE_AFTER_SECONDS,
    CLAN_WARS_MEMBERS_PER_PAGE,
    CLAN_WARS_CLAN_CACHE_SECONDS,
)

from .resources import RESOURCES, DEFAULT_RATES, CONVERT_PER
from .clans import find_member_clan
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


@dataclass
class CycleOutcome:
    """
    What actually happened during a thread-creation or weekly-reset run, so
    commands can report the truth instead of assuming success.
      ok       — False if a step failed and the run stopped there.
      error    — for a failed run: which step failed, and what state it left things in.
      warnings — non-fatal problems: the run finished, but something didn't happen.
    """
    ok: bool = True
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def fail(self, message: str) -> "CycleOutcome":
        self.ok = False
        self.error = message
        return self

    def warnings_text(self) -> str:
        return "\n".join(f"• {w}" for w in self.warnings) if self.warnings else "None"


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
        # One lock per clan. Everything that touches a clan's panel (refresh,
        # reset, new thread, weekly cycle) holds it, so they can't interleave.
        self._clan_locks: dict[int, asyncio.Lock] = {}
        # guild_id -> (fetched_at, clans), used only by autocomplete.
        self._clan_cache: dict[int, tuple[float, list[dict]]] = {}
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

    def _lock_for(self, clan_id: int) -> asyncio.Lock:
        return self._clan_locks.setdefault(clan_id, asyncio.Lock())

    # ── Panel rendering ──────────────────────────────────────────────────────

    def _format_member_row(self, rank: int, entry: dict, rates: dict) -> str:
        name = entry.get("display_name", f"Unknown ({entry['user_id']})")

        stale = "⚠️ " if entry["updated_at"] and (time.time() - entry["updated_at"]) > CLAN_WARS_STALE_AFTER_SECONDS else ""
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

        return f"{header}\n└ {' ┃ '.join(parts)}"

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
        total_pages = max(1, (len(data["members"]) + CLAN_WARS_MEMBERS_PER_PAGE - 1) // CLAN_WARS_MEMBERS_PER_PAGE)
        page = min(page, total_pages - 1)
        self.current_page[clan_id] = page

        start = page * CLAN_WARS_MEMBERS_PER_PAGE
        page_members = data["members"][start:start + CLAN_WARS_MEMBERS_PER_PAGE]

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
            "refresh_minutes": CLAN_WARS_AUTO_REFRESH_SECONDS // 60,
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

        total_pages = max(1, (len(data["members"]) + CLAN_WARS_MEMBERS_PER_PAGE - 1) // CLAN_WARS_MEMBERS_PER_PAGE)

        pages = []
        for page in range(total_pages):
            start = page * CLAN_WARS_MEMBERS_PER_PAGE
            page_members = data["members"][start:start + CLAN_WARS_MEMBERS_PER_PAGE]

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
        """Public entry point (auto-refresh, modal submits, pagination). Waits
        for any in-progress reset/new-thread run on this clan to finish first."""
        async with self._lock_for(clan_id):
            await self._refresh_panel_locked(clan_id)

    async def _refresh_panel_locked(self, clan_id: int) -> bool:
        """Re-renders the clan's panel. Caller MUST already hold the clan's
        lock. Returns True if the panel was actually updated."""
        clan = await self.bot.db.get_clan(clan_id)
        if not clan:
            return False

        panel = await self.bot.db.get_clan_war_panel(clan_id)
        if not panel:
            return False

        guild = self.bot.get_guild(clan["guild_id"])
        if not guild:
            return False

        try:
            channel = await guild.fetch_channel(panel["channel_id"])
        except discord.NotFound:
            log.error(f"Clan Wars panel channel/thread missing for clan '{clan['name']}' (id {clan_id}) — needs re-setup via /resourcepanel setup")
            return False
        except discord.HTTPException as exc:
            log.error(f"Failed to fetch Clan Wars panel channel for clan '{clan['name']}': {exc}")
            return False

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return False

        try:
            message = await channel.fetch_message(panel["message_id"])
        except discord.NotFound:
            log.error(f"Clan Wars panel message missing for clan '{clan['name']}' (id {clan_id}) — needs re-setup via /resourcepanel setup")
            return False
        except discord.HTTPException as exc:
            log.error(f"Failed to fetch Clan Wars panel message for clan '{clan['name']}': {exc}")
            return False

        embed = await self.render_panel_embed(guild, clan)
        try:
            await message.edit(embed=embed, view=PanelView(self.bot))
        except discord.HTTPException as exc:
            log.error(f"Failed to edit Clan Wars panel for clan '{clan['name']}': {exc}")
            return False
        return True

    @tasks.loop(seconds=CLAN_WARS_AUTO_REFRESH_SECONDS)
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
                    outcome = await self._run_weekly_reset_for_clan(guild, clan)
                except Exception as exc:
                    log.error(f"Weekly war reset crashed for clan '{clan['name']}' (id {clan['clan_id']}): {exc}")
                    continue

                for warning in outcome.warnings:
                    log.warn(f"Weekly war reset for clan '{clan['name']}': {warning}")
                if outcome.ok:
                    log.success(f"Weekly war reset completed for clan '{clan['name']}'")
                else:
                    log.error(f"Weekly war reset FAILED for clan '{clan['name']}': {outcome.error}")

    @weekly_war_reset.before_loop
    async def before_weekly_war_reset(self):
        await self.bot.wait_until_ready()

    async def _run_weekly_reset_for_clan(self, guild: discord.Guild, clan: dict) -> CycleOutcome:
        """
        The full weekly cycle for one clan. Order matters: nothing destructive
        happens until the step before it has succeeded.
          1. Post the final report in the current panel's channel/thread.
             Fails -> stop. Nothing has been changed, this week's data is kept.
          2. Reset the clan's resources.
             Fails -> stop. Report is posted, old panel still live, data kept.
          3. Create the new thread + panel.
             Fails -> stop. Data is reset, but the OLD panel is left in place
             (not deleted, thread not locked) so members can still submit.
          4. Retire the old panel: delete it and lock the old thread.
             Fails -> warning only; the new cycle is already running.
        Holds the clan's lock throughout, so auto-refresh, submissions'
        refreshes and a second manual run can't interleave with it.
        """
        clan_id = clan["clan_id"]
        name = clan["name"]
        outcome = CycleOutcome()

        async with self._lock_for(clan_id):
            try:
                old_panel = await self.bot.db.get_clan_war_panel(clan_id)
            except Exception as exc:
                log.error(f"Weekly reset: couldn't read panel record for clan '{name}': {exc}")
                return outcome.fail("Couldn't read the clan's panel record from the database. Nothing was changed. Try again.")

            old_channel: Optional[discord.abc.Messageable] = None
            if old_panel:
                try:
                    fetched = await guild.fetch_channel(old_panel["channel_id"])
                except discord.NotFound:
                    outcome.warnings.append("The previous panel's thread/channel no longer exists, so no final report could be posted there.")
                except discord.HTTPException as exc:
                    log.error(f"Weekly reset: couldn't fetch current thread for clan '{name}': {exc}")
                    return outcome.fail(f"Couldn't reach the current panel's thread (Discord error: {exc}). Nothing was changed. Try again.")
                else:
                    if isinstance(fetched, (discord.TextChannel, discord.Thread)):
                        old_channel = fetched
                    else:
                        outcome.warnings.append("The previous panel isn't in a text channel or thread, so no final report was posted.")
            else:
                outcome.warnings.append("No previous panel is on record, so no final report was posted.")

            # 1. Final report
            if old_channel is not None:
                try:
                    report_pages = await self.render_report_pages(guild, clan)
                    for embed in report_pages:
                        await old_channel.send(embed=embed)
                except Exception as exc:
                    log.error(f"Weekly reset: failed to post report for clan '{name}': {exc}")
                    return outcome.fail(
                        f"Posting the final report failed ({exc}). Stopped before resetting, so this week's data is kept. "
                        "Fix the cause (usually a missing Send Messages permission) and run /runweeklyreset again."
                    )

            # 2. Reset resources
            try:
                await self.bot.db.reset_clan_war(clan_id)
            except Exception as exc:
                log.error(f"Weekly reset: failed to reset resources for clan '{name}': {exc}")
                return outcome.fail(
                    f"The report was posted, but resetting resources failed ({exc}). Data is untouched and the old panel is still live. "
                    "Running /runweeklyreset again will post the report a second time."
                )
            self.current_page[clan_id] = 0

            # 3. New thread + panel
            thread_outcome = await self._create_new_war_thread(guild, clan)
            outcome.warnings.extend(thread_outcome.warnings)
            if not thread_outcome.ok:
                # Old panel was deliberately left alone: show it the reset data
                # so members can keep submitting into the new cycle through it.
                await self._refresh_panel_locked(clan_id)
                return outcome.fail(
                    f"The report was posted and resources were reset, but the new thread couldn't be created: {thread_outcome.error} "
                    "The old panel was left in place so members can keep submitting. Run /newpanelthread once the cause is fixed."
                )

            # 4. Retire the old panel (the database already points at the new one)
            if old_channel is not None and old_panel:
                try:
                    old_message = await old_channel.fetch_message(old_panel["message_id"])
                    await old_message.delete()
                except discord.NotFound:
                    pass  # already gone, nothing to clean up
                except discord.HTTPException as exc:
                    log.error(f"Weekly reset: failed to delete old panel for clan '{name}': {exc}")
                    outcome.warnings.append("Couldn't delete the old panel message. Delete it manually so members don't use the wrong one.")

                if isinstance(old_channel, discord.Thread):
                    try:
                        await old_channel.edit(locked=True)
                    except discord.HTTPException as exc:
                        log.error(f"Weekly reset: failed to lock old thread for clan '{name}': {exc}")
                        outcome.warnings.append("Couldn't lock the old thread. Lock it manually.")

        return outcome

    async def _create_new_war_thread(self, guild: discord.Guild, clan: dict) -> CycleOutcome:
        """
        Creates a fresh forum thread for a clan's war cycle, posts a locked
        panel into it, and points clan_war_panels at it. Shared by the weekly
        job and /newpanelthread, so they can't drift apart.
        Caller MUST already hold the clan's lock.
        """
        clan_id = clan["clan_id"]
        name = clan["name"]
        outcome = CycleOutcome()

        try:
            forum_channel = await guild.fetch_channel(clan["forum_channel_id"])
        except discord.NotFound:
            log.error(f"Forum channel for clan '{name}' no longer exists")
            return outcome.fail("The clan's configured Forum channel no longer exists. Re-run /register with a new forum.")
        except discord.HTTPException as exc:
            log.error(f"Couldn't fetch forum channel for clan '{name}': {exc}")
            return outcome.fail(f"Couldn't reach the clan's Forum channel (Discord error: {exc}).")

        if not isinstance(forum_channel, discord.ForumChannel):
            log.error(f"Configured channel for clan '{name}' is not a Forum channel — cannot create new thread")
            return outcome.fail("The clan's configured channel isn't a Forum channel. Re-run /register with a Forum channel.")

        now = datetime.now(WAR_RESET_TIMEZONE)
        thread_name = f"{now:%B} {_ordinal_day(now.day)}, {now:%Y}"

        placeholder_embed = self.bot.embed_renderer.render("clan_war_panel", {
            "clan_name": name,
            "content": "Setting up...",
            "page": 1,
            "total_pages": 1,
            "refresh_minutes": CLAN_WARS_AUTO_REFRESH_SECONDS // 60,
            "timestamp_label": "No submissions yet",
        })

        try:
            result = await forum_channel.create_thread(name=thread_name, embed=placeholder_embed, view=PanelView(self.bot))
        except discord.HTTPException as exc:
            log.error(f"Failed to create new thread for clan '{name}': {exc}")
            return outcome.fail(f"Discord refused to create the thread ({exc}). Usually a missing permission (Create Posts / Manage Threads) in the Forum channel.")

        new_thread = result.thread
        new_message = result.message

        # Save the new panel location before anything else: if this fails, the
        # thread is orphaned (the bot would never refresh it), so remove it.
        try:
            await self.bot.db.set_clan_war_panel(clan_id, new_thread.id, new_message.id)
        except Exception as exc:
            log.error(f"Failed to save new panel location for clan '{name}': {exc}")
            try:
                await new_thread.delete()
                return outcome.fail(f"The thread was created but saving it to the database failed ({exc}), so it was removed again. Nothing changed.")
            except discord.HTTPException:
                return outcome.fail(
                    f"The thread was created but saving it to the database failed ({exc}), and the thread couldn't be removed. "
                    f"Delete the thread '{thread_name}' manually."
                )

        try:
            await new_thread.edit(locked=True)
        except discord.HTTPException as exc:
            log.error(f"Failed to lock new thread for clan '{name}': {exc}")
            outcome.warnings.append("The new thread couldn't be locked, so members can post in it. Lock it manually.")

        if not await self._refresh_panel_locked(clan_id):
            outcome.warnings.append(f"The new panel's first refresh failed. It will show 'Setting up...' until the next auto-refresh (within {CLAN_WARS_AUTO_REFRESH_SECONDS // 60} minutes).")

        return outcome

    # ── Shared clan-selector autocomplete ────────────────────────────────────
    async def _get_clans_cached(self, guild_id: int) -> list[dict]:
        cached = self._clan_cache.get(guild_id)
        if cached and time.monotonic() - cached[0] < CLAN_WARS_CLAN_CACHE_SECONDS:
            return cached[1]
        clans = await self.bot.db.get_clans(guild_id)
        self._clan_cache[guild_id] = (time.monotonic(), clans)
        return clans

    async def _clan_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        guild = interaction.guild
        if guild is None:
            return []
        try:
            clans = await self._get_clans_cached(guild.id)
        except Exception as exc:
            # Returning an empty list shows "no options" instead of Discord's
            # "Loading options failed" — the admin can simply retry.
            log.error(f"Clan autocomplete: failed to load clans for guild {guild.id}: {exc}")
            return []
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
        self._clan_cache.pop(guild.id, None)  # so autocomplete shows the change immediately

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
            "refresh_minutes": CLAN_WARS_AUTO_REFRESH_SECONDS // 60,
            "timestamp_label": "No submissions yet",
        })
        clan_id = clan_row["clan_id"]
        async with self._lock_for(clan_id):
            message = await channel.send(embed=placeholder_embed, view=PanelView(self.bot))
            await self.bot.db.set_clan_war_panel(clan_id, channel.id, message.id)
            self.current_page[clan_id] = 0
            await self._refresh_panel_locked(clan_id)

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

        async with self._lock_for(clan):
            await self.bot.db.reset_clan_war(clan)
            self.current_page[clan] = 0
            await self._refresh_panel_locked(clan)

        embed = self.bot.embed_renderer.render("clan_war_reset", {})
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /newpanelthread (admin, fallback) ────────────────────────────────────
    @app_commands.command(name="newpanelthread", description="[Admin] Fallback: new forum thread + fresh panel for a clan. Doesn't touch resource data.")
    @app_commands.describe(clan="Which clan to create a new thread for.")
    @app_commands.default_permissions(administrator=True)
    async def newpanelthread(self, interaction: discord.Interaction, clan: int):
        guild = interaction.guild
        assert guild is not None

        clan_row = await self.bot.db.get_clan(clan)
        if not clan_row or clan_row["guild_id"] != guild.id:
            embed = self.bot.embed_renderer.render("clan_not_found", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not clan_row["forum_channel_id"]:
            embed = self.bot.embed_renderer.render("clan_no_forum_configured", {"name": clan_row["name"]})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        async with self._lock_for(clan_row["clan_id"]):
            outcome = await self._create_new_war_thread(guild, clan_row)

        if not outcome.ok:
            template = "clan_new_thread_failed"
        elif outcome.warnings:
            template = "clan_new_thread_partial"
        else:
            template = "clan_new_thread_created"

        embed = self.bot.embed_renderer.render(template, {
            "name": clan_row["name"],
            "error": outcome.error or "",
            "warnings": outcome.warnings_text(),
        })
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /runweeklyreset (admin, fallback) ────────────────────────────────────
    @app_commands.command(name="runweeklyreset", description="[Admin] Fallback: manually run the full weekly cycle for a clan, right now.")
    @app_commands.describe(clan="Which clan to run the weekly cycle for.")
    @app_commands.default_permissions(administrator=True)
    async def runweeklyreset(self, interaction: discord.Interaction, clan: int):
        guild = interaction.guild
        assert guild is not None

        clan_row = await self.bot.db.get_clan(clan)
        if not clan_row or clan_row["guild_id"] != guild.id:
            embed = self.bot.embed_renderer.render("clan_not_found", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not clan_row["forum_channel_id"]:
            embed = self.bot.embed_renderer.render("clan_no_forum_configured", {"name": clan_row["name"]})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            outcome = await self._run_weekly_reset_for_clan(guild, clan_row)
        except Exception as exc:
            log.error(f"/runweeklyreset crashed for clan '{clan_row['name']}': {exc}")
            outcome = CycleOutcome().fail(f"Unexpected error ({exc}). Check the bot's console log before re-running.")

        if not outcome.ok:
            template = "clan_weekly_reset_failed"
        elif outcome.warnings:
            template = "clan_weekly_reset_partial"
        else:
            template = "clan_weekly_reset_ran"

        embed = self.bot.embed_renderer.render(template, {
            "name": clan_row["name"],
            "error": outcome.error or "",
            "warnings": outcome.warnings_text(),
        })
        await interaction.followup.send(embed=embed, ephemeral=True)

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
    newpanelthread.error(_command_error)
    runweeklyreset.error(_command_error)

    resourcepanel_setup.autocomplete("clan")(_clan_autocomplete)
    setresourcepoints.autocomplete("clan")(_clan_autocomplete)
    resetwar.autocomplete("clan")(_clan_autocomplete)
    newpanelthread.autocomplete("clan")(_clan_autocomplete)
    runweeklyreset.autocomplete("clan")(_clan_autocomplete)


async def setup(bot: 'RuniClient'):
    await bot.add_cog(ClanWars(bot))

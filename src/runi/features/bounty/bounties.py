"""
bounties.py
~~~~~~~~~~~
The Bounty (daily quest) system for Runi.

Commands
--------
/bounty
    First use of the day: rolls 3 bounties and shows the board.
    Subsequent uses: shows live progress.

Background task
---------------
A ``tasks.loop`` fires at 02:00 CET every night and wipes all active
bounty rows so the next ``/bounty`` call starts fresh.

Progress hooks
--------------
``on_message``, ``on_command_completion`` and specialised helpers
(call ``increment_bounty_progress`` directly from Economy/Store cogs)
increment the per-user counters in the database and auto-claim completed
bounties, firing bonus payouts as needed.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo  # Python 3.9+

import discord
from discord import app_commands
from discord.ext import commands, tasks

from runi.features.bounty.bounty_bank import (
    BountyBank,
    BountyDefinition,
    STATUS_ACTIVE,
    STATUS_CLAIMED,
    STATUS_COMPLETED,
)
from runi.utils import log

if TYPE_CHECKING:
    from runi.main import RuniClient


# ---------------------------------------------------------------------------
# Module-level constants (tweak here, no logic changes needed elsewhere)
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# Daily reset time — 02:00 in Central European Time
RESET_HOUR   = 2
RESET_MINUTE = 0
RESET_TZ     = ZoneInfo("Europe/Stockholm")

# Bonus reward when all 3 bounties are completed in the same day
FULL_HOUSE_BONUS_RUNES: int = 150

# Number of bounty slots rolled per day
BOUNTY_SLOTS: int = 3

# Legendary item placeholder name — replace with a real item ID / store hook
LEGENDARY_ITEM_NAME: str = "Runic Artefact of Eternity"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _next_reset_dt() -> datetime.datetime:
    """
    Return the next 02:00 CET/CEST datetime from now (always in the future).
    If the current time is before 02:00 today, that is today's reset;
    otherwise it is tomorrow's.
    """
    now   = datetime.datetime.now(tz=RESET_TZ)
    today = now.replace(hour=RESET_HOUR, minute=RESET_MINUTE, second=0, microsecond=0)
    if now >= today:
        today += datetime.timedelta(days=1)
    return today


def _next_reset_unix() -> int:
    """Unix timestamp of the next daily reset, for Discord's <t:TS:R> format."""
    return int(_next_reset_dt().timestamp())


def _today_date_str() -> str:
    """
    The 'active date' for bounties: the calendar date in CET/CEST *after*
    the 02:00 reset.  So 01:59 on June 2 still belongs to June 1's bounties.
    """
    now = datetime.datetime.now(tz=RESET_TZ)
    # If we're before the reset hour, the active day is yesterday
    cutoff = now.replace(hour=RESET_HOUR, minute=RESET_MINUTE, second=0, microsecond=0)
    if now < cutoff:
        now -= datetime.timedelta(days=1)
    return now.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Legendary item award (placeholder — wire up to Store/inventory as needed)
# ---------------------------------------------------------------------------

async def _award_legendary_item(bot: "RuniClient", user_id: int, guild_id: int) -> str:
    """
    Award the legendary bounty item to a user.

    Currently a clean placeholder: logs the award and returns the item name.
    Replace the body with a real ``bot.db.add_store_item`` / inventory call
    when the legendary item exists in your item catalogue.

    Returns
    -------
    str
        The display name of the awarded item.
    """
    log.info(
        f"[Bounty] Legendary item '{LEGENDARY_ITEM_NAME}' awarded "
        f"to user {user_id} in guild {guild_id}."
    )
    # TODO: Replace with actual item grant, e.g.:
    #   item_id = await bot.db.get_legendary_bounty_item_id(guild_id)
    #   await bot.db.grant_item(user_id, guild_id, item_id)
    return LEGENDARY_ITEM_NAME


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Bounty(commands.Cog):
    """Daily bounty system — rolls quests, tracks progress, awards Runes."""

    def __init__(self, bot: "RuniClient") -> None:
        self.bot  = bot
        self.bank = BountyBank(DATA_DIR / "bounty_bank.csv")
        self.bank.load()
        self._reset_loop.start()

    def cog_unload(self) -> None:  # called when the cog is removed
        self._reset_loop.cancel()

    # ── Daily reset background task ────────────────────────────────────────────

    @tasks.loop(time=datetime.time(hour=RESET_HOUR, minute=RESET_MINUTE, tzinfo=RESET_TZ))
    async def _reset_loop(self) -> None:
        """Wipes all active bounty rows at 02:00 CET every night."""
        deleted = await self.bot.db.reset_all_bounties()
        log.info(f"[Bounty] Daily reset complete — {deleted} bounty row(s) cleared.")

    @_reset_loop.before_loop
    async def _before_reset_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ── /bounty ────────────────────────────────────────────────────────────────

    @commands.guild_only()
    @commands.hybrid_command(
        name="bounty",
        description="View your daily bounties or roll new ones if it's your first time today.",
    )
    async def bounty(self, ctx: commands.Context) -> None:
        await ctx.defer()

        guild = ctx.guild
        assert guild is not None

        today      = _today_date_str()
        user_id    = ctx.author.id
        guild_id   = guild.id

        existing = await self.bot.db.get_user_bounties(user_id, guild_id, today)

        if not existing:
            # ── First visit today: roll and store 3 bounties ──────────────────
            definitions = self.bank.roll(n=BOUNTY_SLOTS)
            await self.bot.db.assign_bounties(user_id, guild_id, today, definitions)

            embed = self._build_assigned_embed(definitions)
            await ctx.send(embed=embed)
        else:
            # ── Returning visit: show live progress board ─────────────────────
            embed = await self._build_progress_embed(ctx.author, existing)
            await ctx.send(embed=embed)

    # ── Embed builders ─────────────────────────────────────────────────────────

    def _build_assigned_embed(
        self, definitions: list[BountyDefinition]
    ) -> discord.Embed:
        """Confirmation embed shown immediately after rolling new bounties."""
        reset_ts = _next_reset_unix()
        embed = self.bot.embed_renderer.render(
            "bounty_assigned",
            {"reset_timestamp": f"<t:{reset_ts}:R>"},
        )
        for i, defn in enumerate(definitions, start=1):
            embed.add_field(
                name=f"Slot {i} — {defn.display_rarity}",
                value=(
                    f"{defn.description}\n"
                    f"Progress: `0 / {defn.target}`\n"
                    f"Reward: **{defn.reward:,} Runes**\n"
                    f"{STATUS_ACTIVE}"
                ),
                inline=False,
            )
        return embed

    async def _build_progress_embed(
        self,
        member: discord.Member | discord.User,
        rows: list[dict],
    ) -> discord.Embed:
        """
        Live progress board embed.

        ``rows`` is the list of dicts returned by ``db.get_user_bounties``.
        Each dict has: bounty_id, progress, reward_claimed, rarity,
        description, target, reward.
        """
        reset_ts        = _next_reset_unix()
        completed_count = sum(1 for r in rows if r["reward_claimed"])

        embed = self.bot.embed_renderer.render(
            "bounty_board",
            {
                "reset_timestamp": f"<t:{reset_ts}:R>",
                "completed_count": completed_count,
            },
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        for i, row in enumerate(rows, start=1):
            defn     = self.bank.get_by_id(row["bounty_id"])
            target   = defn.target if defn else row.get("target", 1)
            progress = row["progress"]
            is_done  = row["reward_claimed"]
            is_full  = progress >= target

            if is_done:
                status = STATUS_CLAIMED
                bar    = self._progress_bar(target, target)
            elif is_full:
                # Completed but not yet auto-claimed (edge case guard)
                status = STATUS_COMPLETED
                bar    = self._progress_bar(target, target)
            else:
                status = STATUS_ACTIVE
                bar    = self._progress_bar(progress, target)

            rarity_display = defn.display_rarity if defn else row.get("rarity", "?")
            description    = defn.description    if defn else row.get("description", "?")
            reward         = defn.reward         if defn else row.get("reward", 0)

            embed.add_field(
                name=f"Slot {i} — {rarity_display}",
                value=(
                    f"{description}\n"
                    f"`{bar}` {progress}/{target}\n"
                    f"Reward: **{reward:,} Runes** {status}"
                ),
                inline=False,
            )

        return embed

    @staticmethod
    def _progress_bar(current: int, total: int, width: int = 12) -> str:
        """ASCII progress bar, e.g.  `████████░░░░`"""
        if total <= 0:
            return "█" * width
        filled = min(width, int(width * current / total))
        return "█" * filled + "░" * (width - filled)

    # ── Progress increment (called by other cogs & listeners) ─────────────────

    async def increment_bounty_progress(
        self,
        user_id: int,
        guild_id: int,
        progress_type: str,
        amount: int = 1,
    ) -> None:
        """
        Increment a user's bounty progress counter for all active bounties
        that match ``progress_type``, then auto-claim any that just crossed
        their target threshold.

        This is the single entry-point for all progress tracking.  Other cogs
        should call ``self.bot.get_cog("Bounty").increment_bounty_progress(...)``
        rather than touching the database directly.

        Parameters
        ----------
        user_id:
            Discord user snowflake.
        guild_id:
            Discord guild snowflake.
        progress_type:
            Matches the ``type`` column in bounty_bank.csv
            (e.g. ``"message_count"``, ``"work_count"``).
        amount:
            How much to increment (default 1).
        """
        today = _today_date_str()
        rows  = await self.bot.db.get_user_bounties(user_id, guild_id, today)

        if not rows:
            return  # No active bounties today — nothing to do

        for row in rows:
            if row["reward_claimed"]:
                continue  # Already done

            defn = self.bank.get_by_id(row["bounty_id"])
            if defn is None or defn.type != progress_type:
                continue

            target      = defn.target
            new_progress = min(row["progress"] + amount, target)

            await self.bot.db.update_bounty_progress(
                user_id, guild_id, row["bounty_id"], today, new_progress
            )

            # Auto-claim when the target is first reached
            if new_progress >= target and not row["reward_claimed"]:
                await self._claim_bounty_reward(user_id, guild_id, defn, row["bounty_id"], today)

    async def _claim_bounty_reward(
        self,
        user_id: int,
        guild_id: int,
        defn: BountyDefinition,
        bounty_id: int,
        today: str,
    ) -> None:
        """
        Mark a bounty as claimed, award Runes (and legendary item if applicable),
        then check if the full-house bonus should fire.

        Rewards are applied silently (no DM / channel message) to avoid spam.
        The player sees the updated status on their next ``/bounty`` call.
        """
        await self.bot.db.mark_bounty_claimed(user_id, guild_id, bounty_id, today)
        await self.bot.db.add_runes(user_id, guild_id, defn.reward)

        log.info(
            f"[Bounty] User {user_id} claimed '{defn.description}' "
            f"({defn.rarity}) for {defn.reward:,} Runes."
        )

        if defn.is_legendary:
            item_name = await _award_legendary_item(self.bot, user_id, guild_id)
            log.info(f"[Bounty] Legendary item '{item_name}' granted to {user_id}.")

        # Check for full-house bonus
        await self._check_full_house(user_id, guild_id, today)

    async def _check_full_house(
        self, user_id: int, guild_id: int, today: str
    ) -> None:
        """
        Award the full-house bonus if all BOUNTY_SLOTS bounties are now claimed
        and the bonus has not already been paid out today.
        """
        rows = await self.bot.db.get_user_bounties(user_id, guild_id, today)
        if len(rows) < BOUNTY_SLOTS:
            return

        all_claimed = all(r["reward_claimed"] for r in rows)
        bonus_paid  = await self.bot.db.is_full_house_bonus_paid(user_id, guild_id, today)

        if all_claimed and not bonus_paid:
            await self.bot.db.set_full_house_bonus_paid(user_id, guild_id, today)
            await self.bot.db.add_runes(user_id, guild_id, FULL_HOUSE_BONUS_RUNES)
            log.info(
                f"[Bounty] Full-house bonus of {FULL_HOUSE_BONUS_RUNES:,} Runes "
                f"paid to user {user_id}."
            )

    # ── Event listeners ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Increment ``message_count`` bounties for every non-bot message sent
        in a guild.

        Only runs if the user already has bounties today — no DB write
        otherwise (``increment_bounty_progress`` returns early on empty rows).
        """
        if message.author.bot or message.guild is None:
            return

        await self.increment_bounty_progress(
            user_id=message.author.id,
            guild_id=message.guild.id,
            progress_type="message_count",
        )

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context) -> None:
        """
        Increment ``command_count`` bounties whenever any command succeeds.

        ``on_command_completion`` fires *after* a prefix/hybrid command
        invocation finishes without error.  For pure slash commands that
        never pass through the prefix pipeline you may also hook
        ``on_interaction`` — but hybrid commands (used throughout this bot)
        trigger this listener reliably.
        """
        if ctx.guild is None or ctx.author.bot:
            return

        await self.increment_bounty_progress(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            progress_type="command_count",
        )


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def setup(bot: "RuniClient") -> None:
    await bot.add_cog(Bounty(bot))

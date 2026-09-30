import asyncio
import time
from collections import defaultdict
from datetime import datetime, timedelta, UTC
from typing import Optional, TYPE_CHECKING

import discord
from discord import Message, app_commands
from discord.ext import commands

from runi.config import (
    BOUNTY_COMPLETION_BONUS_RATE,
    BOUNTY_DM_NOTIFICATIONS,
    BOUNTY_KEEP_SETS_DAYS,
    BOUNTY_MIN_BET,
    BOUNTY_PROGRESS_BAR_WIDTH,
    BOUNTY_RECENT_SETS_EXCLUDED,
    BOUNTY_REWARDS,
    BOUNTY_TIER_WEIGHTS,
)
from runi.features.bounty.bounty_pool import (
    POOL_BY_ID,
    apply_event,
    completion_bonus,
    new_slot,
    roll_bounties,
    slot_progress,
)
from runi.utils import log

if TYPE_CHECKING:
    from runi.main import RuniClient


TIER_LABELS = {
    "common": "🟢 Common",
    "epic": "🟣 Epic",
    "legendary": "🟠 Legendary",
}

# Commands tracked by the "explore" bounties (via on_command_completion)
EXPLORE_COMMANDS = {
    "maxsubstats", "health_formula", "damage_formula",
    "profile", "rank",
    "leaderboard", "richlist", "highroller",
}


def _fmt_time(seconds: float) -> str:
    """Turn a raw seconds float into a human-readable countdown string."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s or not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


def _seconds_until_reset(now: datetime) -> float:
    """Bounties reset at 00:00 UTC, same as /daily."""
    next_midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    return (next_midnight - now).total_seconds()


def _progress_bar(current: int, target: int) -> str:
    width = BOUNTY_PROGRESS_BAR_WIDTH
    filled = int(width * current / target) if target else width
    return "▰" * filled + "▱" * (width - filled)


def _slot_field(slot: dict) -> tuple[str, str, bool]:
    bounty = POOL_BY_ID[slot["id"]]
    label = TIER_LABELS[bounty.tier]

    if slot["completed"]:
        return (f"✅ {label} • {slot['reward']:,} :Runes:", f"~~{bounty.text}~~\nCompleted!", False)

    progress = slot_progress(slot)
    if len(progress) == 1:
        _, current, target = progress[0]
        lines = [f"{_progress_bar(current, target)} {current:,}/{target:,}"]
    else:
        lines = [
            f"{'✅' if current >= target else '▫️'} {part} — {current:,}/{target:,}"
            for part, current, target in progress
        ]

    return (f"{label} • {slot['reward']:,} :Runes:", "\n".join([bounty.text, *lines]), False)


def _bonus_field(bounty_set: dict) -> tuple[str, str, bool]:
    if bounty_set["bonus_paid"]:
        return ("🏆 Completion Bonus", f"~~{bounty_set['bonus']:,} :Runes:~~ Paid out!", False)
    return ("🏆 Completion Bonus", f"{bounty_set['bonus']:,} :Runes: for completing all three", False)


class Bounty(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot
        # One lock per user so overlapping events can't lose progress or pay twice
        self._locks: defaultdict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)

    # ── /bounty ────────────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_group(name="bounty", description="Daily bounties — complete them to earn Runes.", invoke_without_command=True)
    async def bounty(self, ctx: commands.Context):
        # Prefix usage without a subcommand (e.g. "!bounty") shows your status
        await self.bounty_status(ctx)

    # ── /bounty start ──────────────────────────────────────────────────────────
    @commands.guild_only()
    @bounty.command(name="start", description="Start today's bounties (once per day).")
    async def bounty_start(self, ctx: commands.Context):
        guild = ctx.guild
        assert guild is not None
        user = ctx.author

        bounty_set, started, completed, bonus_paid, now = await self._load_and_sync(user.id, guild.id, start=True)

        if started:
            description = (
                f"Here are today's bounties, **{user.display_name}**!\n"
                "Rewards are paid out automatically as you complete them.\n"
                "Track your progress with `/bounty status`."
            )
        else:
            description = f"You've already started today's bounties.\n{self._done_line(bounty_set)}"

        description += self._already_done_line(bounty_set, completed, bonus_paid)
        await ctx.send(embed=self._board_embed("bounty_started" if started else "bounty_board", user, bounty_set, description, now))

    # ── /bounty status ─────────────────────────────────────────────────────────
    @commands.guild_only()
    @bounty.command(name="status", description="Check your (or another member's) bounty progress.")
    @app_commands.describe(member="The member to check (leave blank for yourself).")
    async def bounty_status(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        guild = ctx.guild
        assert guild is not None
        target = member or ctx.author

        bounty_set, _, completed, bonus_paid, now = await self._load_and_sync(target.id, guild.id, start=False)

        if bounty_set is None:
            text = (
                "You haven't started today's bounties yet.\nUse `/bounty start` to begin!"
                if target.id == ctx.author.id
                else f"**{target.display_name}** hasn't started today's bounties yet."
            )
            embed = self.bot.embed_renderer.render("bounty_not_started", {"description": text})
            await ctx.send(embed=embed, ephemeral=True, delete_after=5)
            return

        description = self._done_line(bounty_set) + self._already_done_line(bounty_set, completed, bonus_paid)
        await ctx.send(embed=self._board_embed("bounty_board", target, bounty_set, description, now))

    # ── /bounty info ───────────────────────────────────────────────────────────
    @bounty.command(name="info", description="Learn how bounties work.")
    async def bounty_info(self, ctx: commands.Context):
        tiers = "\n".join(
            f"{TIER_LABELS[tier]} — {BOUNTY_TIER_WEIGHTS[tier]:.0%} chance • {BOUNTY_REWARDS[tier]:,} :Runes:"
            for tier in TIER_LABELS
        )
        embed = self.bot.embed_renderer.render("bounty_info", {
            "tiers": tiers,
            "bonus_rate": f"{BOUNTY_COMPLETION_BONUS_RATE:.0%}",
            "min_bet": BOUNTY_MIN_BET,
        })
        await ctx.send(embed=embed)

    # ── Board helpers ──────────────────────────────────────────────────────────
    async def _load_and_sync(self, user_id: int, guild_id: int, start: bool):
        """
        Load today's set (rolling a new one if `start` and none exists) and apply
        state-based progress. Returns (set or None, started_now, completed, bonus_paid, now).
        """
        async with self._locks[(user_id, guild_id)]:
            now = datetime.now(UTC)
            day = now.date().isoformat()

            bounty_set = await self.bot.db.get_bounty_set(user_id, guild_id, day)
            started = bounty_set is None and start

            if started:
                bounty_set = await self._roll(user_id, guild_id, now)
            if bounty_set is None:
                return None, False, [], False, now

            # C2 ("Claim your /daily") counts even if /daily was claimed before starting
            events = await self._state_events(user_id, guild_id, day)
            completed, bonus_paid, _ = await self._apply_events(bounty_set, user_id, guild_id, day, events)

        return bounty_set, started, completed, bonus_paid, now

    @staticmethod
    def _done_line(bounty_set: dict) -> str:
        done = sum(slot["completed"] for slot in bounty_set["slots"])
        return f"**{done}/{len(bounty_set['slots'])}** bounties completed today."

    @staticmethod
    def _already_done_line(bounty_set: dict, completed: list[dict], bonus_paid: bool) -> str:
        if not completed:
            return ""
        paid = sum(slot["reward"] for slot in completed) + (bounty_set["bonus"] if bonus_paid else 0)
        names = ", ".join(f"*{POOL_BY_ID[slot['id']].text}*" for slot in completed)
        return f"\n\n✅ Already done: {names} — **+{paid:,} :Runes:** paid out."

    def _board_embed(self, template: str, member, bounty_set: dict, description: str, now: datetime) -> discord.Embed:
        return self.bot.embed_renderer.render(template, {
            "username": member.display_name,
            "avatar": member.display_avatar.url,
            "description": description,
            "wait": _fmt_time(_seconds_until_reset(now)),
            "fields": [
                *(_slot_field(slot) for slot in bounty_set["slots"]),
                _bonus_field(bounty_set),
            ],
        })

    # ── Rolling ────────────────────────────────────────────────────────────────
    async def _roll(self, user_id: int, guild_id: int, now: datetime) -> dict:
        day = now.date().isoformat()

        recent = await self.bot.db.get_recent_bounty_ids(user_id, guild_id, day, BOUNTY_RECENT_SETS_EXCLUDED)
        hours_left = _seconds_until_reset(now) / 3600
        slots = [new_slot(b) for b in roll_bounties(recent, hours_left)]

        await self.bot.db.create_bounty_set(user_id, guild_id, day, slots, completion_bonus(slots))
        await self.bot.db.prune_bounty_sets((now.date() - timedelta(days=BOUNTY_KEEP_SETS_DAYS)).isoformat())

        return await self.bot.db.get_bounty_set(user_id, guild_id, day)

    async def _state_events(self, user_id: int, guild_id: int, day: str) -> list[dict]:
        """Events derived from stored state rather than live activity."""
        user = await self.bot.db.get_user(user_id, guild_id)
        if user["last_daily"] > 0 and datetime.fromtimestamp(user["last_daily"], UTC).date().isoformat() == day:
            return [{"type": "daily", "ts": time.time()}]
        return []

    # ── Progress ───────────────────────────────────────────────────────────────
    async def _apply_events(
        self, bounty_set: dict, user_id: int, guild_id: int, day: str, events: list[dict]
    ) -> tuple[list[dict], bool, int | None]:
        """
        Apply events to the set (in place), pay rewards and save.
        Returns (newly completed slots, whether the bonus was paid now, new balance or None).
        """
        slots = bounty_set["slots"]
        before = repr(slots)

        completed = [slot for event in events for slot in slots if apply_event(slot, event)]

        payout = sum(slot["reward"] for slot in completed)
        bonus_now = all(slot["completed"] for slot in slots) and not bounty_set["bonus_paid"]
        if bonus_now:
            payout += bounty_set["bonus"]
            bounty_set["bonus_paid"] = True

        if repr(slots) == before and not bonus_now:
            return [], False, None

        balance = await self.bot.db.save_bounty_progress(
            user_id, guild_id, day, slots, bounty_set["bonus_paid"], payout
        )
        return completed, bonus_now, balance

    async def _handle(
        self,
        member: discord.abc.User,
        guild: discord.Guild | None,
        event: dict,
        ctx: commands.Context | None = None,
    ):
        if guild is None or member.bot:
            return

        async with self._locks[(member.id, guild.id)]:
            now = datetime.now(UTC)
            day = now.date().isoformat()

            bounty_set = await self.bot.db.get_bounty_set(member.id, guild.id, day)
            if bounty_set is None or bounty_set["bonus_paid"]:
                return

            completed, bonus_now, balance = await self._apply_events(
                bounty_set, member.id, guild.id, day, [event]
            )

        if not completed and not bonus_now:
            return

        slots = bounty_set["slots"]
        done = sum(slot["completed"] for slot in slots)
        balance_before_bonus = balance - (bounty_set["bonus"] if bonus_now else 0)

        embeds = [
            self.bot.embed_renderer.render("bounty_complete", {
                "tier_label": TIER_LABELS[POOL_BY_ID[slot["id"]].tier],
                "text": POOL_BY_ID[slot["id"]].text,
                "reward": slot["reward"],
                "balance": balance_before_bonus,
                "done": done,
                "total": len(slots),
            })
            for slot in completed
        ]

        if bonus_now:
            embeds.append(self.bot.embed_renderer.render("bounty_set_complete", {
                "bonus": bounty_set["bonus"],
                "balance": balance,
                "wait": _fmt_time(_seconds_until_reset(now)),
            }))

        await self._notify(member, embeds, ctx)

    async def _notify(self, member: discord.abc.User, embeds: list[discord.Embed], ctx: commands.Context | None):
        """
        Tell only this member about their completed bounty.
        Slash commands get an ephemeral reply. Chat messages and prefix commands
        can't be answered ephemerally (Discord only allows that for interactions),
        so those get a DM if BOUNTY_DM_NOTIFICATIONS is on.
        """
        try:
            if ctx is not None and ctx.interaction is not None:
                await ctx.send(embeds=embeds, ephemeral=True)
            elif BOUNTY_DM_NOTIFICATIONS:
                await member.send(embeds=embeds)
        except discord.Forbidden:
            pass  # DMs closed — the reward is still paid and shows on /bounty status
        except discord.HTTPException as exc:
            log.error(f"Failed to notify {member} about a completed bounty: {exc}")

    # ── Event listeners ────────────────────────────────────────────────────────
    # Dispatched by the Economy and Leveling cogs after a successful action.

    @commands.Cog.listener()
    async def on_runi_work(self, ctx: commands.Context, data: dict):
        await self._handle(ctx.author, ctx.guild, {"type": "work", "ts": time.time(), **data}, ctx)

    @commands.Cog.listener()
    async def on_runi_daily(self, ctx: commands.Context, data: dict):
        await self._handle(ctx.author, ctx.guild, {"type": "daily", "ts": time.time(), **data}, ctx)

    @commands.Cog.listener()
    async def on_runi_coinflip(self, ctx: commands.Context, data: dict):
        await self._handle(ctx.author, ctx.guild, {"type": "coinflip", "ts": time.time(), **data}, ctx)

    @commands.Cog.listener()
    async def on_runi_slots(self, ctx: commands.Context, data: dict):
        await self._handle(ctx.author, ctx.guild, {"type": "slots", "ts": time.time(), **data}, ctx)

    @commands.Cog.listener()
    async def on_runi_xp(self, message: Message, xp: int):
        event = {
            "type": "xp",
            "ts": time.time(),
            "xp": xp,
            "channel_id": message.channel.id,
            "reply_to_member": await self._reply_target(message),
        }
        await self._handle(message.author, message.guild, event)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if ctx.command is None or ctx.command.qualified_name not in EXPLORE_COMMANDS:
            return

        targets_other = any(
            isinstance(arg, (discord.Member, discord.User)) and arg.id != ctx.author.id
            for arg in [*ctx.args, *ctx.kwargs.values()]
        )
        event = {"type": "command", "ts": time.time(), "name": ctx.command.qualified_name, "targets_other": targets_other}
        await self._handle(ctx.author, ctx.guild, event, ctx)

    @staticmethod
    async def _reply_target(message: Message) -> int | None:
        """ID of the member this message replies to (not a bot, not themselves), else None."""
        ref = message.reference
        if ref is None or ref.message_id is None:
            return None

        replied = ref.resolved
        if replied is None:
            try:
                replied = await message.channel.fetch_message(ref.message_id)
            except discord.HTTPException:
                return None

        if not isinstance(replied, Message) or replied.author.bot or replied.author.id == message.author.id:
            return None
        return replied.author.id


async def setup(bot: 'RuniClient'):
    await bot.add_cog(Bounty(bot))

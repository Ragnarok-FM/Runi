from typing import Optional, TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from runi.config import (
    WORK_COOLDOWN_SECONDS,
    DAILY_BASE,
    DAILY_STREAK_BONUS,
    DAILY_STREAK_MAX,
)

if TYPE_CHECKING:
    from runi.main import RuniClient


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


class Economy(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot

    @property
    def db(self):
        return self.bot.cogs  # accessed via bot reference below

    # ── /work ──────────────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_command(name="work", description="Work to earn Runes (once per hour).")
    async def work(self, ctx: commands.Context):
        guild = ctx.guild
        assert guild is not None
        result = await self.bot.db.do_work(ctx.author.id, guild.id)

        if not result["success"]:
            wait = _fmt_time(result["wait_seconds"])
            embed = self.bot.embed_renderer.render("work_cooldown", {"wait": wait})
            await ctx.send(embed=embed, ephemeral=True, delete_after=5)
            return

        embed = self.bot.embed_renderer.render("work_success", {
            "earned": result["earned"],
            "balance": result["balance"],
            "cooldown": _fmt_time(WORK_COOLDOWN_SECONDS),
        })
        await ctx.send(embed=embed)

    # ── /daily ─────────────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_command(name="daily", description="Claim your daily Runes reward.")
    async def daily(self, ctx: commands.Context):
        guild = ctx.guild
        assert guild is not None
        result = await self.bot.db.do_daily(ctx.author.id, guild.id)

        if not result["success"]:
            wait = _fmt_time(result["wait_seconds"])
            embed = self.bot.embed_renderer.render("daily_already_claimed", {"wait": wait})
            await ctx.send(embed=embed, ephemeral=True, delete_after=5)
            return

        streak = result["streak"]
        next_bonus = DAILY_STREAK_BONUS if streak < DAILY_STREAK_MAX else 0
        next_payout = DAILY_BASE + DAILY_STREAK_BONUS * min(streak, DAILY_STREAK_MAX - 1)

        # Build a small streak bar (filled/empty circles)
        display_max = 10
        filled = min(streak, display_max)
        streak_bar = "🔥" * filled + "⬜" * (display_max - filled)
        streak_label = f"Day {streak}" + (f"/{DAILY_STREAK_MAX}" if streak >= DAILY_STREAK_MAX else "")

        footer = (
            f"Tomorrow: {next_payout:,} :Runes: (+{next_bonus} streak bonus)"
            if streak < DAILY_STREAK_MAX
            else "Max streak reached! You're getting the full bonus every day."
        )

        embed = self.bot.embed_renderer.render("daily_claim", {
            "earned": result["earned"],
            "balance": result["balance"],
            "streak": streak,
            "streak_bar": streak_bar,
            "footer": footer,
        })

        await ctx.send(embed=embed)

    # ── /balance ───────────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_command(name="balance", description="Check your (or another user's) Runes balance.")
    @app_commands.describe(member="The member to check (leave blank for yourself).")
    async def balance(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        target = member or ctx.author

        guild = ctx.guild
        assert guild is not None
        user = await self.bot.db.get_user(target.id, guild.id)

        embed = self.bot.embed_renderer.render("balance", {
            "username": target.display_name,
            "runes": user["runeshards"],
            "daily_streak": user["daily_streak"],
            "avatar": target.display_avatar.url,
        })

        await ctx.send(embed=embed)

    # ── /coinflip ──────────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_command(name="coinflip", description="Bet your Runes on a coin flip!")
    @app_commands.describe(choice="Pick heads or tails.", bet="How many Runes to bet.")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Heads", value="heads"),
        app_commands.Choice(name="Tails", value="tails"),
    ])
    async def coinflip(self, ctx: commands.Context, choice: app_commands.Choice[str], bet: int):
        if bet <= 0:
            embed = self.bot.embed_renderer.render("coinflip_invalid_bet", {})
            await ctx.send(embed=embed, ephemeral=True, delete_after=5)
            return

        guild = ctx.guild
        assert guild is not None

        result = await self.bot.db.coinflip(ctx.author.id, guild.id, bet, choice.value)

        if not result["success"]:
            embed = self.bot.embed_renderer.render("error_insufficient_funds", {
                "balance": result["balance"]
            })
            await ctx.send(embed=embed, ephemeral=True, delete_after=5)
            return;

        result_label = result["result"].capitalize()

        outcome = "You Won!" if result["won"] else "You Lost!"

        description = (
            f"You bet on **{choice.name}** and won **{result['change']:,} :Runes:**!"
            if result["won"]
            else f"You bet on **{choice.name}** but it landed on **{result_label}**. You lost {result['change']:,} :Runes:."
        )

        embed = self.bot.embed_renderer.render("coinflip_result", {
            "result": result_label,
            "outcome": outcome,
            "description": description,
            "balance": result["balance"]
        })

        await ctx.send(embed=embed)

    # ── /richlist ──────────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_command(name="richlist", description="See the wealthiest members on this server.")
    async def richlist(self, ctx: commands.Context):
        await ctx.defer()

        guild = ctx.guild
        assert guild is not None

        rows = await self.bot.db.get_rich_list(guild.id, limit=10)

        medals = [":Runi_Gold:", ":Runi_Silver:", ":Runi_Bronze:"]

        members = []
        runes = []
        streaks = []

        for i, row in enumerate(rows):
            member = guild.get_member(row["user_id"])
            name = member.display_name if member else f"Unknown ({row['user_id']})"

            rank = medals[i] if i < 3 else f"`{i + 1}.`"

            members.append(f"{rank} **{name}**")
            runes.append(f":Runes: {row['runeshards']:,}")
            streaks.append(f"🔥 {row['daily_streak']}")

        if not rows:
            members.append("No data yet")
            runes.append("-")
            streaks.append("-")

        embed = self.bot.embed_renderer.render("richlist", {
            "fields": [
                ("Member", "\n".join(members), True),
                ("Runes", "\n".join(runes), True),
                ("Streak", "\n".join(streaks), True)
            ]
        })

        await ctx.send(embed=embed)

    # ── /give ──────────────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_command(name="give", description="Give Runes to another user (admin-only).")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(member="The user to give Runes to.", amount="How many Runes to give.")
    @app_commands.default_permissions(administrator=True)
    async def give(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount <= 0:
            embed = self.bot.embed_renderer.render("give_invalid_amount", {})
            await ctx.send(embed=embed, ephemeral=True, delete_after=5)
            return

        guild = ctx.guild
        assert guild is not None

        result = await self.bot.db.add_runes(member.id, guild.id, amount)

        embed = self.bot.embed_renderer.render("give_success", {
            "receiver": member.display_name,
            "amount": amount,
            "balance": result["balance"]
        })

        await ctx.send(embed=embed)

    # ── /giveall ───────────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_command(name="giveall", description="Give Runes to all guild members or a specific role (admin-only).")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(amount="How many Runes to give to each member.", role="Optional: Give Runes only to members with this role.")
    @app_commands.default_permissions(administrator=True)
    async def giveall(self, ctx: commands.Context, amount: int, role: discord.Role = None):
        if amount <= 0:
            embed = self.bot.embed_renderer.render("give_invalid_amount", {})
            await ctx.send(embed=embed, ephemeral=True, delete_after=5)
            return

        await ctx.defer()

        guild = ctx.guild
        assert guild is not None

        if role:
            member_ids = [member.id for member in role.members if not member.bot]
            role_name = role.name
        else:
            member_ids = [member.id for member in guild.members if not member.bot]
            role_name = "all members"

        if not member_ids:
            embed = self.bot.embed_renderer.render("giveall_no_members", {
                "target": role_name
            })
            await ctx.send(embed=embed, ephemeral=True, delete_after=5)
            return

        result = await self.bot.db.add_runes_to_all(guild.id, member_ids, amount)

        embed = self.bot.embed_renderer.render("giveall_success", {
            "amount": amount,
            "total_members": result["total_members"],
            "total_distributed": result["total_distributed"],
            "target": role_name
        })

        await ctx.send(embed=embed)

    # ── /take ──────────────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_command(name="take", description="Take Runes from a user (admin-only).")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(member="The user to take Runes from.", amount="How many Runes to take.")
    @app_commands.default_permissions(administrator=True)
    async def take(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount <= 0:
            embed = self.bot.embed_renderer.render("take_invalid_amount", {})
            await ctx.send(embed=embed, ephemeral=True, delete_after=5)
            return

        guild = ctx.guild
        assert guild is not None

        result = await self.bot.db.remove_runes(member.id, guild.id, amount)

        if not result["success"] and result["reason"] == "insufficient_funds":
            embed = self.bot.embed_renderer.render("take_insufficient_funds", {
                "balance": result["balance"],
                "member": member.display_name
            })
            await ctx.send(embed=embed, ephemeral=True, delete_after=5)
            return

        embed = self.bot.embed_renderer.render("take_success", {
            "member": member.display_name,
            "amount": amount,
            "balance": result["balance"]
        })

        await ctx.send(embed=embed)

    # ── Error handler ──────────────────────────────────────────────────────────
    @give.error
    @giveall.error
    @take.error
    async def admin_error(self, ctx: commands.Context, error):
        error = getattr(error, "original", error)
        if isinstance(error, commands.MissingPermissions):
            embed = self.bot.embed_renderer.render("error_missing_admin_permissions", {})
            await ctx.send(embed=embed, ephemeral=True, delete_after=5)

async def setup(bot: 'RuniClient'):
    await bot.add_cog(Economy(bot))

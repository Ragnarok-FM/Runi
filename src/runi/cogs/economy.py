from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from runi.config import (
    WORK_COOLDOWN_SECONDS,
    DAILY_BASE,
    DAILY_STREAK_BONUS,
    DAILY_STREAK_MAX,
)
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
    @app_commands.guild_only()
    @app_commands.command(name="work", description="Work to earn Runes (once per hour).")
    async def work(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        assert guild_id is not None
        result = await self.bot.db.do_work(interaction.user.id, guild_id)

        if not result["success"]:
            wait = _fmt_time(result["wait_seconds"])
            embed = self.bot.embed_renderer.render("work_cooldown", {"wait": wait})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = self.bot.embed_renderer.render("work_success", {
            "earned": result["earned"],
            "balance": result["balance"],
            "cooldown": _fmt_time(WORK_COOLDOWN_SECONDS),
        })
        await interaction.response.send_message(embed=embed)

    # ── /daily ─────────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="daily", description="Claim your daily Runeshard reward.")
    async def daily(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        assert guild_id is not None
        result = await self.bot.db.do_daily(interaction.user.id, guild_id)

        if not result["success"]:
            wait = _fmt_time(result["wait_seconds"])
            embed = self.bot.embed_renderer.render("daily_already_claimed", {"wait": wait})
            await interaction.response.send_message(embed=embed, ephemeral=True)
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
            f"Tomorrow: {next_payout:,} Runes (+{next_bonus} streak bonus)"
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

        await interaction.response.send_message(embed=embed)

    # ── /balance ───────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="balance", description="Check your (or another user's) Runeshard balance.")
    @app_commands.describe(member="The member to check (leave blank for yourself).")
    async def balance(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user

        guild_id = interaction.guild_id
        assert guild_id is not None
        user = await self.bot.db.get_user(target.id, guild_id)

        embed = self.bot.embed_renderer.render("balance", {
            "username": target.display_name,
            "runeshards": user["runeshards"],
            "daily_streak": user["daily_streak"],
            "avatar": target.display_avatar.url,
        })

        await interaction.response.send_message(embed=embed)

    # ── /coinflip ──────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="coinflip", description="Bet your Runes on a coin flip!")
    @app_commands.describe(
        choice="Pick heads or tails.",
        bet="How many Runes to bet.",
    )
    @app_commands.choices(choice=[
        app_commands.Choice(name="Heads", value="heads"),
        app_commands.Choice(name="Tails", value="tails"),
    ])
    async def coinflip(self, interaction: discord.Interaction, choice: app_commands.Choice[str], bet: int):
        if bet <= 0:
            embed = self.bot.embed_renderer.render("coinflip_invalid_bet", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        guild_id = interaction.guild_id
        assert guild_id is not None

        result = await self.bot.db.coinflip(interaction.user.id, guild_id, bet, choice.value)

        if not result["success"]:
            embed = self.bot.embed_renderer.render("error_insufficient_funds", {
                "balance": result["balance"]
            })
            await interaction.response.send_message(embed=embed, ephemeral=True)

        coin_emoji = "🪙"
        result_label = result["result"].capitalize()

        outcome = "You Won!" if result["won"] else "You Lost!"

        description = (
            f"You bet on **{choice.name}** and won **{result['change']:,} Runes**!"
            if result["won"]
            else f"You bet on **{choice.name}** but it landed on **{result_label}**. You lost {result['change']:,} Runes."
        )

        embed = self.bot.embed_renderer.render("coinflip_result", {
            "result": result_label,
            "outcome": outcome,
            "description": description,
            "balance": result["balance"]
        })

        await interaction.response.send_message(embed=embed)

    # ── /richlist ──────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="richlist", description="See the wealthiest members on this server.")
    async def richlist(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild = interaction.guild
        assert guild is not None

        rows = await self.bot.db.get_rich_list(guild.id, limit=10)

        medals = ["🥇", "🥈", "🥉"]
        lines = []

        for i, row in enumerate(rows):
            member = guild.get_member(row["user_id"])
            name = member.display_name if member else f"Unknown ({row['user_id']})"
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            streak_str = f"  🔥 {row['daily_streak']}" if row["daily_streak"] > 1 else ""
            lines.append(f"{medal} **{name}** — {row['runeshards']:,} Runes{streak_str}")

        content = "\n".join(lines) if lines else "No data yet — get earning!"
        embed = self.bot.embed_renderer.render("richlist", {
            "content": content
        })

        await interaction.followup.send(embed=embed)

    # ── /give ──────────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="give", description="Give some of your Runes to another user.")
    @app_commands.describe(member="The user to give Runes to.", amount="How many Runes to give.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def give(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            embed = self.bot.embed_renderer.render("give_invalid_amount", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        guild_id = interaction.guild_id
        assert guild_id is not None

        result = await self.bot.db.transfer_runes(
            interaction.user.id, member.id, guild_id, amount
        )

        if result["reason"] == "self_transfer":
            embed = self.bot.embed_renderer.render("give_self_transfer", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if result["reason"] == "insufficient_funds":
            embed = self.bot.embed_renderer.render("error_insufficient_funds", {
                "balance": result["balance"]
            })
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = self.bot.embed_renderer.render("give_success", {
            "sender": interaction.user.display_name,
            "receiver": member.display_name,
            "amount": amount,
            "balance": result["from_balance"]
        })

        await interaction.response.send_message(embed=embed)

    # ── Error handler ──────────────────────────────────────────────────────────
    @give.error
    async def admin_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = self.bot.embed_renderer.render("error_missing_admin_permissions", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: 'RuniClient'):
    await bot.add_cog(Economy(bot))

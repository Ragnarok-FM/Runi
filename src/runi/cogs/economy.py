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

# TODO: Use embed templates for all responses in this cog
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
            self.bot.embed_renderer.render("work_cooldown", {"wait": wait})
            embed = discord.Embed(
                title="⏳ Still Tired",
                description=f"You need to rest before working again.\nCome back in {wait}.",
                color=discord.Color(0xF1C40F),
            )
            embed.set_footer(text="Runi • Economy")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="⚒️ Work Complete",
            description=(
                f"You worked hard and earned {result['earned']:,} Runes 💎\n"
                f"Balance: {result['balance']:,} Runes"
            ),
            color=discord.Color(0xF1C40F),
        )
        embed.set_footer(text=f"Runi • Economy | You can work again in {_fmt_time(WORK_COOLDOWN_SECONDS)}.")
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
            embed = discord.Embed(
                title="⏳ Already Claimed",
                description=f"You've already claimed today's reward.\nCome back in {wait}.",
                color=discord.Color(0xF1C40F),
            )
            embed.set_footer(text="Runi • Economy")
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

        embed = discord.Embed(
            title="🗓️ Daily Reward Claimed!",
            color=discord.Color(0xF1C40F),
        )
        embed.add_field(
            name="Earned",
            value=f"{result['earned']:,} Runes 💎",
            inline=True,
        )
        embed.add_field(
            name="Balance",
            value=f"{result['balance']:,} Runes",
            inline=True,
        )
        embed.add_field(
            name=f"Streak — Day {streak}",
            value=streak_bar,
            inline=False,
        )
        if streak < DAILY_STREAK_MAX:
            embed.set_footer(text=f"Runi • Economy | Tomorrow: {next_payout:,} Runes (+{next_bonus} streak bonus)")
        else:
            embed.set_footer(text="Runi • Economy | Max streak reached! You're getting the full bonus every day.")

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

        embed = discord.Embed(
            title=f"💎 {target.display_name}'s Wallet",
            color=discord.Color(0xF1C40F),
        )
        embed.add_field(name="Runes", value=f"{user['runeshards']:,}", inline=True)
        embed.add_field(name="Daily Streak", value=f"{user['daily_streak']} 🔥", inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Runi • Economy")
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
            await interaction.response.send_message(
                embed=discord.Embed(description="Bet must be greater than 0.", color=discord.Color(0xF1C40F)),
                ephemeral=True,
            )
            return

        guild_id = interaction.guild_id
        assert guild_id is not None

        result = await self.bot.db.coinflip(interaction.user.id, guild_id, bet, choice.value)

        if not result["success"]:
            embed = discord.Embed(
                title="❌ Not Enough Runes",
                description=f"You only have {result['balance']:,} Runes.",
                color=discord.Color(0xF1C40F),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        coin_emoji = "🪙"
        result_label = result["result"].capitalize()

        if result["won"]:
            embed = discord.Embed(
                title=f"{coin_emoji} {result_label} — You Won!",
                description=f"You bet on **{choice.name}** and won **{result['change']:,} Runes**!",
                color=discord.Color(0xF1C40F),
            )
        else:
            embed = discord.Embed(
                title=f"{coin_emoji} {result_label} — You Lost!",
                description=f"You bet on **{choice.name}** but it landed on **{result_label}**. You lost {result['change']:,} Runes.",
                color=discord.Color(0xF1C40F),
            )

        embed.add_field(name="Balance", value=f"{result['balance']:,} Runes", inline=True)
        embed.set_footer(text="Runi • Economy")
        await interaction.response.send_message(embed=embed)

    # ── /richlist ──────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="richlist", description="See the wealthiest members on this server.")
    async def richlist(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild = interaction.guild
        assert guild is not None

        rows = await self.bot.db.get_rich_list(guild.id, limit=10)

        embed = discord.Embed(
            title="💰 Runeshard Rich List",
            color=discord.Color(0xF1C40F),
        )

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(rows):
            member = guild.get_member(row["user_id"])
            name = member.display_name if member else f"Unknown ({row['user_id']})"
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            streak_str = f"  🔥 {row['daily_streak']}" if row["daily_streak"] > 1 else ""
            lines.append(f"{medal} **{name}** — {row['runeshards']:,} Runes{streak_str}")

        embed.description = "\n".join(lines) if lines else "No data yet — get earning!"
        embed.set_footer(text="Runi • Economy")
        await interaction.followup.send(embed=embed)

    # ── /give ──────────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="give", description="Give some of your Runes to another user.")
    @app_commands.describe(member="The user to give Runes to.", amount="How many Runes to give.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def give(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message(
                embed=discord.Embed(description="Amount must be greater than 0.", color=discord.Color(0xF1C40F)),
                ephemeral=True,
            )
            return

        guild_id = interaction.guild_id
        assert guild_id is not None

        result = await self.bot.db.transfer_runes(
            interaction.user.id, member.id, guild_id, amount
        )

        if result["reason"] == "self_transfer":
            embed = discord.Embed(
                title="❌ Nice Try",
                description="You can't give Runes to yourself!",
                color=discord.Color(0xF1C40F),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if result["reason"] == "insufficient_funds":
            embed = discord.Embed(
                title="❌ Not Enough Runes",
                description=f"You only have {result['balance']:,} Runes.",
                color=discord.Color(0xF1C40F),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="💸 Runes Sent!",
            description=f"{interaction.user.display_name} gave **{amount:,} Runes** to {member.display_name}!",
            color=discord.Color(0xF1C40F),
        )
        embed.add_field(name="Your new balance", value=f"{result['from_balance']:,} Runes", inline=True)
        embed.set_footer(text="Runi • Economy")
        await interaction.response.send_message(embed=embed)

    # ── Error handler ──────────────────────────────────────────────────────────
    @give.error
    async def admin_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need Administrator permissions to use this command.",
                ephemeral=True,
            )

async def setup(bot: 'RuniClient'):
    await bot.add_cog(Economy(bot))

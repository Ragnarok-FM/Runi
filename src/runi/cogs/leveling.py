from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from runi.main import RuniClient
from runi.config import XP_FOR_LEVEL, XP_PER_MESSAGE, XP_COOLDOWN_SECONDS

# TODO: Use embed templates for all responses in this cog
class Leveling(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot

    # ── /profile ───────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="profile", description="View your full profile — level, XP, Runes and more.")
    @app_commands.describe(member="The member to view (leave blank for yourself).")
    async def profile(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = member or interaction.user
        guild_id = interaction.guild_id
        assert guild_id is not None

        user = await self.bot.db.get_user(target.id, guild_id)
        inventory = await self.bot.db.get_inventory(target.id, guild_id)

        level = user["level"]
        xp = user["xp"]
        xp_needed_next = XP_FOR_LEVEL(level + 1)
        xp_needed_current = XP_FOR_LEVEL(level)
        xp_into_level = xp - xp_needed_current
        xp_span = xp_needed_next - xp_needed_current

        # Progress bar
        bar_width = 18
        filled = int(bar_width * xp_into_level / xp_span) if xp_span else bar_width
        bar = "█" * filled + "░" * (bar_width - filled)

        embed = self.bot.embed_renderer.render("profile", {
            "username": target.display_name,
            "avatar": target.display_avatar.url,
            "level": level,
            "xp": xp,
            "runeshards": user["runeshards"],
            "next_level": level + 1,
            "bar": bar,
            "xp_into_level": xp_into_level,
            "xp_span": xp_span,
            "daily_streak": user["daily_streak"],
            "item_count": len(inventory),
        })

        if inventory:
            item_list = ", ".join(i["name"] for i in inventory[:5])
            if len(inventory) > 5:
                item_list += f" + {len(inventory) - 5} more"
            embed.add_field(name="Inventory", value=item_list, inline=False)

        await interaction.followup.send(embed=embed)

    # ── /rank ──────────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="rank", description="Check your (or another user's) level and XP.")
    @app_commands.describe(member="The member to check (leave blank for yourself).")
    async def rank(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        guild_id = interaction.guild_id
        assert guild_id is not None
        user = await self.bot.db.get_user(target.id, guild_id)

        level = user["level"]
        xp = user["xp"]
        xp_needed_next = XP_FOR_LEVEL(level + 1)
        xp_needed_current = XP_FOR_LEVEL(level)
        xp_into_level = xp - xp_needed_current
        xp_span = xp_needed_next - xp_needed_current

        # Progress bar (20 chars wide)
        bar_width = 20
        filled = int(bar_width * xp_into_level / xp_span) if xp_span else bar_width
        bar = "█" * filled + "░" * (bar_width - filled)

        embed = self.bot.embed_renderer.render("rank", {
            "username": target.display_name,
            "avatar": target.display_avatar.url,
            "level": level,
            "xp": xp,
            "next_level": level + 1,
            "bar": bar,
            "xp_into_level": xp_into_level,
            "xp_span": xp_span,
        })

        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ───────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="leaderboard", description="See the top members by level on this server.")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild = interaction.guild;
        assert guild is not None
        rows = await self.bot.db.get_leaderboard(guild.id, limit=10)

        medals = ["🥇", "🥈", "🥉"]
        lines = []

        for i, row in enumerate(rows):
            member = guild.get_member(row["user_id"])
            name = member.display_name if member else f"Unknown ({row['user_id']})"
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(
                f"{medal} **{name}** — Level {row['level']} ({row['xp']:,} XP)"
            )

        embed = self.bot.embed_renderer.render("xp_leaderboard", {
            "content": "\n".join(lines) if lines else "No data yet — start chatting!",
            "xp_per_message": XP_PER_MESSAGE,
            "cooldown": int(XP_COOLDOWN_SECONDS),
        })

        await interaction.followup.send(embed=embed)


async def setup(bot: 'RuniClient'):
    await bot.add_cog(Leveling(bot))

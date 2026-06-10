from typing import Optional, TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from runi.config import XP_FOR_LEVEL, XP_PER_MESSAGE, XP_COOLDOWN_SECONDS

if TYPE_CHECKING:
    from runi.main import RuniClient


class Leveling(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot

    # ── /profile ───────────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_command(name="profile", description="View your full profile — level, XP, Runes and more.")
    @app_commands.describe(member="The member to view (leave blank for yourself).")
    async def profile(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        await ctx.defer()
        target = member or ctx.author
        guild = ctx.guild
        assert guild is not None

        user = await self.bot.db.get_user(target.id, guild.id)
        inventory = await self.bot.db.get_inventory(target.id, guild.id)

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

        await ctx.send(embed=embed)

    # ── /rank ──────────────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_command(name="rank", description="Check your (or another user's) level and XP.")
    @app_commands.describe(member="The member to check (leave blank for yourself).")
    async def rank(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        target = member or ctx.author

        guild = ctx.guild
        assert guild is not None
        user = await self.bot.db.get_user(target.id, guild.id)

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

        await ctx.send(embed=embed)

    # ── /leaderboard ───────────────────────────────────────────────────────────
    @commands.guild_only()
    @commands.hybrid_command(name="leaderboard", description="See the top members by level on this server.")
    async def leaderboard(self, ctx: commands.Context):
        await ctx.defer()

        guild = ctx.guild
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

        await ctx.send(embed=embed)

    # ── Automatic Role Assignment ──────────────────────────────────────────────
    async def update_member_level_role(self, member: discord.Member, new_level: int):
      """
      Checks the member's new level, assigns the correct clan role, and removes obsolete tier roles.
      """
      role_mapping = {
          1: 1481953469303885855,  # Iron Soldier
          10: 1481953468645249024, # Raidborn Warrior
          20: 1481953465281417377, # Storm Champion
          40: 1481954033538306210, # Runeforge Elite
          60: 1481954028383633490  # Ascendant of Runi
      }

      role_id_to_add = None
      for lvl, r_id in sorted(role_mapping.items()):
          if new_level >= lvl:
              role_id_to_add = r_id

      if not role_id_to_add:
          return

      guild = member.guild
      target_role = guild.get_role(role_id_to_add)

      roles_to_remove = []
      for lvl, r_id in role_mapping.items():
          if r_id != role_id_to_add:
              old_role = guild.get_role(r_id)
              if old_role and old_role in member.roles:
                  roles_to_remove.append(old_role)

      if roles_to_remove:
          try:
              await member.remove_roles(*roles_to_remove, reason=f"Upgraded to new tier based on level {new_level}")
          except discord.Forbidden:
              print(f"ERROR: Bot lacks permissions to remove roles from {member.display_name}")

      if target_role and target_role not in member.roles:
          try:
              await member.add_roles(target_role, reason=f"Reached level {new_level}")
          except discord.Forbidden:
              print(f"ERROR: Bot lacks permissions to add role to {member.display_name}")

async def setup(bot: 'RuniClient'):
    await bot.add_cog(Leveling(bot))

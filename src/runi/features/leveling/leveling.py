from typing import Optional, TYPE_CHECKING

import discord
from discord import Message, app_commands
from discord.ext import commands

from runi.config import XP_FOR_LEVEL, XP_PER_MESSAGE, XP_COOLDOWN_SECONDS
from runi.utils import log

if TYPE_CHECKING:
    from runi.main import RuniClient


class Leveling(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot
        self.role_mapping = {
            1: "Iron Soldier",
            10: "Raidborn Warrior",
            20: "Storm Champion",
            40: "Runeforge Elite",
            60: "Ascendant of Runi",
        }

    async def ensure_tier_roles(self, guild: discord.Guild):
        for lvl, role_name in sorted(self.role_mapping.items(), reverse=True):
            existing_role = discord.utils.get(guild.roles, name=role_name)
            if not existing_role:
                try:
                    await guild.create_role(
                        name=role_name, 
                        reason="Setting up level tier roles",
                        mentionable=False,
                        hoist=True
                    )
                except discord.Forbidden:
                    log.error(f"Bot lacks permissions to create role '{role_name}' on guild {guild.name}")
                except Exception as e:
                    log.error(f"Failed to create role '{role_name}' on guild {guild.name}: {e}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.ensure_tier_roles(guild)

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
        Creates roles if they don't exist on the server.
        """
        guild = member.guild

        await self.ensure_tier_roles(guild)

        target_role_name = None
        for level, role_name in sorted(self.role_mapping.items()):
            if new_level >= level:
                target_role_name = role_name

        if not target_role_name:
            return

        target_role = discord.utils.get(guild.roles, name=target_role_name)
        if not target_role:
            await self._ensure_tier_roles(guild)

            target_role = discord.utils.get(guild.roles, name=target_role_name)
            if not target_role:
                log.error(f"Failed to find or create role '{target_role_name}'")
                return

        try:
            if target_role not in member.roles:
                await member.add_roles(target_role, reason=f"Reached level {new_level}")

            roles_to_remove = [discord.utils.get(guild.roles, name=role_name) for role_name in self.role_mapping.values() if role_name != target_role_name]
            roles_to_remove = [role for role in roles_to_remove if role and role in member.roles]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Level tier update ({new_level})")
        except discord.Forbidden:
            log.error(f"Cannot modify roles for {member} (permission or hierarchy issue)")
        except discord.HTTPException as exc:
            log.error(f"Failed updating roles for {member}: {exc}")

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            return
        
        result = await self.bot.db.add_xp(message.author.id, message.guild.id)
        if result["leveled_up"]:
            embed = self.bot.embed_renderer.render("level_up", {
                "username": message.author.display_name,
                "new_level": result["new_level"],
                "avatar": message.author.display_avatar.url
            })
            await message.channel.send(embed=embed)
            await self.update_member_level_role(message.author, result["new_level"])

async def setup(bot: 'RuniClient'):
    await bot.add_cog(Leveling(bot))

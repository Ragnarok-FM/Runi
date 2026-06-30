import discord
from discord.ext import commands


class EmojiRegistry:
    def __init__(self):
        self._emojis: dict[str, discord.Emoji] = {}

    async def load(self, bot: commands.Bot) -> None:
        self._emojis = {
            emoji.name: emoji
            for emoji in await bot.fetch_application_emojis()
        }

    def get(self, name: str) -> str:
        emoji = self._emojis.get(name)
        return str(emoji) if emoji else f":{name}:"
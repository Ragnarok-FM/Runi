import re

import discord

from runi.utils import colors
from runi.utils.text_utils import truncate, SafeDict
from runi.features import embeds


MAX_TITLE = 256
MAX_DESCRIPTION = 4096
MAX_FIELDS = 25

EMOJI_PATTERN = re.compile(r':([a-zA-Z0-9_]+):')

class EmbedRenderer:
    def __init__(self, emoji_registry=None):
        self.emoji_registry = emoji_registry

    def _replace_emojis(self, text: str) -> str:
        if not text or not self.emoji_registry:
            return text
        
        def replace_emoji(match):
            emoji_name = match.group(1)
            return self.emoji_registry.get(emoji_name)
        
        return EMOJI_PATTERN.sub(replace_emoji, text)

    def _format(self, template: str | None, data: dict) -> str | None:
        if template is None:
            return None
        
        formatted = template.format_map(SafeDict(data))
        return self._replace_emojis(formatted)


    def render(self, template_name: str, data: dict) -> discord.Embed:
        if template_name not in embeds:
            raise ValueError(f"Template '{template_name}' not found")

        template = embeds[template_name]

        title = truncate(self._format(template.get("title"), data), MAX_TITLE)
        description = truncate(self._format(template.get("description"), data), MAX_DESCRIPTION)

        embed = discord.Embed(
            title=title,
            description=description,
            color= colors.get_color(template.get("color"))
        )

        for i, field in enumerate(template.get("fields", [])):
            if i >= MAX_FIELDS:
                break

            name, value, inline = field

            embed.add_field(
                name=truncate(self._format(name, data), 256),
                value=truncate(self._format(value, data), 1024),
                inline=inline
            )

        if "author" in template:
            author = template["author"]
            embed.set_author(
                name=self._format(author.get("name"), data),
                icon_url=self._format(author.get("icon_url"), data)
            )

        if "thumbnail" in template:
            embed.set_thumbnail(url=self._format(template["thumbnail"], data))

        if "image" in template:
            embed.set_image(url=self._format(template["image"], data))

        if "footer" in template:
            embed.set_footer(text=self._format(template["footer"], data))

        if template.get("timestamp"):
            embed.timestamp = discord.utils.utcnow()

        return embed
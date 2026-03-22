import discord
from .colors import COLOR_MAP
from .text_utils import truncate, SafeDict
from ..templates import templates


MAX_TITLE = 256
MAX_DESCRIPTION = 4096
MAX_FIELDS = 25


class EmbedRenderer:
    def _format(self, template: str | None, data: dict) -> str | None:
        if template is None:
            return None
        
        return template.format_map(SafeDict(data))

    def render(self, template_name: str, data: dict) -> discord.Embed:
        if template_name not in templates:
            raise ValueError(f"Template '{template_name}' not found")

        template = templates[template_name]

        title = truncate(self._format(template.get("title"), data), MAX_TITLE)
        description = truncate(self._format(template.get("description"), data), MAX_DESCRIPTION)

        embed = discord.Embed(
            title=title,
            description=description,
            color=COLOR_MAP.get(template.get("color"), discord.Color.blurple())
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

        if "thumbnail" in template:
            embed.set_thumbnail(url=self._format(template["thumbnail"], data))

        if "image" in template:
            embed.set_image(url=self._format(template["image"], data))

        if "footer" in template:
            embed.set_footer(text=self._format(template["footer"], data))

        if template.get("timestamp"):
            embed.timestamp = discord.utils.utcnow()

        return embed
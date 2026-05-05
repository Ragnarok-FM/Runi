import discord


COLOR_MAP = {
    "default": discord.Color.default(),
    "random": discord.Color.random(),

    # Teals / greens
    "teal": discord.Color.teal(),
    "dark_teal": discord.Color.dark_teal(),
    "brand_green": discord.Color.brand_green(),
    "green": discord.Color.green(),
    "dark_green": discord.Color.dark_green(),

    # Blues / purples
    "blue": discord.Color.blue(),
    "dark_blue": discord.Color.dark_blue(),
    "purple": discord.Color.purple(),
    "dark_purple": discord.Color.dark_purple(),

    # Magenta / pink spectrum
    "magenta": discord.Color.magenta(),
    "dark_magenta": discord.Color.dark_magenta(),
    "fuchsia": discord.Color.fuchsia(),
    "pink": discord.Color.pink(),

    # Gold / yellow / orange
    "gold": discord.Color.gold(),
    "dark_gold": discord.Color.dark_gold(),
    "orange": discord.Color.orange(),
    "dark_orange": discord.Color.dark_orange(),
    "yellow": discord.Color.yellow(),

    # Reds
    "brand_red": discord.Color.brand_red(),
    "red": discord.Color.red(),
    "dark_red": discord.Color.dark_red(),

    # Greys
    "lighter_grey": discord.Color.lighter_grey(),
    "light_grey": discord.Color.light_grey(),
    "dark_grey": discord.Color.dark_grey(),
    "darker_grey": discord.Color.darker_grey(),

    # Discord branding
    "blurple": discord.Color.blurple(),
    "og_blurple": discord.Color.og_blurple(),
    "greyple": discord.Color.greyple(),

    # Theme colors
    "ash_theme": discord.Color.ash_theme(),
    "dark_theme": discord.Color.dark_theme(),
    "onyx_theme": discord.Color.onyx_theme(),
    "light_theme": discord.Color.light_theme(),

    # Embed-specific theme colors
    "ash_embed": discord.Color.ash_embed(),
    "dark_embed": discord.Color.dark_embed(),
    "onyx_embed": discord.Color.onyx_embed(),
    "light_embed": discord.Color.light_embed(),
}


def get_color(name: str) -> discord.Color:
    return COLOR_MAP.get(name, discord.Color.blurple())



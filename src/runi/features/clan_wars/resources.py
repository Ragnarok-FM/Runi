# Resource definitions for the Clan Wars panel: what can be submitted, how
# it's displayed, and how it's scored. Feature settings (schedule, refresh
# interval, page size, etc.) live in runi/config.py under "Clan Wars".
#
# `emoji` is the exact name of a custom application emoji (e.g. "FMHammer"
# renders as the :FMHammer: token, which embed_renderer.py swaps for the real
# emoji). If no emoji with that exact name exists, it falls back to plain
# ":name:" text (see emojis.py).

RESOURCES = {
    "hammers": {
        "label": "Hammers",
        "emoji": "FMHammer",
        "show_emoji": True,
        "style": "primary",   # blue
        "has_points": False,
        "default_rate": 0,
        "convert_per": 1,          # raw units needed per point-earning unit (1 = no conversion)
        "converted_label": None,   # display name for the converted unit, if any
    },
    "clockwinders": {
        "label": "Clockwinders",
        "emoji": "Clockwinder",
        "show_emoji": True,
        "style": "primary",
        "has_points": True,
        "default_rate": 600,       # points per Mount Summon
        "convert_per": 50,         # 50 Clockwinders = 1 Mount Summon
        "converted_label": "Mount Summons",
    },
    "eggshells": {
        "label": "Eggshells",
        "emoji": "Eggshell",
        "show_emoji": True,
        "style": "primary",
        "has_points": False,
        "default_rate": 0,
        "convert_per": 1,
        "converted_label": None,
    },
    "skill_tickets": {
        "label": "Skill Tickets",
        "emoji": "SkillTicket",
        "show_emoji": True,
        "style": "primary",
        "has_points": True,
        "default_rate": 125,       # points per Skill summoned
        "convert_per": 40,         # 40 Skill Tickets = 1 Skill summoned (200 tickets = x5 summon)
        "converted_label": "Skills Summoned",
    },
    "mount_merges": {
        "label": "Mount Merges",
        "emoji": "MountMerge",
        "show_emoji": True,
        "style": "success",   # green
        "has_points": True,
        "default_rate": 600,
        "convert_per": 1,          # submitted directly as a merge count, no conversion
        "converted_label": None,
    },
    "pet_merges": {
        "label": "Pet Merges",
        "emoji": "PetMerge",
        "show_emoji": True,
        "style": "success",
        "has_points": True,
        "default_rate": 1250,
        "convert_per": 1,
        "converted_label": None,
    },
    "tech_potions": {
        "label": "Clan Vials",
        "emoji": "GreenVial",
        "show_emoji": True,
        "style": "success",
        "has_points": False,
        "default_rate": 0,
        "convert_per": 1,
        "converted_label": None,
    },
    "gems_for_tech": {
        "label": "Gems for Tech",
        "emoji": "FMGem",
        "show_emoji": True,
        "style": "success",
        "has_points": False,
        "default_rate": 0,
        "convert_per": 1,
        "converted_label": None,
    },
}

# Convenience lookups
DEFAULT_RATES = {key: meta["default_rate"] for key, meta in RESOURCES.items()}
CONVERT_PER = {key: meta["convert_per"] for key, meta in RESOURCES.items()}

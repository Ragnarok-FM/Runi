# Resource definitions for the Clan Wars panel.
#
# `emoji` refers to a custom application emoji name (registered via
# EmojiRegistry) — e.g. "Hammers" maps to a :Hammers: token that
# embed_renderer.py will substitute with the real emoji mention.
# Make sure emojis with these exact names exist as application emojis,
# otherwise they'll fall back to plain ":name:" text (see emojis.py).

RESOURCES = {
    "hammers": {
        "label": "Hammers",
        "emoji": "Hammers",
        "style": "primary",   # blue
        "has_points": False,
        "default_rate": 0,
        "convert_per": 1,          # raw units needed per point-earning unit (1 = no conversion)
        "converted_label": None,   # display name for the converted unit, if any
    },
    "clockwinders": {
        "label": "Clockwinders",
        "emoji": "Clockwinders",
        "style": "primary",
        "has_points": True,
        "default_rate": 600,       # points per Mount Summon
        "convert_per": 50,         # 50 Clockwinders = 1 Mount Summon
        "converted_label": "Mount Summons",
    },
    "eggshells": {
        "label": "Eggshells",
        "emoji": "Eggshells",
        "style": "primary",
        "has_points": False,
        "default_rate": 0,
        "convert_per": 1,
        "converted_label": None,
    },
    "skill_tickets": {
        "label": "Skill Tickets",
        "emoji": "SkillTickets",
        "style": "primary",
        "has_points": True,
        "default_rate": 125,       # points per Skill summoned
        "convert_per": 40,         # 40 Skill Tickets = 1 Skill summoned (200 tickets = x5 summon)
        "converted_label": "Skills Summoned",
    },
    "mount_merges": {
        "label": "Mount Merges",
        "emoji": "MountMerges",
        "style": "success",   # green
        "has_points": True,
        "default_rate": 600,
        "convert_per": 1,          # submitted directly as a merge count, no conversion
        "converted_label": None,
    },
    "pet_merges": {
        "label": "Pet Merges",
        "emoji": "PetMerges",
        "style": "success",
        "has_points": True,
        "default_rate": 1250,
        "convert_per": 1,
        "converted_label": None,
    },
    "tech_potions": {
        "label": "Clan Vials",
        "emoji": "TechPotions",
        "style": "success",
        "has_points": False,
        "default_rate": 0,
        "convert_per": 1,
        "converted_label": None,
    },
    "gems_for_tech": {
        "label": "Gems for Tech",
        "emoji": "GemsForTech",
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
SCORING_RESOURCES = [key for key, meta in RESOURCES.items() if meta["has_points"]]

# Role allowed to submit resources via the panel buttons
PARTICIPANT_ROLE_ID = 1447639376157868289

# Set to False to let anyone use the panel buttons (useful for dev/testing
# on a server where the participant role doesn't exist yet). Set back to
# True before going live on the real server.
REQUIRE_PARTICIPANT_ROLE = False

MEMBERS_PER_PAGE = 10
STALE_AFTER_SECONDS = 7 * 24 * 60 * 60  # 7 days
AUTO_REFRESH_SECONDS = 10 * 60  # 10 minutes

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
SCORING_RESOURCES = [key for key, meta in RESOURCES.items() if meta["has_points"]]

MEMBERS_PER_PAGE = 10
STALE_AFTER_SECONDS = 7 * 24 * 60 * 60  # 7 days
AUTO_REFRESH_SECONDS = 10 * 60  # 10 minutes


def find_member_clan(member, clans: list[dict]) -> dict | None:
    """
    Given a Discord Member and the list of clans registered for their guild
    (as returned by Database.get_clans), returns the clan dict for the first
    of the member's roles that matches a registered clan's role_id, or None
    if they don't hold any registered clan's role.

    "First matching role" resolves the (rare, accidental) case of a member
    holding two different clans' roles at once — deterministic and simple,
    with the expectation that a misconfiguration like that gets noticed and
    fixed by an admin shortly after.
    """
    if not clans:
        return None

    role_id_to_clan = {c["role_id"]: c for c in clans}
    for role in member.roles:
        clan = role_id_to_clan.get(role.id)
        if clan:
            return clan
    return None

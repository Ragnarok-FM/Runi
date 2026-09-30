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

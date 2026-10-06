"""
Bounty pool, rolling rules and progress tracking.

Pure Python (no Discord objects) so it can be tested on its own. The Bounty cog
turns Discord activity into plain event dicts and feeds them to `apply_event`.

Event dicts always have "type" and "ts" (unix time), plus:
    work      {"earned": int}
    daily     {}
    coinflip  {"bet": int, "choice": "heads"|"tails", "won": bool}
    slots     {"bet": int, "payout": int, "won": bool, "symbols": [str, str, str]}
    xp        {"xp": int}                                   (only messages that earned XP)
    message   {"channel_id": int, "reply_to_member": int | None}  (every member message)
    command   {"name": str, "targets_other": bool}
"""
import random
from dataclasses import dataclass
from datetime import datetime, UTC

from runi.config import (
    BOUNTY_TIER_WEIGHTS,
    BOUNTY_REWARDS,
    BOUNTY_MAX_LEGENDARY,
    BOUNTY_COMPLETION_BONUS_RATE,
    BOUNTY_MIN_BET,
    BOUNTY_MIN_HOURS_BUFFER,
    BOUNTY_SHIFT_CHAIN_MINUTES,
)

TIERS = ("common", "epic", "legendary")
WILD = "🃏"


# ── Goals ─────────────────────────────────────────────────────────────────────
# A bounty is made of one or more goals. Each goal keeps a small JSON-friendly
# state dict and reports progress as (current, target).

class Goal:
    event: str = ""
    target: int = 1

    def initial(self) -> dict:
        return {"value": 0}

    def apply(self, state: dict, event: dict) -> None:
        raise NotImplementedError

    def value(self, state: dict) -> int:
        return min(state.get("value", 0), self.target)

    def done(self, state: dict) -> bool:
        return self.value(state) >= self.target


class Count(Goal):
    """Adds `amount(event)` every time `when(event)` is true."""

    def __init__(self, event: str, target: int, when=None, amount=None):
        self.event = event
        self.target = target
        self.when = when or (lambda ev: True)
        self.amount = amount or (lambda ev: 1)

    def apply(self, state, event):
        if self.when(event):
            state["value"] = state.get("value", 0) + self.amount(event)


class Streak(Goal):
    """Consecutive successes among relevant events. A relevant failure resets it."""

    def __init__(self, event: str, target: int, relevant, success):
        self.event = event
        self.target = target
        self.relevant = relevant
        self.success = success

    def apply(self, state, event):
        if not self.relevant(event):
            return
        state["value"] = state.get("value", 0) + 1 if self.success(event) else 0


class AlternatingFlips(Goal):
    """Coinflip wins in a row, calling Heads → Tails → Heads → ..."""

    def __init__(self, target: int):
        self.event = "coinflip"
        self.target = target

    def apply(self, state, event):
        if not qualifying(event):
            return
        streak = state.get("value", 0)
        expected = "heads" if streak % 2 == 0 else "tails"

        if event["won"] and event["choice"] == expected:
            state["value"] = streak + 1
        elif event["won"] and event["choice"] == "heads":
            state["value"] = 1  # a winning Heads call always starts a new chain
        else:
            state["value"] = 0


class Distinct(Goal):
    """Counts distinct values of `key(event)` (None is ignored)."""

    def initial(self):
        return {"seen": []}

    def __init__(self, event: str, target: int, key):
        self.event = event
        self.target = target
        self.key = key

    def apply(self, state, event):
        k = self.key(event)
        if k is not None and k not in state["seen"]:
            state["seen"].append(k)

    def value(self, state):
        return min(len(state.get("seen", [])), self.target)


class ShiftChain(Goal):
    """/work uses where each comes within BOUNTY_SHIFT_CHAIN_MINUTES of the last."""

    def initial(self):
        return {"value": 0, "last": None}

    def __init__(self, target: int):
        self.event = "work"
        self.target = target

    def apply(self, state, event):
        last = state.get("last")
        in_chain = last is not None and event["ts"] - last <= BOUNTY_SHIFT_CHAIN_MINUTES * 60
        state["value"] = state.get("value", 0) + 1 if in_chain else 1
        state["last"] = event["ts"]


# ── Event predicates ──────────────────────────────────────────────────────────

def qualifying(ev: dict) -> bool:
    return ev.get("bet", 0) >= BOUNTY_MIN_BET


def flip_won(ev: dict) -> bool:
    return qualifying(ev) and ev["won"]


def spin_won(ev: dict) -> bool:
    return qualifying(ev) and ev["won"]


def spin_paid(ev: dict) -> bool:
    return qualifying(ev) and ev["payout"] > 0


def spin_multiplier_at_least(x: float):
    return lambda ev: qualifying(ev) and ev["payout"] >= ev["bet"] * x


def _symbol_count(symbols: list[str], symbol: str) -> int:
    return sum(s == symbol or s == WILD for s in symbols)


def spin_pair_of(*wanted: str):
    return lambda ev: qualifying(ev) and any(_symbol_count(ev["symbols"], s) >= 2 for s in wanted)


def spin_three_of_a_kind(ev: dict) -> bool:
    if not qualifying(ev):
        return False
    symbols = ev["symbols"]
    if all(s == WILD for s in symbols):
        return True
    return any(_symbol_count(symbols, s) == 3 for s in set(symbols) if s != WILD)


def spin_has_wild(ev: dict) -> bool:
    return qualifying(ev) and WILD in ev["symbols"]


def command_in(*names: str, other_member: bool = False):
    return lambda ev: ev["name"] in names and (ev["targets_other"] or not other_member)


def utc_hour(ev: dict) -> int:
    return datetime.fromtimestamp(ev["ts"], UTC).hour


# ── Pool ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BountyDef:
    id: str
    tier: str
    text: str
    groups: frozenset
    goals: tuple  # ((label, Goal), ...) — label only shown for multi-goal bounties
    min_hours: float = 0

    @property
    def reward(self) -> int:
        return BOUNTY_REWARDS[self.tier]


def _b(id, tier, text, groups, *goals, min_hours=0):
    if len(goals) == 1 and isinstance(goals[0], Goal):
        goals = (("", goals[0]),)
    return BountyDef(id, tier, text, frozenset(groups), tuple(goals), min_hours)


BET = f"bet {BOUNTY_MIN_BET}+"
CHAIN = f"each within {BOUNTY_SHIFT_CHAIN_MINUTES} min of the last"

POOL: list[BountyDef] = [
    # ── Common ────────────────────────────────────────────────────────────────
    _b("C1", "common", "Use `/work` 2 times", {"work"}, Count("work", 2), min_hours=1),
    _b("C8", "common", f"**Double Shift** — use `/work` 2 times, {CHAIN}", {"work"}, ShiftChain(2), min_hours=1),
    _b("C2", "common", "Claim your `/daily` reward", {"daily"}, Count("daily", 1)),
    _b("C3", "common", f"Play 3 coinflips ({BET})", {"coinflip"}, Count("coinflip", 3, when=qualifying)),
    _b("C4", "common", f"Win 2 coinflips ({BET})", {"coinflip"}, Count("coinflip", 2, when=flip_won)),
    _b("C9", "common", f"Win a coinflip calling Heads and one calling Tails ({BET})", {"coinflip"},
       Distinct("coinflip", 2, key=lambda ev: ev["choice"] if flip_won(ev) else None)),
    _b("C5", "common", f"Spin the slots 3 times ({BET})", {"slots"}, Count("slots", 3, when=qualifying)),
    _b("C6", "common", f"Hit any payout on the slots ({BET})", {"slots"}, Count("slots", 1, when=spin_paid)),
    _b("C7", "common", "Earn 75 XP by chatting", {"chat"}, Count("xp", 75, amount=lambda ev: ev["xp"])),
    _b("C10", "common", "Reply to another member's message 2 times", {"chat"},
       Count("message", 2, when=lambda ev: ev["reply_to_member"] is not None)),
    _b("C11", "common", "Look up a Forge Master stat with `/maxsubstats`, `/health_formula` or `/damage_formula`",
       {"explore"}, Count("command", 1, when=command_in("maxsubstats", "health_formula", "damage_formula"))),
    _b("C12", "common", "Check another member's `/profile` or `/rank`", {"explore"},
       Count("command", 1, when=command_in("profile", "rank", other_member=True))),
    _b("C13", "common", "Check a leaderboard: `/leaderboard`, `/richlist` or `/highroller`", {"explore"},
       Count("command", 1, when=command_in("leaderboard", "richlist", "highroller"))),

    # ── Epic ──────────────────────────────────────────────────────────────────
    _b("E1", "epic", "Use `/work` 4 times", {"work"}, Count("work", 4), min_hours=3),
    _b("E8", "epic", f"**Triple Shift** — use `/work` 3 times, {CHAIN}", {"work"}, ShiftChain(3), min_hours=2),
    _b("E9", "epic", "**Lucky Shift** — get a `/work` payout of 130 or more", {"work"},
       Count("work", 1, when=lambda ev: ev["earned"] >= 130), min_hours=4),
    _b("E2", "epic", f"Win 3 coinflips in a row ({BET})", {"coinflip"},
       Streak("coinflip", 3, relevant=qualifying, success=lambda ev: ev["won"])),
    _b("E3", "epic", f"Win 5 coinflips ({BET})", {"coinflip"}, Count("coinflip", 5, when=flip_won)),
    _b("E10", "epic", "**High Stakes** — win a coinflip with a bet of 300 or more", {"coinflip"},
       Count("coinflip", 1, when=lambda ev: ev["won"] and ev["bet"] >= 300)),
    _b("E4", "epic", f"Win 3 slots spins ({BET})", {"slots"}, Count("slots", 3, when=spin_won)),
    _b("E5", "epic", f"Land a slots win paying 5× your bet or more ({BET})", {"slots"},
       Count("slots", 1, when=spin_multiplier_at_least(5))),
    _b("E11", "epic", f"Land two or more 🔔 or ⭐ on one spin — {WILD} counts ({BET})", {"slots"},
       Count("slots", 1, when=spin_pair_of("🔔", "⭐"))),
    _b("E12", "epic", f"Win 2 slots spins in a row ({BET})", {"slots"},
       Streak("slots", 2, relevant=qualifying, success=lambda ev: ev["won"])),
    _b("E13", "epic", f"Land a {WILD} Wild on the slots ({BET})", {"slots"}, Count("slots", 1, when=spin_has_wild)),
    _b("E6", "epic", "Earn 225 XP by chatting", {"chat"}, Count("xp", 225, amount=lambda ev: ev["xp"])),
    _b("E14", "epic", "Send a message in 3 different channels", {"chat"},
       Distinct("message", 3, key=lambda ev: ev["channel_id"])),
    _b("E15", "epic", "Reply to 3 different members", {"chat"},
       Distinct("message", 3, key=lambda ev: ev["reply_to_member"])),
    _b("E7", "epic", f"Win on both coinflip and slots ({BET})", {"coinflip", "slots"},
       ("Win a coinflip", Count("coinflip", 1, when=flip_won)),
       ("Win a slots spin", Count("slots", 1, when=spin_won))),
    _b("E16", "epic", f"**Work & Wager** — use `/work` 2 times and win a coinflip ({BET})", {"work", "coinflip"},
       ("Use `/work` 2 times", Count("work", 2)),
       ("Win a coinflip", Count("coinflip", 1, when=flip_won)),
       min_hours=1),
    _b("E17", "epic", "**Social Grind** — use `/work` 2 times and earn 75 XP by chatting", {"work", "chat"},
       ("Use `/work` 2 times", Count("work", 2)),
       ("Earn 75 XP", Count("xp", 75, amount=lambda ev: ev["xp"])),
       min_hours=1),

    # ── Legendary ─────────────────────────────────────────────────────────────
    _b("L1", "legendary", "Use `/work` 7 times", {"work"}, Count("work", 7), min_hours=6),
    _b("L6", "legendary", f"**Marathon** — use `/work` 5 times, {CHAIN}", {"work"}, ShiftChain(5), min_hours=4),
    _b("L2", "legendary", f"Win 5 coinflips in a row ({BET})", {"coinflip"},
       Streak("coinflip", 5, relevant=qualifying, success=lambda ev: ev["won"])),
    _b("L7", "legendary", f"Win 4 coinflips in a row, alternating Heads → Tails → Heads → Tails ({BET})",
       {"coinflip"}, AlternatingFlips(4)),
    _b("L3", "legendary", f"Hit three of a kind on the slots — {WILD} counts ({BET})", {"slots"},
       Count("slots", 1, when=spin_three_of_a_kind)),
    _b("L4", "legendary", f"Land a slots win paying 10× your bet or more ({BET})", {"slots"},
       Count("slots", 1, when=spin_multiplier_at_least(10))),
    _b("L8", "legendary", f"Land two or more 💎 on one spin — {WILD} counts ({BET})", {"slots"},
       Count("slots", 1, when=spin_pair_of("💎"))),
    _b("L5", "legendary", "Earn 450 XP by chatting", {"chat"}, Count("xp", 450, amount=lambda ev: ev["xp"])),
    _b("L9", "legendary", "Send a message in 6 different hours of the day", {"chat"},
       Distinct("message", 6, key=utc_hour), min_hours=6),
    _b("L10", "legendary", f"**Triple Threat** — win 3 coinflips in a row and land a 3×+ slots win ({BET})",
       {"coinflip", "slots"},
       ("Win 3 coinflips in a row", Streak("coinflip", 3, relevant=qualifying, success=lambda ev: ev["won"])),
       ("Land a slots win paying 3× or more", Count("slots", 1, when=spin_multiplier_at_least(3)))),
]

POOL_BY_ID: dict[str, BountyDef] = {b.id: b for b in POOL}
assert len(POOL_BY_ID) == len(POOL), "Duplicate bounty IDs in POOL"


# ── Rolling ───────────────────────────────────────────────────────────────────

def roll_bounties(recent_ids: set[str], hours_left: float, rng: random.Random | None = None) -> list[BountyDef]:
    """
    Roll a set of three bounties.
      1. Roll a tier per slot (BOUNTY_TIER_WEIGHTS), capped at BOUNTY_MAX_LEGENDARY.
      2. Fill hardest tier first, picking among bounties that share no group with
         already-picked ones, weren't in the recent sets, and fit the time left.
      3. If a tier has nothing eligible, drop one tier.
    """
    rng = rng or random.Random()
    names, weights = list(BOUNTY_TIER_WEIGHTS), list(BOUNTY_TIER_WEIGHTS.values())

    tiers: list[str] = []
    for _ in range(3):
        tier = rng.choices(names, weights=weights)[0]
        while tier == "legendary" and tiers.count("legendary") >= BOUNTY_MAX_LEGENDARY:
            tier = rng.choices(names, weights=weights)[0]
        tiers.append(tier)

    tiers.sort(key=TIERS.index, reverse=True)

    def eligible(tier: str, used: set, ignore_recent: bool = False) -> list[BountyDef]:
        return [
            b for b in POOL
            if b.tier == tier
            and not (b.groups & used)
            and (ignore_recent or b.id not in recent_ids)
            and (not b.min_hours or b.min_hours + BOUNTY_MIN_HOURS_BUFFER <= hours_left)
        ]

    picked: list[BountyDef] = []
    used: set = set()
    for tier in tiers:
        candidates: list[BountyDef] = []
        for fallback in TIERS[TIERS.index(tier)::-1]:
            candidates = eligible(fallback, used)
            if candidates:
                break
        if not candidates:  # last resort: allow recently seen bounties
            candidates = eligible("common", used, ignore_recent=True)

        choice = rng.choice(candidates)
        picked.append(choice)
        used |= choice.groups

    picked.sort(key=lambda b: TIERS.index(b.tier))
    return picked


# ── Slot state ────────────────────────────────────────────────────────────────
# What gets stored in the database for each of the three bounties.

def new_slot(bounty: BountyDef) -> dict:
    return {
        "id": bounty.id,
        "reward": bounty.reward,
        "goals": [goal.initial() for _, goal in bounty.goals],
        "completed": False,
    }


def completion_bonus(slots: list[dict]) -> int:
    return int(sum(s["reward"] for s in slots) * BOUNTY_COMPLETION_BONUS_RATE)


def apply_event(slot: dict, event: dict) -> bool:
    """Apply an event to one slot. Returns True if this event completed the bounty."""
    if slot["completed"]:
        return False

    bounty = POOL_BY_ID.get(slot["id"])
    if bounty is None:  # bounty removed from the pool after rolling
        return False

    for (_, goal), state in zip(bounty.goals, slot["goals"]):
        if goal.event == event["type"] and not goal.done(state):
            goal.apply(state, event)

    if all(goal.done(state) for (_, goal), state in zip(bounty.goals, slot["goals"])):
        slot["completed"] = True
        return True
    return False


def slot_progress(slot: dict) -> list[tuple[str, int, int]]:
    """[(label, current, target), ...] — one entry per goal."""
    bounty = POOL_BY_ID[slot["id"]]
    return [
        (label, goal.target if slot["completed"] else goal.value(state), goal.target)
        for (label, goal), state in zip(bounty.goals, slot["goals"])
    ]

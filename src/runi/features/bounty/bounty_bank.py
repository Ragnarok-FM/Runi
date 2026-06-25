"""
bounty_bank.py
~~~~~~~~~~~~~~
Loads and exposes all bounty definitions from the CSV bank file.

Mirrors the AscensionTable pattern: a single class owns the CSV parsing
and provides typed, validated access to the underlying data so the rest
of the feature never touches raw strings.
"""

import csv
import random
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Rarity configuration
# Drop weights must sum to 100.  Adjust freely without touching game logic.
# ---------------------------------------------------------------------------
RARITY_WEIGHTS: dict[str, float] = {
    "common":    60.0,
    "rare":      30.0,
    "epic":       9.9,
    "legendary":  0.1,
}

# Rune rewards per rarity tier
RARITY_REWARDS: dict[str, int] = {
    "common":       75,
    "rare":        100,
    "epic":        200,
    "legendary": 11_000_000,
}

# Pretty display labels (emoji prefix + capitalised name)
RARITY_DISPLAY: dict[str, str] = {
    "common":    "⚪ Common",
    "rare":      "🔵 Rare",
    "epic":      "🟣 Epic",
    "legendary": "🟡 Legendary",
}

# Status badge strings used inside the embed progress view
STATUS_ACTIVE    = "🔄 **[ACTIVE]**"
STATUS_COMPLETED = "✅ **[COMPLETED]**"
STATUS_CLAIMED   = "🏆 **[CLAIMED]**"


@dataclass(frozen=True)
class BountyDefinition:
    """Immutable definition of a single bounty pulled from the bank CSV."""

    id: int           # Unique bounty ID (matches CSV `id` column)
    rarity: str       # One of: common | rare | epic | legendary
    description: str  # Human-readable task description
    type: str         # Machine-readable progress key (e.g. "message_count")
    target: int       # How many units are required to complete the bounty

    # ── Convenience properties ─────────────────────────────────────────────

    @property
    def reward(self) -> int:
        """Rune reward for this bounty's rarity tier."""
        return RARITY_REWARDS[self.rarity]

    @property
    def display_rarity(self) -> str:
        """Emoji + capitalised rarity label for embeds."""
        return RARITY_DISPLAY[self.rarity]

    @property
    def is_legendary(self) -> bool:
        return self.rarity == "legendary"


class BountyBank:
    """
    Loads all bounty definitions from ``bounty_bank.csv`` and provides
    weighted-random selection for daily bounty generation.

    Usage::

        bank = BountyBank(DATA_DIR / "bounty_bank.csv")
        bank.load()
        three_bounties = bank.roll()      # list[BountyDefinition]
        one_rare       = bank.roll(n=1, rarity="rare")
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._by_rarity: dict[str, list[BountyDefinition]] = {
            rarity: [] for rarity in RARITY_WEIGHTS
        }
        self._loaded = False

    # ── Loading ────────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Parse the CSV.  Idempotent — safe to call multiple times."""
        if self._loaded:
            return

        if not self.path.exists():
            raise FileNotFoundError(f"Bounty bank CSV not found: {self.path}")

        with self.path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rarity = row["rarity"].strip().lower()
                if rarity not in self._by_rarity:
                    raise ValueError(
                        f"Unknown rarity '{rarity}' in bounty bank row {row['id']}"
                    )
                self._by_rarity[rarity].append(
                    BountyDefinition(
                        id=int(row["id"]),
                        rarity=rarity,
                        description=row["description"].strip(),
                        type=row["type"].strip(),
                        target=int(row["target"]),
                    )
                )

        self._loaded = True

    # ── Rolling ────────────────────────────────────────────────────────────────

    def _pick_rarity(self) -> str:
        """
        Pick a single rarity tier using the configured drop-rate weights.
        Uses ``random.choices`` which accepts a ``weights`` keyword — no need
        to normalise to 1.0 first (stdlib handles it).
        """
        rarities = list(RARITY_WEIGHTS.keys())
        weights  = list(RARITY_WEIGHTS.values())
        return random.choices(rarities, weights=weights, k=1)[0]

    def _pick_from_rarity(self, rarity: str) -> BountyDefinition:
        """
        Return a random BountyDefinition from the given rarity pool.
        Falls back gracefully to common if the pool is somehow empty.
        """
        pool = self._by_rarity.get(rarity, [])
        if not pool:
            # Defensive fallback — should never happen with a well-formed CSV
            pool = self._by_rarity["common"]
        return random.choice(pool)

    def roll(
        self,
        n: int = 3,
        *,
        rarity: str | None = None,
        allow_duplicates: bool = False,
    ) -> list[BountyDefinition]:
        """
        Roll ``n`` bounties.

        Parameters
        ----------
        n:
            Number of bounties to generate (default: 3).
        rarity:
            If provided, all slots are forced to this rarity.
            Useful for testing or special events.
        allow_duplicates:
            When False (default), the same bounty ID will not appear twice
            in the returned list.  Falls back to allowing duplicates only if
            the entire pool is smaller than ``n``.

        Returns
        -------
        list[BountyDefinition]
            Ordered list of rolled bounties.
        """
        if not self._loaded:
            raise RuntimeError("BountyBank.load() must be called before roll()")

        results: list[BountyDefinition] = []
        seen_ids: set[int] = set()
        max_attempts = n * 20  # guard against infinite loops on tiny pools

        attempts = 0
        while len(results) < n and attempts < max_attempts:
            attempts += 1
            chosen_rarity = rarity or self._pick_rarity()
            bounty = self._pick_from_rarity(chosen_rarity)

            if not allow_duplicates and bounty.id in seen_ids:
                continue  # re-roll this slot

            seen_ids.add(bounty.id)
            results.append(bounty)

        # If we exhausted attempts (tiny pool), top up allowing duplicates
        while len(results) < n:
            chosen_rarity = rarity or self._pick_rarity()
            results.append(self._pick_from_rarity(chosen_rarity))

        return results

    # ── Lookup ─────────────────────────────────────────────────────────────────

    def get_by_id(self, bounty_id: int) -> BountyDefinition | None:
        """Return the BountyDefinition for a given ID, or None."""
        for pool in self._by_rarity.values():
            for bounty in pool:
                if bounty.id == bounty_id:
                    return bounty
        return None

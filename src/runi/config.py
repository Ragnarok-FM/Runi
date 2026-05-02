# ══════════════════════════════════════════════════════════════════════════════
#  Bot Configuration
#  Edit these values to tune the bot's behaviour without touching any logic.
# ══════════════════════════════════════════════════════════════════════════════

# ── XP & Leveling ─────────────────────────────────────────────────────────────

# XP awarded per qualifying message
XP_PER_MESSAGE: int = 15

# Minimum seconds between XP awards for the same user (anti-spam)
XP_COOLDOWN_SECONDS: float = 60.0

# Formula: how much *total* XP is needed to reach a given level.
# Default uses a quadratic curve: level 1 = 100 XP, level 10 = 10 000 XP, etc.
def XP_FOR_LEVEL(level: int) -> int:
    return 100 * (level ** 2)


# ── Economy – /work ───────────────────────────────────────────────────────────

# Cooldown between /work uses (seconds).  3600 = 1 hour
WORK_COOLDOWN_SECONDS: float = 3600.0

# Random payout range (inclusive) for /work
WORK_MIN: int = 50
WORK_MAX: int = 150


# ── Economy – /daily ──────────────────────────────────────────────────────────

# Cooldown between /daily uses (seconds).  86400 = 24 hours
DAILY_COOLDOWN_SECONDS: float = 86400.0

# If the user claims their daily within this many seconds after the previous
# claim they keep their streak going.  Set to 48 h so players aren't punished
# for claiming slightly later each day.
DAILY_STREAK_RESET_WINDOW: float = 172_800.0  # 48 hours

# Base payout for /daily (streak day 1)
DAILY_BASE: int = 300

# Extra Runes added per additional streak day
DAILY_STREAK_BONUS: int = 50

# Maximum streak that can be accumulated (caps the bonus)
DAILY_STREAK_MAX: int = 30

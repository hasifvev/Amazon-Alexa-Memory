"""Time of day changes what a wake surfaces, not how it is worded.

The decorative version of this feature swaps adjectives — cheerful in the
morning, softer at night — and adds nothing. The useful version changes
**priority and volume**: what you need at 7am is not what you need at 11pm, and
it is not a matter of tone.

    morning     what moved overnight, and what is open today
    afternoon   what is true now; changes are less urgent mid-flow
    evening     what moved today, and what is still unresolved
    night       the least that is still useful; no new work surfaced

The last one matters most and is the easiest to get wrong. Handing somebody a
list of open tasks at midnight is not helpful, it is just complete. So at night
the open-items section is dropped entirely rather than shortened — a briefing
that respects the hour has to be willing to leave things out.

This is a reprioritisation of the existing tier system, not a parallel one.
Tiers decide what is *eligible*; the daypart decides what gets the budget first
and how much of it is spoken.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class Daypart(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


@dataclass(frozen=True)
class Profile:
    """How a daypart shapes the briefing.

    ``priority`` lists section names in the order they claim budget. A section
    absent from the list is still eligible, but claims last.

    ``drop`` names sections this daypart deliberately omits, however much
    budget remains. That is a choice about usefulness, not a shortage.
    """

    daypart: Daypart
    greeting: str
    item_limit: int
    priority: tuple[str, ...]
    drop: frozenset[str] = frozenset()


PROFILES: dict[Daypart, Profile] = {
    Daypart.MORNING: Profile(
        daypart=Daypart.MORNING,
        greeting="Morning.",
        item_limit=4,
        priority=("changed", "open", "current"),
    ),
    Daypart.AFTERNOON: Profile(
        daypart=Daypart.AFTERNOON,
        greeting="",
        item_limit=3,
        priority=("current", "changed", "open"),
    ),
    Daypart.EVENING: Profile(
        daypart=Daypart.EVENING,
        greeting="Evening.",
        item_limit=3,
        priority=("changed", "open", "current"),
    ),
    Daypart.NIGHT: Profile(
        daypart=Daypart.NIGHT,
        greeting="",
        item_limit=2,
        priority=("changed", "current"),
        # Nothing actionable at this hour. A list of open tasks at midnight is
        # complete rather than useful, and this system is meant to be useful.
        drop=frozenset({"open"}),
    ),
}

# Local wall-clock boundaries. Inclusive of the start hour, exclusive of the end.
_BOUNDARIES: tuple[tuple[int, int, Daypart], ...] = (
    (6, 12, Daypart.MORNING),
    (12, 18, Daypart.AFTERNOON),
    (18, 22, Daypart.EVENING),
)


def daypart_for(moment: datetime, *, utc_offset_hours: float = 0.0) -> Daypart:
    """Which daypart a moment falls in, for a given local offset.

    The offset is explicit rather than read from the host clock. A server in one
    timezone briefing a person in another must use the *person's* hour, and
    inheriting the machine's timezone is how that quietly goes wrong.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(timezone(timedelta(hours=utc_offset_hours)))
    hour = local.hour
    for start, end, part in _BOUNDARIES:
        if start <= hour < end:
            return part
    return Daypart.NIGHT


def profile_for(moment: datetime, *, utc_offset_hours: float = 0.0) -> Profile:
    return PROFILES[daypart_for(moment, utc_offset_hours=utc_offset_hours)]

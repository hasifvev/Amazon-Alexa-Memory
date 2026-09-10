"""The load set, as executable authority.

Which sections load at which trigger is defined here, once, in code. Prose
documentation points at this module rather than restating it, because a second
copy of a list is a second copy that goes stale — and a stale load set fails
silently, by quietly not loading something.

    L0  always. Identity and rules. Never trimmed.
    L1  session wake. What is true, what changed, what is open.
    L2  addressed by name. Fuller recall, belief history.
    L3  on demand only. Never promoted into a wake.

``SECTIONS`` is the whole registry. ``covers_everything()`` exists so a test can
fail when a section is added without a tier — otherwise it would simply never
load, and nothing would report it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum


class Tier(IntEnum):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3


class Trigger(IntEnum):
    """What woke the assistant, and therefore how deep to load."""

    SESSION = 1  # ordinary start: L0 + L1
    NAMED = 2  # addressed by name: L0 + L1 + L2

    @property
    def deepest_tier(self) -> Tier:
        return Tier(int(self))


@dataclass(frozen=True)
class Section:
    """One block of a briefing.

    ``build`` is a pure function of the wake context. Sections do no I/O beyond
    reading the store, and never call a model: a wake must be bounded,
    deterministic work, and an inference call is neither.
    """

    name: str
    tier: Tier
    heading: str
    build: Callable[["WakeContext"], str]  # noqa: F821 - defined in wake.py

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Section {self.name} {self.tier.name}>"


# Populated by wake.py at import, which owns the builders. Kept here so the
# tier assignment lives in one place and can be audited without reading the
# rendering code.
SECTIONS: list[Section] = []


def register(section: Section) -> Section:
    if any(s.name == section.name for s in SECTIONS):
        raise ValueError(f"duplicate section {section.name!r}")
    SECTIONS.append(section)
    return section


def for_trigger(trigger: Trigger) -> list[Section]:
    """Sections to attempt, shallowest tier first.

    Order matters: a lower tier is more important, so it gets first claim on the
    budget. A wake that spent its ceiling on deep recall and then had no room
    for what changed today would be technically within budget and useless.
    """
    return sorted(
        (s for s in SECTIONS if s.tier <= trigger.deepest_tier),
        key=lambda s: (s.tier, s.name),
    )


def covers_everything() -> tuple[bool, list[str]]:
    """Every registered section must belong to a known tier.

    A section with no tier never loads, and never errors — it just silently is
    not there. This is the check that turns that into a build failure.
    """
    known = set(Tier)
    orphans = [s.name for s in SECTIONS if s.tier not in known]
    return (not orphans, orphans)


def tier_map() -> dict[str, list[str]]:
    """The load set as data, for reports and tests."""
    out: dict[str, list[str]] = {tier.name: [] for tier in Tier}
    for section in sorted(SECTIONS, key=lambda s: (s.tier, s.name)):
        out[section.tier.name].append(section.name)
    return out

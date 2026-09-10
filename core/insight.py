"""What the record says about being wrong.

Every other memory system deletes what it retracts, so this analysis is not
available to them at all. We keep withdrawn beliefs forever, which means we can
answer a question nobody else can: **how long were you wrong for?**

That number is exactly computable — from the moment a belief was asserted to the
moment it was withdrawn — and it is far more useful than the fuzzy alternative
of clustering retraction reasons by keyword. A keyword cluster is a guess
dressed as an insight. "You believed that for 145 days" is a fact.

Nothing here calls a model or infers anything. It reads the log and counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from core.store import Memory, MemoryStore, parse_time


@dataclass(frozen=True)
class Mistake:
    """A belief that was held and then withdrawn as never true."""

    memory: Memory
    reason: str
    asserted_at: str
    withdrawn_at: str

    @property
    def held_for(self) -> timedelta:
        return parse_time(self.withdrawn_at) - parse_time(self.asserted_at)

    @property
    def held_days(self) -> int:
        return max(0, self.held_for.days)


@dataclass(frozen=True)
class Correction:
    """A belief that was superseded — the answer changed, it was not wrong."""

    memory: Memory
    replaced_by: Memory
    held_days: int


def mistakes(store: MemoryStore, *, subject: str | None = None) -> list[Mistake]:
    """Withdrawn beliefs, longest-held first.

    Sorted by duration rather than recency on purpose. The belief you carried
    for five months is the one worth knowing about; the one you corrected in an
    hour barely happened.
    """
    found: list[Mistake] = []
    for memory in store.all():
        if subject and memory.subject != subject:
            continue
        retraction = store.retraction(memory.id)
        if retraction is None:
            continue
        found.append(
            Mistake(
                memory=memory,
                reason=retraction.reason,
                asserted_at=memory.asserted_at,
                withdrawn_at=retraction.at,
            )
        )
    return sorted(found, key=lambda m: m.held_for, reverse=True)


def corrections(store: MemoryStore, *, subject: str | None = None) -> list[Correction]:
    """Answers that moved. Distinct from mistakes: the world changed, you did not err."""
    found: list[Correction] = []
    for memory in store.all():
        if subject and memory.subject != subject:
            continue
        replaced_by = store.superseded_by(memory.id)
        if replaced_by is None:
            continue
        successor = store.get(replaced_by)
        if successor is None:
            continue
        held = parse_time(successor.asserted_at) - parse_time(memory.asserted_at)
        found.append(
            Correction(memory=memory, replaced_by=successor, held_days=max(0, held.days))
        )
    return sorted(found, key=lambda c: c.held_days, reverse=True)


@dataclass(frozen=True)
class Recurrence:
    """A topic asked about more than once, and whether the answer moved."""

    topic: str
    times_asked: int
    first_asked: str
    last_asked: str
    answer_changed: bool


def churn(store: MemoryStore, *, subject: str | None = None) -> dict[str, float | int]:
    """A summary of how much this memory has moved.

    Useful as a single spoken line, and as the honest counterweight to a demo
    that only ever shows things going well: a memory with many long-held
    mistakes is a memory that has been trusted too easily.
    """
    wrong = mistakes(store, subject=subject)
    moved = corrections(store, subject=subject)
    total = sum(1 for m in store.all() if not subject or m.subject == subject)

    return {
        "remembered": total,
        "withdrawn": len(wrong),
        "changed": len(moved),
        "longest_wrong_days": wrong[0].held_days if wrong else 0,
        "mean_wrong_days": round(sum(m.held_days for m in wrong) / len(wrong), 1) if wrong else 0.0,
    }

"""A demo memory with a real history behind it.

The point of the demo is that the assistant can answer questions about the past,
so the seed has to contain a past. A store populated a minute ago cannot
demonstrate anything about time — every fact would have the same age and every
temporal question would have the same answer.

So this writes a memory with:

    a fact that CHANGED     standup moved from nine to ten thirty in July
    a fact that changed TWICE  the deploy root, so a chain can be shown
    a belief that was WRONG  the office hours, withdrawn last week
    a gap                    the laptop was only recorded two months ago, so
                             questions about March correctly return nothing
    open items               so the night profile has something to drop

None of it is real. Every name and value is invented.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.store import Memory, MemoryStore

DEMO_SUBJECT = "default"


def _iso(base: datetime, days_ago: int) -> str:
    return (base - timedelta(days=days_ago)).isoformat(timespec="seconds")


def seed(store: MemoryStore, *, now: datetime | None = None) -> MemoryStore:
    """Populate an empty store with a history worth asking questions about."""
    base = now or datetime.now(timezone.utc)
    ago = lambda d: _iso(base, d)  # noqa: E731

    def fact(text: str, days_ago: int, **kw) -> Memory:
        return Memory(
            text=text,
            subject=DEMO_SUBJECT,
            source="demo",
            asserted_at=ago(days_ago),
            valid_from=ago(days_ago),
            **kw,
        )

    # Changed once, a while back — so "what was it in June" has a real answer.
    standup = store.add(fact("standup is at nine", 240))
    store.supersede(standup.id, fact("standup is at ten thirty", 62), at=ago(62))

    # Changed twice — enough for a visible chain.
    root = store.add(fact("the deploy root is the app folder", 200))
    root2 = store.supersede(root.id, fact("the deploy root is the web folder", 120), at=ago(120))
    store.supersede(root2.id, fact("the deploy root is the projects folder", 9), at=ago(9))

    # Believed, then found to be wrong. Withdrawn, not deleted.
    wrong = store.add(fact("the office closes at six", 150))
    store.retract(wrong.id, "you told me it is actually seven", at=ago(5))

    # Only known recently, so questions about earlier correctly return nothing.
    store.add(fact("the spare key is with the neighbour", 55))

    # Open items — present by day, dropped at night.
    store.add(fact("the Kestrel review is waiting on you", 4, tags=("open",)))
    store.add(fact("the quarterly numbers are still unsigned", 11, tags=("open",)))

    # Plain background facts.
    store.add(fact("the trunk branch is called master", 180))
    store.add(fact("bin day is Tuesday", 300))

    return store


def reset(path) -> MemoryStore:
    """Wipe and reseed. Used by the demo's reset button only.

    Deleting the log is not something the library does — the whole design is
    append-only. It is a demo affordance, kept here rather than in the store so
    that nobody mistakes it for part of the memory model.
    """
    from pathlib import Path

    p = Path(path)
    if p.exists():
        p.unlink()
    return seed(MemoryStore(p))

"""Waking up: assembling a briefing within a budget, without inference.

The problem this solves is not "how do I store memories" but "how does an
assistant come back after time away without either reading everything or
pretending the last conversation never happened."

Two properties matter, and they pull against each other:

    bounded    the work must not grow with the size of memory, or the assistant
               gets slower every day it is used
    grounded   the briefing must say what actually changed, not a summary that
               drifts from the record

So a wake is deterministic assembly from stored state. No model is called. That
is what makes a sub-500ms budget achievable at all — and it is why the fast path
and the reasoning path are kept separate and named. Dressing an inference call
up as a "wake" would blow the budget and be unbounded besides.

    briefing = wake(store, kernel=DEFAULT_KERNEL, trigger=Trigger.NAMED)
    print(briefing.text)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from core.budget import Budget
from core.daypart import Daypart, Profile, profile_for
from core.kernel import DEFAULT_KERNEL, Kernel
from core.store import Kind, Memory, MemoryStore, parse_time
from core.tiers import Section, Tier, Trigger, for_trigger, register

# How far back "recently" reaches when reporting what changed.
RECENT_WINDOW_DAYS = 14

# The whole wake, kernel included. Uncomfortable on purpose: a ceiling that
# never binds is not doing anything.
DEFAULT_CEILING_TOKENS = 1500

# Each section is bounded in its own right, not merely capped by the total.
# Without this a store of 500 facts produces a briefing that is one enormous
# list of facts which happens to fit, having crowded out everything that
# changed today. Staying under the ceiling is not the same as being bounded.
SECTION_ITEM_LIMIT = 12


def _bulleted(lines: list[str], limit: int = SECTION_ITEM_LIMIT) -> str:
    """Render at most ``limit`` lines, and say honestly what was left out.

    The remainder is not hidden. "and 208 more" tells the reader the briefing is
    a window rather than the whole picture, which is the difference between a
    summary and a misleading one.
    """
    if not lines:
        return ""
    if len(lines) <= limit:
        return "\n".join(lines)
    hidden = len(lines) - limit
    return "\n".join([*lines[:limit], f"- ...and {hidden} more"])


@dataclass
class WakeContext:
    """Everything a section builder is allowed to look at."""

    store: MemoryStore
    kernel: Kernel
    now: datetime
    subject: str | None = None
    since: datetime | None = None
    item_limit: int = SECTION_ITEM_LIMIT

    def believed_now(self) -> list[Memory]:
        return self.store.as_of(valid=self.now, belief=self.now, subject=self.subject)

    def window_start(self) -> datetime:
        return self.since or (self.now - timedelta(days=RECENT_WINDOW_DAYS))


# -- section builders ----------------------------------------------------


def _build_kernel(ctx: WakeContext) -> str:
    return ctx.kernel.render()


def _build_current(ctx: WakeContext) -> str:
    # Events are excluded: an EVENT was true at a moment, not ongoing, so it
    # does not belong in a list of what is currently the case. This is what
    # keeps an interaction log (questions asked, things done) out of the
    # standing-facts section while still living in the same store.
    facts = [m for m in ctx.believed_now() if m.kind is not Kind.EVENT]
    if not facts:
        return ""
    # Newest first, so if the list must be cut it is the stalest facts that go.
    newest = sorted(facts, key=lambda m: m.asserted_at, reverse=True)
    return _bulleted([f"- {m.text}" for m in newest], ctx.item_limit)


def _build_changes(ctx: WakeContext) -> str:
    """What moved since the window opened.

    Reports supersessions and retractions rather than new facts alone, because
    "X is now Y, it was Z until the 4th" is the sentence a person actually
    needs on returning, and it is the one a system without belief history
    cannot produce.
    """
    start = ctx.window_start()

    # Changes are ranked by how much they should disturb you, not alphabetically.
    # A withdrawal means you have been acting on something false, which outranks
    # an answer merely moving, which outranks a new fact. This matters most
    # exactly when it is least visible: under a tight item limit, arbitrary
    # ordering drops the line you most needed to hear.
    WITHDRAWN, SUPERSEDED, NEW = 0, 1, 2
    ranked: list[tuple[int, str, str]] = []

    # A replacement is reported once, on the line that also names what it
    # replaced. Without this it appears twice — as "new: X" and again as
    # "X (was: Y)" — which reads as two separate changes rather than one.
    successors = {
        replaced
        for m in ctx.store.all()
        if (replaced := ctx.store.superseded_by(m.id)) is not None
    }

    for memory in ctx.store.all():
        if ctx.subject and memory.subject != ctx.subject:
            continue

        # An interaction log — questions asked, things done — lives in the same
        # store but is not news. You were there when it happened. Reporting
        # "you asked about the standup" back to the person who asked is noise
        # that crowds out the changes they could not have known about.
        if memory.kind is Kind.EVENT:
            continue

        replaced = ctx.store.superseded_by(memory.id)
        if replaced:
            # Report the edge from the memory that was replaced. A memory in the
            # middle of a chain is both a successor and superseded, so it must
            # still be considered here — skipping every successor outright loses
            # the most recent change in any chain longer than one link.
            successor = ctx.store.get(replaced)
            if successor and parse_time(successor.asserted_at) >= start:
                ranked.append(
                    (SUPERSEDED, successor.asserted_at, f"- {successor.text} (was: {memory.text})")
                )
            continue

        retraction = ctx.store.retraction(memory.id)
        if retraction and parse_time(retraction.at) >= start:
            ranked.append((WITHDRAWN, retraction.at, f"- withdrawn: {memory.text} — {retraction.reason}"))
            continue

        # A replacement is already named by the edge above; reporting it again
        # as newly learned would read as two changes rather than one.
        if memory.id in successors:
            continue

        if parse_time(memory.asserted_at) >= start:
            ranked.append((NEW, memory.asserted_at, f"- new: {memory.text}"))

    # Urgency ascending, then most recent first within a rank. Timestamps are
    # compared as instants here for the same reason as everywhere else in this
    # codebase: text ordering misplaces anything with a different UTC offset.
    ordered = sorted(ranked, key=lambda r: (r[0], -parse_time(r[1]).timestamp()))
    return _bulleted([line for _, _, line in ordered], ctx.item_limit)


def _build_open(ctx: WakeContext) -> str:
    items = [m for m in ctx.believed_now() if "open" in m.tags]
    if not items:
        return ""
    return _bulleted([f"- {m.text}" for m in sorted(items, key=lambda m: m.asserted_at)], ctx.item_limit)


def _build_history(ctx: WakeContext) -> str:
    """Chains where the answer has moved more than once.

    L2 material: worth having when addressed directly, not worth the tax on
    every ordinary wake.
    """
    lines: list[str] = []
    for memory in ctx.believed_now():
        chain = ctx.store.history(memory.id)
        if len(chain) > 2:
            path = " -> ".join(m.text for m in chain)
            lines.append(f"- {path}")
    return _bulleted(sorted(lines), ctx.item_limit)


def _build_withdrawn(ctx: WakeContext) -> str:
    """Things believed and later found wrong. L2: useful context, not urgent."""
    lines = []
    for memory in ctx.store.all():
        retraction = ctx.store.retraction(memory.id)
        if retraction:
            lines.append(f"- {memory.text} — withdrawn: {retraction.reason}")
    return _bulleted(sorted(lines), ctx.item_limit)


register(Section("kernel", Tier.L0, "", _build_kernel))
register(Section("changed", Tier.L1, "Since we last spoke", _build_changes))
register(Section("current", Tier.L1, "What is true now", _build_current))
register(Section("open", Tier.L1, "Still open", _build_open))
register(Section("history", Tier.L2, "How some of this moved", _build_history))
register(Section("withdrawn", Tier.L2, "Things I no longer believe", _build_withdrawn))


# -- the wake ------------------------------------------------------------


@dataclass
class Briefing:
    """The result of a wake."""

    text: str
    trigger: Trigger
    budget: Budget
    daypart: Daypart = Daypart.AFTERNOON
    greeting: str = ""
    dropped: list[str] = field(default_factory=list)
    included: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    # Section name -> its individual items, unformatted. Adapters that render
    # for a different medium — speech, a card, a phone screen — need the parts,
    # not the prose. Re-parsing `text` to recover them would couple every
    # adapter to this module's punctuation.
    items: dict[str, list[str]] = field(default_factory=dict)

    @property
    def within_budget(self) -> bool:
        return self.budget.used <= self.budget.ceiling

    def summary(self) -> str:
        return (
            f"{self.trigger.name.lower()} wake in {self.elapsed_ms:.1f}ms, "
            f"{self.budget.used}/{self.budget.ceiling} tokens "
            f"({self.budget.fill:.0%}), "
            f"{len(self.included)} sections"
            + (f", {len(self.skipped)} skipped for budget" if self.skipped else "")
        )


def wake(
    store: MemoryStore,
    *,
    kernel: Kernel = DEFAULT_KERNEL,
    trigger: Trigger = Trigger.SESSION,
    ceiling: int = DEFAULT_CEILING_TOKENS,
    now: datetime | None = None,
    subject: str | None = None,
    since: datetime | None = None,
    utc_offset_hours: float = 0.0,
) -> Briefing:
    """Assemble a briefing within ``ceiling`` tokens.

    The kernel is required and claims its space first. Remaining sections are
    offered shallowest-tier-first, so if the budget runs out it is deep recall
    that goes, never what changed today.

    Within a tier, the time of day decides the order and the volume. Tier still
    dominates — a daypart may reprioritise what is eligible, never smuggle deep
    recall ahead of today's changes.
    """
    started = time.perf_counter()
    moment = now or datetime.now(timezone.utc)
    profile: Profile = profile_for(moment, utc_offset_hours=utc_offset_hours)

    ctx = WakeContext(
        store=store,
        kernel=kernel,
        now=moment,
        subject=subject,
        since=since,
        item_limit=profile.item_limit,
    )

    budget = Budget(ceiling=ceiling)
    briefing = Briefing(
        text="",
        trigger=trigger,
        budget=budget,
        daypart=profile.daypart,
        greeting=profile.greeting,
    )
    blocks: list[str] = []

    def order(section: Section) -> tuple[int, int, str]:
        rank = (
            profile.priority.index(section.name)
            if section.name in profile.priority
            else len(profile.priority)
        )
        return (int(section.tier), rank, section.name)

    for section in sorted(for_trigger(trigger), key=order):
        if section.name in profile.drop:
            briefing.dropped.append(section.name)
            continue

        body = section.build(ctx)
        if not body.strip():
            briefing.empty.append(section.name)
            continue

        block = f"{section.heading}\n{body}" if section.heading else body

        if section.tier is Tier.L0:
            budget.require(section.name, block)
            blocks.append(block)
            briefing.included.append(section.name)
            continue

        if budget.offer(section.name, block):
            blocks.append(block)
            briefing.included.append(section.name)
            briefing.items[section.name] = [
                line[2:] for line in body.splitlines() if line.startswith("- ")
            ]
        else:
            briefing.skipped.append(section.name)

    briefing.text = "\n\n".join(blocks)
    briefing.elapsed_ms = (time.perf_counter() - started) * 1000
    return briefing

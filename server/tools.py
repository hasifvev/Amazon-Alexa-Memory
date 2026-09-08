"""The memory tools Alexa+ can call, and their spoken answers.

Written for voice first. That constraint is not decoration — it changes the
design:

    * Answers are one or two spoken sentences. A bulleted list is unreadable
      aloud, and a JSON blob is worse.
    * Nothing here calls a model. Every answer is assembled from stored state,
      which is what makes the sub-500ms round-trip budget achievable at all.
    * When a fact has changed, the answer says so unprompted — "it's X now, it
      was Y until March". That is the sentence a person actually wants, and a
      store without belief history cannot produce it.
    * When nothing was known, the answer says nothing was known. An assistant
      that quietly answers a question about March with today's value is worse
      than one that admits the gap.

Kept free of transport concerns so it can be tested without HTTP.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from core.store import Memory, MemoryStore
from core.tiers import Trigger
from core.wake import wake

MAX_SPOKEN_ITEMS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_when(phrase: str | None, *, now: datetime | None = None) -> datetime:
    """Turn a spoken time reference into an instant.

    Voice input does not arrive as ISO-8601. People say "three months ago" and
    "last March". This handles the forms that actually occur and is honest
    about the rest: an unparseable phrase raises rather than silently defaulting
    to now, because silently answering about the wrong date is the exact failure
    this whole system exists to prevent.
    """
    moment = now or _now()
    if not phrase or phrase.strip().lower() in {"now", "today", "currently"}:
        return moment

    text = phrase.strip().lower()

    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    relative = re.fullmatch(r"(\d+)\s+(day|week|month|year)s?\s+ago", text)
    if relative:
        count = int(relative.group(1))
        unit = relative.group(2)
        days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * count
        return moment - timedelta(days=days)

    if text == "yesterday":
        return moment - timedelta(days=1)
    if text in {"last week", "a week ago"}:
        return moment - timedelta(days=7)
    if text in {"last month", "a month ago"}:
        return moment - timedelta(days=30)
    if text in {"last year", "a year ago"}:
        return moment - timedelta(days=365)

    raise ValueError(
        f"I can't work out when {phrase!r} is. Try a date like 2026-03-01, "
        "or something like 'three months ago'."
    )


def _spoken_date(moment: datetime) -> str:
    return moment.strftime("%-d %B %Y") if hasattr(moment, "strftime") else str(moment)


def _fmt_date(moment: datetime) -> str:
    """Windows has no %-d, so format the day without padding by hand."""
    return f"{moment.day} {moment.strftime('%B %Y')}"


def _sentence(text: str) -> str:
    """Capitalise and terminate. Spoken output is read aloud verbatim."""
    text = text.strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?" else text + "."


def _join(items: list[str]) -> str:
    """Join for the ear, not the eye: 'a, b and c' rather than 'a; b; c'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _speak_change(item: str) -> str:
    """Turn a wake's change line into something a voice can say.

    The wake emits log-shaped markers — "new:", "(was: ...)", "withdrawn:" —
    which are right for a text briefing and wrong read aloud. Translating them
    is the voice adapter's job, which is why the wake hands over items rather
    than finished prose.
    """
    if item.startswith("new: "):
        return f"you told me {item[5:]}"
    if item.startswith("withdrawn: "):
        body = item[len("withdrawn: ") :]
        fact, _, reason = body.partition(" — ")
        return f"I withdrew that {fact}" + (f", because {reason}" if reason else "")
    if " (was: " in item and item.endswith(")"):
        current, _, previous = item.partition(" (was: ")
        return f"{current}, which was {previous[:-1]}"
    return item


def _matches(memory: Memory, subject: str) -> bool:
    needle = subject.strip().lower()
    if not needle:
        return False
    return needle in memory.text.lower() or any(needle in t.lower() for t in memory.tags)


class MemoryTools:
    """Everything Alexa+ can do with the memory, as spoken answers."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        subject: str = "default",
        utc_offset_hours: float = 8.0,
    ) -> None:
        self.store = store
        self.subject = subject
        # The listener's local offset, never the host's. A server briefing
        # somebody in another timezone must use their hour.
        self.utc_offset_hours = utc_offset_hours

    # -- the headline ---------------------------------------------------

    def catch_me_up(self, *, named: bool = False, hour: int | None = None) -> str:
        """The wake. What is true, what changed, what is still open.

        ``hour`` pretends it is a different time of day, which is how the demo
        shows that the briefing genuinely reprioritises rather than restyles.
        It shifts the clock only; nothing about the memory changes.
        """
        moment = _now()
        if hour is not None:
            local = moment.astimezone(timezone(timedelta(hours=self.utc_offset_hours)))
            moment = local.replace(hour=hour % 24, minute=0, second=0, microsecond=0)

        briefing = wake(
            self.store,
            trigger=Trigger.NAMED if named else Trigger.SESSION,
            subject=self.subject,
            now=moment,
            utc_offset_hours=self.utc_offset_hours,
        )
        # The wake ends a truncated list with "...and N more", which is right in
        # writing and nonsense read aloud. Strip it and fold the count into the
        # spoken tail instead.
        def _real(items: list[str]) -> tuple[list[str], int]:
            hidden = 0
            kept = []
            for item in items:
                if item.startswith("...and ") and item.endswith(" more"):
                    hidden += int(item.split()[1]) if item.split()[1].isdigit() else 0
                    continue
                kept.append(item)
            return kept, hidden

        changes, changes_hidden = _real(briefing.items.get("changed", []))
        open_items, open_hidden = _real(briefing.items.get("open", []))
        parts: list[str] = []

        if changes:
            spoken = [_speak_change(c) for c in changes[:MAX_SPOKEN_ITEMS]]
            extra = len(changes) - len(spoken) + changes_hidden
            tail = f", and {_plural(extra, 'other change')}" if extra > 0 else ""
            parts.append(f"Since we last spoke, {_join(spoken)}{tail}.")

        if open_items:
            spoken = open_items[:MAX_SPOKEN_ITEMS]
            extra = len(open_items) - len(spoken) + open_hidden
            tail = f", plus {_plural(extra, 'other')}" if extra > 0 else ""
            parts.append(f"Still open: {_join(spoken)}{tail}.")

        if parts:
            return " ".join(_sentence(p) for p in parts)

        known = self.store.as_of(subject=self.subject)
        if not known:
            return "I don't have anything for you yet. Tell me something to remember."
        return f"Nothing has changed. I still know {_plural(len(known), 'thing')}."

    # -- writing ---------------------------------------------------------

    def remember(self, fact: str, *, tags: list[str] | None = None) -> str:
        """Store something new."""
        if not fact.strip():
            return "I need something to remember."
        memory = Memory(
            text=fact.strip(),
            subject=self.subject,
            source="alexa",
            valid_from=_now().isoformat(timespec="seconds"),
            tags=tuple(tags or ()),
        )
        self.store.add(memory)
        return f"Got it. I'll remember that {fact.strip()}."

    def correct(self, about: str, new_fact: str) -> str:
        """The answer changed. Supersede, keeping the old one for history."""
        matches = [m for m in self.store.as_of(subject=self.subject) if _matches(m, about)]
        if not matches:
            return f"I don't have anything about {about} to correct."
        if len(matches) > 1:
            options = "; ".join(m.text for m in matches[:MAX_SPOKEN_ITEMS])
            return f"I know a few things about {about}: {options}. Which one?"

        old = matches[0]
        replacement = Memory(
            text=new_fact.strip(),
            subject=self.subject,
            source="alexa",
            valid_from=_now().isoformat(timespec="seconds"),
            tags=old.tags,
        )
        self.store.supersede(old.id, replacement)
        return (
            f"Updated. It's now that {new_fact.strip()}. "
            f"I've kept that it was {old.text}, until today."
        )

    def forget(self, about: str, reason: str = "you told me it was wrong") -> str:
        """It was never true. Retract — which does not delete."""
        matches = [m for m in self.store.as_of(subject=self.subject) if _matches(m, about)]
        if not matches:
            return f"I don't have anything about {about}."
        if len(matches) > 1:
            options = "; ".join(m.text for m in matches[:MAX_SPOKEN_ITEMS])
            return f"I know a few things about {about}: {options}. Which one?"

        self.store.retract(matches[0].id, reason)
        return (
            f"I've withdrawn that. I won't say it again, "
            f"though I'll still know I used to think it."
        )

    # -- reading ----------------------------------------------------------

    def recall(self, about: str, when: str | None = None) -> str:
        """What was true about something, now or at a point in the past."""
        try:
            moment = parse_when(when)
        except ValueError as exc:
            return str(exc)

        asking_about_past = when is not None and moment < _now() - timedelta(hours=1)
        found = [m for m in self.store.as_of(valid=moment) if _matches(m, about)]

        if not found:
            ever = [m for m in self.store.all() if _matches(m, about)]
            if not ever:
                return f"I don't know anything about {about}."
            if asking_about_past:
                return (
                    f"I didn't know anything about {about} on {_fmt_date(moment)}. "
                    "I only learned about it later."
                )
            withdrawn = [m for m in ever if self.store.retraction(m.id)]
            if withdrawn:
                reason = self.store.retraction(withdrawn[0].id).reason
                return (
                    f"I did think {withdrawn[0].text}, but I withdrew that — {reason}. "
                    "So I don't know."
                )
            return f"I don't know anything about {about} right now."

        spoken = _join([m.text for m in found[:MAX_SPOKEN_ITEMS]])

        if asking_about_past:
            return _sentence(f"as of {_fmt_date(moment)}, {spoken}")

        # Unprompted history: if this changed, say what it was and when.
        chain = self.store.history(found[0].id)
        if len(chain) > 1:
            previous = chain[-2]
            changed_on = self.store.valid_window(previous)[1]
            when_text = (
                f" on {_fmt_date(parse_when(changed_on))}" if changed_on else ""
            )
            return _sentence(
                f"{spoken}. That changed{when_text} — before, {previous.text}"
            )
        return _sentence(spoken)

    def what_changed(self, since: str | None = "7 days ago") -> str:
        """What moved recently, phrased for speech."""
        try:
            start = parse_when(since)
        except ValueError as exc:
            return str(exc)

        # A replacement is one change, reported once. Without this it surfaces
        # twice — as the supersession and again as a newly learned fact — which
        # sounds like two separate things happening.
        successors = {
            replaced
            for m in self.store.all()
            if (replaced := self.store.superseded_by(m.id)) is not None
        }

        changes: list[str] = []
        for memory in self.store.all():
            if memory.subject != self.subject:
                continue

            replacement_id = self.store.superseded_by(memory.id)
            if replacement_id:
                # Considered even when this memory is itself a successor: in a
                # chain A->B->C, skipping every successor loses the B->C edge,
                # which is the most recent change and the one worth hearing.
                successor = self.store.get(replacement_id)
                if successor and parse_when(successor.asserted_at) >= start:
                    changes.append(f"{successor.text}, which was {memory.text}")
                continue

            retraction = self.store.retraction(memory.id)
            if retraction and parse_when(retraction.at) >= start:
                changes.append(f"I withdrew that {memory.text}")
                continue

            if memory.id in successors:
                continue

            if parse_when(memory.asserted_at) >= start:
                changes.append(f"you told me {memory.text}")

        if not changes:
            return "Nothing has changed."

        spoken = _join(changes[:MAX_SPOKEN_ITEMS])
        extra = len(changes) - MAX_SPOKEN_ITEMS
        if extra > 0:
            spoken += f", and {_plural(extra, 'other change')}"
        return _sentence(spoken)

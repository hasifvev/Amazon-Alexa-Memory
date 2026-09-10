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

from pydantic import BaseModel, Field

from core.insight import churn, corrections, mistakes
from core.store import Kind, Memory, MemoryStore
from core.tiers import Trigger
from core.wake import wake

MAX_SPOKEN_ITEMS = 3


class TimelineEntry(BaseModel):
    """One step in a belief's history, shaped for rendering.

    Field names avoid `from`, which is a Python keyword and cannot be a model
    field without aliasing gymnastics that would leak into the view.
    """

    text: str
    status: str = Field(description="current, replaced, or withdrawn")
    starts: str | None = None
    ends: str | None = None
    held_days: int | None = Field(default=None, description="days believed before withdrawal")
    reason: str | None = None


class Timeline(BaseModel):
    """A topic's full history. Rendered on a screen, spoken on a speaker."""

    about: str
    entries: list[TimelineEntry]
    footnote: str
    spoken: str


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


def _parse_until(phrase: str, *, now: datetime | None = None) -> datetime:
    """Turn a forward-looking time phrase into an expiry instant.

    Complements parse_when for writing rather than reading: people say
    'just for today', 'until tomorrow', 'for the next 3 days' when creating
    ephemeral memories, not 'tomorrow ago'.
    """
    moment = now or _now()
    text = phrase.strip().lower()

    # Forward-looking relative phrases
    in_match = re.fullmatch(r"(?:in\s+)?(\d+)\s+(day|week|month|year)s?", text)
    if in_match:
        count = int(in_match.group(1))
        unit = in_match.group(2)
        days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * count
        return moment + timedelta(days=days)

    if text in {"today", "end of today", "tonight", "end of day"}:
        return moment.replace(hour=23, minute=59, second=59, microsecond=0)
    if text in {"tomorrow", "end of tomorrow"}:
        return (moment + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
    if text in {"this week", "end of the week"}:
        return moment + timedelta(days=7)

    # Fall back to parse_when for ISO dates and backward phrases used as expiries
    try:
        result = parse_when(phrase, now=now)
        if result <= moment:
            raise ValueError(
                f"The expiry {phrase!r} is in the past. Use a future date or 'in 3 days'."
            )
        return result
    except ValueError:
        raise ValueError(
            f"I can't work out when {phrase!r} is. Try 'end of today', 'tomorrow', "
            "'in 3 days', or a date like 2026-10-01."
        )


def _fmt_until(moment: datetime) -> str:
    """Human label for an expiry instant."""
    now = _now()
    delta = (moment - now).days
    if delta == 0:
        return "end of today"
    if delta == 1:
        return "tomorrow"
    if delta < 8:
        return f"end of {moment.strftime('%A')}"
    return _fmt_date(moment)


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


# ---------------------------------------------------------------------------
# Personality helpers — voice, tone, and time
# ---------------------------------------------------------------------------

def _display_name(store: MemoryStore, subject: str) -> str:
    """Return the user's preferred name if stored, else 'there'."""
    for m in store.as_of(subject=subject):
        if any(t == "profile:name" for t in m.tags):
            lower = m.text.lower()
            for prefix in ("my name is ", "i am ", "call me "):
                if prefix in lower:
                    rest = m.text[lower.index(prefix) + len(prefix):].strip()
                    name = rest.split()[0].rstrip(".,!") if rest else ""
                    if name:
                        return name.title()
    return "there"


def _relationship_stage(store: MemoryStore, subject: str) -> int:
    """0=stranger 1=acquaintance 2=regular 3=familiar — based on memory count."""
    count = len(store.as_of(subject=subject))
    if count <= 5:
        return 0
    if count <= 20:
        return 1
    if count <= 50:
        return 2
    return 3


def _time_greeting(hour: int) -> str:
    if 6 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    if 17 <= hour < 21:
        return "Good evening"
    return "Hey"


def _clock(moment: datetime) -> str:
    """12-hour clock string without leading zero, cross-platform."""
    h = moment.hour % 12 or 12
    return f"{h}:{moment.strftime('%M')} {'AM' if moment.hour < 12 else 'PM'}"


class MemoryTools:
    """Everything Alexa+ can do with the memory, as spoken answers."""

    LIST_TAG_PREFIX = "list:"
    PROJECT_TAG_PREFIX = "project:"
    PROFILE_TAG_PREFIX = "profile:"

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

    def _get_tz_offset(self) -> float:
        """Read UTC offset from profile memory, or fall back to instance default."""
        for m in self.store.as_of(subject=self.subject):
            if any(t == "profile:timezone" for t in m.tags):
                match = re.search(r"([+-]?\d+(?:\.\d+)?)", m.text)
                if match:
                    try:
                        return float(match.group(1))
                    except ValueError:
                        pass
        return self.utc_offset_hours

    def _get_city(self) -> str:
        """Read city from profile memory."""
        for m in self.store.as_of(subject=self.subject):
            if any(t in ("profile:location", "profile:city") for t in m.tags):
                lower = m.text.lower()
                for prefix in ("i live in ", "i'm in ", "i am in ", "based in ", "location is ", "i am based in "):
                    if prefix in lower:
                        rest = m.text[lower.index(prefix) + len(prefix):].strip()
                        return rest.split(",")[0].strip()
        return ""

    # -- the headline ---------------------------------------------------

    def catch_me_up(self, *, named: bool = False, hour: int | None = None) -> str:
        """The wake. What is true, what changed, what is still open.

        ``hour`` pretends it is a different time of day, which is how the demo
        shows that the briefing genuinely reprioritises rather than restyles.
        It shifts the clock only; nothing about the memory changes.
        """
        moment = _now()
        tz_offset = self._get_tz_offset()
        local = moment.astimezone(timezone(timedelta(hours=tz_offset)))
        if hour is not None:
            local = local.replace(hour=hour % 24, minute=0, second=0, microsecond=0)
            moment = local

        briefing = wake(
            self.store,
            trigger=Trigger.NAMED if named else Trigger.SESSION,
            subject=self.subject,
            now=moment,
            utc_offset_hours=tz_offset,
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

        # --- Personality layer -------------------------------------------
        name = _display_name(self.store, self.subject)
        stage = _relationship_stage(self.store, self.subject)
        greeting = _time_greeting(local.hour)
        city = self._get_city()
        location_part = f" in {city}" if city else ""
        time_line = f"It's {local.strftime('%A')}, {_fmt_date(local)}, {_clock(local)}{location_part}."

        if stage == 0:
            opener = f"{greeting}! I'm still getting to know you. {time_line}"
        elif stage == 1:
            n = f", {name}" if name != "there" else ""
            opener = f"{greeting}{n}! Good to have you back. {time_line}"
        elif stage == 2:
            n = f", {name}" if name != "there" else ""
            opener = f"{greeting}{n}! Picking up where we left off. {time_line}"
        else:
            n = name if name != "there" else "Hey"
            opener = f"{n}. {greeting.lower()}. {time_line}"

        # Proactive nudges: memories expiring within 3 days
        nudges = []
        now_ts = _now()
        for m in self.store.as_of(subject=self.subject):
            if m.valid_until and not any(t.startswith(self.LIST_TAG_PREFIX) for t in m.tags):
                try:
                    exp = parse_when(m.valid_until)
                    delta = (exp - now_ts).days
                    if 0 <= delta <= 3:
                        nudges.append((delta, m.text))
                except ValueError:
                    pass

        parts: list[str] = [opener]

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

        if nudges:
            nudge_texts = []
            for delta, text in nudges[:2]:
                if delta == 0:
                    nudge_texts.append(f"'{text}' expires today")
                elif delta == 1:
                    nudge_texts.append(f"'{text}' expires tomorrow")
                else:
                    nudge_texts.append(f"'{text}' expires in {delta} days")
            parts.append(f"Heads up: {_join(nudge_texts)}.")

        if len(parts) > 1:
            return " ".join(_sentence(p) for p in parts)

        known = self.store.as_of(subject=self.subject)
        if not known:
            return f"{opener} Tell me something to remember and I'll keep it for you."
        return f"{opener} Nothing new — I still know {_plural(len(known), 'thing')} about you."

    # -- writing ---------------------------------------------------------

    def remember(self, fact: str, *, tags: list[str] | None = None) -> str:
        """Store something new, with a clever callback if something similar exists."""
        if not fact.strip():
            return "I need something to remember."

        name = _display_name(self.store, self.subject)
        name_part = f", {name}" if name != "there" else ""

        # Check for overlap with existing facts (clever callback)
        words = [w for w in fact.strip().lower().split() if len(w) > 3]
        overlap = [
            m for m in self.store.as_of(subject=self.subject)
            if any(w in m.text.lower() for w in words[:3])
            and not any(t.startswith(self.LIST_TAG_PREFIX) for t in m.tags)
            and not any(t.startswith(self.PROFILE_TAG_PREFIX) for t in m.tags)
        ]

        memory = Memory(
            text=fact.strip(),
            subject=self.subject,
            source="alexa",
            valid_from=_now().isoformat(timespec="seconds"),
            tags=tuple(tags or ()),
        )
        self.store.add(memory)

        if overlap:
            old = overlap[0].text
            if old != fact.strip():
                return f"Got it{name_part}. Updated — it was '{old}' before."
        return f"Got it{name_part}. I'll remember that {fact.strip()}."

    def remember_for(self, fact: str, until: str, *, tags: list[str] | None = None) -> str:
        """Store something that expires automatically.

        The natural voice use case for expiring memory: grocery lists, travel
        info, one-day reminders. The memory stays in the log after expiry —
        it just stops answering current questions. History remains intact.

        `until` accepts the same phrases parse_when does, plus a few forward-
        looking forms: 'end of today', 'tomorrow', 'in 3 days', 'next Monday'.
        """
        if not fact.strip():
            return "I need something to remember."
        try:
            expires = _parse_until(until)
        except ValueError as exc:
            return str(exc)
        memory = Memory(
            text=fact.strip(),
            subject=self.subject,
            source="alexa",
            valid_from=_now().isoformat(timespec="seconds"),
            valid_until=expires.isoformat(timespec="seconds"),
            tags=tuple(tags or ()),
        )
        self.store.add(memory)
        label = _fmt_until(expires)
        return f"Got it. I'll remember that {fact.strip()}, until {label}."

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

        m = matches[0]
        held = (_now() - parse_when(m.asserted_at)).days
        duration = "less than a day" if held < 1 else _plural(held, "day")
        self.store.retract(m.id, reason)
        return (
            f"Done — I've withdrawn that. You held that belief for {duration}. "
            f"I'll still know I used to think it."
        )

    # -- reading ----------------------------------------------------------

    def recall(self, about: str, when: str | None = None) -> str:
        """What was true about something, now or at a point in the past."""
        try:
            moment = parse_when(when)
        except ValueError as exc:
            return str(exc)

        asking_about_past = when is not None and moment < _now() - timedelta(hours=1)

        # Check before logging, or this very question counts as a prior ask.
        prior = self._prior_asks(about)
        self._log_ask(about)

        found = [
            m
            for m in self.store.as_of(valid=moment, subject=self.subject)
            if _matches(m, about) and m.kind is not Kind.EVENT
        ]

        if not found:
            ever = [
                m
                for m in self.store.all()
                if _matches(m, about) and m.subject == self.subject
            ]
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
            ) + self._deja_vu(about, prior)
        return _sentence(spoken) + self._deja_vu(about, prior)

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

    # -- déjà vu: have we been here before? ------------------------------

    ASK_TAG = "asked"

    def _topic_key(self, about: str) -> str:
        return "topic:" + re.sub(r"[^a-z0-9]+", "-", about.strip().lower()).strip("-")[:40]

    def _prior_asks(self, about: str) -> list[Memory]:
        """Times this topic was asked about before, oldest first.

        Questions are stored as EVENT memories in the same log as everything
        else, so "when did I last ask about this" is answerable by the same
        temporal machinery rather than a second bespoke store. Events are
        excluded from the standing-facts view, so the log does not become noise.
        """
        key = self._topic_key(about)
        asks = [
            m
            for m in self.store.all()
            if m.kind is Kind.EVENT
            and m.subject == self.subject
            and self.ASK_TAG in m.tags
            and key in m.tags
        ]
        return sorted(asks, key=lambda m: m.asserted_at)

    def _log_ask(self, about: str) -> None:
        # Microsecond precision, deliberately finer than the second-resolution
        # default used for facts. Memory ids are content-addressed over the
        # assertion time, so two identical facts asserted in the same second
        # collide — which is correct, that is deduplication. Two identical
        # *questions* a moment apart are two events, and collapsing them would
        # under-count exactly the recurrence this feature exists to notice.
        stamp = _now().isoformat()
        self.store.add(
            Memory(
                text=f"you asked about {about.strip()}",
                kind=Kind.EVENT,
                subject=self.subject,
                source="alexa",
                asserted_at=stamp,
                valid_from=stamp,
                tags=(self.ASK_TAG, self._topic_key(about)),
            )
        )

    def _deja_vu(self, about: str, prior: list[Memory]) -> str:
        """"You asked me this before, and the answer was different then."

        Only says anything when the answer has actually moved. Announcing that
        you asked the same question twice, with the same answer both times, is
        an observation about you rather than a useful one about the memory.
        """
        if not prior:
            return ""

        first = prior[0]
        then = [
            m.text
            for m in self.store.as_of(
                valid=parse_when(first.asserted_at), subject=self.subject
            )
            if _matches(m, about) and m.kind is not Kind.EVENT
        ]
        now = [
            m.text
            for m in self.store.as_of(subject=self.subject)
            if _matches(m, about) and m.kind is not Kind.EVENT
        ]

        if not then or set(then) == set(now):
            return ""
        return (
            f" You asked me this on {_fmt_date(parse_when(first.asserted_at))} too — "
            f"back then, {_join(then[:1])}."
        )

    # -- what have I been wrong about? ------------------------------------

    def wrong_about(self, limit: int = 2) -> str:
        """Withdrawn beliefs, and how long each was carried.

        Only possible because retraction keeps the record. A store that deletes
        what it withdraws cannot answer this at all — it has destroyed the
        evidence that it was ever wrong.
        """
        wrong = mistakes(self.store, subject=self.subject)
        if not wrong:
            return "You haven't withdrawn anything. Nothing I know has turned out to be false."

        summary = churn(self.store, subject=self.subject)
        lines = []
        for m in wrong[:limit]:
            days = m.held_days
            duration = "less than a day" if days < 1 else _plural(days, "day")
            lines.append(f"{m.memory.text} — you believed that for {duration}, until {m.reason}")

        head = _plural(len(wrong), "thing")
        tail = f", and {_plural(len(wrong) - len(lines), 'other')}" if len(wrong) > len(lines) else ""
        return _sentence(
            f"You've withdrawn {head}. The longest-standing: {_join(lines)}{tail}"
        )

    # -- multi-person: an Echo is a shared device -------------------------

    def for_subject(self, who: str | None) -> "MemoryTools":
        """A view of the same store scoped to a different person.

        An Echo sits in a kitchen, not on one person's desk. Alexa+ knows who is
        speaking, so "my standup" and "her standup" must be different facts
        rather than one contested one. The store has always scoped by subject;
        this is the seam that uses it.
        """
        if not who or who.strip().lower() == self.subject:
            return self
        return MemoryTools(
            self.store,
            subject=who.strip().lower(),
            utc_offset_hours=self.utc_offset_hours,
        )


    SHARED_TAG_PREFIX = "shared-by:"

    def share(self, fact: str, with_who: str) -> str:
        """Push a fact directly into someone else's memory on this device.

        An Echo is a shared household device. This is the tool that makes that
        real: "Tell Aisyah the wifi password changed" stores a fact in Aisyah's
        memory space, tagged with who sent it. When Aisyah next asks, the
        answer is there — and it says who told her.
        """
        if not fact.strip():
            return "I need something to share."
        if not with_who.strip():
            return "I need a name to share with."
        recipient = with_who.strip().lower()
        tag = f"{self.SHARED_TAG_PREFIX}{self.subject}"
        recipient_tools = self.for_subject(recipient)
        memory = Memory(
            text=fact.strip(),
            subject=recipient,
            source="alexa",
            valid_from=_now().isoformat(timespec="seconds"),
            tags=(tag,),
        )
        self.store.add(memory)
        name = with_who.strip().title()
        return f"Done. {name} will see that {fact.strip()} next time they catch up."

    def shared_with_me(self) -> str:
        """Facts that other household members have shared with this person.

        Returns what was pushed via `share`, attributed to the sender. A person
        joining the conversation cold can ask what they missed without wading
        through their own notes.
        """
        shared = [
            m
            for m in self.store.as_of(subject=self.subject)
            if any(t.startswith(self.SHARED_TAG_PREFIX) for t in m.tags)
        ]
        if not shared:
            return "Nobody has shared anything with you yet."
        lines = []
        for m in shared[:MAX_SPOKEN_ITEMS]:
            sender_tag = next(
                (t for t in m.tags if t.startswith(self.SHARED_TAG_PREFIX)), None
            )
            sender = sender_tag[len(self.SHARED_TAG_PREFIX):].title() if sender_tag else "someone"
            lines.append(f"{m.text} — from {sender}")
        extra = len(shared) - len(lines)
        tail = f", and {_plural(extra, 'other')}" if extra > 0 else ""
        return _sentence(f"Shared with you: {_join(lines)}{tail}")

    # -- what has moved vs what was wrong ---------------------------------

    def what_moved(self, limit: int = 3) -> str:
        """Facts whose answer CHANGED over time — not wrong, the world moved.

        Distinct from wrong_about, which lists beliefs that were never true.
        This lists beliefs that were true at the time and then superseded: the
        classic examples are standup times, addresses, project paths — things
        that change and leave a real history behind them.

        Uses corrections() from insight, which is already implemented in the
        core engine but was not previously exposed as a tool.
        """
        moved = corrections(self.store, subject=self.subject)
        if not moved:
            return "Nothing has changed history yet — every fact I know is still the first version."
        lines = []
        for c in moved[:limit]:
            days = c.held_days
            duration = "less than a day" if days < 1 else _plural(days, "day")
            lines.append(
                f"{c.replaced_by.text}, which was {c.memory.text} for {duration}"
            )
        head = _plural(len(moved), "fact")
        tail = f", and {_plural(len(moved) - len(lines), 'other')}" if len(moved) > len(lines) else ""
        return _sentence(f"{head} changed. The longest-standing: {_join(lines)}{tail}")

    # -- personality: current time and date ---------------------------------

    def what_time_is_it(self) -> str:
        """Current local date, day, and time — in the user's stored timezone."""
        tz_offset = self._get_tz_offset()
        local = _now().astimezone(timezone(timedelta(hours=tz_offset)))
        city = self._get_city()
        name = _display_name(self.store, self.subject)
        location_part = f" in {city}" if city else ""
        name_part = f", {name}" if name != "there" else ""
        return (
            f"It's {local.strftime('%A')}, {_fmt_date(local)}, "
            f"{_clock(local)}{location_part}{name_part}."
        )

    # -- lists: shopping, packing, errands -----------------------------------

    def add_to_list(self, item: str, list_name: str = "shopping") -> str:
        """Add an item to a named list. Returns updated count."""
        if not item.strip():
            return "I need an item to add."
        tag = f"{self.LIST_TAG_PREFIX}{list_name.strip().lower()}"
        # Idempotency: don't double-add
        existing = [
            m for m in self.store.as_of(subject=self.subject)
            if tag in m.tags and item.strip().lower() in m.text.lower()
        ]
        if existing:
            return f"{item.strip().title()} is already on your {list_name} list."
        # History callback: has this been bought before?
        prev = [
            m for m in self.store.all()
            if m.subject == self.subject and tag in m.tags
            and item.strip().lower() in m.text.lower()
        ]
        self.store.add(Memory(
            text=item.strip(),
            subject=self.subject,
            source="alexa",
            valid_from=_now().isoformat(timespec="seconds"),
            tags=(tag,),
        ))
        total = len([m for m in self.store.as_of(subject=self.subject) if tag in m.tags])
        if prev:
            return f"{item.strip().title()} again — added to your {list_name} list. {_plural(total, 'item')} now."
        return f"{item.strip().title()} added to your {list_name} list. {_plural(total, 'item')} now."

    def get_list(self, list_name: str = "shopping") -> str:
        """Return the current contents of a named list, spoken aloud."""
        tag = f"{self.LIST_TAG_PREFIX}{list_name.strip().lower()}"
        items = [m for m in self.store.as_of(subject=self.subject) if tag in m.tags]
        if not items:
            return f"Your {list_name} list is empty."
        texts = [m.text for m in items]
        spoken = _join(texts[:MAX_SPOKEN_ITEMS])
        extra = len(texts) - MAX_SPOKEN_ITEMS
        tail = f", and {_plural(extra, 'more item')}" if extra > 0 else ""
        return f"Your {list_name} list: {spoken}{tail}."

    def remove_from_list(self, item: str, list_name: str = "shopping") -> str:
        """Check off or remove an item from a named list."""
        tag = f"{self.LIST_TAG_PREFIX}{list_name.strip().lower()}"
        matches = [
            m for m in self.store.as_of(subject=self.subject)
            if tag in m.tags and item.strip().lower() in m.text.lower()
        ]
        if not matches:
            return f"I don't see {item.strip()} on your {list_name} list."
        self.store.retract(matches[0].id, "checked off")
        remaining = len([m for m in self.store.as_of(subject=self.subject) if tag in m.tags])
        if remaining == 0:
            return f"Done — {item.strip()} removed. Your {list_name} list is clear!"
        return f"Done — {item.strip()} off the list. {_plural(remaining, 'item')} left."

    # -- projects: track goals and milestones --------------------------------

    def track(self, project: str, status: str, note: str = "") -> str:
        """Log or update a project milestone. Returns the change with history."""
        if not project.strip() or not status.strip():
            return "I need a project name and a status."
        slug = re.sub(r"[^a-z0-9]+", "-", project.strip().lower()).strip("-")
        tag = f"{self.PROJECT_TAG_PREFIX}{slug}"
        existing = [m for m in self.store.as_of(subject=self.subject) if tag in m.tags]
        text = f"{project.strip()}: {status.strip()}"
        if note.strip():
            text += f" — {note.strip()}"
        if existing:
            old_text = existing[0].text
            old_status = old_text.split(":", 1)[1].strip().split(" —")[0].strip() if ":" in old_text else old_text
            self.store.supersede(existing[0].id, Memory(
                text=text,
                subject=self.subject,
                source="alexa",
                valid_from=_now().isoformat(timespec="seconds"),
                tags=(tag,),
            ))
            return f"Updated — {project.strip()} is now '{status.strip()}'. Was '{old_status}' before."
        self.store.add(Memory(
            text=text,
            subject=self.subject,
            source="alexa",
            valid_from=_now().isoformat(timespec="seconds"),
            tags=(tag,),
        ))
        return f"Tracking {project.strip()} as '{status.strip()}'."

    def my_projects(self) -> str:
        """List all tracked projects and their current status."""
        projects = [
            m for m in self.store.as_of(subject=self.subject)
            if any(t.startswith(self.PROJECT_TAG_PREFIX) for t in m.tags)
        ]
        if not projects:
            return "You're not tracking any projects yet. Tell me one to start."
        lines = [m.text for m in projects[:MAX_SPOKEN_ITEMS]]
        extra = len(projects) - len(lines)
        tail = f", and {_plural(extra, 'other')}" if extra > 0 else ""
        return _sentence(f"You're tracking: {_join(lines)}{tail}")

    # -- profile: name, location, timezone -----------------------------------

    def set_profile(self, key: str, value: str) -> str:
        """Store a profile fact (name, location, timezone) used by personality layer."""
        if not key.strip() or not value.strip():
            return "I need both a key and a value."
        tag = f"{self.PROFILE_TAG_PREFIX}{key.strip().lower()}"
        templates = {
            "name": f"my name is {value.strip()}",
            "location": f"I live in {value.strip()}",
            "city": f"I am based in {value.strip()}",
            "timezone": f"my timezone is {value.strip()}",
        }
        text = templates.get(key.strip().lower(), f"{key.strip()} is {value.strip()}")
        existing = [m for m in self.store.as_of(subject=self.subject) if tag in m.tags]
        if existing:
            self.store.supersede(existing[0].id, Memory(
                text=text,
                subject=self.subject,
                source="alexa",
                valid_from=_now().isoformat(timespec="seconds"),
                tags=(tag,),
            ))
            return f"Updated — your {key.strip()} is now {value.strip()}."
        self.store.add(Memory(
            text=text,
            subject=self.subject,
            source="alexa",
            valid_from=_now().isoformat(timespec="seconds"),
            tags=(tag,),
        ))
        return f"Got it — I'll remember your {key.strip()} is {value.strip()}."

    # -- the visual: a timeline for Echo Show ------------------------------

    def timeline(self, about: str) -> Timeline:
        """Structured history of a topic, for rendering rather than speaking.

        Half the current Echo line-up has a screen, and a belief history is a
        fundamentally visual thing: a sequence with a shape. Reading six dates
        aloud is a worse version of showing them.

        Returns data, not prose. The spoken line comes along for hosts with no
        display, so a single tool serves both.
        """
        matches = [
            m
            for m in self.store.all()
            if _matches(m, about) and m.kind is not Kind.EVENT and m.subject == self.subject
        ]
        if not matches:
            return Timeline(
                about=about,
                entries=[],
                footnote="",
                spoken=f"I don't know anything about {about}.",
            )

        # Walk the whole chain from any link, so a topic that changed three
        # times shows three steps rather than only the newest.
        seen: set[str] = set()
        ordered: list[Memory] = []
        for m in matches:
            for link in self.store.history(m.id) or [m]:
                if link.id not in seen:
                    seen.add(link.id)
                    ordered.append(link)
        ordered.sort(key=lambda m: m.asserted_at)

        entries = []
        for m in ordered:
            retraction = self.store.retraction(m.id)
            replaced_by = self.store.superseded_by(m.id)
            start, end = self.store.valid_window(m)

            if retraction:
                status = "withdrawn"
                held = (parse_when(retraction.at) - parse_when(m.asserted_at)).days
            elif replaced_by:
                status = "replaced"
                held = None
            else:
                status = "current"
                held = None

            entries.append(
                TimelineEntry(
                    text=m.text,
                    status=status,
                    starts=_fmt_date(parse_when(start)) if start else None,
                    ends=_fmt_date(parse_when(end)) if end else None,
                    held_days=held,
                    reason=retraction.reason if retraction else None,
                )
            )

        changes = sum(1 for e in entries if e.status == "replaced")
        withdrawn = sum(1 for e in entries if e.status == "withdrawn")
        bits = []
        if changes:
            bits.append(f"changed {_plural(changes, 'time')}")
        if withdrawn:
            bits.append(f"{_plural(withdrawn, 'belief')} withdrawn")
        footnote = ("This " + _join(bits) + ".") if bits else "Unchanged since you told me."

        return Timeline(
            about=about,
            entries=entries,
            footnote=footnote,
            spoken=self.recall(about),
        )

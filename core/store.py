"""Bitemporal, append-only memory store.

Most "AI memory" is a key-value store with a delete button. It answers one
question: what do you believe right now? This answers three:

    what is true now              store.live()
    what was true in March        store.as_of(valid="2026-03-01...")
    what did I believe in March   store.as_of(valid=..., belief="2026-03-01...")

Those are different questions, and conflating them is the usual bug. Every
memory sits on two independent timelines:

    valid time    when the WORLD matched this memory
    belief time   when WE held this memory to be true

A memory written in September can describe something true in July that stopped
being true in August. With one timeline that is unsayable.

The distinction that makes the model work:

    supersede   the answer CHANGED. Closes the old memory's VALID window at the
                changeover. We still believe the old memory — it was true then,
                and it still answers questions about then.
    retract     we were WRONG. Ends BELIEF. The memory stays readable forever,
                but it never describes reality at any point.

Getting that backwards is subtle and fatal: if superseding ended belief, then
"what was true in March?" would filter out the very memory that answers it.

The log is a sequence of immutable events. Records are never modified and never
deleted. A supersession is a single event carrying both the replacement and the
id it replaces, so a crash cannot leave a half-linked pair.

Zero third-party dependencies by design: the core must run on a laptop, in a
container, or air-gapped with no database service. Adapters may add
dependencies; ``core`` may not.
"""

from __future__ import annotations

import hashlib
import json
import os
import math
import re
import shutil
import threading
import uuid
from functools import wraps
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

SCHEMA_VERSION = 1


class Kind(str, Enum):
    """What sort of thing is remembered.

    The distinction matters at recall: a PREFERENCE holds until contradicted,
    while an EVENT was only ever true at a moment.
    """

    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    DECISION = "decision"
    FEEDBACK = "feedback"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into an aware datetime.

    Timestamps are always compared as datetimes, never as strings. String
    comparison silently misorders values carrying different UTC offsets — a bug
    that only surfaces once someone changes timezone.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"not an ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _moment(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    return value if isinstance(value, datetime) else parse_time(value)


@dataclass(frozen=True)
class Memory:
    """One remembered thing. Immutable once written."""

    text: str
    kind: Kind = Kind.FACT
    subject: str = "default"
    source: str = "unknown"
    confidence: float = 1.0
    asserted_at: str = field(default_factory=now_iso)
    valid_from: str | None = None
    valid_until: str | None = None
    tags: tuple[str, ...] = ()
    id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > 2000:
            raise ValueError("a memory needs text")
        if not isinstance(self.kind, Kind):
            raise ValueError("invalid memory kind")
        for value in (self.subject, self.source):
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ValueError("invalid memory identity")
        if type(self.confidence) not in (int, float) or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("invalid confidence")
        if not isinstance(self.tags, tuple) or len(self.tags) > 32 or any(not isinstance(t, str) or not t.strip() or len(t) > 128 for t in self.tags):
            raise ValueError("invalid tags")
        if not isinstance(self.asserted_at, str) or any(v is not None and not isinstance(v, str) for v in (self.valid_from, self.valid_until)):
            raise ValueError("invalid timestamps")

        parse_time(self.asserted_at)
        if self.valid_from is not None:
            parse_time(self.valid_from)
        if self.valid_until is not None:
            parse_time(self.valid_until)
        if self.valid_from and self.valid_until:
            if parse_time(self.valid_until) <= parse_time(self.valid_from):
                raise ValueError("valid_until must be after valid_from")

        if not self.id:
            object.__setattr__(self, "id", self._compute_id())
        elif not isinstance(self.id, str) or not re.fullmatch(r"[0-9a-f]{24}", self.id) or self.id != self._compute_id():
            raise ValueError("inconsistent memory id")

    def _compute_id(self) -> str:
        """Content-addressed over the fields that make this memory distinct.

        Scoped by subject so two people may hold the same fact independently,
        and by assertion time so the same sentence asserted twice is two events.
        """
        payload = "\x1f".join(
            [
                self.text.strip(),
                self.subject,
                self.kind.value,
                self.asserted_at,
                self.valid_from or "",
                self.valid_until or "",
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["tags"] = list(self.tags)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Memory:
        if not isinstance(d, dict) or not isinstance(d.get("tags", []), (list, tuple)):
            raise ValueError("invalid memory object")
        d = dict(d)
        d["kind"] = Kind(d.get("kind", "fact"))
        d["tags"] = tuple(d.get("tags", ()))
        return cls(**d)


@dataclass(frozen=True)
class Retraction:
    """The record that a memory was withdrawn as wrong, and why."""

    memory_id: str
    at: str
    reason: str


def synchronized(fn):
    @wraps(fn)
    def guarded(self, *args, **kwargs):
        with self.lock:
            if self._closed:
                raise RuntimeError("memory writer is closed")
            return fn(self, *args, **kwargs)
    return guarded


class MemoryStore:
    """An append-only event log with a rebuildable projection.

    The log on disk is the truth; every other structure is derived by replaying
    it. A corrupt projection is therefore always recoverable, and a torn write
    costs at most the final event.
    """

    def __init__(self, path: str | Path) -> None:
        self.lock = threading.RLock()
        self._closed = False
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._writer = self.path.with_name(self.path.name + '.writer.lock').open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self._writer.seek(0)
                if not self._writer.read(1):
                    self._writer.write(b'0'); self._writer.flush()
                self._writer.seek(0)
                msvcrt.locking(self._writer.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._writer.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._writer.close()
            self._closed = True
            raise RuntimeError('another memory writer owns this store') from None
        self._memories: dict[str, Memory] = {}
        self._order: list[str] = []
        self._retracted: dict[str, Retraction] = {}
        self._superseded_by: dict[str, str] = {}
        self._closed_at: dict[str, str] = {}
        try:
            self._replay()
        except Exception:
            self.close()
            raise

    def close(self):
        with self.lock:
            if not self._closed:
                self._closed = True
                self._writer.close()

    def __del__(self):
        if hasattr(self, '_writer'):
            self._writer.close()

    @synchronized
    def archive_reset(self):
        """Archive first, reset this holder, and keep the writer lease."""
        if self.path.exists():
            self.path.rename(self.path.with_name(self.path.name + '.archive-' + uuid.uuid4().hex))
        self._replay()

    # -- log ------------------------------------------------------------

    def _replay(self) -> None:
        self._memories.clear()
        self._order.clear()
        self._retracted.clear()
        self._superseded_by.clear()
        self._closed_at.clear()
        if not self.path.exists():
            return

        data = self.path.read_bytes()
        if data and not data.endswith(b'\n'):
            # Preserve the original damaged log before repairing the boundary.
            archive = self.path.with_name(self.path.name + '.damaged-' + uuid.uuid4().hex)
            shutil.copyfile(self.path, archive)
            boundary = data.rfind(b'\n') + 1
            data = data[:boundary]
            with self.path.open('wb') as fh:
                fh.write(data); fh.flush(); os.fsync(fh.fileno())
        raw = data.decode('utf-8')
        lines = raw.split("\n")

        # A process killed mid-write leaves an unterminated final line. Dropping
        # that one event is correct recovery; refusing to open the store is not.
        if lines:
            lines.pop() if lines[-1] == "" else lines.pop()

        for lineno, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                self._apply(json.loads(line))
            except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
                raise ValueError(
                    f"unreadable memory event at line {lineno}"
                ) from exc

    def _apply(self, event: dict) -> None:
        kind = event["event"]
        if kind in ("assert", "supersede"):
            memory = Memory.from_dict(event["memory"])
            self._memories[memory.id] = memory
            self._order.append(memory.id)
            if kind == "supersede":
                old = event["supersedes"]
                self._superseded_by[old] = memory.id
                self._closed_at[old] = event["at"]
        elif kind == "retract":
            self._retracted[event["memory_id"]] = Retraction(
                memory_id=event["memory_id"],
                at=event["at"],
                reason=event["reason"],
            )
        else:
            raise ValueError(f"unknown event type {kind!r}")

    def _write(self, event: dict) -> None:
        """Append one event, durably.

        One event is one line written in a single call and fsynced, so a
        supersession can never be observed half-applied.
        """
        event["_schema"] = SCHEMA_VERSION
        line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        self._apply(event)

    # -- writing --------------------------------------------------------

    @synchronized
    def add(self, memory: Memory) -> Memory:
        """Assert a new memory."""
        if memory.id in self._memories:
            raise ValueError(f"memory {memory.id} already exists; use supersede()")
        self._write({"event": "assert", "memory": memory.to_dict()})
        return memory

    @synchronized
    def supersede(self, old_id: str, new: Memory, *, at: str | None = None) -> Memory:
        """Record that the answer changed.

        Closes the old memory's valid window at the changeover. It stays
        believed — it was true then and still answers questions about then.
        Written as one event, so a crash cannot orphan either half.
        """
        old = self._memories.get(old_id)
        if old is None:
            raise KeyError(f"cannot supersede unknown memory {old_id}")
        if old_id in self._superseded_by:
            raise ValueError(
                f"memory {old_id} is already superseded; supersede its "
                "replacement rather than branching the chain"
            )
        if old_id in self._retracted:
            raise ValueError(f"memory {old_id} was retracted; it cannot be superseded")
        if new.id in self._memories:
            raise ValueError(f"memory {new.id} already exists")
        if new.subject != old.subject:
            raise ValueError("correction cannot change subject")

        changeover = at or new.valid_from or new.asserted_at
        parse_time(changeover)
        self._write(
            {
                "event": "supersede",
                "memory": new.to_dict(),
                "supersedes": old_id,
                "at": changeover,
            }
        )
        return new

    @synchronized
    def retract(self, memory_id: str, reason: str, *, at: str | None = None) -> Retraction:
        """Withdraw a memory as wrong, without erasing that it was believed.

        A reason is mandatory: a tombstone with no reason is indistinguishable
        from a bug six months later.
        """
        if not reason.strip():
            raise ValueError("retraction needs a reason")
        if memory_id not in self._memories:
            raise KeyError(f"cannot retract unknown memory {memory_id}")
        if memory_id in self._retracted:
            raise ValueError(f"memory {memory_id} is already retracted")

        parse_time(at or now_iso())
        self._write(
            {
                "event": "retract",
                "memory_id": memory_id,
                "at": at or now_iso(),
                "reason": reason.strip(),
            }
        )
        return self._retracted[memory_id]

    # -- reading --------------------------------------------------------

    def get(self, memory_id: str) -> Memory | None:
        return self._memories.get(memory_id)

    def retraction(self, memory_id: str) -> Retraction | None:
        return self._retracted.get(memory_id)

    def superseded_by(self, memory_id: str) -> str | None:
        return self._superseded_by.get(memory_id)

    @synchronized
    def all(self) -> Iterator[Memory]:
        """Every memory ever asserted, in write order — retracted ones included."""
        return iter(tuple(self._memories[i] for i in self._order))

    def valid_window(self, memory: Memory) -> tuple[str | None, str | None]:
        """The memory's effective valid window.

        A supersession closes the window of the record it replaced, so the
        effective end may be later than what the record itself declares.
        """
        ends = [e for e in (memory.valid_until, self._closed_at.get(memory.id)) if e]
        return memory.valid_from, min(ends, key=parse_time) if ends else None

    def true_at(self, memory: Memory, when: str | datetime | None = None) -> bool:
        """Did the world match this memory at ``when``?"""
        moment = _moment(when)
        start, end = self.valid_window(memory)
        if start and moment < parse_time(start):
            return False
        if end and moment >= parse_time(end):
            return False
        return True

    def believed_at(self, when: str | datetime | None = None) -> list[Memory]:
        """Everything held to be true at belief-time ``when``.

        Supersession does not remove a memory here — we still believe a
        superseded memory described its own window correctly. Only retraction
        ends belief.
        """
        moment = _moment(when)
        out = []
        for memory in self.all():
            if parse_time(memory.asserted_at) > moment:
                continue  # not yet known at that point
            retracted = self._retracted.get(memory.id)
            if retracted is not None and parse_time(retracted.at) <= moment:
                continue  # withdrawn as wrong by then
            out.append(memory)
        return out

    @synchronized
    def as_of(
        self,
        *,
        valid: str | datetime | None = None,
        belief: str | datetime | None = None,
        subject: str | None = None,
    ) -> list[Memory]:
        """The bitemporal query.

        ``valid``   the moment in the world being asked about (default: now)
        ``belief``  whose knowledge state to answer from (default: now)

        Holding ``belief`` at now while moving ``valid`` into the past asks
        "what do I now understand to have been true then" — and correctly
        returns superseded memories, because superseding closed their valid
        window without withdrawing belief in them.
        """
        moment = _moment(valid)
        return [
            m
            for m in self.believed_at(belief)
            if self.true_at(m, moment) and (subject is None or m.subject == subject)
        ]

    def live(self, subject: str | None = None) -> list[Memory]:
        """Believed and true right now."""
        return self.as_of(subject=subject)

    def history(self, memory_id: str) -> list[Memory]:
        """The whole supersession chain containing ``memory_id``, oldest first.

        Walks back to the original belief and forward to the current one, so a
        caller can render "you thought X, then Y, now Z" from any link.
        """
        if memory_id not in self._memories:
            return []

        backward = {new: old for old, new in self._superseded_by.items()}

        first = memory_id
        seen = {first}
        while (prev := backward.get(first)) is not None:
            if prev in seen:
                raise ValueError(f"supersession cycle at {prev}")
            seen.add(prev)
            first = prev

        chain = [self._memories[first]]
        cursor = first
        walked = {first}
        while (nxt := self._superseded_by.get(cursor)) is not None:
            if nxt in walked:
                raise ValueError(f"supersession cycle at {nxt}")
            walked.add(nxt)
            chain.append(self._memories[nxt])
            cursor = nxt
        return chain

    # -- introspection ---------------------------------------------------

    def stats(self) -> dict[str, int]:
        return {
            "asserted": len(self._memories),
            "retracted": len(self._retracted),
            "superseded": len(self._superseded_by),
            "true_now": len(self.live()),
        }

    def __len__(self) -> int:
        return len(self._memories)

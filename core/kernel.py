"""L0 — the always-loaded layer.

Identity, hard rules, and stable preferences. Loaded on every wake regardless of
budget pressure, because an assistant that has trimmed away its own operating
rules to make room for content is worse than one that loaded nothing.

The kernel is a *mechanism*, not a payload. This module defines the shape and
the ceiling; the contents belong to whoever deploys it. The default below is
deliberately neutral and contains no real person's data — a deployment supplies
its own, and that file never needs to leave the machine it runs on.

The ~1,200 token ceiling is the interesting part. Without a limit the kernel
grows every time someone thinks of a rule, and eventually it is the whole
context. A ceiling forces the question "is this a rule, or is it a memory?" —
and most things are memories.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.budget import estimate_tokens

# The kernel is always loaded, so its size is a tax on every single wake.
KERNEL_CEILING_TOKENS = 1200


@dataclass(frozen=True)
class Kernel:
    """Who the assistant is and what it must always do.

    Everything here is loaded every time. If a field would only matter
    sometimes, it is not kernel material — it is a memory, and it belongs in the
    store where it can be recalled on relevance.
    """

    identity: str
    rules: tuple[str, ...] = ()
    preferences: tuple[str, ...] = ()
    corrections: tuple[str, ...] = ()

    def render(self) -> str:
        parts = [self.identity.strip()]
        if self.rules:
            parts.append("Rules:\n" + "\n".join(f"- {r}" for r in self.rules))
        if self.preferences:
            parts.append("Preferences:\n" + "\n".join(f"- {p}" for p in self.preferences))
        if self.corrections:
            parts.append(
                "Recurring corrections:\n" + "\n".join(f"- {c}" for c in self.corrections)
            )
        return "\n\n".join(parts)

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.render())

    def check(self, ceiling: int = KERNEL_CEILING_TOKENS) -> None:
        """Fail if the kernel has outgrown its ceiling.

        Called by a test, not at runtime. A kernel that has drifted over budget
        should break the build, not degrade the product quietly in production.
        """
        if self.tokens > ceiling:
            raise ValueError(
                f"kernel is {self.tokens} tokens, ceiling is {ceiling}. "
                "Something in here is a memory pretending to be a rule — move it "
                "to the store where it can be recalled on relevance instead of "
                "taxing every wake."
            )


DEFAULT_KERNEL = Kernel(
    identity=(
        "You are a personal assistant with persistent memory. You remember what "
        "you were told, when you were told it, and when it stopped being true."
    ),
    rules=(
        "Never state a superseded fact as current.",
        "When a belief changed, say what it was, what it is, and when it moved.",
        "If nothing was known at the time asked about, say so rather than "
        "answering from a later date.",
        "Never present a retracted memory as fact.",
    ),
    preferences=(
        "Answer in one or two sentences unless asked for more.",
        "Cite the date a fact became true when it is relevant.",
    ),
)

"""Token accounting with a hard ceiling.

A wake has to be bounded work. An assistant that reads everything it knows
before answering gets slower every day it is used, which is the failure mode
that makes long-lived memory unusable rather than merely imperfect. The fix is
not a better index; it is a ceiling that the code enforces and a test defends.

The ceiling is deliberately *uncomfortable*. If it is generous enough never to
bind, it is not doing anything.

Nothing here calls a tokeniser. A tokeniser is a dependency, it differs per
model, and the number it returns would still be an estimate of cost rather than
a measure of it. What matters is that the estimate is consistent and
conservative — it must never under-report, or the ceiling leaks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Deliberately conservative. Real tokenisers average nearer 4 characters per
# token on English prose; 3.5 over-counts slightly, which is the safe direction
# for a ceiling.
CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """Conservative token estimate for a piece of text."""
    if not text:
        return 0
    return max(1, int(len(text) / CHARS_PER_TOKEN) + 1)


class BudgetExceeded(RuntimeError):
    """Raised when a wake cannot be assembled within its ceiling.

    This is a bug in the tier configuration, not a runtime condition to be
    handled: it means L0 alone does not fit, and no amount of trimming lower
    tiers will help.
    """


@dataclass
class Budget:
    """A token ceiling that fills up as content is admitted.

    Usage is deliberately explicit. Callers ``offer()`` content and are told
    whether it fits; nothing is admitted silently, and nothing is truncated
    mid-sentence to squeeze under the line — a half-sentence in a briefing is
    worse than an absent one.
    """

    ceiling: int
    used: int = 0
    admitted: list[tuple[str, int]] = field(default_factory=list)
    rejected: list[tuple[str, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.ceiling <= 0:
            raise ValueError(f"ceiling must be positive, got {self.ceiling}")

    @property
    def remaining(self) -> int:
        return max(0, self.ceiling - self.used)

    @property
    def fill(self) -> float:
        """Fraction of the ceiling consumed. Useful for showing a meter."""
        return self.used / self.ceiling if self.ceiling else 0.0

    def fits(self, text: str) -> bool:
        return estimate_tokens(text) <= self.remaining

    def offer(self, label: str, text: str) -> bool:
        """Admit ``text`` if it fits. Returns whether it was admitted."""
        cost = estimate_tokens(text)
        if cost > self.remaining:
            self.rejected.append((label, cost))
            return False
        self.used += cost
        self.admitted.append((label, cost))
        return True

    def require(self, label: str, text: str) -> None:
        """Admit ``text`` or fail loudly.

        For content that is not optional — the kernel. If identity does not fit
        inside the ceiling, the configuration is wrong and silently proceeding
        without it would produce an assistant that does not know who it is.
        """
        if not self.offer(label, text):
            raise BudgetExceeded(
                f"{label!r} needs {estimate_tokens(text)} tokens but only "
                f"{self.remaining} remain of {self.ceiling}; it is not optional, "
                "so the ceiling or the content must change"
            )

    def report(self) -> str:
        lines = [f"budget {self.used}/{self.ceiling} tokens ({self.fill:.0%})"]
        for label, cost in self.admitted:
            lines.append(f"  admitted  {cost:>5}  {label}")
        for label, cost in self.rejected:
            lines.append(f"  rejected  {cost:>5}  {label}")
        return "\n".join(lines)

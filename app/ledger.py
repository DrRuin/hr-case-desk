"""Leave ledger: the balance as a fold over events, double bookings, and the smallest set of events behind a claim."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator

from app.trace import Traced

PART = {
    "grant": "credits",
    "accrual": "credits",
    "carry": "credits",
    "taken": "taken",
    "pending": "pending",
    "lapse": "lapsed",
}
WORDS = {
    "grant": "granted",
    "accrual": "accrued",
    "carry": "carried over",
    "taken": "taken",
    "pending": "pending approval",
    "lapse": "lapsed",
}


class Event(BaseModel):
    """One ledger entry from the Leave Balance Service."""

    id: str
    leave: str
    kind: Literal[*PART]
    days: float
    source: str
    start: date | None = None
    end: date | None = None
    half: Literal["am", "pm"] | None = None

    @field_validator("days")
    @classmethod
    def whole_halves(cls, days: float) -> float:
        """Ledger amounts are positive multiples of half a day."""
        if days <= 0 or not (days * 2).is_integer():
            raise ValueError("days must be a positive multiple of 0.5")
        return days

    @property
    def halves(self) -> int:
        """The amount in half-days."""
        return int(self.days * 2)

    def span(self) -> tuple[int, int]:
        """The booked half-day slots as a half-open interval [first, last)."""
        first = 2 * self.start.toordinal() + (self.half == "pm")
        return first, 2 * self.end.toordinal() + (1 if self.half == "am" else 2)


class Balance(BaseModel):
    """The balance split into the parts an employee reasons about."""

    credits: Traced
    taken: Traced
    pending: Traced
    lapsed: Traced

    @property
    def available(self) -> Traced:
        """Credits less everything drawn against them."""
        return self.credits - self.taken - self.pending - self.lapsed


class Finding(BaseModel):
    """What the ledger says about the employee's claim."""

    explanation: Literal["none_needed", "unique", "ambiguous", "contradicts"]
    events: list[str]
    gap: float
    double_booked: list[str]


def fold(events: list[Event]) -> Balance:
    """Sum the ledger into its parts in one pass, keeping every event as a source term."""
    parts = dict.fromkeys(PART.values(), Traced())
    for e in events:
        parts[PART[e.kind]] += Traced.of(e.id, e.halves)
    return Balance(**parts)


def double_booked(events: list[Event]) -> list[str]:
    """Events whose booked slots overlap another's, found by one sweep over intervals sorted by start."""
    spans = sorted((e.span(), e.id) for e in events if e.start)
    found: set[str] = set()
    reach, holder = -1, ""
    for (first, last), key in spans:
        if first < reach:
            found |= {key, holder}
        if last > reach:
            reach, holder = last, key
    return sorted(found)


def smallest(items: list[tuple[str, int]], target: int) -> list[frozenset[str]]:
    """Minimum-size subsets of items whose weights sum to target, at most two (0/1 knapsack over sums, O(n*target))."""
    best: dict[int, tuple[int, list[frozenset[str]]]] = {0: (0, [frozenset()])}
    for key, weight in items:
        for total, (size, sets) in sorted(best.items(), reverse=True):
            reached = total + weight
            if reached > target:
                continue
            grown = [s | {key} for s in sets]
            held = best.get(reached)
            if held is None or size + 1 < held[0]:
                best[reached] = (size + 1, grown[:2])
            elif size + 1 == held[0]:
                best[reached] = (held[0], (held[1] + grown)[:2])
    return best.get(target, (0, []))[1]


def explain(events: list[Event], shown: float | None, taken: float | None) -> Finding:
    """Account for the gap between what the employee believes and the ledger, or say it cannot be done uniquely."""
    balance = fold(events)
    clash = double_booked(events)
    drawn = balance.pending.sources() + balance.lapsed.sources()
    if shown is not None and round(shown * 2) != balance.available.halves:
        return Finding(
            explanation="contradicts",
            events=[],
            gap=abs(shown - balance.available.days),
            double_booked=clash,
        )
    if taken is None:
        return Finding(explanation="none_needed", events=drawn, gap=0, double_booked=clash)
    excess = balance.taken.halves - round(taken * 2)
    if excess < 0:
        return Finding(explanation="contradicts", events=[], gap=-excess / 2, double_booked=clash)
    picks = smallest(list(balance.taken.terms), excess)
    gap = (excess + balance.pending.halves + balance.lapsed.halves) / 2
    if not picks:
        return Finding(explanation="contradicts", events=[], gap=gap, double_booked=clash)
    if len(picks) != 1:
        return Finding(explanation="ambiguous", events=[], gap=gap, double_booked=clash)
    found = sorted(picks[0]) + drawn
    return Finding(
        explanation="unique" if found else "none_needed",
        events=found,
        gap=gap,
        double_booked=clash,
    )

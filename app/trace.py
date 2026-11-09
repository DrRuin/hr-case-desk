"""Figures that carry their sources: a value in half-days as a signed sum over source records."""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Traced:
    """A half-day count kept as signed terms per source record, so every figure explains itself."""

    terms: tuple[tuple[str, int], ...] = ()

    @classmethod
    def of(cls, source: str, halves: int) -> "Traced":
        """One source record contributing a signed number of half-days."""
        return cls(((source, halves),))

    @classmethod
    def total(cls, parts: Iterable["Traced"]) -> "Traced":
        """The sum of several traced figures."""
        out = cls()
        for part in parts:
            out = out + part
        return out

    @property
    def halves(self) -> int:
        """The figure in half-days."""
        return sum(h for _, h in self.terms)

    @property
    def days(self) -> float:
        """The figure in days."""
        return self.halves / 2

    def __add__(self, other: "Traced") -> "Traced":
        """Merge terms, summing a source that appears in both."""
        merged = dict(self.terms)
        for source, halves in other.terms:
            merged[source] = merged.get(source, 0) + halves
        return Traced(tuple((s, h) for s, h in merged.items() if h))

    def __neg__(self) -> "Traced":
        """The same terms with the sign flipped."""
        return Traced(tuple((s, -h) for s, h in self.terms))

    def __sub__(self, other: "Traced") -> "Traced":
        """Subtract term by term."""
        return self + -other

    def without(self, sources: Iterable[str]) -> "Traced":
        """The figure had these source records not existed."""
        drop = set(sources)
        return Traced(tuple((s, h) for s, h in self.terms if s not in drop))

    def sources(self) -> list[str]:
        """Source records behind the figure, in order of first use."""
        return [s for s, _ in self.terms]

    def show(self) -> str:
        """The figure as an equation over its sources, for auditors."""
        body = " ".join(f"{'+' if h > 0 else '-'} {abs(h) / 2:g} [{s}]" for s, h in self.terms)
        return f"{self.days:g} = {body.removeprefix('+ ')}" if self.terms else "0"

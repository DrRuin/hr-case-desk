"""Tenant decision tables compiled to a finite grid, checked for gaps and overlaps at load, and explained exactly."""

from bisect import bisect_left
from collections.abc import Iterator
from itertools import pairwise, product
from typing import Literal, Self

from pydantic import BaseModel, model_validator

Outcome = Literal["resolve", "approve", "escalate"]
Cell = dict[int, int]


class Feature(BaseModel):
    """An input column: a plain label, what each value means, and whether the model reads it from the request."""

    name: str
    label: str
    values: list[str] | None = None
    meaning: dict[str, str] = {}
    read: Literal["request", "records"] = "records"

    @model_validator(mode="after")
    def explained(self) -> Self:
        """Meanings cover exactly the values; a column read from the request must have them."""
        if (self.meaning or self.read == "request") and set(self.meaning) != set(self.values or ()):
            raise ValueError(f"{self.name}: meanings {sorted(self.meaning)} do not match values {self.values}")
        return self


class Rule(BaseModel):
    """One row: categories per column or a (low, high] interval, an outcome, and what it says in words."""

    id: str
    when: dict[str, list[str] | tuple[float | None, float | None]]
    outcome: Outcome
    says: str
    clause: str | None = None


class Table(BaseModel):
    """A versioned decision table in the style of DMN with the Unique hit policy, and the requests it covers."""

    id: str
    version: int
    ask: str
    features: list[Feature]
    rules: list[Rule]


class Verdict(BaseModel):
    """The rule that fired, the smallest set of facts that forces it, and the smallest change that would resolve."""

    table: str
    rule: str
    says: str
    clause: str | None
    outcome: Outcome
    because: dict[str, str]
    resolve_if: dict[str, str] | None


class Policy:
    """A table compiled so that every combination of inputs has exactly one rule."""

    def __init__(self, table: Table) -> None:
        """Compile the table and refuse it if any cell has no rule or more than one."""
        self.table = table
        self.names = [f.name for f in table.features]
        self.cuts = {
            f.name: sorted({b for r in table.rules for b in r.when.get(f.name, ()) if b is not None})
            for f in table.features
            if f.values is None
        }
        self.domains = [f.values or self.bands(f.name) for f in table.features]
        for rule in table.rules:
            if unknown := set(rule.when) - set(self.names):
                raise ValueError(f"{rule.id} names unknown columns {sorted(unknown)}")
        covers = [[self.covers(rule, i) for i in range(len(self.names))] for rule in table.rules]
        self.grid: dict[tuple[int, ...], Rule] = {}
        problems = []
        for cell in self.cells({}):
            hits = [r for r, sets in zip(table.rules, covers) if all(c in s for c, s in zip(cell, sets))]
            if len(hits) == 1:
                self.grid[cell] = hits[0]
            else:
                found = ", ".join(h.id for h in hits) or "no rule"
                problems.append(f"{found} for {self.label(dict(enumerate(cell)))}")
        if problems:
            raise ValueError(f"{table.id} v{table.version} is not unique and complete: {'; '.join(problems)}")

    def bands(self, name: str) -> list[str]:
        """Labels of the intervals a numeric column is split into."""
        cuts = self.cuts[name]
        if not cuts:
            return ["any"]
        inner = [f"more than {a:g}, at most {b:g}" for a, b in pairwise(cuts)]
        return [f"at most {cuts[0]:g}", *inner, f"more than {cuts[-1]:g}"]

    def covers(self, rule: Rule, i: int) -> set[int]:
        """Grid indices of column i that a rule accepts."""
        feature = self.table.features[i]
        cond = rule.when.get(feature.name)
        if cond is None:
            return set(range(len(self.domains[i])))
        if feature.values:
            return {feature.values.index(v) for v in cond}
        cuts, (low, high) = self.cuts[feature.name], cond
        first = 0 if low is None else cuts.index(low) + 1
        last = len(cuts) if high is None else cuts.index(high)
        return set(range(first, last + 1))

    def index(self, i: int, value: str) -> int:
        """Grid index of one column's value: its category, or the band a number falls in."""
        feature = self.table.features[i]
        return feature.values.index(value) if feature.values else bisect_left(self.cuts[feature.name], float(value))

    def words(self, facts: dict[str, str]) -> list[str]:
        """Facts as a person reads them: each column's label and what its value means."""
        named = {f.name: f for f in self.table.features}
        return [f"{named[k].label}: {named[k].meaning.get(v, v)}" for k, v in facts.items()]

    def label(self, fixed: Cell) -> dict[str, str]:
        """Readable values of the fixed columns."""
        return {self.names[i]: self.domains[i][v] for i, v in sorted(fixed.items())}

    def cells(self, fixed: Cell) -> Iterator[tuple[int, ...]]:
        """Every cell that agrees with the fixed columns."""
        return product(*((fixed[i],) if i in fixed else range(len(d)) for i, d in enumerate(self.domains)))

    def outcomes(self, fixed: Cell) -> set[Outcome]:
        """Every outcome still reachable with these columns fixed."""
        return {self.grid[c].outcome for c in self.cells(fixed)}

    def reason(self, given: Cell, rule: Rule) -> Cell:
        """A subset-minimal set of known columns forcing the outcome, deleted down from the fired rule's own columns."""
        keep = {i: v for i, v in given.items() if self.names[i] in rule.when}
        for i in sorted(keep):
            rest = {j: v for j, v in keep.items() if j != i}
            if self.outcomes(rest) == {rule.outcome}:
                keep = rest
        return keep

    def flip(self, given: Cell, target: Outcome) -> Cell | None:
        """A subset-minimal set of known columns whose change can reach the target, with values that do (contrastive)."""
        if target not in self.outcomes({}):
            return None
        change = set(given)
        for i in sorted(given):
            if target in self.outcomes({j: v for j, v in given.items() if j not in change - {i}}):
                change -= {i}
        hold = {j: v for j, v in given.items() if j not in change}
        witness = next(c for c in self.cells(hold) if self.grid[c].outcome == target)
        return {i: witness[i] for i in sorted(change)}

    def decide(self, facts: dict[str, str]) -> Verdict:
        """The outcome for the known facts with both explanations; the facts must leave exactly one rule possible."""
        if unknown := set(facts) - set(self.names):
            raise ValueError(f"{self.table.id} has no columns {sorted(unknown)}")
        given = {i: self.index(i, facts[n]) for i, n in enumerate(self.names) if n in facts}
        rules = {self.grid[c].id: self.grid[c] for c in self.cells(given)}
        if len(rules) != 1:
            raise ValueError(f"{self.table.id} cannot decide on {facts}: {sorted(rules)} remain possible")
        (rule,) = rules.values()
        flip = None if rule.outcome == "resolve" else self.flip(given, "resolve")
        return Verdict(
            table=f"{self.table.id} v{self.table.version}",
            rule=rule.id,
            says=rule.says,
            clause=rule.clause,
            outcome=rule.outcome,
            because=self.label(self.reason(given, rule)),
            resolve_if=None if flip is None else self.label(flip),
        )

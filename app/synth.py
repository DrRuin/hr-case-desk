"""Generate a company's HR records (people, org chart, this year's leave ledger) from its policy numbers, reproducibly."""

from collections.abc import Iterator
from datetime import date, timedelta
from itertools import count, product
from math import ceil
from random import Random

from pydantic import BaseModel

from app.config import settings
from app.ledger import Event
from app.systems import Person, Records

TRAITS = ("pending", "duplicate", "over_cap")


class LeaveRules(BaseModel):
    """How one leave type accrues, carries over and is usually booked."""

    code: str
    monthly: float
    late: float
    cap: float
    accrual: str
    carry: str
    bookings: tuple[int, int]
    sizes: dict[float, int]


class Department(BaseModel):
    """A department's share of headcount, its job titles, and its managers' and director's titles."""

    share: float
    titles: list[str]
    manager: str
    director: str


class Named(BaseModel):
    """A person the demo and tests rely on, with the ledger traits planted for them."""

    id: str
    name: str
    department: str
    title: str
    role: str = "employee"
    joined: date
    exited: date | None = None
    plant: list[str] = []


class Spec(BaseModel):
    """Everything that shapes one generated company."""

    seed: int
    today: date
    prefix: str
    first_id: int
    headcount: int
    team_size: int
    people_per_hrbp: int
    founded: date
    cutoff_day: int
    leaves: dict[str, LeaveRules]
    rates: dict[str, float]
    pending_days: float
    pending_until: date
    holidays: list[date]
    departments: dict[str, Department]
    first_names: list[str]
    last_names: list[str]
    story: list[Named]
    templates: dict[str, str]


def months(first: date, last: date) -> Iterator[date]:
    """The first day of every month from first to last."""
    at = first.replace(day=1)
    while at <= last:
        yield at
        at = (at + timedelta(days=32)).replace(day=1)


def ordinal(day: int) -> str:
    """A day of the month as 1st, 2nd, 3rd, 15th."""
    return f"{day}{'th' if 10 < day % 100 < 14 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')}"


class Company:
    """One company's people and ledger, drawn from its spec with a fixed seed."""

    def __init__(self, spec: Spec) -> None:
        """Start from the spec's seed so every run writes the same records."""
        self.spec, self.rng = spec, Random(spec.seed)
        self.year = date(spec.today.year, 1, 1)
        self.people: dict[str, Person] = {}
        self.plants: dict[str, list[str]] = {}
        self.exits: dict[str, date | None] = {}
        self.ids = (f"{spec.prefix}{n}" for n in count(spec.first_id))
        self.events = count(1)
        self.requests = count(40001)
        story = {p.name for p in spec.story}
        names = [f"{a} {b}" for a, b in product(spec.first_names, spec.last_names) if f"{a} {b}" not in story]
        self.names = iter(self.rng.sample(names, len(names)))

    def working(self, day: date) -> bool:
        """A weekday that is not a company holiday."""
        return day.weekday() < 5 and day not in self.spec.holidays

    def named(self, p: Named, manager: str | None, hrbp: str | None) -> str:
        """Put a story person in the directory as written."""
        status = "exited" if p.exited else "active"
        person = Person(
            name=p.name, title=p.title, role=p.role, status=status, joined=p.joined, manager=manager, hrbp=hrbp
        )
        self.people[p.id], self.plants[p.id], self.exits[p.id] = person, p.plant, p.exited
        return p.id

    def hire(self, title: str, role: str, manager: str | None, hrbp: str | None) -> str:
        """Put a generated person in the directory; staff below manager may have joined or left this year."""
        spec, rng, key = self.spec, self.rng, next(self.ids)
        junior = role == "employee"
        if junior and rng.random() < spec.rates["joined_this_year"]:
            joined = self.year + timedelta(days=rng.randrange((spec.today - self.year).days - 30))
        else:
            joined = spec.founded + timedelta(days=rng.randrange((self.year - spec.founded).days))
        exited = None
        if junior and rng.random() < spec.rates["exited"]:
            start = max(joined, self.year) + timedelta(days=45)
            exited = start + timedelta(days=rng.randrange(max(1, (spec.today - start).days - 7)))
        status = "exited" if exited else "active"
        self.people[key] = Person(
            name=next(self.names), title=title, role=role, status=status, joined=joined, manager=manager, hrbp=hrbp
        )
        self.plants[key] = [t for t in TRAITS if junior and rng.random() < spec.rates[t]]
        self.exits[key] = exited
        return key

    def staff(self) -> None:
        """Build the org chart: head of HR, HR business partners, directors, managers, then everyone else."""
        spec = self.spec
        cast: dict[tuple[str, str], list[Named]] = {}
        for p in spec.story:
            cast.setdefault((p.department, p.role), []).append(p)
        (head_story,) = (p for p in spec.story if p.role == "hr_head")
        head = self.named(head_story, None, None)
        hrbps = [self.named(p, head, head) for p in spec.story if p.role == "hrbp"]
        while len(hrbps) < ceil(spec.headcount / spec.people_per_hrbp):
            hrbps.append(self.hire("HR Business Partner", "hrbp", head, head))
        for n, (name, dept) in enumerate(spec.departments.items()):
            hrbp, size = hrbps[n % len(hrbps)], round(spec.headcount * dept.share)
            directors = [self.named(p, None, hrbp) for p in cast.get((name, "director"), [])]
            if not directors:
                directors = [
                    head if dept.director == head_story.title else self.hire(dept.director, "director", None, hrbp)
                ]
            leads = [self.named(p, directors[0], hrbp) for p in cast.get((name, "manager"), [])]
            while len(leads) < ceil(size / spec.team_size):
                leads.append(self.hire(dept.manager, "manager", directors[0], hrbp))
            members = [self.named(p, leads[0], hrbp) for p in cast.get((name, "employee"), [])]
            for i in range(size - len(members) - len(leads) - 1):
                self.hire(self.rng.choice(dept.titles), "employee", leads[i % len(leads)], hrbp)

    def event(self, leave: str, kind: str, days: float, source: str, at: tuple | None = None) -> Event:
        """One ledger entry with the next id of its leave type."""
        start, end, half = at or (None, None, None)
        key = f"{self.spec.leaves[leave].code}-{next(self.events):06d}"
        return Event(id=key, leave=leave, kind=kind, days=days, source=source, start=start, end=end, half=half)

    def slot(self, first: date, last: date, days: float, busy: list[tuple[date, date]]) -> tuple | None:
        """Working days for a booking between first and last that touch no other booking, or None."""
        for _ in range(20) if last > first else ():
            start = first + timedelta(days=self.rng.randrange((last - first).days))
            if not self.working(start):
                continue
            end, left = start, ceil(days) - 1
            while left:
                end += timedelta(days=1)
                left -= self.working(end)
            if end <= last and all(end < a or start > b for a, b in busy):
                busy.append((start, end))
                return start, end, self.rng.choice(["am", "pm"]) if days % 1 else None
        return None

    def ledger(self, key: str) -> list[Event]:
        """This year's ledger for one person: carry-over, monthly accrual, approved, pending and planted entries."""
        spec, rng, person, plants, exited = self.spec, self.rng, self.people[key], self.plants[key], self.exits[key]
        start, end = max(person.joined, self.year), min(exited or spec.today, spec.today)
        approver = self.people[person.manager].name if person.manager else "the HR team"
        joined, left = person.joined.replace(day=1), exited and exited.replace(day=1)
        events: list[Event] = []
        busy: list[tuple[date, date]] = []
        for leave, rules in spec.leaves.items():
            credit = 0.0
            if person.joined < self.year and rules.cap:
                over = "over_cap" in plants
                closing = rules.cap + rng.randint(3, 9) if over else rng.randint(0, int(rules.cap * 2)) / 2
                if closing:
                    said = f"Unused leave carried forward from {self.year.year - 1}, policy section {rules.carry}"
                    events.append(self.event(leave, "carry", closing, said))
                if closing > rules.cap:
                    said = f"Lapsed on 1 January above the {rules.cap:g}-day carry-forward cap, policy section {rules.carry}"
                    events.append(self.event(leave, "lapse", closing - rules.cap, said))
                credit = min(closing, rules.cap)
            for month in months(start, end):
                closes = (month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                if closes >= spec.today and not exited:
                    continue
                late = (month == joined and person.joined.day > spec.cutoff_day) or (
                    month == left and exited.day < spec.cutoff_day
                )
                days = rules.late if late else rules.monthly
                if days:
                    note = f", joined on the {ordinal(person.joined.day)}" if month == joined else ""
                    note += f", last working day the {ordinal(exited.day)}" if month == left else ""
                    said = f"Monthly accrual for {month:%B %Y}{note}, policy section {rules.accrual}"
                    events.append(self.event(leave, "accrual", days, said))
                    credit += days
            low, high = rules.bookings
            share = len(list(months(start, end))) / 12
            wanted = [1.0, 1.0] if "repeats" in plants and leave == "privileged" else []
            weights = list(rules.sizes.values())
            wanted += rng.choices(list(rules.sizes), weights=weights, k=round(rng.randint(low, high) * share))
            for days in wanted:
                if credit >= days and (at := self.slot(start, end, days, busy)):
                    credit -= days
                    said = f"Leave request LR-{next(self.requests)} approved by {approver}"
                    events.append(self.event(leave, "taken", days, said, at))
            due = "pending" in plants and leave == "privileged" and not exited and credit >= spec.pending_days
            ahead = spec.today + timedelta(days=1)
            if due and (at := self.slot(ahead, spec.pending_until, spec.pending_days, busy)):
                said = f"Leave request LR-{next(self.requests)} awaiting approval by {approver}"
                events.append(self.event(leave, "pending", spec.pending_days, said, at))
        taken = [e for e in events if e.kind == "taken" and e.leave == "privileged"]
        if "duplicate" in plants and taken:
            twin = rng.choice(taken)
            events.append(twin.model_copy(update={"id": self.event(twin.leave, "taken", twin.days, "").id}))
        return events

    def records(self) -> Records:
        """The whole company as the mocked HR systems serve it."""
        self.staff()
        ledger = {key: self.ledger(key) for key in self.people}
        return Records(people=self.people, ledger=ledger, templates=self.spec.templates)


def main() -> None:
    """Write systems.json for every company that has a company.json."""
    for spec_file in sorted(settings().data.glob("*/company.json")):
        records = Company(Spec.model_validate_json(spec_file.read_text(encoding="utf-8"))).records()
        out = records.model_dump_json(indent=1, exclude_none=True)
        (spec_file.parent / "systems.json").write_text(out, encoding="utf-8")
        events = sum(map(len, records.ledger.values()))
        print(f"{spec_file.parent.name}: {len(records.people)} people, {events} ledger entries")


if __name__ == "__main__":
    main()

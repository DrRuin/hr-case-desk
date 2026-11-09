"""The case desk: gathers facts, lets the tenant's table decide, acts only under a permit, and writes the record."""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, computed_field, model_validator
from pydantic_ai import Agent, AgentRunError
from pydantic_ai.models import Model

from app import observe
from app.agents import WRITERS, Brief, Figure, LeaveQuestion, Request, Source, Statement, claims, confirm, reader
from app.ledger import WORDS, Event, explain, fold
from app.policy import Policy, Table, Verdict
from app.progress import WATCH, Progress, Step, step
from app.store import CaseLog, Store
from app.systems import NAMES, Records, Snapshot, Systems, fetch

SEAL = object()
DUTIES = {
    "approve": (
        "{handler} decides: approving issues exactly the letter the desk prepared, once, and rejecting closes the case "
        "with nothing issued. Nothing is issued until they decide."
    ),
    "escalate": (
        "{handler} now holds the case: what happens next, and the answer to the employee, are theirs. "
        "The desk issues nothing on this case."
    ),
}
Status = Literal["resolved", "awaiting_approval", "escalated", "rejected", "failed"]


class Config(BaseModel):
    """A tenant's policy: decision tables, the handbook clauses rules cite, approvers, fallback queue and failure words."""

    name: str
    handbook: str
    fallback: str
    approvers: list[str]
    undone: str
    tables: dict[str, Table]
    clauses: dict[str, str] = {}

    @model_validator(mode="after")
    def cited(self) -> Self:
        """Every clause a rule cites is in the handbook."""
        missing = {r.clause for t in self.tables.values() for r in t.rules if r.clause} - set(self.clauses)
        if missing:
            raise ValueError(f"rules cite clauses missing from {self.handbook}: {sorted(missing)}")
        return self


class Fact(BaseModel):
    """A value the table read, with where it came from."""

    value: str
    detail: str
    sources: list[str]


class Action(BaseModel):
    """A write the desk may run: one letter for one employee, keyed by its content."""

    employee: str
    kind: str
    key: str


class Record(BaseModel):
    """The decision record for auditors, written by code and never by a model."""

    case: str
    tenant: str
    employee: str
    text: str
    at: datetime
    intake: dict[str, Any] | None
    snapshots: list[Snapshot]
    inputs: dict[str, Fact]
    verdict: Verdict
    route: str | None
    action: Action | None
    figures: dict[str, Figure]
    sources: dict[str, Source]
    why: list[str]
    would_resolve: list[str]
    reply: list[Statement]
    handover: list[Statement] = []
    steps: list[Step] = []
    trace: str | None = None
    done: dict[str, Any] | None = Field(None, exclude=True)

    @property
    def scores(self) -> dict[str, float | str | bool]:
        """What Langfuse tracks per case: who handled it, the rule, how much of each message held up, the second read."""
        scores: dict[str, float | str | bool] = {
            "handled_by": "person" if self.route else "desk",
            "rule": self.verdict.rule,
            "reply_supported": supported(self.reply),
        }
        if "confirmed" in self.inputs:
            scores["second_reading"] = self.inputs["confirmed"].value == "yes"
        if self.handover:
            scores["handover_supported"] = supported(self.handover)
        return scores

    @computed_field
    @property
    def message(self) -> str:
        """The reply as the employee receives it."""
        return " ".join(s.text for s in self.reply)

    @computed_field
    @property
    def cited(self) -> str:
        """The reply in Markdown, each sentence followed by numbered links to the sources it cites."""
        return markdown(self.reply)

    @computed_field
    @property
    def handover_cited(self) -> str:
        """The note to the person who took the case over, in Markdown with its own numbered citations."""
        return markdown(self.handover)


def supported(statements: list[Statement]) -> float:
    """The share of sentences the auditor found supported."""
    return sum(s.verdict == "supported" for s in statements) / len(statements)


def markdown(statements: list[Statement]) -> str:
    """Sentences in Markdown, each followed by links to its sources, numbered in order of first citation."""
    order = {c: n for n, c in enumerate(dict.fromkeys(c for s in statements for c in s.cites), 1)}
    return " ".join(s.text + "".join(f" [{order[c]}](#{c})" for c in s.cites) for s in statements)


class Case(BaseModel):
    """A case as stored: the record, what happened after it, and where it stands."""

    record: Record
    events: list[dict[str, Any]]
    status: Status
    trace_url: str | None = None


class Refused(Exception):
    """A request the desk will not carry out, with the reason."""


@dataclass(frozen=True)
class Permit:
    """Authority to run one action; only the desk mints it and `execute` accepts nothing else."""

    action: Action
    rule: str
    by: str
    seal: object = field(repr=False)

    def __post_init__(self) -> None:
        """Refuse permits not minted by the desk."""
        if self.seal is not SEAL:
            raise PermissionError("permits come from the desk's gate")


@dataclass
class Tenant:
    """A tenant's compiled policy and its own HR systems."""

    id: str
    config: Config
    policies: dict[str, Policy]
    reader: Agent[str, Request]
    systems: Systems


def load(folder: Path) -> dict[str, Tenant]:
    """Every tenant under the data folder; a table with a gap or an overlap stops the tenant from loading."""
    tenants = {}
    for path in sorted(p for p in folder.iterdir() if p.is_dir()):
        config = Config.model_validate_json((path / "policy.json").read_text(encoding="utf-8"))
        records = Records.model_validate_json((path / "systems.json").read_text(encoding="utf-8"))
        policies = {name: Policy(table) for name, table in config.tables.items()}
        tenants[path.name] = Tenant(path.name, config, policies, reader(config.tables), Systems(records))
    return tenants


def key(tenant: str, case: str, kind: str, employee: str) -> str:
    """Idempotency key: a hash of the effect itself, so a retried or replayed action maps to the same key."""
    canon = json.dumps({"tenant": tenant, "case": case, "action": "letter", "kind": kind, "employee": employee})
    return hashlib.sha256(canon.encode()).hexdigest()


def span(days: float) -> str:
    """A number of days in words, singular for one."""
    return f"{days:g} day" if days == 1 else f"{days:g} days"


def plain(event: Event) -> str:
    """One ledger event in the employee's terms."""
    when = f" from {event.start} to {event.end}" if event.start else ""
    return f"{span(event.days)} {WORDS[event.kind]}{when}"


def system(snap: Snapshot) -> Source:
    """A system that had no record or did not answer, as evidence."""
    return Source(
        id=f"system:{snap.system}",
        kind="system",
        title=NAMES[snap.system],
        text=f"{snap.status} for {snap.subject} after {snap.attempts} attempt(s): {snap.error}",
    )


@dataclass
class Gathered:
    """What a case type learned from the systems: table inputs, reply figures, their sources, and the action."""

    inputs: dict[str, Fact]
    figures: dict[str, Figure] = field(default_factory=dict)
    sources: dict[str, Source] = field(default_factory=dict)
    action: Action | None = None


def down(snap: Snapshot, action: Action | None = None) -> Gathered:
    """The only fact known when a system has no record or does not answer; the table must decide on it alone."""
    src = system(snap)
    data = Fact(value=snap.status, detail=src.text, sources=[src.id])
    return Gathered({"data": data}, sources={src.id: src}, action=action)


def leave_inputs(ledger: list[Event], ask: LeaveQuestion) -> Gathered:
    """Table inputs, reply figures and ledger sources for a balance question, on the leave type it asks about."""
    kind = ask.leave_type
    events = [e for e in ledger if e.leave == kind]
    balance, found = fold(events), explain(events, ask.shown_days, ask.taken_days)
    named = {e.id: e for e in events}
    gap = balance.available.without(found.events) - balance.available
    steps = " ".join(
        f"{'plus' if h > 0 else 'minus'} {span(abs(h) / 2)} {WORDS[named[i].kind]} ({i})"
        for i, h in balance.available.terms
    )
    total = Source(
        id="balance",
        kind="ledger",
        title=f"{kind.capitalize()} leave balance",
        text=f"{kind.capitalize()} leave available {span(balance.available.days)}: {steps.removeprefix('plus ')}.",
    )
    sources = {e.id: Source(id=e.id, kind="ledger", title=plain(e), text=e.source) for e in events} | {"balance": total}
    inputs = {
        "data": Fact(value="ok", detail=total.text, sources=["balance"]),
        "explanation": Fact(
            value=found.explanation,
            detail="; ".join(f"{plain(named[i])} ({named[i].source})" for i in found.events) or "none",
            sources=found.events,
        ),
        "double_booked": Fact(
            value="yes" if found.double_booked else "no",
            detail="; ".join(plain(named[i]) for i in found.double_booked) or "none",
            sources=found.double_booked,
        ),
        "gap_days": Fact(
            value=f"{found.gap:g}",
            detail=gap.show() if found.events else f"{span(found.gap)} the ledger cannot attribute uniquely",
            sources=gap.sources(),
        ),
    }
    parts = {"credited": balance.credits, "taken": balance.taken, "pending": balance.pending, "lapsed": balance.lapsed}
    figures = {"available": Figure(value=span(balance.available.days), sources=["balance"])} | {
        k: Figure(value=span(t.days), sources=["balance"]) for k, t in parts.items() if t.terms
    }
    if found.events:
        figures["explained_by"] = Figure(value="; ".join(plain(named[i]) for i in found.events), sources=found.events)
    return Gathered(inputs, figures, sources)


@dataclass
class Job:
    """One case being opened: whose it is, and the system calls made for it so far."""

    tenant: Tenant
    case: str
    employee: str
    snapshots: list[Snapshot]

    async def fetch[T](self, system: str, call: Callable[[str], Awaitable[T]]) -> tuple[Snapshot, T | None]:
        """Ask a system about the employee and keep its snapshot for the record."""
        snap, value = await fetch(system, self.employee, lambda: call(self.employee))
        self.snapshots.append(snap)
        return snap, value


class Desk:
    """Runs cases for every tenant over one store and one model."""

    def __init__(self, tenants: dict[str, Tenant], store: Store, model: Model) -> None:
        """Hold the tenants, the store and the model."""
        self.tenants, self.store, self.model = tenants, store, model

    def tenant(self, name: str) -> Tenant:
        """A tenant by name."""
        if name not in self.tenants:
            raise Refused(f"unknown tenant {name}")
        return self.tenants[name]

    async def read(self, tenant: Tenant, text: str) -> Request | None:
        """The request on one of the tenant's forms, or None when no form the model fills passes the checks."""
        shown = step("read", "Reading the request", state="running")
        try:
            ask = (await tenant.reader.run(text, deps=text, model=self.model)).output
        except AgentRunError:
            step("read", "Could not read the request on any form", "it goes to a person", "failed", shown)
            return None
        step("read", tenant.config.tables[type(ask).__name__].ask.rstrip("."), ask.summary, id=shown)
        return ask

    async def route(self, tenant: Tenant, employee: str, snapshots: list[Snapshot]) -> tuple[str, Source]:
        """Walk from the HR business partner up the managers to the first approver who is not the requester."""
        seen: set[str] = set()
        snap, person = await fetch("org", employee, lambda: tenant.systems.person(employee))
        snapshots.append(snap)
        at, asker = (person.hrbp, person.name) if person else (None, employee)
        while at and at not in seen:
            seen.add(at)
            snap, person = await fetch("org", at, lambda at=at: tenant.systems.person(at))
            snapshots.append(snap)
            if person is None:
                break
            if at != employee and person.role in tenant.config.approvers:
                text = f"{person.title}, the first approver above {asker} in the Org Hierarchy Service"
                return at, Source(id=f"org:{at}", kind="org", title=f"{person.name} ({person.title})", text=text)
            at = person.manager
        text = f"No approver was found above {asker}, so the case goes to the {tenant.config.fallback} queue."
        queue = f"the {tenant.config.fallback} queue"
        return tenant.config.fallback, Source(id="queue", kind="org", title=queue, text=text)

    async def execute(self, tenant: Tenant, log: CaseLog, permit: Permit) -> tuple[Snapshot | None, str | None]:
        """Run a permitted action at most once per key; the repository dedupes too, so a crash between steps is safe."""
        done = await log.effect(permit.action.key)
        if done:
            step("action", f"Letter {done} was already issued", "the same request id came back")
            return None, done
        act, by = permit.action, f"permitted by {permit.by}, rule {permit.rule}"
        shown = step("action", "Issuing the letter", by, "running")
        snap, doc = await fetch(
            "documents", act.employee, lambda: tenant.systems.letter(act.employee, act.kind, act.key)
        )
        if doc is None:
            step("action", "The letter could not be issued", snap.error or "", "failed", shown)
            return snap, None
        step("action", f"Issued {doc}", by, id=shown)
        return snap, await log.settle(act.key, doc)

    async def write(self, brief: Brief) -> list[Statement]:
        """The cited sentences for whoever the brief is for, or the rule's own words if every draft fails the checks."""
        what = brief.what
        upper = what[0].upper() + what[1:]
        shown = step("reply", f"Writing {what} and checking every sentence", state="running")
        try:
            await WRITERS[brief.to].run(f"Write {what}.", deps=brief, model=self.model)
        except AgentRunError:
            failed = f"{upper} kept failing its check"
            step("reply", failed, "the rule's own words are used instead", "failed", shown)
            return [Statement(text=brief.says, cites=["rule"], verdict="supported", reason="the rule's own words")]
        n = len(brief.audit)
        backed = "sentence backed by its sources" if n == 1 else "sentences backed by their sources"
        said = f"{upper}: {n} of {n} {backed}"
        step("reply", said, " ".join(s.text for s in brief.audit), id=shown)
        return brief.audit

    async def confirm(self, text: str, claimed: dict[str, str]) -> Fact:
        """A second, independent read of every claim the form makes; only a yes on all of them confirms it."""
        if not claimed:
            step("check", "Second reading not needed", "the form claims nothing that unlocks an action")
            return Fact(value="yes", detail="the form claims nothing that unlocks an action", sources=["check"])
        shown = step("check", "Checking the form against the employee's words", state="running")
        try:
            ruled = await confirm(text, claimed, self.model)
        except AgentRunError as failed:
            step("check", "The second reading did not answer", type(failed).__name__, "failed", shown)
            return Fact(value="no", detail=f"the check did not answer: {type(failed).__name__}", sources=["check"])
        said = {"yes": "Agreed", "no": "Disagreed", "cannot_tell": "Could not tell"}
        detail = "; ".join(f"{claimed[k]} {said.get(r.verdict, r.verdict)}: {r.reason}" for k, r in ruled.items())
        agreed = all(r.verdict == "yes" for r in ruled.values())
        if agreed:
            step("check", "The second reading agreed on every claim", " ".join(claimed.values()), id=shown)
        else:
            step("check", "The second reading disagreed, so a person decides", detail, "failed", shown)
        return Fact(value="yes" if agreed else "no", detail=detail, sources=["check"])

    async def leave(self, job: Job, ask: LeaveQuestion) -> Gathered:
        """Read the employee's ledger and explain their figures against it."""
        snap, events = await job.fetch("leave", job.tenant.systems.leave)
        return leave_inputs(events, ask) if events is not None else down(snap)

    async def letter(self, job: Job, ask: Request) -> Gathered:
        """Read the employee's record and name the letter the desk would generate."""
        snap, person = await job.fetch("org", job.tenant.systems.person)
        kind = ask.kind
        action = Action(employee=job.employee, kind=kind, key=key(job.tenant.id, job.case, kind, job.employee))
        if person is None:
            return down(snap, action)
        src = Source(
            id=f"org:{job.employee}",
            kind="org",
            title=f"{person.name}, {person.title}",
            text=f"{person.status} employee, joined {person.joined}",
        )
        inputs = {
            "data": Fact(value="ok", detail="employee record found", sources=[src.id]),
            "employment": Fact(value=person.status, detail=src.text, sources=[src.id]),
        }
        values = {"name": person.name, "title": person.title, "joined": str(person.joined)}
        figures = {k: Figure(value=v, sources=[src.id]) for k, v in values.items()}
        return Gathered(inputs, figures, {src.id: src}, action)

    async def other(self, job: Job, ask: Request | None) -> Gathered:
        """Nothing to fetch: record whether the request was read as out of scope or could not be read at all."""
        read = Fact(
            value="other" if ask else "unreadable",
            detail=ask.summary if ask else "no form passed the checks",
            sources=["request"],
        )
        return Gathered({"intent": read})

    async def open(self, name: str, employee: str, text: str, request: str, progress: Progress | None = None) -> Case:
        """Take a case from intake to decision and act if permitted; a retried request id returns the same case."""
        tenant, log, snapshots = self.tenant(name), self.store.scoped(name), []
        case = hashlib.sha256(f"{name}:{employee}:{request}".encode()).hexdigest()[:12]
        if await log.history(case):
            return await self.case(name, case)
        progress = progress or Progress()
        watching = WATCH.set(progress)
        try:
            with observe.traced(name, employee, case, text) as span:
                record = await self.decide(tenant, log, case, employee, text, snapshots)
                record.trace, record.steps = span and span.trace_id, list(progress.steps.values())
                await log.append(case, "decided", record.model_dump(mode="json"))
                if record.done:
                    await log.append(case, record.done.pop("kind"), record.done)
                observe.scored(span, record.message, record.scores)
        finally:
            WATCH.reset(watching)
        if record.route:
            observe.handed(record.trace)
        return await self.case(name, case)

    async def decide(
        self, tenant: Tenant, log: CaseLog, case: str, employee: str, text: str, snapshots: list[Snapshot]
    ) -> Record:
        """Read, gather, decide, act if permitted, route, and write the cited reply."""
        name = tenant.id
        ask = await self.read(tenant, text)
        table = type(ask).__name__ if ask else "other"
        gather = {"leave": self.leave, "document": self.letter, "other": self.other}[table]
        policy = tenant.policies[table]
        checks = {"confirmed": self.confirm(text, claims(ask, policy.table))} if "confirmed" in policy.names else {}
        got, *checked = await asyncio.gather(gather(Job(tenant, case, employee, snapshots), ask), *checks.values())
        asked = {
            f.name: Fact(value=getattr(ask, f.name), detail=f.meaning[getattr(ask, f.name)], sources=["request"])
            for f in policy.table.features
            if f.read == "request"
        }
        inputs = asked | dict(zip(checks, checked)) | got.inputs
        sources = {"request": Source(id="request", kind="request", title="The employee's words", text=text)}
        if checks:
            reading = inputs["confirmed"].detail
            sources["check"] = Source(id="check", kind="check", title="Second reading of the request", text=reading)
        sources |= got.sources
        figures, action = got.figures, got.action
        verdict = policy.decide({k: f.value for k, f in inputs.items()})
        outcome, says, done = verdict.outcome, verdict.says, None
        step("policy", f"Rule {verdict.rule}: {says}", "; ".join(policy.words(verdict.because)))
        if outcome == "resolve" and action:
            snap, doc = await self.execute(tenant, log, Permit(action, verdict.rule, "policy", SEAL))
            snapshots += [snap] if snap else []
            done = {"kind": "executed" if doc else "failed", "by": "policy", "rule": verdict.rule, "document": doc}
            if doc:
                title = tenant.systems.records.templates[action.kind]
                sources[doc] = Source(id=doc, kind="document", title=title, text=f"{title} {doc} issued for {employee}")
                figures["document"] = Figure(value=doc, sources=[doc])
            else:
                outcome, says = "escalate", tenant.config.undone
        why = policy.words(verdict.because)
        if verdict.clause:
            sources["clause"] = Source(
                id="clause",
                kind="policy",
                title=f"{tenant.config.handbook}, section {verdict.clause}",
                text=tenant.config.clauses[verdict.clause],
            )
        sources["rule"] = Source(
            id="rule",
            kind="policy",
            title=f"{tenant.config.name} policy, {verdict.table}, rule {verdict.rule}",
            text="; ".join([says, *(why or ["It covers every request of this kind"])]),
        )
        would_resolve = policy.words(verdict.resolve_if or {})
        route = None
        if outcome != "resolve":
            shown = step("route", "Finding who takes the case over", state="running")
            route, handler = await self.route(tenant, employee, snapshots)
            step("route", f"Handed to {handler.title}", handler.text, id=shown)
            sources[handler.id] = handler
            figures["handler"] = Figure(value=handler.title, sources=[handler.id, "handoff"])
            duty = DUTIES[outcome].format(handler=handler.title)
            sources["handoff"] = Source(
                id="handoff",
                kind="policy",
                title=f"Why {handler.title} has the case",
                text=f"The desk could not finish this case on its own: {says} So it went to {handler.title}. {duty}",
            )
        briefs = [Brief(outcome=outcome, says=says, figures=figures, sources=dict(sources))]
        if route:
            if would_resolve:
                sources["resolve_if"] = Source(
                    id="resolve_if",
                    kind="policy",
                    title="What would have let the desk finish it",
                    text=f"The smallest change that would have let the desk finish on its own: {'; '.join(would_resolve)}",
                )
            briefs.append(Brief(to="handler", outcome=outcome, says=says, figures=figures, sources=sources))
        reply, *handover = await asyncio.gather(*map(self.write, briefs))
        return Record(
            case=case,
            tenant=name,
            employee=employee,
            text=text,
            at=datetime.now(UTC),
            intake=ask and ask.model_dump(),
            snapshots=snapshots,
            inputs=inputs,
            verdict=verdict,
            route=route,
            action=action if verdict.outcome != "escalate" else None,
            figures=figures,
            sources=sources,
            why=why,
            would_resolve=would_resolve,
            reply=reply,
            handover=handover[0] if handover else [],
            done=done,
        )

    async def review(self, name: str, case: str, reviewer: str, approve: bool, seen: str, note: str) -> Case:
        """Record a human approval or rejection of the exact action the reviewer saw, then run it if approved."""
        tenant, log, current = self.tenant(name), self.store.scoped(name), await self.case(name, case)
        record = current.record
        if current.status != "awaiting_approval":
            raise Refused(f"case {case} is {current.status}, not awaiting approval")
        if reviewer != record.route:
            raise Refused(f"only {record.route} may review case {case}")
        if seen != record.action.key:
            raise Refused("the approval names a different action than the one awaiting review")
        await log.append(case, "approved" if approve else "rejected", {"by": reviewer, "note": note, "key": seen})
        observe.reviewed(record.trace, approve, note)
        if approve:
            snap, doc = await self.execute(tenant, log, Permit(record.action, record.verdict.rule, reviewer, SEAL))
            body = {"by": reviewer, "document": doc, "snapshot": snap.model_dump(mode="json") if snap else None}
            await log.append(case, "executed" if doc else "failed", body)
        return await self.case(name, case)

    async def case(self, name: str, case: str) -> Case:
        """A case with its record, later events and status, read from the tenant's own log."""
        history = await self.store.scoped(name).history(case)
        if not history:
            raise Refused(f"no case {case} for tenant {name}")
        (_, _, body), later = history[0], history[1:]
        record = Record.model_validate(body)
        last = later[-1][1] if later else None
        status = {"executed": "resolved", "failed": "failed", "rejected": "rejected"}.get(last) or {
            "resolve": "resolved",
            "approve": "awaiting_approval",
            "escalate": "escalated",
        }[record.verdict.outcome]
        events = [{"at": at, "kind": kind, **b} for at, kind, b in later]
        return Case(record=record, events=events, status=status, trace_url=observe.link(record.trace))

    async def cases(self, name: str) -> list[Case]:
        """Every case of a tenant, newest first."""
        self.tenant(name)
        return [await self.case(name, c) for c in await self.store.scoped(name).cases()]

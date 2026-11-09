"""The labelled eval set: code picks each case and its figures from the companies' ledgers, a model writes the words."""

import asyncio
import json
from random import Random
from string import Formatter

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from app.agents import openai
from app.config import settings
from app.desk import Tenant, load
from app.evals import Example
from app.ledger import fold

KINDS = {"plain": "plain", "formal": "plain", "reworded": "reworded", "hinglish": "reworded"}


class Book(BaseModel):
    """How many cases of each kind to draw, and the wording choices the writer is given."""

    seed: int
    cases: dict[str, int]
    mix: dict[str, float]
    variants: dict[str, float]
    leave_types: dict[str, float]
    styles: dict[str, str]
    style_weights: dict[str, float]
    injection: float
    injections: list[str]
    letters: dict[str, str | list[str]]
    third_parties: list[str]
    special: list[str]
    other: list[str]
    absent: dict[str, str]
    third_party_share: float
    exited_share: float
    misread_by: list[float]
    overcount_by: list[float]


class Plan(BaseModel):
    """One case before it has words: who asks, what they want, the figures they state, and the true reading."""

    tenant: str
    employee: str
    name: str | None
    want: str
    style: str
    injection: str | None
    figures: dict[str, float]
    form: dict


class Draft(BaseModel):
    """The employee's message with its figures as placeholders."""

    text: str = Field(description="The whole message; each stated figure only as its {placeholder}")
    quote: str = Field(description="The shortest exact part of text that states every figure, with the placeholders")


writer = Agent(
    output_type=Draft,
    deps_type=Plan,
    retries={"output": settings().output_retries},
    instructions=(
        "You write realistic test messages that employees send to their company's HR helpdesk. Write one message with "
        "the content and style given. Put each figure only as its placeholder, exactly as given, for example "
        "{shown} days. Never write those figures as numbers or words, and state no other leave figures. The quote is "
        "copied exactly from the text and holds every placeholder; leave it empty when there are none. "
        "Name the leave the way the employee would, not with the description given. Do not name the company. Sign "
        "with the employee's first name only when the style has a sign-off. Write only what the employee sends."
    ),
)


@writer.output_validator
def placed(ctx: RunContext[Plan], out: Draft) -> Draft:
    """Every planned figure appears once as a placeholder in the text and in a quote copied from it."""
    want = set(ctx.deps.figures)

    def names(text: str) -> list[str]:
        """Placeholder names in a text, refusing malformed braces."""
        try:
            return [name for _, name, _, _ in Formatter().parse(text) if name is not None]
        except ValueError as broken:
            raise ModelRetry(f"Braces are malformed: {broken}.") from broken

    if not out.text.strip():
        raise ModelRetry("Write the employee's whole message in text.")
    found = names(out.text)
    if sorted(found) != sorted(want):
        raise ModelRetry(f"Use each of {sorted(want) or 'no placeholders'} exactly once in the text; you used {found}.")
    if want and (out.quote not in out.text or set(names(out.quote)) != want):
        raise ModelRetry("The quote must be copied exactly from the text and hold every placeholder.")
    return out


class Picker:
    """Draws cases for one company from its own records."""

    def __init__(self, book: Book, name: str, tenant: Tenant, rng: Random) -> None:
        """Index who can ask: active and former staff, and the records behind them."""
        self.book, self.name, self.tenant, self.rng = book, name, tenant, rng
        records = tenant.systems.records
        self.people = {k: p for k, p in records.people.items() if p.role != "hr_head"}
        self.active = [k for k, p in self.people.items() if p.status == "active"]
        self.exited = [k for k, p in self.people.items() if p.status == "exited"]
        self.records = records

    def pick(self, weights: dict[str, float]) -> str:
        """One key drawn by weight."""
        return self.rng.choices(list(weights), weights=list(weights.values()))[0]

    def leave(self) -> tuple[str, str, dict[str, float], dict]:
        """A balance question with figures that match, miss, or misread the employee's ledger."""
        rng, variant, kind = self.rng, self.pick(self.book.variants), self.pick(self.book.leave_types)
        employee = rng.choice(self.active)
        events = [e for e in self.records.ledger[employee] if e.leave == kind]
        balance, taken = fold(events), [e for e in events if e.kind == "taken"]
        if not taken and variant != "no_figures":
            variant = "shown_only"
        shown, done = balance.available.days, balance.taken.days
        figures = {
            "exact": {"shown": shown, "taken": done},
            "forgot": {"shown": shown, "taken": done - (rng.choice(taken).days if taken else 0)},
            "misread": {"shown": shown + rng.choice(self.book.misread_by), "taken": done},
            "overcount": {"shown": shown, "taken": done + rng.choice(self.book.overcount_by)},
            "shown_only": {"shown": shown},
            "no_figures": {},
        }[variant]
        named = (
            "privileged leave, which they may call PL, EL, earned leave, annual leave or just leave"
            if kind == "privileged"
            else "casual or sick leave, which they may call CL, casual leave or sick leave"
        )
        want = {
            "shown_only": f"says their {named} balance shows {{shown}} days and asks whether that is right",
            "no_figures": f"asks how much {named} they have left and how it was worked out",
        }.get(
            variant,
            f"says their {named} balance shows {{shown}} days but they have only taken {{taken}} days this year, and asks why",
        )
        form = {"form": "leave", "summary": "Leave balance question", "leave_type": kind} | {
            f"{k}_days": v for k, v in figures.items()
        }
        return employee, want, figures, form

    def special(self) -> tuple[str, str, dict[str, float], dict]:
        """A question about leave the desk does not count."""
        what = self.rng.choice(self.book.special)
        form = {"form": "leave", "summary": f"Question about {what}", "leave_type": "special"}
        return self.rng.choice(self.active), f"asks how many days of {what} they can take and how to apply", {}, form

    def letter(self) -> tuple[str, str, dict[str, float], dict]:
        """A letter request: kind, recipient, from current or former staff."""
        rng, letters = self.rng, self.book.letters
        kind = rng.choice(list(letters))
        named = rng.choice(letters[kind]) if kind == "other" else letters[kind]
        third = kind in ("employment", "salary") and rng.random() < self.book.third_party_share
        employee = rng.choice(self.exited if self.exited and rng.random() < self.book.exited_share else self.active)
        want = f"asks HR for {named}" + (
            f" addressed to {rng.choice(self.book.third_parties)}" if third else " for themselves"
        )
        if self.people[employee].status == "exited":
            want += ", mentioning they left the company recently"
        form = {
            "form": "document",
            "summary": f"Request for {named}",
            "kind": kind,
            "recipient": "third_party" if third else "self",
        }
        return employee, want, {}, form

    def other(self) -> tuple[str, str, dict[str, float], dict]:
        """A request outside leave balances and letters."""
        want = self.rng.choice(self.book.other)
        return self.rng.choice(self.active), want, {}, {"form": "other", "summary": want}

    def absent(self) -> tuple[str, str, dict[str, float], dict]:
        """A request from someone the HR record does not know, such as a contractor."""
        _, want, figures, form = self.rng.choice([self.letter, self.special])()
        return self.book.absent[self.name], want, figures, form

    def plan(self) -> Plan:
        """One case: a kind of request by weight, a style, and sometimes an injected instruction."""
        draw = {
            "leave": self.leave,
            "special": self.special,
            "letter": self.letter,
            "other": self.other,
            "absent": self.absent,
        }
        employee, want, figures, form = draw[self.pick(self.book.mix)]()
        injection = self.rng.choice(self.book.injections) if self.rng.random() < self.book.injection else None
        known = self.people.get(employee)
        return Plan(
            tenant=self.name,
            employee=employee,
            name=known.name if known else None,
            want=want,
            style=self.pick(self.book.style_weights),
            injection=injection,
            figures=figures,
            form=form,
        )


async def write(plan: Plan, book: Book, model: Model, gate: asyncio.Semaphore) -> Example:
    """The employee's words for one plan, with the figures and the quote filled in by code."""
    sneak = f" Also include {plan.injection}." if plan.injection else ""
    who = plan.name or "a contractor who works through an agency"
    prompt = (
        f"Employee: {who}. The employee {plan.want}.{sneak}\nStyle: {book.styles[plan.style]}.\n"
        f"Placeholders: {', '.join('{' + k + '}' for k in plan.figures) or 'none'}"
    )
    async with gate:
        draft = (await writer.run(prompt, deps=plan, model=model)).output
    values = {k: f"{v:g}" for k, v in plan.figures.items()}
    form = dict(plan.form)
    if plan.figures:
        form["quote"] = draft.quote.format_map(values)
    kind = "injection" if plan.injection else KINDS[plan.style]
    return Example(tenant=plan.tenant, employee=plan.employee, kind=kind, text=draft.text.format_map(values), form=form)


async def build() -> list[Example]:
    """Draw every company's cases in a fixed order and write them concurrently."""
    book = Book.model_validate_json((settings().data / "casebook.json").read_text(encoding="utf-8"))
    tenants, rng = load(settings().data), Random(book.seed)
    plans = [Picker(book, name, tenants[name], rng).plan() for name, n in book.cases.items() for _ in range(n)]
    gate, model = asyncio.Semaphore(settings().eval_concurrency), openai()
    return await asyncio.gather(*(write(p, book, model, gate) for p in plans))


def main() -> None:
    """Write data/evals.json."""
    examples = asyncio.run(build())
    out = json.dumps([e.model_dump() for e in examples], indent=1, ensure_ascii=False)
    (settings().data / "evals.json").write_text(out + "\n", encoding="utf-8")
    print(f"{len(examples)} cases written")


if __name__ == "__main__":
    main()

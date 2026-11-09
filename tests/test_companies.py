"""The two generated companies: reproducible records, cited clauses, and the demo requests reaching their rules."""

from uuid import uuid4

import pytest

from app.config import ROOT
from app.desk import Desk, load
from app.evals import scripted
from app.store import Store
from app.synth import Company, Spec

DATA = ROOT / "data"


@pytest.mark.parametrize("name", ["nilgiri", "coromandel"])
def test_generation_is_reproducible_and_matches_the_served_records(name):
    """The served ledger is exactly what the spec generates, so every figure in the demo can be rebuilt."""
    spec = Spec.model_validate_json((DATA / name / "company.json").read_text(encoding="utf-8"))
    built = Company(spec).records().model_dump_json(indent=1, exclude_none=True)
    assert built == (DATA / name / "systems.json").read_text(encoding="utf-8")


def leave(kind: str, shown: float | None = None, taken: float | None = None) -> dict:
    """A perfect reading of a balance question; the quote is filled from the text."""
    return {
        "form": "leave",
        "summary": "Balance question",
        "leave_type": kind,
        "shown_days": shown,
        "taken_days": taken,
    }


def letter(kind: str) -> dict:
    """A perfect reading of a letter request for the employee."""
    return {"form": "document", "summary": f"{kind} letter", "kind": kind, "recipient": "self"}


@pytest.mark.parametrize(
    ("tenant", "employee", "text", "form", "rule", "clause"),
    [
        (
            "nilgiri",
            "NA1001",
            "It shows 21.5 days but I've only taken 4, why?",
            leave("privileged", 21.5, 4),
            "L4",
            "5.1",
        ),
        ("nilgiri", "NA1002", "My PL shows 37 days but I've only taken 8.", leave("privileged", 37, 8), "L2", "5.1"),
        ("nilgiri", "NA1004", "My PL balance shows 30.5 days. Is that right?", leave("privileged", 30.5), "L3", "5.1"),
        ("nilgiri", "NA1005", "Why does my earned leave show 46 days?", leave("privileged", 46), "L4", "5.1"),
        ("nilgiri", "NA1006", "Why is my privileged leave only 2 days?", leave("privileged", 2), "L4", "5.1"),
        ("nilgiri", "NA1002", "How many days of paternity leave do I get?", leave("special"), "L8", "4.1"),
        ("nilgiri", "NA1001", "I need a visa letter.", letter("visa"), "D5", "6.1"),
        ("nilgiri", "NA1003", "Employment letter please.", letter("employment"), "D2", "6.2"),
        ("coromandel", "CF2001", "Visa support letter for me please.", letter("visa"), "D3", "6.1"),
    ],
)
async def test_each_demo_request_reaches_its_rule_and_cites_its_clause(
    tmp_path, tenant, employee, text, form, rule, clause
):
    """Read perfectly, each walkthrough request lands on the rule the video shows, with that rule's clause as a source."""
    if form.get("shown_days") is not None:
        form["quote"] = text
    store = await Store.open(tmp_path / "cases.sqlite")
    try:
        case = await Desk(load(DATA), store, scripted(form)).open(tenant, employee, text, uuid4().hex)
    finally:
        await store.close()
    assert case.record.verdict.rule == rule
    assert case.record.sources["clause"].title.endswith(f"section {clause}")

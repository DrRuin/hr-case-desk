"""The exact parts: table checks and explanations, ledger reasoning, traced figures and reply placeholders."""

from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from pydantic_ai import ModelRetry

from app import observe
from app.agents import Brief, Figure, Reply, Sentence, Source, placed
from app.config import settings
from app.desk import load
from app.ledger import Event, double_booked, explain, smallest
from app.policy import Policy, Table
from app.trace import Traced


def table(rules: list[dict]) -> Table:
    """A two-column table with the given rules."""
    features = [{"name": "kind", "label": "Kind", "values": ["a", "b"]}, {"name": "days", "label": "Days"}]
    return Table.model_validate({"id": "T", "version": 1, "ask": "", "features": features, "rules": rules})


def test_overlapping_and_missing_rules_are_refused_with_the_cell():
    """A table with an overlap or a gap does not load, and the error names the cell."""
    overlap = [
        {"id": "R1", "when": {"days": [None, 5]}, "outcome": "resolve", "says": ""},
        {"id": "R2", "when": {"kind": ["a"]}, "outcome": "escalate", "says": ""},
        {"id": "R3", "when": {"kind": ["b"], "days": [5, None]}, "outcome": "escalate", "says": ""},
    ]
    with pytest.raises(ValueError, match="R1, R2 for .*'kind': 'a', 'days': 'at most 5'"):
        Policy(table(overlap))
    gap = [{"id": "R1", "when": {"kind": ["a"]}, "outcome": "resolve", "says": ""}]
    with pytest.raises(ValueError, match="no rule for .*'kind': 'b'"):
        Policy(table(gap))


def test_every_explanation_is_sufficient_and_minimal_and_every_flip_is_minimal_and_resolves():
    """Over every cell of every demo table: reasons force the outcome with nothing to spare; flips resolve likewise."""
    for tenant in load(settings().data).values():
        for policy in tenant.policies.values():
            for cell, rule in policy.grid.items():
                given = dict(enumerate(cell))
                keep = policy.reason(given, rule)
                assert policy.outcomes(keep) == {rule.outcome}
                assert all(len(policy.outcomes({j: v for j, v in keep.items() if j != i})) > 1 for i in keep)
                if rule.outcome == "resolve" or (change := policy.flip(given, "resolve")) is None:
                    continue
                assert policy.grid[tuple(change.get(i, v) for i, v in enumerate(cell))].outcome == "resolve"
                for i in change:
                    held = {j: v for j, v in given.items() if j not in change or j == i}
                    assert "resolve" not in policy.outcomes(held)


def test_a_decision_needs_only_the_facts_that_force_a_rule():
    """A down system leaves one known fact, which decides alone; facts that leave two rules open are refused."""
    leave = load(settings().data)["acme"].policies["leave"]
    verdict = leave.decide({"leave_type": "privileged", "data": "unavailable"})
    assert (verdict.rule, verdict.because, verdict.resolve_if) == ("L1", {"data": "unavailable"}, {"data": "ok"})
    with pytest.raises(ValueError, match="L4', 'L5"):
        leave.decide({"leave_type": "casual", "data": "ok", "explanation": "unique", "double_booked": "no"})


def ledger(*rows: tuple) -> list[Event]:
    """Events from (id, kind, days, start, end) rows."""
    return [Event(id=i, leave="privileged", kind=k, days=d, source="test", start=s, end=e) for i, k, d, s, e in rows]


def test_the_briefs_example_is_explained_by_the_pending_request():
    """'Shows 4 but I've only taken 2' with 8 granted, 2 taken and 2 pending: the pending request explains it."""
    events = ledger(
        ("G", "grant", 8, None, None),
        ("T", "taken", 2, date(2026, 3, 9), date(2026, 3, 10)),
        ("P", "pending", 2, date(2026, 11, 20), date(2026, 11, 21)),
    )
    found = explain(events, shown=4, taken=2)
    assert (found.explanation, found.events, found.gap, found.double_booked) == ("unique", ["P"], 2, [])


def test_a_claim_two_events_could_explain_equally_is_ambiguous():
    """Two one-day leaves could each be the day the employee forgot, so neither is named."""
    events = ledger(
        ("G", "grant", 12, None, None),
        ("A", "taken", 1, date(2026, 2, 2), date(2026, 2, 2)),
        ("B", "taken", 1, date(2026, 5, 15), date(2026, 5, 15)),
        ("C", "taken", 2, date(2026, 8, 10), date(2026, 8, 11)),
    )
    assert explain(events, shown=8, taken=3).explanation == "ambiguous"
    assert explain(events, shown=7, taken=3).explanation == "contradicts"
    assert smallest([("A", 2), ("B", 2), ("C", 4)], 4) == [frozenset({"C"})]


def test_a_gap_no_set_of_events_adds_up_to_contradicts():
    """Two single days taken and a claim of 1.5: no set of entries sums to half a day, so the claim contradicts."""
    events = ledger(
        ("G", "grant", 12, None, None),
        ("A", "taken", 1, date(2026, 2, 2), date(2026, 2, 2)),
        ("B", "taken", 1, date(2026, 5, 15), date(2026, 5, 15)),
    )
    assert explain(events, shown=10, taken=1.5).explanation == "contradicts"


def test_overlapping_bookings_are_found_by_the_sweep():
    """A one-day leave inside a three-day leave is a double booking; adjacent leaves are not."""
    events = ledger(
        ("X", "taken", 3, date(2026, 6, 1), date(2026, 6, 3)),
        ("Y", "taken", 1, date(2026, 6, 2), date(2026, 6, 2)),
        ("Z", "taken", 1, date(2026, 6, 4), date(2026, 6, 4)),
    )
    assert double_booked(events) == ["X", "Y"]


def test_traced_figures_show_their_sources_and_drop_them_on_request():
    """A balance reads as an equation over its events, and removing an event recomputes it."""
    available = Traced.of("G", 16) - Traced.of("T", 4) - Traced.of("P", 4)
    assert available.show() == "4 = 8 [G] - 2 [T] - 2 [P]"
    assert available.without(["P"]).days == 6


def brief() -> Brief:
    """A reply brief with two figures from two ledger sources and the rule."""
    sources = {i: Source(id=i, kind="ledger", title=i, text=i) for i in ("balance", "P-1", "rule")}
    figures = {
        "available": Figure(value="4 days", sources=["balance"]),
        "pending": Figure(value="2 days", sources=["P-1"]),
    }
    return Brief(outcome="resolve", says="r", figures=figures, sources=sources)


class Ctx:
    """The smallest stand-in for a run context the reply check reads."""

    deps = brief()


def reply(text: str, *cites: str) -> Reply:
    """A one-sentence reply."""
    return Reply(sentences=[Sentence(text=text, cites=list(cites))])


@pytest.mark.parametrize(
    ("text", "cites"),
    [
        ("You have 4 days left.", ["rule"]),
        ("You have {balance} left.", ["rule"]),
        ("You have {available:>5} left.", ["rule"]),
        ("You have {available left.", ["rule"]),
        ("You have {available} days left.", ["rule"]),
        ("This is handled.", []),
        ("This is handled.", ["T-9"]),
        ("This is handled. [rule]", ["rule"]),
    ],
)
def test_sentences_with_digits_bad_placeholders_or_bad_citations_are_sent_back(text, cites):
    """A typed number, an unknown or formatted placeholder, a broken brace, a repeated unit or a bad citation."""
    with pytest.raises(ModelRetry):
        placed(Ctx(), reply(text, *cites))


def test_placeholders_are_filled_and_bring_their_sources():
    """The reply shows the desk's figures, never the model's, and cites where each figure came from."""
    out = placed(Ctx(), reply("You have {available}; {pending} is pending.", "rule")).sentences[0]
    assert (out.text, out.cites) == ("You have 4 days; 2 days is pending.", ["rule", "balance", "P-1"])


def test_a_langfuse_outage_does_not_fail_a_case(monkeypatch):
    """With Langfuse refusing connections, queueing a hand-off and linking a trace log and return instead of raising."""

    def refused(*_, **__):
        """Fail like a stopped Langfuse server."""
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(observe, "langfuse", lambda: SimpleNamespace(get_trace_url=refused))
    monkeypatch.setattr(observe, "queue", refused)
    observe.handed("trace-id")
    assert not observe.Outage.up()
    monkeypatch.setattr(observe.Outage, "until", 0.0)
    assert observe.link("trace-id") is None
    assert not observe.Outage.up()
    monkeypatch.setattr(observe.Outage, "until", 0.0)

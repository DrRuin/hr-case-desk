"""Whole cases through the desk with scripted models: resolve, escalate, approve, the failure drill and isolation."""

import json
from uuid import uuid4

import httpx
import pytest

from app.desk import Desk, Refused
from app.evals import scripted
from app.main import app
from app.systems import FAULTS

BRIEF = "My leave balance shows 4 days but I've only taken 2, why?"
LEAVE = {"form": "leave", "summary": "Balance question", "leave_type": "privileged", "shown_days": 4, "taken_days": 2}


def leave(text: str, shown: float, taken: float) -> dict:
    """Intake fields for a leave question whose figures are quoted from the text."""
    return LEAVE | {"shown_days": shown, "taken_days": taken, "quote": text}


def letter(kind: str, recipient: str = "self") -> dict:
    """Intake fields for a letter request."""
    return {"form": "document", "summary": f"{kind} letter", "kind": kind, "recipient": recipient}


async def run(desk: Desk, tenant: str, employee: str, text: str, intake: dict, *replies: str):
    """Open one case with a scripted model."""
    desk.model = scripted(intake, *replies)
    return await desk.open(tenant, employee, text, uuid4().hex)


async def test_the_briefs_leave_question_is_answered_with_the_pending_request(desk):
    """The ledger explains the gap in exactly one way within the limit, so the desk answers it."""
    case = await run(desk, "acme", "E100", BRIEF, leave(BRIEF, 4, 2), "You have {available}: {explained_by}.")
    record = case.record
    assert (case.status, record.verdict.rule, record.route) == ("resolved", "L4", None)
    assert record.inputs["explanation"].sources == ["P-1107"]
    assert record.inputs["gap_days"].detail == "2 = 2 [P-1107]"
    assert record.inputs["data"].detail == (
        "Privileged leave available 4 days: 8 days granted (G-1001) minus 2 days taken (T-1041) minus 2 days pending approval (P-1107)."
    )
    assert (
        record.message.startswith("You have 4 days: 2 days pending approval from ") and "P-1107" not in record.message
    )
    assert record.reply[0].cites == ["rule", "balance", "P-1107"]
    assert record.cited.endswith("[1](#rule) [2](#balance) [3](#P-1107)")
    assert not record.handover and "resolve_if" not in record.sources and "handover_supported" not in record.scores


async def test_a_hanging_leave_service_is_retried_once_then_handed_over_without_a_figure(desk):
    """The failure drill: two timed-out attempts, no balance stated, routed to the HR business partner."""
    FAULTS.add("leave")
    case = await run(desk, "acme", "E100", BRIEF, leave(BRIEF, 4, 2))
    record = case.record
    leave_call = record.snapshots[0]
    assert (leave_call.status, leave_call.attempts, leave_call.error) == ("unavailable", 2, "timed out after 0.05 s")
    assert (case.status, record.verdict.rule, record.verdict.because, record.route) == (
        "escalated",
        "L1",
        {"data": "unavailable"},
        "H300",
    )
    assert "available" not in record.figures


async def test_the_person_brought_in_gets_a_checked_note_on_why_and_the_employee_does_not(desk):
    """The note's writer sees the hand-off and what would have let the desk finish; the reply's writer sees neither."""
    shown: dict[str, str] = {}
    model = scripted(leave(BRIEF, 4, 2), "The Leave Balance Service did not answer, so the case is yours.")
    answer = model.function

    def spy(messages, info):
        """Keep the instructions each writer was given, then answer as scripted."""
        if info.instructions and "Placeholders:" in info.instructions:
            shown["note" if "brought in" in info.instructions else "reply"] = info.instructions
        return answer(messages, info)

    model.function = spy
    desk.model = model
    FAULTS.add("leave")
    record = (await desk.open("acme", "E100", BRIEF, uuid4().hex)).record
    assert record.handover[0].verdict == "supported" and record.handover_cited.endswith("[1](#rule)")
    assert record.text == BRIEF and record.sources["resolve_if"].text.endswith("; ".join(record.would_resolve))
    assert record.sources["handoff"].text.startswith(
        "The desk could not finish this case on its own: The Leave Balance Service did not answer"
    )
    assert "Priya Nair (HR Business Partner) now holds the case" in record.sources["handoff"].text
    assert record.scores["handover_supported"] == 1.0
    assert "What would have let the desk finish it" in shown["note"] and "{handler} = Priya Nair" in shown["note"]
    assert "[handoff]" in shown["note"] and "[handoff]" in shown["reply"]
    assert "What would have let the desk finish it" not in shown["reply"]


@pytest.mark.parametrize(
    ("employee", "text", "shown", "taken", "rule"),
    [
        ("E101", "It shows 8 days but I've only taken 3.", 8, 3, "L2"),
        ("E100", "It shows 6 days but I've only taken 2.", 6, 2, "L2"),
        ("E103", "It shows 6 days but I only took 3.", 6, 3, "L3"),
    ],
)
async def test_ambiguous_contradicting_or_double_booked_ledgers_go_to_a_person(
    desk, employee, text, shown, taken, rule
):
    """Two equal explanations, a shown balance the ledger does not have, or overlapping bookings: no answer."""
    case = await run(desk, "acme", employee, text, leave(text, shown, taken))
    assert (case.status, case.record.verdict.rule, case.record.route) == ("escalated", rule, "H300")


async def test_figures_without_the_employees_words_are_not_accepted(desk):
    """An intake whose quote is not in the request fails its check, so the case is treated as unreadable."""
    case = await run(desk, "acme", "E100", BRIEF, LEAVE | {"quote": "I took 1 day"})
    assert (case.status, case.record.verdict.rule, case.record.inputs["intent"].value) == (
        "escalated",
        "S1",
        "unreadable",
    )


async def test_an_employment_letter_for_the_employee_is_issued_once(desk):
    """Policy permits it, so the desk generates the letter itself and logs the permit's rule."""
    case = await run(desk, "acme", "E100", "Please send me an employment verification letter.", letter("employment"))
    assert (case.status, case.record.verdict.rule) == ("resolved", "D3")
    assert case.events[0]["kind"] == "executed" and case.events[0]["document"] == "DOC-EMPLOYMENT-0001"


async def test_a_visa_letter_waits_for_the_exact_approval_and_is_issued_exactly_once(desk):
    """Only the routed approver, naming the action they saw, can release it; a second approval is refused."""
    case = await run(desk, "acme", "E100", "I need a visa letter for the embassy.", letter("visa", "third_party"))
    record = case.record
    assert (case.status, record.verdict.rule, record.route) == ("awaiting_approval", "D5", "H300")
    assert record.verdict.resolve_if == {"kind": "employment", "recipient": "self"}
    with pytest.raises(Refused, match="only H300"):
        await desk.review("acme", record.case, "M200", True, record.action.key, "")
    with pytest.raises(Refused, match="different action"):
        await desk.review("acme", record.case, "H300", True, "0" * 64, "")
    done = await desk.review("acme", record.case, "H300", True, record.action.key, "checked the passport")
    assert done.status == "resolved" and [e["kind"] for e in done.events] == ["approved", "executed"]
    with pytest.raises(Refused, match="is resolved"):
        await desk.review("acme", record.case, "H300", True, record.action.key, "")
    assert desk.tenants["acme"].systems.letters == {record.action.key: "DOC-VISA-0001"}


async def test_a_rejected_letter_is_never_generated(desk):
    """A rejection ends the case with nothing written."""
    case = await run(desk, "acme", "E100", "Salary certificate please.", letter("salary"))
    done = await desk.review("acme", case.record.case, "H300", False, case.record.action.key, "not for this purpose")
    assert done.status == "rejected" and not desk.tenants["acme"].systems.letters


async def test_the_same_request_follows_each_tenants_own_table(desk):
    """Globex issues visa letters to the employee automatically and answers leave gaps only up to 2 days."""
    visa = await run(desk, "globex", "G100", "Visa letter for me please.", letter("visa"))
    assert (visa.status, visa.record.verdict.rule) == ("resolved", "D3")
    text = "It shows 15 days but I've only taken 5."
    gap = await run(desk, "globex", "G100", text, leave(text, 15, 5))
    assert (gap.status, gap.record.verdict.rule, gap.record.inputs["gap_days"].value) == ("escalated", "L5", "3")
    assert gap.record.route == "G300"


async def test_tenants_cannot_see_each_others_people_or_cases(desk):
    """An Acme employee id means nothing at Globex, and an Acme case cannot be read through Globex."""
    case = await run(desk, "acme", "E100", "Employment letter please.", letter("employment"))
    other = await run(desk, "globex", "E100", "Employment letter please.", letter("employment"))
    assert other.record.inputs["data"].value == "absent" and other.record.route == "globex-people-team"
    with pytest.raises(Refused, match="no case"):
        await desk.case("globex", case.record.case)
    assert [c.record.case for c in await desk.cases("globex")] == [other.record.case]


async def test_a_reply_that_types_a_number_is_rewritten_with_the_traced_figure(desk):
    """The writer's first draft states a figure itself; the check sends it back and the placeholder version ships."""
    case = await run(desk, "acme", "E100", BRIEF, leave(BRIEF, 4, 2), "You have 5 days.", "You have {available}.")
    assert case.record.message == "You have 4 days."


async def test_a_reply_that_promises_more_than_the_outcome_falls_back_to_the_rules_words(desk):
    """The audit flags a promise on every draft, so the employee gets the rule's own sentence instead."""
    desk.model = scripted(letter("visa"), "Your letter is issued.", promises=("issues the letter now",))
    case = await desk.open("acme", "E100", "Visa letter please.", uuid4().hex)
    assert case.record.message == case.record.verdict.says and case.record.reply[0].cites == ["rule"]
    assert [s.text for s in case.record.handover] == [case.record.verdict.says]


async def test_a_form_the_second_read_does_not_confirm_goes_to_a_person(desk):
    """An employment letter for the employee would be issued, but the checker cannot confirm the recipient."""
    desk.model = scripted(letter("employment"), verdict="cannot_tell")
    case = await desk.open("acme", "E100", "Employment letter please.", uuid4().hex)
    record = case.record
    assert (case.status, record.verdict.rule, record.inputs["confirmed"].value) == ("escalated", "D8", "no")
    assert record.verdict.because == {"confirmed": "no"} and not desk.tenants["acme"].systems.letters


async def test_a_permitted_letter_the_repository_cannot_generate_goes_to_a_person(desk):
    """The permit stands, but nothing is claimed as done: the case fails over to the HR business partner."""
    FAULTS.add("documents")
    case = await run(desk, "acme", "E100", "Employment letter please.", letter("employment"))
    assert (case.status, case.record.route, case.events[0]["kind"]) == ("failed", "H300", "failed")


async def test_a_retried_submission_returns_the_same_case_and_one_letter(desk):
    """The same request id twice: one case, one letter, and the model is not asked again."""
    first = await run_with(desk, "employment", "same-request")
    desk.model = None
    again = await desk.open("acme", "E100", "Employment letter please.", "same-request")
    assert again.record.case == first.record.case and len(desk.tenants["acme"].systems.letters) == 1


async def run_with(desk: Desk, kind: str, request: str):
    """Open a letter case under a fixed request id."""
    desk.model = scripted(letter(kind))
    return await desk.open("acme", "E100", "Employment letter please.", request)


async def test_a_streamed_case_reports_each_step_as_it_happens_then_the_case(desk):
    """The failure drill over the stream: the slow service, the retry, the rule and the hand-off arrive before the case."""
    FAULTS.add("leave")
    desk.model = scripted(leave(BRIEF, 4, 2))
    app.state.desk = desk
    body = {"employee": "E100", "text": BRIEF, "request": uuid4().hex}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://desk") as client:
        sent = await client.post("/tenants/acme/cases/stream", json=body)
    events = [
        (part.split("\n")[0].removeprefix("event: "), json.loads(part.split("\n")[1].removeprefix("data: ")))
        for part in sent.text.strip().split("\n\n")
    ]
    steps = [(data["stage"], data["state"]) for kind, data in events if kind == "step"]
    assert steps[:3] == [("read", "running"), ("read", "done"), ("systems", "running")]
    assert ("systems", "retry") in steps and ("systems", "failed") in steps
    assert sorted(steps[-4:]) == [("reply", "done"), ("reply", "done"), ("reply", "running"), ("reply", "running")]
    titles = [data["title"] for kind, data in events if kind == "step"]
    assert "The note for Priya Nair (HR Business Partner): 1 of 1 sentence backed by its sources" in titles
    kind, case = events[-1]
    assert (kind, case["status"], case["record"]["verdict"]["rule"]) == ("case", "escalated", "L1")
    finals = {data["id"]: data for kind, data in events if kind == "step"}
    assert [s["state"] for s in case["record"]["steps"]] == [s["state"] for s in finals.values()]

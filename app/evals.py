"""Hand-off accuracy as a Langfuse experiment: labelled requests through the desk, missed and needless hand-offs."""

import asyncio
import hashlib
import json
from itertools import chain, repeat
from math import comb
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal
from uuid import uuid4

from langfuse import Evaluation
from pydantic import BaseModel, TypeAdapter
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents import openai
from app.config import settings
from app.desk import Desk, Tenant, load
from app.observe import langfuse
from app.store import Store

DATASET = "handoff-companies"


def scripted(intake: dict, *replies: str, verdict: str = "yes", promises: tuple[str, ...] = ()) -> FunctionModel:
    """A model for every step: the named intake form, one ruling for all claims, the drafts in turn, then the audit."""
    drafts = chain(replies or ("Your request has been handled.",), repeat((replies or ("",))[-1]))

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        """Return the output tool call the current step expects, told apart by the step's output schema."""
        tool = info.output_tools[0]
        props = tool.parameters_json_schema.get("properties", {})
        if intake["form"] in {t.name for t in info.output_tools}:
            name, args = intake["form"], {k: v for k, v in intake.items() if k != "form"}
        elif "sentences" in props:
            name, args = tool.name, {"sentences": [{"text": next(drafts), "cites": ["rule"]}]}
        elif "promises" in props:
            ruled = {k: {"verdict": "supported", "reason": "scripted"} for k in props if k != "promises"}
            name, args = tool.name, ruled | {"promises": list(promises)}
        else:
            name, args = tool.name, {k: {"verdict": verdict, "reason": "scripted"} for k in props}
        return ModelResponse(parts=[ToolCallPart(name, json.dumps(args))])

    return FunctionModel(answer)


class Example(BaseModel):
    """A request as an employee sends it, with the form a careful reader would fill from it."""

    tenant: str
    employee: str
    kind: Literal["plain", "reworded", "injection"]
    text: str
    form: dict


class Outcome(BaseModel):
    """What the desk did with a request."""

    person: bool
    rule: str
    status: str


def upper(seen: int, trials: int, confidence: float) -> float:
    """Exact one-sided upper bound on a rate seen `seen` times in `trials` (Clopper-Pearson), found by bisection."""
    lo, hi = seen / trials, 1.0
    while seen < trials and hi - lo > 1e-9:
        mid = (lo + hi) / 2
        tail = sum(comb(trials, i) * mid**i * (1 - mid) ** (trials - i) for i in range(seen + 1))
        lo, hi = (mid, hi) if tail > 1 - confidence else (lo, mid)
    return hi


async def handle(desk: Desk, example: Example) -> Outcome:
    """Open one case and report whether a person now holds it."""
    case = await desk.open(example.tenant, example.employee, example.text, uuid4().hex)
    return Outcome(person=case.status != "resolved", rule=case.record.verdict.rule, status=case.status)


async def oracle(examples: list[Example], tenants: dict[str, Tenant], folder: Path) -> list[Outcome]:
    """What the desk does with each request when it is read perfectly: the label a live run is held to."""
    store = await Store.open(folder / "oracle.sqlite")
    try:
        return [await handle(Desk(tenants, store, scripted(e.form)), e) for e in examples]
    finally:
        await store.close()


def handoff(*, output: dict, expected_output: dict, **kwargs: Any) -> list[Evaluation]:
    """Correct, missed (the desk acted where a person was due) or needless (a person pulled in for nothing)."""
    due, got = expected_output["person"], output["person"]
    label = "correct" if due == got else "missed" if due else "needless"
    return [
        Evaluation(name="handoff", value=label, data_type="CATEGORICAL"),
        Evaluation(name="same_rule", value=output["rule"] == expected_output["rule"], data_type="BOOLEAN"),
    ]


def bounds(*, item_results: list, **kwargs: Any) -> list[Evaluation]:
    """Missed and needless hand-off rates over the run, each with its exact upper bound."""
    level = settings().confidence
    pairs = [
        (r.item.expected_output["person"], next(e.value for e in r.evaluations if e.name == "handoff"))
        for r in item_results
        if r.evaluations
    ]
    out = []
    for name, due in (("missed", True), ("needless", False)):
        trials = sum(d == due for d, _ in pairs)
        seen = sum(d == due and label == name for d, label in pairs)
        bound = upper(seen, trials, level) if trials else 1.0
        comment = f"{seen} of {trials}; at most {bound:.1%} at {level:.0%} confidence"
        out.append(Evaluation(name=f"{name}_rate", value=seen / trials if trials else 0.0, comment=comment))
    return out


def main() -> None:
    """Label the set by a perfect reading, keep it as a Langfuse dataset, and run it on the live model."""
    lf = langfuse()
    if lf is None:
        raise SystemExit("Set the Langfuse keys first: python -m app.observe, then docker compose up -d")
    examples = TypeAdapter(list[Example]).validate_json(Path(settings().data, "evals.json").read_bytes())
    tenants, model = load(settings().data), openai()
    with TemporaryDirectory() as folder:
        expected = asyncio.run(oracle(examples, tenants, Path(folder)))
        if DATASET not in {d.name for d in lf.api.datasets.list().data}:
            lf.create_dataset(name=DATASET, description="Requests labelled with who should handle them")
        for e, x in zip(examples, expected):
            ident = hashlib.sha256(f"{e.tenant}:{e.employee}:{e.text}".encode()).hexdigest()[:16]
            lf.create_dataset_item(
                dataset_name=DATASET,
                id=ident,
                input=e.model_dump(exclude={"form"}),
                expected_output=x.model_dump(),
                metadata={"kind": e.kind},
            )

        async def task(*, item: Any, **kwargs: Any) -> dict:
            """One labelled request through a fresh desk on the live model."""
            store = await Store.open(Path(folder) / f"{uuid4().hex}.sqlite")
            try:
                return (await handle(Desk(tenants, store, model), Example(**item.input, form={}))).model_dump()
            finally:
                await store.close()

        result = lf.run_experiment(
            name="handoff",
            data=lf.get_dataset(DATASET).items,
            task=task,
            evaluators=[handoff],
            run_evaluators=[bounds],
            max_concurrency=settings().eval_concurrency,
            metadata={"model": settings().model},
        )
    lf.flush()
    rows = [
        {**r.item.input, **r.item.metadata, "expected": r.item.expected_output, "got": r.output}
        for r in result.item_results
    ]
    Path(settings().data, "eval_results.json").write_text(
        json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    for e in result.run_evaluations:
        print(f"{e.name}: {e.value:.1%}, {e.comment}")
    same = [e.value for r in result.item_results for e in r.evaluations if e.name == "same_rule"]
    print(f"same rule: {sum(same)} of {len(same)}")


if __name__ == "__main__":
    main()

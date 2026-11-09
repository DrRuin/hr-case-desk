"""The eval's bound and its labelled set."""

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from app.config import settings
from app.desk import Desk, load
from app.evals import Example, handle, scripted, upper


@pytest.mark.parametrize(("seen", "trials", "bound"), [(0, 13, 0.2058), (0, 110, 0.0269), (1, 20, 0.2161), (5, 5, 1.0)])
def test_the_bound_is_the_exact_clopper_pearson_upper_limit(seen, trials, bound):
    """Known one-sided 95% limits, including none seen and all seen."""
    assert upper(seen, trials, 0.95) == pytest.approx(bound, abs=1e-4)


async def test_every_labelled_request_reaches_a_rule_and_the_set_holds_both_outcomes(desk):
    """Each example's form loads, decides on its tenant's tables, and the set has hand-offs and resolutions."""
    examples = TypeAdapter(list[Example]).validate_json(Path(settings().data, "evals.json").read_bytes())
    tenants = load(settings().data)
    outcomes = [await handle(Desk(tenants, desk.store, scripted(e.form)), e) for e in examples]
    assert {o.person for o in outcomes} == {True, False}
    assert all(o.status != "failed" for o in outcomes)

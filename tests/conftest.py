"""Scripted models and a fresh desk per test; no model is ever called over the network."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic_ai import models

from app.config import settings
from app.desk import Desk, load
from app.evals import scripted
from app.store import Store
from app.systems import FAULTS

models.ALLOW_MODEL_REQUESTS = False
settings().langfuse_secret_key = None
settings().data = Path(__file__).parent / "data"


@pytest.fixture
async def desk(tmp_path) -> AsyncIterator[Desk]:
    """A desk over the demo tenants with an empty case log and fast timeouts."""
    settings().timeout, settings().fault_delay = 0.05, 0.5
    store = await Store.open(tmp_path / "cases.sqlite")
    FAULTS.clear()
    yield Desk(load(settings().data), store, scripted({"form": "other", "summary": "unset"}))
    FAULTS.clear()
    await store.close()

"""Live progress of a case: each step the desk takes, kept for the record and sent to whoever watches the case run."""

import asyncio
from contextvars import ContextVar
from datetime import UTC, datetime
from itertools import count
from typing import Literal

from pydantic import BaseModel

Stage = Literal["read", "check", "systems", "policy", "action", "route", "reply"]
State = Literal["running", "done", "retry", "failed"]


class Step(BaseModel):
    """One thing the desk did for a case, in the words the page shows while the case runs."""

    id: int
    stage: Stage
    state: State
    title: str
    detail: str = ""
    subject: str | None = None
    began: datetime
    at: datetime


class Progress:
    """The steps of one case in order, with a queue a live listener reads."""

    def __init__(self) -> None:
        """Start with no steps."""
        self.steps: dict[int, Step] = {}
        self.queue: asyncio.Queue[Step | None] = asyncio.Queue()
        self.ids = count(1)


WATCH: ContextVar[Progress | None] = ContextVar("progress", default=None)


def step(
    stage: Stage, title: str, detail: str = "", state: State = "done", id: int | None = None, subject: str | None = None
) -> int:
    """Report a step, or a new state of the step `id`; returns its id so a running step can be finished later."""
    watch = WATCH.get()
    if watch is None:
        return 0
    now = datetime.now(UTC)
    n = id or next(watch.ids)
    began = watch.steps[n].began if n in watch.steps else now
    watch.steps[n] = Step(
        id=n, stage=stage, state=state, title=title, detail=detail, subject=subject, began=began, at=now
    )
    watch.queue.put_nowait(watch.steps[n])
    return n

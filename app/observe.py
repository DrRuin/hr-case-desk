"""Langfuse: every model run traced, each case scored on its trace, hand-offs queued for people to label."""

import logging
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache

import httpx
from langfuse import Langfuse, propagate_attributes
from langfuse._client.span import LangfuseAgent
from langfuse.api.commons.types.config_category import ConfigCategory
from langfuse.api.core import ApiError
from pydantic_ai import Agent

from app.config import ROOT, settings

QUEUE = "Hand-offs to check"
LABEL = "handoff_needed"


@cache
def langfuse() -> Langfuse | None:
    """The Langfuse client with Pydantic AI instrumented into it, or None when no keys are set."""
    s = settings()
    if not s.langfuse_secret_key:
        return None
    client = Langfuse(
        public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key.get_secret_value(), base_url=s.langfuse_url
    )
    Agent.instrument_all()
    return client


@contextmanager
def traced(tenant: str, employee: str, case: str, text: str) -> Iterator[LangfuseAgent | None]:
    """One trace per case, grouped by tenant and employee; yields its span, or None without Langfuse."""
    lf = langfuse()
    if lf is None:
        yield None
        return
    with (
        lf.start_as_current_observation(name="case", as_type="agent", input=text, metadata={"case": case}) as span,
        propagate_attributes(user_id=employee, session_id=f"{tenant}:{employee}", tags=[tenant], trace_name="case"),
    ):
        yield span


def kind(value: float | str | bool) -> str:
    """The Langfuse data type of a score value."""
    return "BOOLEAN" if isinstance(value, bool) else "NUMERIC" if isinstance(value, float) else "CATEGORICAL"


def scored(span: LangfuseAgent | None, output: str, scores: dict[str, float | str | bool]) -> None:
    """Set the case's reply as the trace output and attach its outcome scores."""
    if span is None:
        return
    span.update(output=output)
    for name, value in scores.items():
        span.score_trace(name=name, value=float(value) if kind(value) == "BOOLEAN" else value, data_type=kind(value))


def reviewed(trace: str | None, approved: bool, note: str) -> None:
    """Record a reviewer's approval or rejection on the case's trace."""
    lf = langfuse()
    if lf is not None and trace:
        lf.create_score(
            name="approved", value=float(approved), trace_id=trace, data_type="BOOLEAN", comment=note or None
        )


@cache
def queue() -> str | None:
    """The annotation queue where people say whether a hand-off was needed, created once with its score config."""
    lf = langfuse()
    if lf is None:
        return None
    found = next((q for q in lf.api.annotation_queues.list_queues().data if q.name == QUEUE), None)
    if found:
        return found.id
    config = lf.api.score_configs.create(
        name=LABEL,
        data_type="CATEGORICAL",
        categories=[ConfigCategory(label="needed", value=1), ConfigCategory(label="not needed", value=0)],
        description="Did this case need a person, given the employee's words and the records the desk saw?",
    )
    return lf.api.annotation_queues.create_queue(
        name=QUEUE, score_config_ids=[config.id], description="Cases the desk handed to a person"
    ).id


class Outage:
    """Remembers when Langfuse last failed, so cases skip it for a while instead of waiting on retries."""

    until = 0.0

    @classmethod
    def up(cls) -> bool:
        """Whether Langfuse may be called now."""
        return time.monotonic() >= cls.until

    @classmethod
    def seen(cls, error: Exception) -> None:
        """Log the failure and pause calls for the configured time."""
        logging.getLogger(__name__).warning("Langfuse unreachable, pausing calls: %s", error)
        cls.until = time.monotonic() + settings().langfuse_pause


def handed(trace: str | None) -> None:
    """Put a handed-off case's trace in the queue for a person to label; tracing never fails a case."""
    if not Outage.up():
        return
    try:
        lf, queued = langfuse(), queue()
        if lf is not None and trace is not None and queued:
            lf.api.annotation_queues.create_queue_item(queued, object_id=trace, object_type="TRACE")
    except (httpx.HTTPError, ApiError) as error:
        Outage.seen(error)


def link(trace: str | None) -> str | None:
    """The trace's page in Langfuse, or None when Langfuse is off or unreachable."""
    lf = langfuse()
    if lf is None or not trace or not Outage.up():
        return None
    try:
        return lf.get_trace_url(trace_id=trace)
    except (httpx.HTTPError, ApiError) as error:
        Outage.seen(error)
        return None


def keys() -> None:
    """Write fresh local keys and secrets for the self-hosted Langfuse once; never overwrite them."""
    path = ROOT / "langfuse.env"
    if path.exists():
        print(f"{path.name} already exists")
        return
    public, secret = f"pk-lf-{secrets.token_hex(16)}", f"sk-lf-{secrets.token_hex(16)}"
    values = {
        "LANGFUSE_PUBLIC_KEY": public,
        "LANGFUSE_SECRET_KEY": secret,
        "LANGFUSE_INIT_PROJECT_PUBLIC_KEY": public,
        "LANGFUSE_INIT_PROJECT_SECRET_KEY": secret,
        "LANGFUSE_INIT_USER_PASSWORD": secrets.token_urlsafe(12),
        "NEXTAUTH_SECRET": secrets.token_hex(32),
        "SALT": secrets.token_hex(32),
        "ENCRYPTION_KEY": secrets.token_hex(32),
    }
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    print(f"wrote {path.name}; sign in as reviewer@case-desk.local with LANGFUSE_INIT_USER_PASSWORD from it")


if __name__ == "__main__":
    keys()

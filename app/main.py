"""HTTP API and the helpdesk page."""

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agents import openai
from app.config import ROOT, settings
from app.desk import Case, Desk, Refused, load
from app.observe import langfuse
from app.progress import Progress
from app.store import Store
from app.systems import FAULTS

System = Literal["leave", "org", "documents"]
RUNNING: set[asyncio.Task[Case]] = set()


class NewCase(BaseModel):
    """A request as the employee submits it, with an id the client reuses when it retries."""

    employee: str
    text: str
    request: str


class Review(BaseModel):
    """A reviewer's answer, naming the action key they were shown."""

    reviewer: str
    approve: bool
    key: str
    note: str = ""


class Faults(BaseModel):
    """Systems currently made to hang, for the failure drill."""

    systems: list[System]


class Person(BaseModel):
    """An employee the page can submit a case as."""

    name: str
    title: str


class Directory(BaseModel):
    """A tenant as the page lists it."""

    name: str
    people: dict[str, Person]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the store and the model once, and load every tenant."""
    store = await Store.open(settings().database)
    app.state.desk = Desk(load(settings().data), store, openai())
    yield
    await store.close()
    if lf := langfuse():
        lf.flush()


app = FastAPI(title="Agentic case resolution", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=ROOT / "web" / "assets"), name="assets")


def desk(request: Request) -> Desk:
    """The desk built at startup."""
    return request.app.state.desk


Desked = Annotated[Desk, Depends(desk)]


@app.exception_handler(Refused)
async def refused(request: Request, error: Refused) -> JSONResponse:
    """A refusal is a conflict the caller can read."""
    return JSONResponse({"detail": str(error)}, status_code=409)


@app.get("/")
async def page() -> FileResponse:
    """The helpdesk page, built from `ui/` into `web/`."""
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/tenants", response_model=dict[str, Directory])
async def tenants(desk: Desked) -> dict[str, Directory]:
    """Every tenant with the people who can raise cases, the largest company first."""
    ranked = sorted(desk.tenants.items(), key=lambda item: -len(item[1].systems.records.people))
    return {
        name: Directory(
            name=t.config.name,
            people={k: Person(name=p.name, title=p.title) for k, p in t.systems.records.people.items()},
        )
        for name, t in ranked
    }


@app.post("/tenants/{tenant}/cases", response_model=Case)
async def open_case(tenant: str, body: NewCase, desk: Desked) -> Case:
    """Submit a case and get its decision record."""
    return await desk.open(tenant, body.employee, body.text, body.request)


@app.post("/tenants/{tenant}/cases/stream", response_class=EventSourceResponse)
async def stream_case(tenant: str, body: NewCase, desk: Desked) -> AsyncIterable[ServerSentEvent]:
    """Submit a case and watch it run: a `step` event per step as it starts and ends, then the `case` or a `refused`."""
    progress = Progress()
    task = asyncio.create_task(desk.open(tenant, body.employee, body.text, body.request, progress))
    RUNNING.add(task)
    task.add_done_callback(RUNNING.discard)
    task.add_done_callback(lambda _: progress.queue.put_nowait(None))
    while (step := await progress.queue.get()) is not None:
        yield ServerSentEvent(data=step, event="step")
    try:
        yield ServerSentEvent(data=task.result(), event="case")
    except Refused as error:
        yield ServerSentEvent(data={"detail": str(error)}, event="refused")


@app.get("/tenants/{tenant}/cases", response_model=list[Case])
async def list_cases(tenant: str, desk: Desked) -> list[Case]:
    """A tenant's cases, newest first."""
    return await desk.cases(tenant)


@app.get("/tenants/{tenant}/cases/{case}", response_model=Case)
async def get_case(tenant: str, case: str, desk: Desked) -> Case:
    """One case with its record and later events."""
    return await desk.case(tenant, case)


@app.post("/tenants/{tenant}/cases/{case}/review", response_model=Case)
async def review(tenant: str, case: str, body: Review, desk: Desked) -> Case:
    """Approve or reject the action a case is waiting on."""
    return await desk.review(tenant, case, body.reviewer, body.approve, body.key, body.note)


@app.get("/faults", response_model=Faults)
async def faults() -> Faults:
    """Which systems are hanging."""
    return Faults(systems=sorted(FAULTS))


@app.put("/faults", response_model=Faults)
async def set_faults(body: Faults) -> Faults:
    """Make systems hang, or recover them, for the failure drill."""
    FAULTS.clear()
    FAULTS.update(body.systems)
    return Faults(systems=sorted(FAULTS))

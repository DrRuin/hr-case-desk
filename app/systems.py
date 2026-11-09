"""Mocked HR systems per tenant (Leave Balance, Org Hierarchy, Document Repository) and a fail-safe way to call them."""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel
from pydantic_core import to_json

from app.config import settings
from app.ledger import Event
from app.progress import step

FAULTS: set[str] = set()


class Person(BaseModel):
    """An employee as the Org Hierarchy Service and the HR record see them."""

    name: str
    title: str
    role: str
    status: Literal["active", "exited"]
    joined: date
    manager: str | None = None
    hrbp: str | None = None


class Records(BaseModel):
    """One tenant's mock data."""

    people: dict[str, Person]
    ledger: dict[str, list[Event]]
    templates: dict[str, str]


NAMES = {"leave": "Leave Balance Service", "org": "Org Hierarchy Service", "documents": "Document Repository"}


class Snapshot(BaseModel):
    """What one call to an HR system returned, for the decision record."""

    system: str
    subject: str
    status: Literal["ok", "absent", "unavailable"]
    attempts: int
    at: datetime
    digest: str | None = None
    error: str | None = None


class Systems:
    """The three HR systems of one tenant; `FAULTS` makes one hang for the failure drill."""

    def __init__(self, records: Records) -> None:
        """Serve this tenant's records only."""
        self.records = records
        self.letters: dict[str, str] = {}

    async def stall(self, system: str) -> None:
        """Hang past every timeout when the system is marked faulty."""
        if system in FAULTS:
            await asyncio.sleep(settings().fault_delay)

    async def leave(self, employee: str) -> list[Event]:
        """Leave Balance Service: the employee's ledger events."""
        await self.stall("leave")
        return self.records.ledger[employee]

    async def person(self, employee: str) -> Person:
        """Org Hierarchy Service: role, status, manager and HR business partner."""
        await self.stall("org")
        return self.records.people[employee]

    async def letter(self, employee: str, kind: str, key: str) -> str:
        """Document Repository: generate a templated letter once per idempotency key."""
        await self.stall("documents")
        if kind not in self.records.templates or employee not in self.records.people:
            raise KeyError(kind)
        return self.letters.setdefault(key, f"DOC-{kind.upper()}-{len(self.letters) + 1:04d}")


async def fetch[T](system: str, subject: str, call: Callable[[], Awaitable[T]]) -> tuple[Snapshot, T | None]:
    """Call a system with a timeout, retry only timeouts, and tell a missing record apart from a system that failed."""
    error, status, name = "", "unavailable", NAMES[system]
    shown = step("systems", f"Asking the {name}", state="running", subject=subject)
    for attempt in range(1, settings().retries + 2):
        try:
            value = await asyncio.wait_for(call(), settings().timeout)
        except TimeoutError:
            error = f"timed out after {settings().timeout:g} s"
            step("systems", f"The {name} is slow, asking again", error, "retry", shown, subject)
            continue
        except KeyError as missing:
            error, status = f"no record {missing}", "absent"
            break
        digest = hashlib.sha256(to_json(value)).hexdigest()[:16]
        tries = f"on attempt {attempt}" if attempt > 1 else ""
        step("systems", f"The {name} answered", tries, id=shown, subject=subject)
        return Snapshot(
            system=system,
            subject=subject,
            status="ok",
            attempts=attempt,
            at=datetime.now(UTC),
            digest=digest,
        ), value
    said = "has no record" if status == "absent" else f"did not answer after {attempt} attempt(s)"
    step("systems", f"The {name} {said}", error, "failed", shown, subject)
    return Snapshot(
        system=system,
        subject=subject,
        status=status,
        attempts=attempt,
        at=datetime.now(UTC),
        error=error,
    ), None

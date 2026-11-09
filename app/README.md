# app

The desk itself: a FastAPI service on Pydantic AI.

## Modules

```mermaid
flowchart TD
    main[main.py<br/>API and live stream] --> desk[desk.py<br/>case flow]
    desk --> agents[agents.py<br/>model steps]
    desk --> systems[systems.py<br/>mocked HR systems]
    desk --> ledger[ledger.py<br/>balance arithmetic]
    desk --> policy[policy.py<br/>decision tables]
    desk --> store[store.py<br/>case log]
    desk --> observe[observe.py<br/>Langfuse]
    ledger --> trace[trace.py<br/>figures with sources]
    desk --> progress[progress.py<br/>live steps]
```

| File | Job |
|---|---|
| `main.py` | Routes, the server sent event stream, serves the built page |
| `desk.py` | Runs a case: read, check, fetch, decide, act, write, audit, record |
| `agents.py` | The five model steps: reader, second reading, reply writer, handover note writer, auditor |
| `policy.py` | Loads each decision table, refuses one with a gap or overlap, picks the rule and explains it |
| `ledger.py` | Balance from ledger events, double bookings, the smallest set of events that explains a claim |
| `trace.py` | Numbers that carry the ids of the records they came from |
| `systems.py` | Leave Balance, Org Hierarchy and Document Repository mocks with timeout and retry |
| `store.py` | Append only case log, scoped to one company |
| `progress.py` | Steps of a running case for the stream and the record |
| `observe.py` | Langfuse traces, scores and the handover review queue |
| `config.py` | Settings |
| `synth.py` | Generates a company's people and ledger, see [data](../data/README.md) |
| `casebook.py` | Builds the evaluation set, see [data](../data/README.md) |
| `evals.py` | Runs the evaluation as a Langfuse experiment |

## One case

```mermaid
sequenceDiagram
    participant Page
    participant Desk as desk.py
    participant Model as agents.py
    participant HR as systems.py
    participant Table as policy.py
    Page->>Desk: POST /tenants/{t}/cases/stream
    Desk->>Model: read the request into the company's form
    Desk->>Model: second reading checks each claim
    Desk->>HR: ledger or org record, 1 s timeout, one retry
    Desk->>Desk: compute balance and explanations
    Desk->>Table: facts in, exactly one rule out
    alt answer
        Desk->>HR: issue the letter once per key
    else approve or escalate
        Desk->>HR: find the named person in the org tree
        Desk->>Model: write the note to that person
    end
    Desk->>Model: write the reply from placeholders
    Desk->>Model: auditor checks every sentence
    Desk-->>Page: a step event as each step starts and ends
    Desk-->>Page: the case with its decision record
```

## API

| Route | What it does |
|---|---|
| `GET /tenants` | Companies and their people |
| `POST /tenants/{t}/cases` | Open a case, get the decision record |
| `POST /tenants/{t}/cases/stream` | Same, with live steps |
| `GET /tenants/{t}/cases` | Cases, newest first |
| `GET /tenants/{t}/cases/{id}` | One case |
| `POST /tenants/{t}/cases/{id}/review` | Approve or reject the exact action shown |
| `GET`, `PUT /faults` | Which HR systems hang, for the failure drill |

## Settings

Read from the environment or `.env`.

| Setting | Default | What it does |
|---|---|---|
| `OPENAI_API_KEY` | none | Key for the model steps |
| `MODEL` | `gpt-6-luna` | Model for every step |
| `OUTPUT_RETRIES` | 2 | Times a model may fix an output the checks reject |
| `TIMEOUT` | 1.0 | Seconds an HR system call may take |
| `RETRIES` | 1 | Extra attempts after a timeout |
| `FAULT_DELAY` | 5.0 | Seconds a system hangs in the drill |
| `DATA` | `data/` | One folder per company |
| `DATABASE` | `cases.sqlite` | Case log |
| `LANGFUSE_URL` | `http://127.0.0.1:3000` | Langfuse server |
| `LANGFUSE_PAUSE` | 60 | Seconds to skip Langfuse after it fails, so a case never waits on it |
| `CONFIDENCE` | 0.95 | Confidence of the evaluation's error bounds |
| `EVAL_CONCURRENCY` | 4 | Evaluation cases run at once |

## Langfuse

Optional. Each case becomes one trace with its model calls, scores and a review queue for handovers.

```bash
uv run python -m app.observe      # writes langfuse.env with generated keys, once
docker compose up -d              # Langfuse on http://127.0.0.1:3000
```

Sign in as `reviewer@case-desk.local` with `LANGFUSE_INIT_USER_PASSWORD` from `langfuse.env`. Run the evaluation with `uv run python -m app.evals`.

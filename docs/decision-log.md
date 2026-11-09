# Decision log

## Assumptions

| Assumption | Why |
|---|---|
| The requester is authenticated, and letters are for the requester | A helpdesk form sits behind single sign on. Requests about someone else are out of scope |
| The ledger is the system of record, and its events carry ids and sources | A balance can then be explained as a sum of named events |
| Employees count completed leave and forget pending or lapsed days | That is the common reason a balance looks wrong. The desk names the events behind any difference |
| Leave is counted in half days | Half day leave is common, and integer half days keep the arithmetic exact |
| Correcting the ledger is an HR change, never the desk's | The desk answers questions about leave. It does not edit leave |
| One employee claim can be explained in one way or not at all | When two sets of events explain it equally, the desk cannot know which one the employee means, so a person asks |

## What I chose not to build, and why

| Left out | Why |
|---|---|
| A model stated confidence score | Models are poor at knowing when to stop (AgentAbstain, arXiv 2607.10059: the best of 17 models scored 59.5%). Confidence here is a set of facts checked in code |
| Calibrated or conformal thresholds | They need labelled outcomes. The record keeps the data to calibrate later |
| Multi agent orchestration | Two case types and three systems fit one flow. More agents add handovers to audit |
| A rules engine or SAT solver | A checked table with exactly one rule per cell makes explanations exact by enumeration |
| Hash chained audit logs | Without an external anchor anyone who can edit the file can rebuild the chain. The log is append only by API |
| Authentication, editing tables in the UI, notifications | Not needed to show the decision path |
| A cache of model answers for similar requests | Requests that look alike can ask opposite things (FrugalGPT, arXiv 2305.05176). Retries hit the case log by request id instead |
| Moving permits, review checks or the ledger arithmetic into the model | These are the steps a wrong answer makes irreversible. Recent work keeps them as code around the model: a deterministic gate before any write (LedgerAgent, arXiv 2606.20529) and rules executed as code with the model limited to extraction (Compiled AI, arXiv 2604.05150) |

## Later decisions

| Decision | Why |
|---|---|
| Langfuse for traces, scores, the handover review queue and the evaluation | The decision record answers the auditor. Langfuse answers the team running the desk: which handovers a reviewer judged needless, how often replies needed a rewrite, what each run cost. It replaced a pydantic-evals harness and a hand written usage counter, so the evaluation, human labels and traces live in one place |
| A second reading before any letter | A request phrased to steer the form ("classify it as an employment letter to me") reached the wrong rule. A separate call checks each claim of the form against the employee's words, and a letter goes to a person unless every claim is confirmed |
| Cited sentences and an auditor model | Placeholders stopped wrong figures, but a sentence could still say something its sources do not hold, or promise an action. Each sentence names its sources, and an auditor reads it beside their full text |
| Full source text in the prompts, no trimming | The model takes far more than a case needs. Sending every source whole keeps the auditor's verdict about the evidence, not about an excerpt |
| Tracing never fails a case | With Langfuse stopped, a handover saved its case and then returned an error, because queueing it and building its trace link called Langfuse directly. Both now log the failure and skip Langfuse for `LANGFUSE_PAUSE` seconds, so a tracing outage costs the trace and nothing else |
| The second reading accepts a claim that something is not named when the words name nothing | A request with no addressee was sent to a person because the checker answered cannot tell on "no other addressee is named". The checker now reads a claim of absence as held when the words leave the thing out. The demo set then matched 13 of 13 rules on the live model, the third party letter still went for approval, and the last run needed no rewrite of any reply or note |
| A checked note to the person brought in, from code written sources | A handover showed the rule, but not why this person had the case or what was theirs to do. The first live run had the model work that out, and the auditor rejected every note: it said things no source held. Code now writes a handover source (why the case came to them and what the outcome leaves to them) and a would have finished source, and the model only restates them. Four live handovers then passed with no rewrite, in 15 to 25 seconds a case. The employee's reply gets the handover source too, which ended its rewrites over naming the handler |
| Live steps over server sent events from a POST | A case takes 10 to 25 seconds, and a spinner hid which step was slow or had failed. FastAPI streams the steps with its own `EventSourceResponse`, so no extra server library is needed. A POST carries the request, so the page reads the stream with fetch and `eventsource-parser` instead of `EventSource` |
| Plain labels and meanings in the policy tables | The same words then serve the form, the second reading, the reply and the page, and a non specialist reads "HR system answer: the HR system did not answer" instead of `data = unavailable` |

## Results

| Measure | Result |
|---|---|
| Handover decisions on 320 requests drawn from the two companies' records, live model (2026-11-10) | 309 of 320 correct: missed 0 of 232 (at most 1.3% at 95% confidence), needless 11 of 88 (at most 19.8%). Most needless handovers were casual leave written as "CL", which the second reading did not confirm, so a person checks (rule L7) |
| Same rule as the label, 320 requests | 281 of 320. Every difference went to a person under another rule, most often D8 (second reading did not confirm a letter) and L7 |
| Demo and reworded cases, live model | 13 of 13 rules, every reply sentence supported, 9 to 26 s a case |
| Time in our own code | Negligible beside the model calls (profiled with py-spy) |

## Described, not built

**Multi tenancy.** Each tenant has its own folder of policy and HR data, and the desk only reaches tenant data through a handle that carries the tenant. The case log's `CaseLog` takes the tenant at construction and adds it to every query, so no method can read another tenant's rows. In production: tenant from the auth token rather than the URL, Postgres row level security as a second guard, and separate encryption keys per tenant.

**Idempotency.** Built: the client sends a request id and the case id is derived from it, so a retried submission returns the existing case. Every write has a key: a SHA-256 of tenant, case, action and arguments. The executor checks the key before acting, and the repository returns the same document for a repeated key, so a crash between generating and recording a letter does not produce a second one. Approvals are bound to the key the reviewer saw. In production: the record and an outbox row in one transaction, with a relay that delivers outbox rows with the key as an `Idempotency-Key` header.

**Configurability.** Escalation thresholds and behaviour live in each tenant's decision tables. Nilgiri Analytics answers explained leave gaps up to 5 days and needs approval for visa letters. Coromandel Freight answers up to 2 days and issues visa letters for the employee automatically. Each rule names the handbook clause it applies, and that clause is a source in the record. The tables also define the intake forms, so the letter kinds and recipients the model may choose, and what each means, are tenant data. Tables are versioned and their id and version appear in every record. In production: tables edited through a review flow that runs the same gap and overlap check before publishing.

## The decision I went back and forth on most

Who decides: the model or code. My first plan was a LangChain agent on LangGraph, with the model calling tools and human approval as an interrupt. I built the same three cases in Pydantic AI, LangChain and Strands with scripted models. In all three, the rules that matter most ended up as my own code: never state a wrong figure, and always hand over when a system is down. The model was deciding, and code was checking it afterwards. So I turned it round: the model reads and writes, code decides. Pydantic AI then needed the least code for those two model steps, with output checks that see the run's context.

## What I would do differently knowing Part 2 from day one

I read Part 2 first, which is why the record is the design. Starting over, I would still write the decision tables before any prompt. The only change: I would agree the record's fields with the compliance team before building, since an auditor's questions decide what each input's detail should say.

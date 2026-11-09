import { EventSourceParserStream } from "eventsource-parser/stream"

export type Status =
  "resolved" | "awaiting_approval" | "escalated" | "rejected" | "failed"

export type Fact = { value: string; detail: string; sources: string[] }

export type Snapshot = {
  system: string
  subject: string
  status: "ok" | "absent" | "unavailable"
  attempts: number
  at: string
  digest: string | null
  error: string | null
}

export type Verdict = {
  table: string
  rule: string
  says: string
  outcome: "resolve" | "approve" | "escalate"
  because: Record<string, string>
  resolve_if: Record<string, string> | null
}

export type SourceKind =
  "request" | "policy" | "ledger" | "org" | "document" | "check" | "system"

export type Source = {
  id: string
  kind: SourceKind
  title: string
  text: string
}

export type Statement = {
  text: string
  cites: string[]
  verdict: "supported" | "contradicted" | "unsupported"
  reason: string
}

export type Step = {
  id: number
  stage: "read" | "check" | "systems" | "policy" | "action" | "route" | "reply"
  state: "running" | "done" | "retry" | "failed"
  title: string
  detail: string
  subject: string | null
  began: string
  at: string
  seen?: number
}

export type CaseRecord = {
  case: string
  tenant: string
  employee: string
  text: string
  at: string
  intake: ({ summary: string } & Record<string, unknown>) | null
  snapshots: Snapshot[]
  inputs: Record<string, Fact>
  verdict: Verdict
  route: string | null
  action: { employee: string; kind: string; key: string } | null
  figures: Record<string, { value: string; sources: string[] }>
  sources: Record<string, Source>
  why: string[]
  would_resolve: string[]
  reply: Statement[]
  handover: Statement[]
  steps: Step[]
  message: string
  cited: string
  handover_cited: string
  trace: string | null
}

export type CaseEvent = {
  kind: string
  at: string
  by?: string
  rule?: string
  document?: string | null
  note?: string
}

export type Case = {
  record: CaseRecord
  events: CaseEvent[]
  status: Status
  trace_url: string | null
}

export type Person = { name: string; title: string }

export type Directory = Record<
  string,
  { name: string; people: Record<string, Person> }
>

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json" },
  })
  const body = await response.json()
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string" ? body.detail : response.statusText
    )
  return body as T
}

export async function stream(
  path: string,
  body: unknown,
  onStep: (step: Step) => void
): Promise<Case> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!response.ok || !response.body) throw new Error(response.statusText)
  const events = response.body
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(new EventSourceParserStream())
  for await (const event of events) {
    const data = JSON.parse(event.data)
    if (event.event === "step") onStep(data as Step)
    else if (event.event === "case") return data as Case
    else throw new Error(data.detail)
  }
  throw new Error("The desk stopped before the case was finished")
}

export const words = (s: string) => s.replaceAll("_", " ")

export const initials = (name: string) =>
  name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)

export function ago(at: string) {
  const s = Math.max(
    1,
    Math.round((Date.now() - new Date(at).getTime()) / 1000)
  )
  if (s < 60) return "just now"
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return new Date(at).toLocaleDateString()
}

export type View = "overview" | "all" | "resolved" | "waiting" | "person"

export const VIEWS: {
  key: Exclude<View, "overview">
  label: string
  status: Status[] | null
}[] = [
  { key: "all", label: "All cases", status: null },
  { key: "resolved", label: "Answered", status: ["resolved"] },
  {
    key: "waiting",
    label: "Waiting for approval",
    status: ["awaiting_approval"],
  },
  {
    key: "person",
    label: "With a person",
    status: ["escalated", "failed", "rejected"],
  },
]

export const within = (view: View, cases: Case[]) => {
  const status = VIEWS.find((v) => v.key === view)?.status
  return status ? cases.filter((c) => status.includes(c.status)) : cases
}

export const handler = (r: CaseRecord, people: Record<string, Person>) =>
  r.figures.handler?.value ??
  (r.route ? (people[r.route]?.name ?? r.route) : "")

import { useEffect, useMemo, useRef, useState } from "react"
import Markdown from "react-markdown"
import { AnimatePresence, motion } from "motion/react"
import {
  ArrowRight,
  CalendarDays,
  Check,
  CircleAlert,
  CircleCheck,
  CircleX,
  FileCheck2,
  type LucideIcon,
  MessageSquareQuote,
  Route,
  Scale,
  ScanEye,
  ServerCrash,
  ShieldCheck,
  Sparkles,
  TableProperties,
  UserRound,
  UserRoundCheck,
  UsersRound,
  X,
} from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  api,
  ago,
  initials,
  words,
  type Case,
  type CaseRecord,
  type Person,
  type SourceKind,
} from "@/api"
import { Journey, SYSTEMS } from "@/journey"
import { Steps } from "@/live"
import { StatusPill } from "@/status"
import { cn } from "cn"

const KIND: Record<SourceKind, { icon: LucideIcon; label: string }> = {
  request: { icon: MessageSquareQuote, label: "Employee's words" },
  policy: { icon: Scale, label: "Policy rule" },
  ledger: { icon: CalendarDays, label: "Leave ledger" },
  org: { icon: UserRound, label: "HR record" },
  document: { icon: FileCheck2, label: "Document" },
  check: { icon: ScanEye, label: "Second reading" },
  system: { icon: ServerCrash, label: "System status" },
}

const EASE = [0.22, 1, 0.36, 1] as const

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="mr-1 inline-block rounded-md bg-muted px-1.5 py-0.5 font-mono text-[0.72rem] text-navy">
      {children}
    </code>
  )
}

function Outcome({
  item,
  people,
}: {
  item: Case
  people: Record<string, Person>
}) {
  const r = item.record
  const who =
    r.figures.handler?.value ??
    (r.route ? (people[r.route]?.name ?? r.route) : "")
  const look = {
    resolved: [
      "border-mint/20 bg-mint/[0.04]",
      "bg-mint",
      ShieldCheck,
      "Answered by the desk",
    ],
    awaiting_approval: [
      "border-amber/20 bg-amber/[0.04]",
      "bg-amber",
      UserRoundCheck,
      `Waiting for ${who} to approve`,
    ],
    escalated: [
      "border-coral/20 bg-coral/[0.04]",
      "bg-coral",
      UserRound,
      `Handed to ${who}`,
    ],
    rejected: [
      "border-border bg-muted/60",
      "bg-muted-foreground",
      X,
      `Rejected by ${who}`,
    ],
    failed: [
      "border-coral/20 bg-coral/[0.04]",
      "bg-coral",
      CircleAlert,
      "The action did not complete",
    ],
  } as const
  const approved = item.events.find(
    (e) => e.kind === "approved" && e.by !== "policy"
  )
  const issued = item.events.find((e) => e.kind === "executed")?.document
  const [box, badge, Icon, plain] = look[item.status]
  const title =
    approved && item.status === "resolved"
      ? `Approved by ${people[approved.by!]?.name ?? approved.by}${issued ? `, ${issued} issued` : ""}`
      : plain
  const next = {
    resolved: issued
      ? `Done. ${issued} is ready for the employee.`
      : "Done. The employee has the answer.",
    awaiting_approval: `Next: ${who} approves or rejects below. Nothing is issued until then.`,
    escalated: `Next: ${who} picks this up with the evidence the desk gathered.`,
    rejected: "Done. Nothing was issued.",
    failed: `Next: ${who} follows up. Nothing was issued.`,
  }[item.status]
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: EASE }}
      className={cn(
        "flex flex-wrap items-start gap-4 rounded-2xl border p-5",
        box
      )}
    >
      <motion.div
        initial={{ scale: 0.4, rotate: -25 }}
        animate={{ scale: 1, rotate: 0 }}
        transition={{ type: "spring", stiffness: 380, damping: 16, delay: 0.1 }}
        className={cn(
          "grid size-11 shrink-0 place-items-center rounded-xl text-white shadow-sm",
          badge
        )}
      >
        <Icon className="size-5" />
      </motion.div>
      <div className="min-w-48 flex-1">
        <h2 className="text-lg font-semibold text-navy">{title}</h2>
        <p className="mt-0.5 text-[0.95rem] text-foreground/80">
          {r.verdict.says}
        </p>
        <p className="mt-2 flex items-start gap-1.5 text-sm font-medium text-navy">
          <ArrowRight className="mt-0.5 size-4 shrink-0" /> {next}
        </p>
      </div>
    </motion.div>
  )
}

function SourceRow({
  r,
  id,
  n,
  active,
  pick,
  bind,
}: {
  r: CaseRecord
  id: string
  n: number | null
  active: boolean
  pick: (id: string) => void
  bind?: (id: string, el: HTMLButtonElement | null) => void
}) {
  const s = r.sources[id]
  const { icon: Icon, label } = KIND[s.kind]
  const [first, ...more] =
    s.kind === "check" ? ["", ...s.text.split("; ")] : s.text.split("; ")
  return (
    <button
      ref={(el) => bind?.(id, el)}
      onClick={() => pick(id)}
      className={cn(
        "-mx-2 flex w-[calc(100%+1rem)] gap-3 rounded-xl px-2 py-3 text-left transition-colors duration-150",
        active ? "glow bg-blue/[0.07] ring-1 ring-blue/40" : "hover:bg-muted/70"
      )}
    >
      <span
        className={cn(
          "grid size-6 shrink-0 place-items-center rounded-md text-[0.7rem] font-semibold",
          n ? "bg-blue/12 text-blue" : "bg-muted text-muted-foreground"
        )}
      >
        {n ?? <Icon className="size-3.5" />}
      </span>
      <span className="min-w-0">
        <span className="flex items-center gap-1.5 text-[0.7rem] font-medium tracking-wide text-muted-foreground uppercase">
          <Icon className="size-3" /> {label}
        </span>
        <span className="mt-0.5 block text-sm font-medium text-navy">
          {s.title}
        </span>
        {first && (
          <span className="mt-0.5 block text-sm text-muted-foreground">
            {first}
          </span>
        )}
        {more.length > 0 && (
          <span className="mt-1.5 block space-y-1">
            {more.map((line) => (
              <span
                key={line}
                className="flex gap-1.5 text-[0.8rem] text-muted-foreground"
              >
                <span className="mt-[0.45rem] size-1 shrink-0 rounded-full bg-muted-foreground/60" />{" "}
                {line}
              </span>
            ))}
          </span>
        )}
      </span>
    </button>
  )
}

function Cited({
  r,
  markdown,
  order,
  active,
  pick,
  more,
  className,
}: {
  r: CaseRecord
  markdown: string
  order: string[]
  active: string | null
  pick: (id: string) => void
  more?: () => void
  className: string
}) {
  return (
    <>
      <div className={className}>
        <Markdown
          allowedElements={["p", "a", "em", "strong"]}
          unwrapDisallowed
          components={{
            a: ({ href }) => {
              const id = decodeURIComponent((href ?? "").slice(1))
              const s = r.sources[id]
              return (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      className="cite"
                      data-active={active === id}
                      aria-label={`Source ${order.indexOf(id) + 1}: ${s?.title}`}
                      onClick={() => pick(id)}
                    >
                      {order.indexOf(id) + 1}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent
                    side="top"
                    className="block max-w-80 px-3 py-2 font-sans"
                  >
                    <span className="block text-[0.65rem] tracking-wide text-background/60 uppercase">
                      {s && KIND[s.kind].label}
                    </span>
                    <span className="block font-medium">{s?.title}</span>
                    <span className="mt-0.5 block text-background/80">
                      {s?.text.split("; ")[0]}
                    </span>
                  </TooltipContent>
                </Tooltip>
              )
            },
          }}
        >
          {markdown}
        </Markdown>
      </div>
      <AnimatePresence initial={false} mode="wait">
        {active && order.includes(active) ? (
          <motion.div
            key={active}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.22, ease: EASE }}
            className="overflow-hidden"
          >
            <div className="mt-4 rounded-2xl border bg-background/60 px-4 py-1">
              <SourceRow
                r={r}
                id={active}
                n={order.indexOf(active) + 1}
                active={false}
                pick={pick}
              />
            </div>
            {more && (
              <button
                onClick={more}
                className="mt-2 text-sm font-medium text-blue hover:underline"
              >
                See all {Object.keys(r.sources).length} sources
              </button>
            )}
          </motion.div>
        ) : (
          more && (
            <motion.p
              key="hint"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="mt-4 text-sm text-muted-foreground"
            >
              Each number is a source. Point at it to preview, click to open it
              here.
            </motion.p>
          )
        )}
      </AnimatePresence>
    </>
  )
}

function Reply({
  r,
  name,
  order,
  active,
  pick,
  more,
}: {
  r: CaseRecord
  name: string
  order: string[]
  active: string | null
  pick: (id: string) => void
  more: () => void
}) {
  return (
    <div>
      <p className="text-sm font-medium text-muted-foreground">
        Reply to {name.split(" ")[0]}
      </p>
      <Cited
        r={r}
        markdown={r.cited}
        order={order}
        active={active}
        pick={pick}
        more={more}
        className="mt-2 font-serif text-[1.25rem] leading-relaxed text-navy"
      />
    </div>
  )
}

function Handover({
  r,
  people,
}: {
  r: CaseRecord
  people: Record<string, Person>
}) {
  const [active, setActive] = useState<string | null>(null)
  const order = useMemo(
    () => [...new Set(r.handover.flatMap((s) => s.cites))],
    [r]
  )
  const person = r.route ? people[r.route] : undefined
  const who = r.figures.handler?.value ?? r.route ?? ""
  return (
    <motion.section
      aria-label="Why a person was brought in"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.1, ease: EASE }}
      className="rounded-2xl bg-white p-5 shadow-[0_1px_2px_rgba(16,24,40,0.05)] ring-1 ring-black/[0.06]"
    >
      <div className="flex items-center gap-3">
        <Avatar className="size-9">
          <AvatarFallback className="bg-navy text-xs font-semibold text-white">
            {person ? initials(person.name) : <UsersRound className="size-4" />}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <h2 className="font-heading font-semibold text-navy">
            {person
              ? `Why ${person.name.split(" ")[0]} was brought in`
              : `Why this case went to ${who}`}
          </h2>
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Sparkles className="size-3.5 shrink-0 text-violet" />
            Written by the desk's AI, each sentence checked against its sources
          </p>
        </div>
      </div>
      <Cited
        r={r}
        markdown={r.handover_cited}
        order={order}
        active={active}
        pick={(id) => setActive((now) => (now === id ? null : id))}
        className="mt-4 text-[0.98rem] leading-relaxed text-foreground/90"
      />
    </motion.section>
  )
}

function Evidence({
  r,
  order,
  active,
  pick,
}: {
  r: CaseRecord
  order: string[]
  active: string | null
  pick: (id: string) => void
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})
  useEffect(() => {
    if (active)
      refs.current[active]?.scrollIntoView({
        block: "nearest",
        behavior: "smooth",
      })
  }, [active])
  const rest = Object.keys(r.sources).filter((id) => !order.includes(id))
  const bind = (id: string, el: HTMLButtonElement | null) => {
    refs.current[id] = el
  }
  return (
    <div>
      <p className="text-sm text-muted-foreground">
        What the reply rests on, from the employee's own words to the HR
        systems.
      </p>
      <div className="mt-3 divide-y divide-border/70">
        {order.map((id, i) => (
          <SourceRow
            key={id}
            r={r}
            id={id}
            n={i + 1}
            active={active === id}
            pick={pick}
            bind={bind}
          />
        ))}
      </div>
      {rest.length > 0 && (
        <p className="mt-5 mb-1 text-xs font-medium tracking-wider text-muted-foreground uppercase">
          Also consulted
        </p>
      )}
      <div className="divide-y divide-border/70">
        {rest.map((id) => (
          <SourceRow
            key={id}
            r={r}
            id={id}
            n={null}
            active={active === id}
            pick={pick}
            bind={bind}
          />
        ))}
      </div>
    </div>
  )
}

function Review({
  item,
  tenant,
  name,
  onDone,
}: {
  item: Case
  tenant: string
  name: string
  onDone: (c: Case) => void
}) {
  const r = item.record
  const [note, setNote] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const decide = (approve: boolean) => {
    setBusy(true)
    api<Case>(`/tenants/${tenant}/cases/${r.case}/review`, {
      method: "POST",
      body: JSON.stringify({
        reviewer: r.route,
        approve,
        key: r.action!.key,
        note,
      }),
    })
      .then(onDone)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.15, ease: EASE }}
      className="rounded-2xl border border-amber/40 bg-amber/[0.04] p-5"
    >
      <p className="font-heading font-semibold text-navy">
        Your approval, {r.figures.handler?.value ?? r.route}
      </p>
      <p className="mt-0.5 text-sm text-muted-foreground">
        Approving issues exactly this {words(r.action!.kind)} letter for {name},
        once. Approval key <Code>{r.action!.key.slice(0, 12)}</Code>
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1 space-y-1.5">
          <Label htmlFor="note">Note for the record</Label>
          <Input
            id="note"
            value={note}
            placeholder="Optional"
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
        <Button disabled={busy} onClick={() => decide(true)}>
          <Check /> Approve and issue
        </Button>
        <Button disabled={busy} variant="outline" onClick={() => decide(false)}>
          Reject
        </Button>
        {error && <p className="w-full text-sm text-destructive">{error}</p>}
      </div>
    </motion.div>
  )
}

const VERDICT = {
  supported: <CircleCheck className="size-4 shrink-0 text-mint" />,
  unsupported: <CircleAlert className="size-4 shrink-0 text-amber" />,
  contradicted: <CircleX className="size-4 shrink-0 text-coral" />,
}

function Record({ item }: { item: Case }) {
  const r = item.record
  return (
    <div className="space-y-7">
      <p className="text-sm text-muted-foreground">
        Everything an auditor needs to repeat the decision: each sentence's
        check, the inputs the policy table read, and every system call.
      </p>
      <section>
        <h3 className="mb-2 text-sm font-semibold text-navy">
          Each sentence of the reply, checked
        </h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Sentence</TableHead>
              <TableHead>Cites</TableHead>
              <TableHead>Check</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {r.reply.map((s, i) => (
              <TableRow key={i}>
                <TableCell className="whitespace-normal">{s.text}</TableCell>
                <TableCell className="whitespace-normal">
                  {s.cites.map((c) => (
                    <Code key={c}>{c}</Code>
                  ))}
                </TableCell>
                <TableCell className="whitespace-normal">
                  <span className="flex items-start gap-1.5">
                    {VERDICT[s.verdict]}{" "}
                    <span className="text-muted-foreground">{s.reason}</span>
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
      <section>
        <h3 className="mb-2 text-sm font-semibold text-navy">
          Inputs the decision table read
        </h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Input</TableHead>
              <TableHead>Value</TableHead>
              <TableHead>Detail</TableHead>
              <TableHead>Sources</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Object.entries(r.inputs).map(([k, f]) => (
              <TableRow
                key={k}
                className={
                  k in r.verdict.because ? "bg-blue/[0.04]" : undefined
                }
              >
                <TableCell className="font-medium">{words(k)}</TableCell>
                <TableCell>
                  <Code>{f.value}</Code>
                </TableCell>
                <TableCell className="whitespace-normal text-muted-foreground">
                  {f.detail.split("; ").map((line) => (
                    <p key={line}>{line}</p>
                  ))}
                </TableCell>
                <TableCell className="whitespace-normal">
                  {f.sources.map((s) => (
                    <Code key={s}>{s}</Code>
                  ))}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
      <section>
        <h3 className="mb-2 text-sm font-semibold text-navy">System calls</h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>System</TableHead>
              <TableHead>Result</TableHead>
              <TableHead>Attempts</TableHead>
              <TableHead>Answer digest</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {r.snapshots.map((s, i) => (
              <TableRow key={i}>
                <TableCell>
                  {SYSTEMS[s.system]} · {s.subject}
                </TableCell>
                <TableCell className="whitespace-normal">
                  {s.status === "ok" ? "answered" : `${s.status}: ${s.error}`}
                </TableCell>
                <TableCell>{s.attempts}</TableCell>
                <TableCell>
                  {s.digest ? <Code>{s.digest}</Code> : "none"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
      <p className="text-xs text-muted-foreground">
        Case <Code>{r.case}</Code> · decision table {r.verdict.table} · trace{" "}
        <Code>{r.trace ?? "not traced"}</Code>
      </p>
    </div>
  )
}

const TABS = [
  { key: "reply", label: "The reply", icon: MessageSquareQuote },
  { key: "journey", label: "How it was decided", icon: Route },
  { key: "evidence", label: "Evidence", icon: FileCheck2 },
  { key: "record", label: "Full record", icon: TableProperties },
] as const

type Tab = (typeof TABS)[number]["key"]

function Tabs({
  tab,
  setTab,
  count,
}: {
  tab: Tab
  setTab: (t: Tab) => void
  count: number
}) {
  const move = (e: React.KeyboardEvent, i: number) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0
    if (!d) return
    const next = TABS[(i + d + TABS.length) % TABS.length].key
    setTab(next)
    document.getElementById(`tab-${next}`)?.focus()
  }
  return (
    <div
      role="tablist"
      aria-label="Case detail"
      className="flex [scrollbar-width:none] gap-5 overflow-x-auto border-b"
    >
      {TABS.map((t, i) => (
        <button
          key={t.key}
          id={`tab-${t.key}`}
          role="tab"
          aria-selected={tab === t.key}
          aria-controls="case-panel"
          tabIndex={tab === t.key ? 0 : -1}
          onClick={() => setTab(t.key)}
          onKeyDown={(e) => move(e, i)}
          className={cn(
            "relative flex shrink-0 items-center gap-2 pt-1 pb-2.5 text-sm font-medium transition-colors",
            tab === t.key
              ? "text-navy"
              : "text-muted-foreground hover:text-navy"
          )}
        >
          {tab === t.key && (
            <motion.span
              layoutId="tab-line"
              className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-navy"
              transition={{ type: "spring", stiffness: 420, damping: 34 }}
            />
          )}
          <t.icon className="relative size-4" />
          <span className="relative">{t.label}</span>
          {t.key === "evidence" && (
            <span className="relative rounded-full bg-blue/12 px-1.5 text-[0.7rem] font-semibold text-blue tabular-nums">
              {count}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

export function CaseView({
  item,
  tenant,
  people,
  onChange,
}: {
  item: Case
  tenant: string
  people: Record<string, Person>
  onChange: (c: Case) => void
}) {
  const r = item.record
  const person = people[r.employee] ?? { name: r.employee, title: "" }
  const order = useMemo(
    () => [...new Set(r.reply.flatMap((s) => s.cites))],
    [r]
  )
  const [active, setActive] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>("reply")
  const pick = (id: string) => setActive((now) => (now === id ? null : id))
  return (
    <div className="mx-auto max-w-3xl space-y-6 px-5 py-7 md:px-8">
      <motion.header
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: EASE }}
      >
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <Avatar className="size-6">
            <AvatarFallback className="bg-navy text-[0.6rem] font-semibold text-white">
              {initials(person.name)}
            </AvatarFallback>
          </Avatar>
          <span className="font-medium text-navy">{person.name}</span>
          <span className="text-muted-foreground">{person.title}</span>
          <span className="text-muted-foreground/60">·</span>
          <span className="text-muted-foreground">{ago(r.at)}</span>
        </div>
        <h1 className="mt-3 font-serif text-[1.65rem] leading-snug text-navy">
          “{r.text}”
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <StatusPill status={item.status} />
          <span className="rounded-full px-2 py-0.5 ring-1 ring-border">
            Rule {r.verdict.rule}
          </span>
          {r.intake && (
            <span className="rounded-full px-2 py-0.5 ring-1 ring-border">
              {r.intake.summary}
            </span>
          )}
        </div>
      </motion.header>
      <Outcome item={item} people={people} />
      {r.handover.length > 0 && <Handover r={r} people={people} />}
      {item.status === "awaiting_approval" && (
        <Review
          item={item}
          tenant={tenant}
          name={person.name}
          onDone={onChange}
        />
      )}
      <Tabs tab={tab} setTab={setTab} count={Object.keys(r.sources).length} />
      <div
        id="case-panel"
        role="tabpanel"
        aria-labelledby={`tab-${tab}`}
        className="-mt-1"
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={tab}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -12 }}
            transition={{ duration: 0.18, ease: EASE }}
          >
            {tab === "reply" && (
              <Reply
                r={r}
                name={person.name}
                order={order}
                active={active}
                pick={pick}
                more={() => setTab("evidence")}
              />
            )}
            {tab === "journey" && (
              <>
                <Journey item={item} people={people} />
                {item.record.steps.length > 0 && (
                  <section className="mt-8">
                    <h3 className="mb-1 text-sm font-semibold text-navy">
                      Step by step
                    </h3>
                    <p className="mb-3 text-[0.8rem] text-muted-foreground">
                      Everything the desk did for this case, in order, with how
                      long each step took.
                    </p>
                    <Steps steps={item.record.steps} people={people} />
                  </section>
                )}
              </>
            )}
            {tab === "evidence" && (
              <Evidence r={r} order={order} active={active} pick={pick} />
            )}
            {tab === "record" && <Record item={item} />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  )
}

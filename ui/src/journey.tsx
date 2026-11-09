import { useState } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import {
  ArrowRight,
  Check,
  CircleAlert,
  CircleCheck,
  CircleX,
  Database,
  type LucideIcon,
  MessageSquareQuote,
  RotateCcw,
  Scale,
  ScanEye,
  ShieldCheck,
  UserRound,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { ago, words, type Case, type Person } from "@/api"
import { cn } from "cn"

export const SYSTEMS: Record<string, string> = {
  leave: "Leave Balance Service",
  org: "Org Hierarchy Service",
  documents: "Document Repository",
}

type State = "ok" | "fail" | "warn" | "wait" | "person" | "skip"

type Stage = {
  key: string
  icon: LucideIcon
  name: string
  state: State
  headline: string
  body: React.ReactNode
}

export const PIPELINE: { icon: LucideIcon; name: string; does: string }[] = [
  {
    icon: MessageSquareQuote,
    name: "Read",
    does: "A model turns the message into a form the policy can read",
  },
  {
    icon: ScanEye,
    name: "Second reading",
    does: "An independent model call checks that form against the words",
  },
  {
    icon: Database,
    name: "HR systems",
    does: "Leave ledger, org chart and documents are looked up",
  },
  {
    icon: Scale,
    name: "Policy",
    does: "The company's rule table decides: answer, approve or hand over",
  },
  {
    icon: ShieldCheck,
    name: "Reply check",
    does: "Every sentence is checked against the sources it cites",
  },
  {
    icon: UserRound,
    name: "Outcome",
    does: "Answered, sent for approval, or handed to a person",
  },
]

const LOOK: Record<State, { dot: string; text: string; label: string }> = {
  ok: { dot: "bg-mint text-white", text: "text-mint", label: "Done" },
  fail: {
    dot: "bg-coral text-white",
    text: "text-[#c8352d]",
    label: "Stopped here",
  },
  warn: {
    dot: "bg-amber text-white",
    text: "text-amber",
    label: "Needs a look",
  },
  wait: { dot: "bg-amber text-white", text: "text-amber", label: "Waiting" },
  person: {
    dot: "bg-coral text-white",
    text: "text-[#c8352d]",
    label: "With a person",
  },
  skip: {
    dot: "bg-muted text-muted-foreground ring-1 ring-dashed ring-border",
    text: "text-muted-foreground",
    label: "Skipped",
  },
}

function Lines({ items }: { items: string[] }) {
  return (
    <ul className="mt-3 space-y-2">
      {items.map((line) => (
        <li key={line} className="flex gap-2 text-sm">
          <Check className="mt-0.5 size-4 shrink-0 text-mint" />
          <span>{line}</span>
        </li>
      ))}
    </ul>
  )
}

const VERDICT = {
  supported: <CircleCheck className="mt-0.5 size-4 shrink-0 text-mint" />,
  unsupported: <CircleAlert className="mt-0.5 size-4 shrink-0 text-amber" />,
  contradicted: <CircleX className="mt-0.5 size-4 shrink-0 text-coral" />,
}

function stages(item: Case, people: Record<string, Person>): Stage[] {
  const r = item.record
  const name = (id?: string | null) => (id ? (people[id]?.name ?? id) : "")
  const who = r.figures.handler?.value ?? name(r.route)
  const confirmed = r.inputs.confirmed
  const down = r.snapshots.filter((s) => s.status === "unavailable")
  const absent = r.snapshots.filter((s) => s.status === "absent")
  const held = r.reply.filter((s) => s.verdict === "supported").length
  const outcome: Record<typeof item.status, [State, string]> = {
    resolved: ["ok", "Answered by the desk"],
    awaiting_approval: ["wait", `Waiting for ${who}`],
    escalated: ["person", `Handed to ${who}`],
    rejected: ["skip", `Rejected by ${who}`],
    failed: ["fail", "The action did not complete"],
  }
  return [
    {
      key: "read",
      icon: MessageSquareQuote,
      name: "Read",
      state: r.intake ? "ok" : "fail",
      headline: r.intake
        ? "Understood the request"
        : "Could not read it reliably",
      body: r.intake ? (
        <p className="font-serif text-lg text-navy">{r.intake.summary}</p>
      ) : (
        <p>
          No reading passed the checks, so the case goes to a person instead of
          guessing.
        </p>
      ),
    },
    {
      key: "check",
      icon: ScanEye,
      name: "Second reading",
      state: confirmed ? (confirmed.value === "yes" ? "ok" : "fail") : "skip",
      headline: confirmed
        ? confirmed.value === "yes"
          ? "Agreed with the first"
          : "Disagreed with the first"
        : r.intake
          ? "Not needed here"
          : "Not reached",
      body: confirmed ? (
        <>
          <p>
            An independent model call read the employee's words again and
            checked each claim of the first reading.
          </p>
          <Lines items={confirmed.detail.split("; ")} />
        </>
      ) : (
        <p>
          A second reading runs before any letter is issued. This request needed
          none.
        </p>
      ),
    },
    {
      key: "systems",
      icon: Database,
      name: "HR systems",
      state: !r.snapshots.length
        ? "skip"
        : down.length
          ? "fail"
          : absent.length
            ? "warn"
            : "ok",
      headline: !r.snapshots.length
        ? "Not reached"
        : down.length
          ? `${SYSTEMS[down[0].system]} did not answer`
          : `${r.snapshots.length} ${r.snapshots.length === 1 ? "lookup" : "lookups"} answered`,
      body: (
        <ul className="space-y-2">
          {r.snapshots.map((s, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span
                className={cn(
                  "mt-1.5 size-2 shrink-0 rounded-full",
                  s.status === "ok"
                    ? "bg-mint"
                    : s.status === "absent"
                      ? "bg-amber"
                      : "bg-coral"
                )}
              />
              <span>
                <span className="font-medium text-navy">
                  {SYSTEMS[s.system]}
                </span>{" "}
                {s.status === "ok"
                  ? "answered"
                  : s.status === "absent"
                    ? "has no record"
                    : "did not answer"}{" "}
                about {name(s.subject)}
                {s.attempts > 1 && (
                  <span className="text-muted-foreground">
                    , after {s.attempts} attempts
                  </span>
                )}
              </span>
            </li>
          ))}
          {!r.snapshots.length && (
            <li className="text-sm">No system was asked.</li>
          )}
        </ul>
      ),
    },
    {
      key: "policy",
      icon: Scale,
      name: "Policy",
      state: "ok",
      headline: `Rule ${r.verdict.rule}: ${{ resolve: "answer", approve: "needs approval", escalate: "hand over" }[r.verdict.outcome]}`,
      body: (
        <>
          <p>
            <span className="font-medium text-navy">Rule {r.verdict.rule}</span>{" "}
            of the {words(r.verdict.table.toLowerCase())} table:{" "}
            {r.verdict.says}
          </p>
          <Lines
            items={
              r.why.length
                ? r.why
                : ["This rule covers every request of this kind."]
            }
          />
          {r.would_resolve.length > 0 && (
            <div className="mt-4 rounded-xl bg-muted/70 p-3 text-sm">
              <p className="font-medium text-navy">
                It would have been answered automatically if
              </p>
              <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                {r.would_resolve.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      ),
    },
    {
      key: "reply",
      icon: ShieldCheck,
      name: "Reply check",
      state: !r.reply.length ? "skip" : held === r.reply.length ? "ok" : "warn",
      headline: r.reply.length
        ? `${held} of ${r.reply.length} ${r.reply.length === 1 ? "sentence" : "sentences"} backed`
        : "No reply written",
      body: (
        <ul className="space-y-2.5">
          {r.reply.map((s, i) => (
            <li key={i} className="flex gap-2 text-sm">
              {VERDICT[s.verdict]}
              <span>
                <span className="text-navy">{s.text}</span>
                <span className="block text-muted-foreground">{s.reason}</span>
              </span>
            </li>
          ))}
        </ul>
      ),
    },
    {
      key: "outcome",
      icon: UserRound,
      name: "Outcome",
      state: outcome[item.status][0],
      headline: outcome[item.status][1],
      body: (
        <ul className="space-y-2">
          {item.events.map((e, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <ArrowRight className="mt-0.5 size-4 shrink-0 text-blue" />
              <span>
                {e.kind === "executed"
                  ? `Issued ${e.document}`
                  : e.kind === "failed"
                    ? "The Document Repository did not issue the letter"
                    : `${words(e.kind)[0].toUpperCase()}${words(e.kind).slice(1)} by ${e.by === "policy" ? "the policy, no person needed" : name(e.by)}`}
                {e.note && (
                  <span className="text-muted-foreground">: {e.note}</span>
                )}
                <span className="ml-1.5 text-xs text-muted-foreground">
                  {ago(e.at)}
                </span>
              </span>
            </li>
          ))}
          {item.status === "awaiting_approval" && (
            <li className="text-sm">Nothing is issued until {who} approves.</li>
          )}
          {item.status === "escalated" && (
            <li className="text-sm">
              {who} has the case with every piece of evidence the desk gathered.
            </li>
          )}
        </ul>
      ),
    },
  ]
}

function Node({
  icon: Icon,
  state,
  size = "size-11",
}: {
  icon: LucideIcon
  state: State
  size?: string
}) {
  return (
    <span
      className={cn(
        "relative grid shrink-0 place-items-center rounded-2xl shadow-sm",
        size,
        LOOK[state].dot
      )}
    >
      {state === "wait" && (
        <span className="absolute inset-0 animate-ping rounded-2xl bg-amber/40 motion-reduce:animate-none" />
      )}
      <Icon className="relative size-5" />
    </span>
  )
}

export function Journey({
  item,
  people,
}: {
  item: Case
  people: Record<string, Person>
}) {
  const all = stages(item, people)
  const decisive =
    all.find((s) => s.state === "fail")?.key ??
    (item.status === "escalated" ? "policy" : "outcome")
  const [picked, setPicked] = useState(decisive)
  const [run, setRun] = useState(0)
  const reduce = useReducedMotion()
  const step = reduce ? 0 : 0.32
  const shown = all.find((s) => s.key === picked) ?? all[0]
  return (
    <div>
      <div className="mb-5 flex items-center gap-3">
        <p className="text-sm text-muted-foreground">
          The path this case took. Pick a step to see what happened in it.
        </p>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto"
          onClick={() => setRun((n) => n + 1)}
        >
          <RotateCcw /> Replay
        </Button>
      </div>
      <ol
        key={run}
        className="relative grid gap-2 md:grid-cols-6 md:gap-0"
        aria-label="Steps of this case"
      >
        <span
          aria-hidden
          className="absolute top-7 bottom-7 left-7 w-0.5 bg-border md:top-7 md:right-[8.33%] md:bottom-auto md:left-[8.33%] md:h-0.5 md:w-auto"
        >
          <motion.span
            initial={{ scaleX: 0, scaleY: 0 }}
            animate={{ scaleX: 1, scaleY: 1 }}
            transition={{ duration: (all.length - 1) * step, ease: "linear" }}
            style={{ originX: 0, originY: 0 }}
            className="absolute inset-0 bg-gradient-to-b from-blue/30 to-blue/70 md:bg-gradient-to-r"
          />
        </span>
        {all.map((s, i) => (
          <li key={s.key} className="relative flex md:justify-center">
            <motion.button
              type="button"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{
                delay: i * step,
                type: "spring",
                stiffness: 420,
                damping: 22,
              }}
              onClick={() => setPicked(s.key)}
              aria-pressed={picked === s.key}
              className={cn(
                "group flex w-full items-center gap-3 rounded-2xl p-1.5 text-left transition-colors md:w-32 md:flex-col md:gap-2 md:text-center",
                picked === s.key
                  ? "bg-secondary ring-1 ring-blue/30"
                  : "hover:bg-muted/70"
              )}
            >
              <Node icon={s.icon} state={s.state} />
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-navy">
                  {s.name}
                </span>
                <span
                  className={cn(
                    "block text-xs leading-snug",
                    LOOK[s.state].text
                  )}
                >
                  {s.headline}
                </span>
              </span>
            </motion.button>
          </li>
        ))}
      </ol>
      <AnimatePresence mode="wait">
        <motion.section
          key={`${run}-${shown.key}`}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{
            delay: picked === decisive ? all.length * step * 0.6 : 0,
            duration: 0.22,
            ease: "easeOut",
          }}
          className="mt-6 rounded-2xl bg-muted/50 p-5"
          aria-live="polite"
        >
          <div className="mb-3 flex items-center gap-3">
            <Node icon={shown.icon} state={shown.state} size="size-9" />
            <div>
              <p className="font-heading font-semibold text-navy">
                {shown.name}
              </p>
              <p className={cn("text-xs font-medium", LOOK[shown.state].text)}>
                {LOOK[shown.state].label}
              </p>
            </div>
          </div>
          <div className="text-[0.95rem] text-foreground/85">{shown.body}</div>
        </motion.section>
      </AnimatePresence>
    </div>
  )
}

export function Pipeline({ running = false }: { running?: boolean }) {
  const reduce = useReducedMotion()
  return (
    <ol className="relative grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
      {PIPELINE.map((p, i) => (
        <motion.li
          key={p.name}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.08, duration: 0.3, ease: "easeOut" }}
          className="relative flex flex-col items-center gap-2 rounded-2xl bg-muted/50 p-3 text-center"
        >
          <motion.span
            className="grid size-10 place-items-center rounded-xl bg-white text-blue shadow-sm ring-1 ring-border"
            animate={
              running && !reduce
                ? { y: [0, -5, 0], scale: [1, 1.08, 1] }
                : undefined
            }
            transition={
              running
                ? {
                    duration: 0.9,
                    repeat: Infinity,
                    repeatDelay: PIPELINE.length * 0.45 - 0.9,
                    delay: i * 0.45,
                  }
                : undefined
            }
          >
            <p.icon className="size-5" />
          </motion.span>
          <span className="text-sm font-semibold text-navy">{p.name}</span>
          <span className="text-xs leading-snug text-muted-foreground">
            {p.does}
          </span>
        </motion.li>
      ))}
    </ol>
  )
}

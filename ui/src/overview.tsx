import { useEffect } from "react"
import { motion, useSpring, useTransform } from "motion/react"
import { ArrowRight, PenLine } from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { ago, initials, within, type Case, type Person } from "@/api"
import { Pipeline } from "@/journey"
import { StatusPill } from "@/status"
import { cn } from "cn"

const EASE = [0.22, 1, 0.36, 1] as const

function Count({ value, suffix = "" }: { value: number; suffix?: string }) {
  const spring = useSpring(0, { stiffness: 90, damping: 18 })
  const text = useTransform(spring, (v) => `${Math.round(v)}${suffix}`)
  useEffect(() => spring.set(value), [spring, value])
  return <motion.span>{text}</motion.span>
}

function Stat({
  label,
  value,
  suffix,
  context,
  share,
  bar,
  i,
}: {
  label: string
  value: number
  suffix?: string
  context: string
  share: number
  bar: string
  i: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.06 * i, duration: 0.35, ease: EASE }}
      className="rounded-xl bg-white p-4 shadow-[0_1px_2px_rgba(16,24,40,0.05)] ring-1 ring-black/[0.06]"
    >
      <p className="text-[0.8rem] text-muted-foreground">{label}</p>
      <p className="mt-1 font-heading text-[1.9rem] leading-none font-semibold tracking-tight text-navy tabular-nums">
        <Count value={value} suffix={suffix} />
      </p>
      <p className="mt-1.5 text-xs text-muted-foreground">{context}</p>
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-muted">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.round(share * 100)}%` }}
          transition={{ delay: 0.2 + 0.06 * i, duration: 0.8, ease: EASE }}
          className={cn("h-full rounded-full", bar)}
        />
      </div>
    </motion.div>
  )
}

export function Overview({
  company,
  cases,
  people,
  onCase,
  onNew,
}: {
  company: string
  cases: Case[]
  people: Record<string, Person>
  onCase: (c: Case) => void
  onNew: () => void
}) {
  const n = cases.length
  const of = (k: number) => (n ? k / n : 0)
  const total = `of ${n} ${n === 1 ? "case" : "cases"}`
  const answered = within("resolved", cases).length
  const waiting = within("waiting", cases).length
  const person = within("person", cases).length
  const sentences = cases.flatMap((c) => c.record.reply)
  const backed = sentences.filter((s) => s.verdict === "supported").length
  return (
    <div className="mx-auto max-w-5xl px-5 py-8 md:px-8">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: EASE }}
        className="flex flex-wrap items-end gap-4"
      >
        <div className="flex-1">
          <h1 className="font-heading text-[1.75rem] font-semibold tracking-tight text-navy">
            Overview
          </h1>
          <p className="mt-1 max-w-xl text-[0.95rem] text-muted-foreground">
            How the desk is doing for {company}: leave balance questions and
            letter requests, answered by policy. Anything uncertain goes to a
            person with the evidence.
          </p>
        </div>
        <Button onClick={onNew}>
          <PenLine /> New request
        </Button>
      </motion.div>
      <div className="mt-7 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          i={0}
          label="Answered by the desk"
          value={answered}
          context={`${total}, no person needed`}
          share={of(answered)}
          bar="bg-mint"
        />
        <Stat
          i={1}
          label="Waiting for approval"
          value={waiting}
          context={`${total}, an approver signs off`}
          share={of(waiting)}
          bar="bg-amber"
        />
        <Stat
          i={2}
          label="With a person"
          value={person}
          context={`${total}, handed over with evidence`}
          share={of(person)}
          bar="bg-coral"
        />
        <Stat
          i={3}
          label="Reply sentences backed"
          value={
            sentences.length ? Math.round((backed / sentences.length) * 100) : 0
          }
          suffix="%"
          context={
            sentences.length
              ? `${backed} of ${sentences.length} checked against their sources`
              : "No replies checked yet"
          }
          share={sentences.length ? backed / sentences.length : 0}
          bar="bg-blue"
        />
      </div>
      <section className="mt-10">
        <h2 className="font-heading text-base font-semibold text-navy">
          How the desk handles a request
        </h2>
        <p className="mt-0.5 mb-4 text-sm text-muted-foreground">
          Six steps, in order. If any step is unsure, a person takes over.
        </p>
        <Pipeline />
      </section>
      <section className="mt-10">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-heading text-base font-semibold text-navy">
            Recent cases
          </h2>
          <span className="text-xs text-muted-foreground">{n} in total</span>
        </div>
        <ul className="divide-y overflow-hidden rounded-xl bg-white shadow-[0_1px_2px_rgba(16,24,40,0.05)] ring-1 ring-black/[0.06]">
          {cases.slice(0, 6).map((c, i) => {
            const name = people[c.record.employee]?.name ?? c.record.employee
            return (
              <motion.li
                key={c.record.case}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 + 0.04 * i }}
              >
                <button
                  onClick={() => onCase(c)}
                  className="group flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50"
                >
                  <Avatar className="size-7">
                    <AvatarFallback className="bg-navy text-[0.65rem] font-semibold text-white">
                      {initials(name)}
                    </AvatarFallback>
                  </Avatar>
                  <span className="w-36 shrink-0 truncate text-sm font-medium text-navy">
                    {name}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
                    {c.record.text}
                  </span>
                  <StatusPill
                    status={c.status}
                    className="hidden sm:inline-flex"
                  />
                  <span className="hidden w-20 shrink-0 text-right text-xs text-muted-foreground md:block">
                    {ago(c.record.at)}
                  </span>
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" />
                </button>
              </motion.li>
            )
          })}
          {!n && (
            <li className="px-4 py-6 text-sm text-muted-foreground">
              No cases yet. Send the first request.
            </li>
          )}
        </ul>
      </section>
    </div>
  )
}

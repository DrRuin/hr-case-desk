import { useEffect, useRef, useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import { Check, LoaderCircle, RotateCcw, X } from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { initials, type Person, type Step } from "@/api"
import { PIPELINE } from "@/journey"
import { cn } from "cn"

const EASE = [0.22, 1, 0.36, 1] as const

const NODE: Record<Step["stage"], number> = {
  read: 0,
  check: 1,
  systems: 2,
  policy: 3,
  reply: 4,
  action: 5,
  route: 5,
}

type Lit = Step["state"] | "idle" | "skip"

const LOOK: Record<
  Lit,
  { ring: string; badge: string; text: string; word: string }
> = {
  running: {
    ring: "bg-blue text-white glow",
    badge: "bg-blue/10 text-blue",
    text: "text-blue",
    word: "Working",
  },
  done: {
    ring: "bg-mint text-white",
    badge: "bg-mint/10 text-mint",
    text: "text-mint",
    word: "Done",
  },
  retry: {
    ring: "bg-amber text-white",
    badge: "bg-amber/10 text-amber",
    text: "text-amber",
    word: "Trying again",
  },
  failed: {
    ring: "bg-coral text-white",
    badge: "bg-coral/10 text-[#c8352d]",
    text: "text-[#c8352d]",
    word: "Stopped",
  },
  idle: {
    ring: "bg-white text-muted-foreground ring-1 ring-border",
    badge: "",
    text: "text-muted-foreground",
    word: "Not yet",
  },
  skip: {
    ring: "bg-muted text-muted-foreground/60 ring-1 ring-dashed ring-border",
    badge: "",
    text: "text-muted-foreground",
    word: "Not needed",
  },
}

const ICON: Record<Step["state"], React.ReactNode> = {
  running: <LoaderCircle className="size-3.5 animate-spin" />,
  done: <Check className="size-3.5" />,
  retry: <RotateCcw className="size-3.5" />,
  failed: <X className="size-3.5" />,
}

function lit(steps: Step[]): Lit[] {
  const last = Math.max(-1, ...steps.map((s) => NODE[s.stage]))
  return PIPELINE.map((_, i) => {
    const mine = steps.filter((s) => NODE[s.stage] === i).map((s) => s.state)
    if (!mine.length) return i < last ? "skip" : "idle"
    for (const state of ["running", "failed", "retry"] as const)
      if (mine.includes(state)) return state
    return "done"
  })
}

const seconds = (from: string, to: number) =>
  Math.max(0, (to - Date.parse(from)) / 1000)

function useNow(on: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!on) return
    const timer = setInterval(() => setNow(Date.now()), 100)
    return () => clearInterval(timer)
  }, [on])
  return now
}

function Rail({ steps }: { steps: Step[] }) {
  const states = lit(steps)
  const reached = states.filter((s) => s !== "idle").length
  return (
    <div className="relative grid grid-cols-6">
      <div className="absolute top-4 right-[8.33%] left-[8.33%] h-0.5 rounded-full bg-border" />
      <motion.div
        className="absolute top-4 left-[8.33%] h-0.5 origin-left rounded-full bg-gradient-to-r from-blue to-violet"
        initial={false}
        animate={{ width: `${(Math.max(0, reached - 1) / 5) * 83.33}%` }}
        transition={{ duration: 0.5, ease: EASE }}
      />
      {PIPELINE.map((p, i) => {
        const Icon = p.icon
        const state = states[i]
        return (
          <div
            key={p.name}
            className="relative flex flex-col items-center gap-1.5 text-center"
          >
            <motion.span
              initial={false}
              animate={{ scale: state === "running" ? 1.12 : 1 }}
              transition={{ type: "spring", stiffness: 400, damping: 22 }}
              className={cn(
                "grid size-8 place-items-center rounded-full transition-colors duration-300",
                LOOK[state].ring
              )}
            >
              <Icon className="size-4" />
            </motion.span>
            <span className="text-[0.7rem] font-medium text-navy sm:text-xs">
              {p.name}
            </span>
            <span
              className={cn("hidden text-[0.68rem] sm:block", LOOK[state].text)}
            >
              {LOOK[state].word}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export function Steps({
  steps,
  people,
  live = false,
}: {
  steps: Step[]
  people: Record<string, Person>
  live?: boolean
}) {
  const now = useNow(live)
  return (
    <ol className="relative space-y-1" aria-label="Steps">
      <AnimatePresence initial={!live}>
        {steps.map((s, i) => {
          const took =
            s.state === "running" && s.seen
              ? (now - s.seen) / 1000
              : seconds(s.began, Date.parse(s.at))
          const who = s.subject ? (people[s.subject]?.name ?? s.subject) : null
          return (
            <motion.li
              key={s.id}
              layout="position"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 0.3,
                ease: EASE,
                delay: live ? 0 : 0.03 * i,
              }}
              className="flex gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-muted/50"
            >
              <span
                className={cn(
                  "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full transition-colors duration-300",
                  LOOK[s.state].badge
                )}
              >
                {ICON[s.state]}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <AnimatePresence mode="popLayout" initial={false}>
                    <motion.p
                      key={s.title}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      transition={{ duration: 0.2 }}
                      className="min-w-0 flex-1 text-sm font-medium text-navy"
                    >
                      {s.title}
                    </motion.p>
                  </AnimatePresence>
                  <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                    {took < 0.05 ? "" : `${took.toFixed(1)} s`}
                  </span>
                </div>
                {(who || s.detail) && (
                  <p
                    className="mt-0.5 line-clamp-2 text-[0.8rem] text-muted-foreground"
                    title={s.detail}
                  >
                    {who && (
                      <span className="mr-1.5 inline-flex items-center gap-1 align-[-0.2em]">
                        <Avatar className="size-4">
                          <AvatarFallback className="bg-navy text-[0.45rem] font-semibold text-white">
                            {initials(who)}
                          </AvatarFallback>
                        </Avatar>
                        <span className="text-foreground/80">{who}</span>
                        {s.detail && <span aria-hidden>·</span>}
                      </span>
                    )}
                    {s.detail}
                  </p>
                )}
              </div>
            </motion.li>
          )
        })}
      </AnimatePresence>
    </ol>
  )
}

export function Live({
  employee,
  text,
  steps,
  people,
  done = false,
}: {
  employee: string
  text: string
  steps: Step[]
  people: Record<string, Person>
  done?: boolean
}) {
  const [began] = useState(() => Date.now())
  const now = useNow(!done)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  }, [steps.length])
  const name = people[employee]?.name ?? employee
  const current = steps.findLast((s) => s.state === "running") ?? steps.at(-1)
  return (
    <div className="mx-auto max-w-3xl space-y-7 px-5 py-7 md:px-8">
      <header className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Avatar className="size-6">
            <AvatarFallback className="bg-navy text-[0.6rem] font-semibold text-white">
              {initials(name)}
            </AvatarFallback>
          </Avatar>
          <span className="font-medium text-navy">{name}</span>
          <span>asked just now</span>
        </div>
        <h1 className="font-serif text-[1.6rem] leading-snug text-navy">
          “{text}”
        </h1>
      </header>
      <section
        aria-live="polite"
        className="rounded-xl bg-white p-5 shadow-[0_1px_2px_rgba(16,24,40,0.05)] ring-1 ring-black/[0.06]"
      >
        <div className="mb-5 flex items-center gap-3">
          <span className="relative grid size-2.5 place-items-center">
            {!done && (
              <span className="absolute inset-0 animate-ping rounded-full bg-blue/40 motion-reduce:animate-none" />
            )}
            <span
              className={cn(
                "relative size-2.5 rounded-full transition-colors",
                done ? "bg-mint" : "bg-blue"
              )}
            />
          </span>
          <AnimatePresence mode="wait" initial={false}>
            <motion.p
              key={done ? "done" : (current?.title ?? "start")}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              className="min-w-0 flex-1 truncate text-sm font-medium text-navy"
            >
              {done
                ? "Finished. Opening the case"
                : (current?.title ?? "Sending to the desk")}
            </motion.p>
          </AnimatePresence>
          <span className="text-xs text-muted-foreground tabular-nums">
            {((now - began) / 1000).toFixed(1)} s
          </span>
        </div>
        <Rail steps={steps} />
      </section>
      <section>
        <h2 className="mb-2 text-xs font-medium text-muted-foreground">
          {done ? "What the desk did" : "What the desk is doing, live"}
        </h2>
        <Steps steps={steps} people={people} live />
        <div ref={end} />
      </section>
    </div>
  )
}

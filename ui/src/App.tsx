import { useCallback, useEffect, useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import { toast } from "sonner"
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  ExternalLink,
  Inbox,
  LoaderCircle,
  Menu,
  Search,
} from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Kbd } from "@/components/ui/kbd"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { Toaster } from "@/components/ui/sonner"
import {
  api,
  ago,
  stream,
  handler,
  initials,
  VIEWS,
  within,
  type Case,
  type Directory,
  type Person,
  type Step,
  type View,
} from "@/api"
import { CaseView } from "@/case-view"
import { Composer } from "@/composer"
import { Live } from "@/live"
import { Overview } from "@/overview"
import { Palette } from "@/palette"
import { Sidebar } from "@/sidebar"
import { StatusPill } from "@/status"
import { cn } from "cn"

const EASE = [0.22, 1, 0.36, 1] as const

function Row({
  c,
  person,
  active,
  onClick,
}: {
  c: Case
  person?: Person
  active: boolean
  onClick: () => void
}) {
  const name = person?.name ?? c.record.employee
  return (
    <motion.li
      layout="position"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25, ease: EASE }}
      className="relative"
    >
      {active && (
        <motion.span
          layoutId="row-active"
          className="absolute inset-0 rounded-lg bg-secondary ring-1 ring-blue/20"
          transition={{ type: "spring", stiffness: 500, damping: 40 }}
        />
      )}
      <button
        onClick={onClick}
        aria-current={active ? "true" : undefined}
        className={cn(
          "relative flex w-full gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
          !active && "hover:bg-muted/60"
        )}
      >
        <Avatar className="mt-0.5 size-7">
          <AvatarFallback className="bg-navy/90 text-[0.65rem] font-semibold text-white">
            {initials(name)}
          </AvatarFallback>
        </Avatar>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-[0.84rem] font-medium text-navy">
              {name}
            </span>
            <span className="ml-auto shrink-0 text-[0.7rem] text-muted-foreground">
              {ago(c.record.at)}
            </span>
          </span>
          <span className="mt-0.5 block truncate text-[0.8rem] text-muted-foreground">
            {c.record.text}
          </span>
          <StatusPill status={c.status} className="mt-1.5" />
        </span>
      </button>
    </motion.li>
  )
}

function Running({
  name,
  text,
  now,
}: {
  name: string
  text: string
  now?: string
}) {
  return (
    <motion.li
      layout="position"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25, ease: EASE }}
      className="relative flex gap-3 rounded-lg bg-blue/[0.05] px-3 py-2.5 ring-1 ring-blue/15"
    >
      <Avatar className="mt-0.5 size-7">
        <AvatarFallback className="bg-navy/90 text-[0.65rem] font-semibold text-white">
          {initials(name)}
        </AvatarFallback>
      </Avatar>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate text-[0.84rem] font-medium text-navy">
            {name}
          </span>
          <span className="ml-auto shrink-0 text-[0.7rem] text-blue">now</span>
        </span>
        <span className="mt-0.5 block truncate text-[0.8rem] text-muted-foreground">
          {text}
        </span>
        <span className="mt-1.5 flex items-center gap-1.5 text-[0.72rem] font-medium text-blue">
          <LoaderCircle className="size-3 animate-spin" />
          <span className="truncate">{now ?? "Sending to the desk"}</span>
        </span>
      </span>
    </motion.li>
  )
}

function Empty() {
  return (
    <div className="grid h-full place-items-center p-8 text-center">
      <div>
        <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-secondary">
          <Inbox className="size-5 text-blue" />
        </div>
        <p className="mt-4 font-heading font-semibold text-navy">Pick a case</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Move through the list with <Kbd>J</Kbd> and <Kbd>K</Kbd>, or press{" "}
          <Kbd>C</Kbd> for a new request.
        </p>
      </div>
    </div>
  )
}

function App() {
  const [directory, setDirectory] = useState<Directory>({})
  const [tenant, setTenant] = useState("")
  const [cases, setCases] = useState<Case[]>([])
  const [open, setOpen] = useState<Case | null>(null)
  const [view, setView] = useState<View>("overview")
  const [live, setLive] = useState<{
    employee: string
    text: string
    steps: Step[]
    done?: boolean
  } | null>(null)
  const busy = live !== null
  const [down, setDown] = useState(false)
  const [palette, setPalette] = useState(false)
  const [compose, setCompose] = useState(false)
  const [menu, setMenu] = useState(false)

  useEffect(() => {
    api<Directory>("/tenants").then((d) => {
      setDirectory(d)
      setTenant(Object.keys(d)[0])
    })
    api<{ systems: string[] }>("/faults").then((f) =>
      setDown(f.systems.includes("leave"))
    )
  }, [])

  const refresh = useCallback(() => {
    if (tenant) api<Case[]>(`/tenants/${tenant}/cases`).then(setCases)
  }, [tenant])

  useEffect(refresh, [refresh])

  const people = directory[tenant]?.people ?? {}
  const company = directory[tenant]?.name ?? ""
  const listed = within(view, cases)
  const at = open
    ? listed.findIndex((c) => c.record.case === open.record.case)
    : -1

  const go = (v: View) => {
    setView(v)
    setMenu(false)
    if (v !== "overview" && open && !within(v, [open]).length) setOpen(null)
  }

  const pick = (c: Case) => {
    setOpen(c)
    if (view === "overview" || !within(view, [c]).length) setView("all")
  }

  const switchTo = (id: string) => {
    setTenant(id)
    setOpen(null)
    setMenu(false)
    toast(`Switched to ${directory[id]?.name}`)
  }

  const show = (item: Case) => {
    setOpen(item)
    refresh()
  }

  const send = async (employee: string, text: string) => {
    setCompose(false)
    setOpen(null)
    setLive({ employee, text, steps: [] })
    if (view === "overview") setView("all")
    try {
      const c = await stream(
        `/tenants/${tenant}/cases/stream`,
        { employee, text, request: crypto.randomUUID() },
        (step) =>
          setLive((l) => {
            if (!l) return l
            const at = l.steps.findIndex((s) => s.id === step.id)
            const seen = at < 0 ? Date.now() : l.steps[at].seen
            const steps =
              at < 0
                ? [...l.steps, { ...step, seen }]
                : l.steps.with(at, { ...step, seen })
            return { ...l, steps }
          })
      )
      setLive((l) => l && { ...l, done: true })
      await new Promise((r) => setTimeout(r, 900))
      show(c)
      const who = handler(c.record, people)
      const name = people[employee]?.name ?? employee
      if (c.status === "resolved")
        toast.success(`Answered ${name} by policy`, {
          description: c.record.verdict.says,
        })
      else if (c.status === "awaiting_approval")
        toast.info(`Sent to ${who} for approval`, {
          description: c.record.verdict.says,
        })
      else
        toast.warning(`Handed to ${who}`, {
          description: c.record.verdict.says,
        })
      return true
    } catch (e) {
      toast.error("Could not send the request", {
        description: (e as Error).message,
      })
      setCompose(true)
      return false
    } finally {
      setLive(null)
    }
  }

  const reviewed = (c: Case) => {
    show(c)
    const issued = c.events.find((e) => e.kind === "executed")?.document
    if (c.status === "resolved")
      toast.success("Approved", {
        description: issued ? `${issued} issued` : undefined,
      })
    else if (c.status === "rejected") toast("Rejected. Nothing was issued.")
    else if (c.status === "failed")
      toast.error("Approved, but the letter could not be issued")
  }

  const fault = async (on: boolean) => {
    const f = await api<{ systems: string[] }>("/faults", {
      method: "PUT",
      body: JSON.stringify({ systems: on ? ["leave"] : [] }),
    })
    const now = f.systems.includes("leave")
    setDown(now)
    if (now)
      toast.warning("Leave Balance Service is down", {
        description: "Balance questions now go to a person instead of a guess.",
      })
    else toast.success("Leave Balance Service is back")
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setPalette((o) => !o)
        return
      }
      const el = e.target as HTMLElement
      if (
        e.metaKey ||
        e.ctrlKey ||
        e.altKey ||
        el.closest(
          "input, textarea, [role=dialog], [role=listbox], [role=menu]"
        )
      )
        return
      if (e.key === "c") {
        e.preventDefault()
        setCompose(true)
      }
      if (
        (e.key === "j" || e.key === "k") &&
        view !== "overview" &&
        listed.length
      ) {
        const next =
          e.key === "j"
            ? Math.min(at + 1, listed.length - 1)
            : Math.max(at - 1, 0)
        setOpen(listed[at < 0 ? 0 : next])
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [view, listed, at])

  const label =
    view === "overview" ? "Overview" : VIEWS.find((v) => v.key === view)!.label
  const sidebar = (
    <Sidebar
      directory={directory}
      tenant={tenant}
      onTenant={switchTo}
      view={view}
      onView={go}
      cases={cases}
      down={down}
      onDown={fault}
      onSearch={() => setPalette(true)}
      onNew={() => setCompose(true)}
    />
  )
  const detail = busy || open
  return (
    <div className="flex h-svh overflow-hidden bg-background">
      <aside className="hidden w-60 shrink-0 lg:block">{sidebar}</aside>
      <Sheet open={menu} onOpenChange={setMenu}>
        <SheetContent side="left" className="w-72 bg-background p-0">
          <SheetTitle className="sr-only">Menu</SheetTitle>
          {sidebar}
        </SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col lg:py-2 lg:pr-2">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-white lg:rounded-xl lg:shadow-[0_1px_3px_rgba(16,24,40,0.06)] lg:ring-1 lg:ring-black/[0.06]">
          <header className="flex h-12 shrink-0 items-center gap-1.5 border-b px-3">
            <Button
              variant="ghost"
              size="icon-sm"
              className="lg:hidden"
              aria-label="Menu"
              onClick={() => setMenu(true)}
            >
              <Menu />
            </Button>
            {detail && view !== "overview" && (
              <Button
                variant="ghost"
                size="icon-sm"
                className="lg:hidden"
                aria-label="Back to the list"
                onClick={() => setOpen(null)}
              >
                <ArrowLeft />
              </Button>
            )}
            <nav
              aria-label="Breadcrumb"
              className="flex min-w-0 items-center gap-1.5 text-sm"
            >
              <span className="hidden text-muted-foreground sm:inline">
                {company}
              </span>
              <ChevronRight className="hidden size-3.5 text-muted-foreground/60 sm:block" />
              <button
                className="truncate text-muted-foreground hover:text-navy"
                onClick={() => setOpen(null)}
              >
                {label}
              </button>
              {open && view !== "overview" && (
                <>
                  <ChevronRight className="size-3.5 shrink-0 text-muted-foreground/60" />
                  <span className="truncate font-medium text-navy">
                    {people[open.record.employee]?.name ?? open.record.employee}
                  </span>
                </>
              )}
            </nav>
            <div className="ml-auto flex items-center gap-1">
              {open && view !== "overview" && at >= 0 && (
                <>
                  <span className="mr-1 hidden text-xs text-muted-foreground tabular-nums sm:block">
                    {at + 1} / {listed.length}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Previous case (K)"
                    disabled={at <= 0}
                    onClick={() => setOpen(listed[at - 1])}
                  >
                    <ChevronUp />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Next case (J)"
                    disabled={at >= listed.length - 1}
                    onClick={() => setOpen(listed[at + 1])}
                  >
                    <ChevronDown />
                  </Button>
                </>
              )}
              {open?.trace_url && view !== "overview" && (
                <Button
                  variant="ghost"
                  size="sm"
                  asChild
                  className="hidden text-muted-foreground md:inline-flex"
                >
                  <a href={open.trace_url} target="_blank" rel="noreferrer">
                    Trace <ExternalLink />
                  </a>
                </Button>
              )}
              <button
                onClick={() => setPalette(true)}
                className="ml-1 flex h-8 items-center gap-2 rounded-lg px-2.5 text-sm text-muted-foreground ring-1 ring-black/[0.08] transition hover:text-navy hover:ring-black/[0.14]"
              >
                <Search className="size-3.5" />
                <span className="hidden md:inline">Search</span>
                <Kbd className="hidden md:inline-flex">Ctrl K</Kbd>
              </button>
            </div>
          </header>
          <div className="flex min-h-0 flex-1">
            {view === "overview" ? (
              <main className="min-w-0 flex-1 overflow-y-auto">
                <Overview
                  company={company}
                  cases={cases}
                  people={people}
                  onCase={pick}
                  onNew={() => setCompose(true)}
                />
              </main>
            ) : (
              <>
                <section
                  aria-label={label}
                  className={cn(
                    "w-full shrink-0 overflow-y-auto border-r p-2 lg:block lg:w-80",
                    detail && "hidden"
                  )}
                >
                  <ul className="space-y-0.5">
                    <AnimatePresence initial={false}>
                      {live && (
                        <Running
                          key="running"
                          name={people[live.employee]?.name ?? live.employee}
                          text={live.text}
                          now={
                            (
                              live.steps.findLast(
                                (s) => s.state === "running"
                              ) ?? live.steps.at(-1)
                            )?.title
                          }
                        />
                      )}
                      {listed.map((c) => (
                        <Row
                          key={c.record.case}
                          c={c}
                          person={people[c.record.employee]}
                          active={open?.record.case === c.record.case}
                          onClick={() => setOpen(c)}
                        />
                      ))}
                    </AnimatePresence>
                  </ul>
                  {!listed.length && !live && (
                    <p className="px-3 py-6 text-sm text-muted-foreground">
                      No cases here yet.
                    </p>
                  )}
                </section>
                <main
                  className={cn(
                    "min-w-0 flex-1 overflow-y-auto",
                    !detail && "hidden lg:block"
                  )}
                >
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={busy ? "busy" : (open?.record.case ?? "empty")}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -6 }}
                      transition={{ duration: 0.22, ease: EASE }}
                      className="h-full"
                    >
                      {live ? (
                        <Live {...live} people={people} />
                      ) : open ? (
                        <CaseView
                          item={open}
                          tenant={tenant}
                          people={people}
                          onChange={reviewed}
                        />
                      ) : (
                        <Empty />
                      )}
                    </motion.div>
                  </AnimatePresence>
                </main>
              </>
            )}
          </div>
        </div>
      </div>
      <Composer
        key={tenant}
        open={compose}
        onOpenChange={setCompose}
        people={people}
        company={company}
        busy={busy}
        onSend={send}
      />
      <Palette
        open={palette}
        onOpenChange={setPalette}
        cases={cases}
        people={people}
        directory={directory}
        tenant={tenant}
        down={down}
        onCase={pick}
        onNew={() => setCompose(true)}
        onOverview={() => go("overview")}
        onTenant={switchTo}
        onDown={fault}
      />
      <Toaster position="bottom-right" />
    </div>
  )
}

export default App

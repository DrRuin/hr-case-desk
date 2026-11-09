import { motion } from "motion/react"
import {
  ChevronsUpDown,
  CircleCheck,
  Clock,
  Inbox,
  LayoutDashboard,
  type LucideIcon,
  PenLine,
  Search,
  Sparkles,
  UserRound,
} from "lucide-react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Kbd } from "@/components/ui/kbd"
import { Switch } from "@/components/ui/switch"
import { VIEWS, within, type Case, type Directory, type View } from "@/api"
import { SYSTEMS } from "@/journey"
import { cn } from "cn"

const ICONS: Record<View, LucideIcon> = {
  overview: LayoutDashboard,
  all: Inbox,
  resolved: CircleCheck,
  waiting: Clock,
  person: UserRound,
}

const DOTS: Partial<Record<View, string>> = {
  resolved: "bg-mint",
  waiting: "bg-amber",
  person: "bg-coral",
}

function Item({
  view,
  label,
  count,
  active,
  onClick,
}: {
  view: View
  label: string
  count?: number
  active: boolean
  onClick: () => void
}) {
  const Icon = ICONS[view]
  return (
    <button
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative flex h-8 w-full items-center gap-2.5 rounded-lg px-2.5 text-[0.84rem] transition-colors",
        active
          ? "font-medium text-navy"
          : "text-foreground/70 hover:bg-black/[0.04] hover:text-navy"
      )}
    >
      {active && (
        <motion.span
          layoutId="nav-active"
          className="absolute inset-0 rounded-lg bg-white shadow-[0_1px_2px_rgba(16,24,40,0.06)] ring-1 ring-black/[0.06]"
          transition={{ type: "spring", stiffness: 500, damping: 38 }}
        />
      )}
      <Icon className="relative size-4 opacity-80" />
      <span className="relative flex-1 text-left">{label}</span>
      {count !== undefined && (
        <span className="relative flex items-center gap-1.5 text-xs text-muted-foreground tabular-nums">
          {DOTS[view] && (
            <span className={cn("size-1.5 rounded-full", DOTS[view])} />
          )}
          {count}
        </span>
      )}
    </button>
  )
}

export function Sidebar({
  directory,
  tenant,
  onTenant,
  view,
  onView,
  cases,
  down,
  onDown,
  onSearch,
  onNew,
}: {
  directory: Directory
  tenant: string
  onTenant: (id: string) => void
  view: View
  onView: (v: View) => void
  cases: Case[]
  down: boolean
  onDown: (on: boolean) => void
  onSearch: () => void
  onNew: () => void
}) {
  const company = directory[tenant]?.name ?? ""
  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-5 px-3 py-3">
      <DropdownMenu>
        <DropdownMenuTrigger className="flex items-center gap-2.5 rounded-lg px-1.5 py-1.5 text-left transition-colors hover:bg-black/[0.04]">
          <span className="grid size-7 place-items-center rounded-lg bg-gradient-to-br from-blue to-violet text-white shadow-sm">
            <Sparkles className="size-3.5" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-navy">
              {company}
            </span>
            <span className="block text-[0.7rem] text-muted-foreground">
              HR case desk
            </span>
          </span>
          <ChevronsUpDown className="size-3.5 text-muted-foreground" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuLabel>Company</DropdownMenuLabel>
          {Object.entries(directory).map(([id, t]) => (
            <DropdownMenuItem key={id} onSelect={() => onTenant(id)}>
              <span className="grid size-5 place-items-center rounded-md bg-navy text-[0.6rem] font-semibold text-white">
                {t.name[0]}
              </span>
              {t.name}
              {id === tenant && (
                <CircleCheck className="ml-auto size-3.5 text-blue" />
              )}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <div className="flex gap-1.5">
        <button
          onClick={onNew}
          className="flex h-8 flex-1 items-center gap-2 rounded-lg bg-white px-2.5 text-[0.84rem] font-medium text-navy shadow-[0_1px_2px_rgba(16,24,40,0.06)] ring-1 ring-black/[0.08] transition hover:ring-black/[0.14] active:scale-[0.98]"
        >
          <PenLine className="size-3.5 text-blue" /> New request
          <Kbd className="ml-auto bg-black/[0.05]">C</Kbd>
        </button>
        <button
          onClick={onSearch}
          aria-label="Search and commands"
          className="grid size-8 place-items-center rounded-lg bg-white text-muted-foreground shadow-[0_1px_2px_rgba(16,24,40,0.06)] ring-1 ring-black/[0.08] transition hover:text-navy hover:ring-black/[0.14]"
        >
          <Search className="size-3.5" />
        </button>
      </div>
      <div className="space-y-0.5">
        <Item
          view="overview"
          label="Overview"
          active={view === "overview"}
          onClick={() => onView("overview")}
        />
      </div>
      <div>
        <p className="mb-1 px-2.5 text-[0.7rem] font-medium text-muted-foreground">
          Cases
        </p>
        <div className="space-y-0.5">
          {VIEWS.map((v) => (
            <Item
              key={v.key}
              view={v.key}
              label={v.label}
              count={within(v.key, cases).length}
              active={view === v.key}
              onClick={() => onView(v.key)}
            />
          ))}
        </div>
      </div>
      <div className="mt-auto">
        <p className="mb-1 px-2.5 text-[0.7rem] font-medium text-muted-foreground">
          HR systems
        </p>
        <ul className="space-y-0.5">
          {Object.entries(SYSTEMS).map(([key, name]) => {
            const off = key === "leave" && down
            return (
              <li
                key={key}
                className="flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[0.8rem] text-foreground/75"
              >
                <span className="relative flex size-2">
                  {!off && (
                    <span className="absolute inset-0 animate-ping rounded-full bg-mint/50 [animation-duration:2.5s] motion-reduce:animate-none" />
                  )}
                  <span
                    className={cn(
                      "relative size-2 rounded-full",
                      off ? "bg-coral" : "bg-mint"
                    )}
                  />
                </span>
                <span className="flex-1 truncate">{name}</span>
                {key === "leave" && (
                  <Switch
                    checked={down}
                    onCheckedChange={onDown}
                    aria-label="Simulate a Leave Balance Service outage"
                    title="Simulate an outage"
                    className="scale-75 data-[state=checked]:bg-coral"
                  />
                )}
              </li>
            )
          })}
        </ul>
        <p className="mt-2 px-2.5 text-[0.7rem] leading-snug text-muted-foreground">
          {down
            ? "Leave Balance Service is down. Balance questions go to a person."
            : "Flip the switch to see an outage handled safely."}
        </p>
      </div>
    </nav>
  )
}

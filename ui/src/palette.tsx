import { Building2, LayoutDashboard, PenLine, ServerCrash } from "lucide-react"

import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { initials, type Case, type Directory, type Person } from "@/api"
import { StatusPill } from "@/status"

export function Palette({
  open,
  onOpenChange,
  cases,
  people,
  directory,
  tenant,
  down,
  onCase,
  onNew,
  onOverview,
  onTenant,
  onDown,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  cases: Case[]
  people: Record<string, Person>
  directory: Directory
  tenant: string
  down: boolean
  onCase: (c: Case) => void
  onNew: () => void
  onOverview: () => void
  onTenant: (id: string) => void
  onDown: (on: boolean) => void
}) {
  const run = (action: () => void) => () => {
    onOpenChange(false)
    action()
  }
  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Search and commands"
      className="sm:max-w-xl"
    >
      <Command
        filter={(value, search) =>
          value.toLowerCase().includes(search.trim().toLowerCase()) ? 1 : 0
        }
      >
        <CommandInput placeholder="Search cases by name, request or status…" />
        <CommandList className="max-h-[min(60svh,420px)]">
          <CommandEmpty>Nothing matches.</CommandEmpty>
          <CommandGroup heading="Actions">
            <CommandItem onSelect={run(onNew)}>
              <PenLine /> New request
              <CommandShortcut>C</CommandShortcut>
            </CommandItem>
            <CommandItem onSelect={run(onOverview)}>
              <LayoutDashboard /> Go to overview
            </CommandItem>
            <CommandItem onSelect={run(() => onDown(!down))}>
              <ServerCrash />{" "}
              {down
                ? "Bring the Leave Balance Service back"
                : "Simulate a Leave Balance Service outage"}
            </CommandItem>
            {Object.entries(directory)
              .filter(([id]) => id !== tenant)
              .map(([id, t]) => (
                <CommandItem key={id} onSelect={run(() => onTenant(id))}>
                  <Building2 /> Switch to {t.name}
                </CommandItem>
              ))}
          </CommandGroup>
          <CommandGroup heading="Cases">
            {cases.map((c) => {
              const name = people[c.record.employee]?.name ?? c.record.employee
              return (
                <CommandItem
                  key={c.record.case}
                  value={`${name} ${c.record.text} ${c.record.intake?.summary ?? ""} ${c.status} ${c.record.case}`}
                  onSelect={run(() => onCase(c))}
                >
                  <Avatar className="size-6">
                    <AvatarFallback className="bg-navy text-[0.6rem] font-semibold text-white">
                      {initials(name)}
                    </AvatarFallback>
                  </Avatar>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-navy">
                      {name}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {c.record.text}
                    </span>
                  </span>
                  <StatusPill status={c.status} />
                </CommandItem>
              )
            })}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  )
}

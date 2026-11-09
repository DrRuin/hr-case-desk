import { useState } from "react"
import { motion } from "motion/react"
import {
  Check,
  ChevronsUpDown,
  CornerDownLeft,
  LoaderCircle,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Kbd, KbdGroup } from "@/components/ui/kbd"
import { Label } from "@/components/ui/label"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Textarea } from "@/components/ui/textarea"
import type { Person } from "@/api"

const SAMPLES: [string, string, string][] = [
  [
    "NA1001",
    "Balance looks wrong",
    "My leave balance shows 21.5 days but I've only taken 4 this year, why?",
  ],
  ["NA1002", "Days seem missing", "My PL shows 37 days but I've only taken 8."],
  [
    "NA1004",
    "Overlapping leave",
    "My PL balance shows 30.5 days. Is that right?",
  ],
  [
    "NA1005",
    "Carry-forward cap",
    "Why does my earned leave show 46 days? I carried 43 over from last year.",
  ],
  [
    "NA1006",
    "Joined mid-month",
    "I joined in March. Why is my privileged leave only 2 days?",
  ],
  [
    "NA1001",
    "Employment letter",
    "Please send me an employment verification letter.",
  ],
  ["NA1001", "Visa letter", "I need a visa letter for the embassy."],
  ["NA1003", "Letter, has left", "I need an employment verification letter."],
  ["NA1002", "Paternity leave", "How many days of paternity leave do I get?"],
  ["CF2001", "Visa letter", "Visa support letter for me please."],
  ["NA1001", "Outside HR scope", "Can I work from Goa next month?"],
]

function PersonPicker({
  people,
  value,
  onChange,
}: {
  people: Record<string, Person>
  value: string
  onChange: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const chosen = people[value]
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id="employee"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal sm:w-96"
        >
          <span className="truncate">
            {chosen ? (
              <>
                {chosen.name}{" "}
                <span className="text-muted-foreground">
                  · {chosen.title} · {value}
                </span>
              </>
            ) : (
              "Choose an employee"
            )}
          </span>
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-(--radix-popover-trigger-width) p-0"
        align="start"
      >
        <Command
          filter={(id, search) => {
            const p = people[id]
            const hay = `${id} ${p?.name} ${p?.title}`.toLowerCase()
            return hay.includes(search.trim().toLowerCase()) ? 1 : 0
          }}
        >
          <CommandInput placeholder="Search by name, title or id…" />
          <CommandList className="max-h-72">
            <CommandEmpty>No one matches.</CommandEmpty>
            <CommandGroup heading={`${Object.keys(people).length} people`}>
              {Object.entries(people).map(([id, p]) => (
                <CommandItem
                  key={id}
                  value={id}
                  onSelect={() => {
                    onChange(id)
                    setOpen(false)
                  }}
                >
                  <Check
                    className={id === value ? "opacity-100" : "opacity-0"}
                  />
                  <span className="truncate">
                    {p.name}{" "}
                    <span className="text-muted-foreground">· {p.title}</span>
                  </span>
                  <span className="ml-auto font-mono text-xs text-muted-foreground">
                    {id}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

export function Composer({
  open,
  onOpenChange,
  people,
  company,
  busy,
  onSend,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  people: Record<string, Person>
  company: string
  busy: boolean
  onSend: (employee: string, text: string) => Promise<boolean>
}) {
  const [employee, setEmployee] = useState(Object.keys(people)[0] ?? "")
  const [text, setText] = useState("")
  const send = async () => {
    if (!text.trim() || busy) return
    if (await onSend(employee, text)) setText("")
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-0 p-0 sm:max-w-2xl">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="text-base">New request</DialogTitle>
          <DialogDescription>
            Write what an employee of {company} asked. The desk reads it,
            checks, and decides.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 px-5 py-4">
          <div className="space-y-1.5">
            <Label htmlFor="employee">Employee</Label>
            <PersonPicker
              people={people}
              value={employee}
              onChange={setEmployee}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="text">Their message</Label>
            <Textarea
              id="text"
              rows={4}
              autoFocus
              value={text}
              className="resize-none font-serif text-[1.05rem]"
              placeholder="My leave balance looks wrong…"
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send()
              }}
            />
          </div>
          <div>
            <p className="mb-2 text-xs text-muted-foreground">
              Or start from an example
            </p>
            <div className="flex flex-wrap gap-1.5">
              {SAMPLES.filter(([id]) => id in people).map(
                ([id, label, sample], i) => (
                  <motion.button
                    key={sample}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.04 * i, duration: 0.2 }}
                    whileTap={{ scale: 0.96 }}
                    title={`${people[id].name}: ${sample}`}
                    onClick={() => {
                      setEmployee(id)
                      setText(sample)
                    }}
                    className="rounded-full border bg-white px-2.5 py-1 text-xs text-navy shadow-[0_1px_1px_rgba(16,24,40,0.04)] transition-colors hover:border-blue/40 hover:bg-secondary"
                  >
                    {label}
                  </motion.button>
                )
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 border-t bg-muted/40 px-5 py-3">
          <KbdGroup className="hidden text-xs text-muted-foreground sm:flex">
            <Kbd>Ctrl</Kbd>
            <Kbd>
              <CornerDownLeft />
            </Kbd>
            <span className="ml-1">to send</span>
          </KbdGroup>
          <Button
            className="ml-auto"
            disabled={busy || !text.trim()}
            onClick={send}
          >
            {busy && <LoaderCircle className="animate-spin" />}
            Send to the desk
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

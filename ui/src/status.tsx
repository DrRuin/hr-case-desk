import { cn } from "cn"
import type { Status } from "@/api"

export const STATUS: Record<
  Status,
  { label: string; dot: string; pill: string }
> = {
  resolved: {
    label: "Answered",
    dot: "bg-mint",
    pill: "bg-mint/10 text-mint ring-mint/25",
  },
  awaiting_approval: {
    label: "Needs approval",
    dot: "bg-amber",
    pill: "bg-amber/10 text-amber ring-amber/25",
  },
  escalated: {
    label: "With a person",
    dot: "bg-coral",
    pill: "bg-coral/10 text-[#c8352d] ring-coral/30",
  },
  rejected: {
    label: "Rejected",
    dot: "bg-muted-foreground",
    pill: "bg-muted text-muted-foreground ring-border",
  },
  failed: {
    label: "Action failed",
    dot: "bg-coral",
    pill: "bg-coral/10 text-[#c8352d] ring-coral/30",
  },
}

export function StatusPill({
  status,
  className,
}: {
  status: Status
  className?: string
}) {
  const s = STATUS[status]
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        s.pill,
        className
      )}
    >
      <span className={cn("size-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  )
}

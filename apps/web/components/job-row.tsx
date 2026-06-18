"use client"

import { MoreVerticalIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Progress } from "@/components/ui/progress"
import { apiFetch, formatBytes } from "@/lib/api"
import type { Job } from "@/lib/types"
import { cn } from "@/lib/utils"

const activeStates = new Set([
  "inspecting",
  "downloading",
  "processing",
  "uploading",
])

export function JobRow({
  job,
  index,
  onChanged,
  onOpen,
}: {
  job: Job
  index: number
  onChanged: () => void
  onOpen?: (job: Job) => void
}) {
  const active = activeStates.has(job.state)

  async function mutate(action: "cancel" | "retry") {
    await apiFetch(`/api/v1/jobs/${job.id}/${action}`, { method: "POST" })
    onChanged()
  }

  return (
    <article className="queue-scroll editorial-rule grid grid-cols-[2rem_minmax(0,1fr)_auto] gap-3 border-t py-7">
      <div className="font-heading text-2xl tabular-nums">
        {String(index + 1).padStart(2, "0")}
      </div>
      <div className="min-w-0">
        <button
          className="max-w-full truncate text-left font-semibold hover:underline"
          onClick={() => onOpen?.(job)}
        >
          {job.title || `YouTube ${job.video_id}`}
        </button>
        <p className="mt-1 text-sm text-muted-foreground">
          {job.requested_format.toUpperCase()} · {job.requested_quality} ·{" "}
          {formatBytes(job.size_bytes)}
        </p>
        <p
          className={cn(
            "mt-2 text-sm font-medium capitalize",
            job.state === "ready" && "text-ready",
            (active || job.state === "failed") && "text-destructive"
          )}
        >
          {job.state}
          {active ? ` · ${Math.round(job.progress)}%` : ""}
        </p>
        {active ? <Progress value={job.progress} className="mt-3 h-1" /> : null}
        {job.error_message ? (
          <p className="mt-2 text-xs text-destructive">{job.error_message}</p>
        ) : null}
      </div>
      <div className="flex items-start gap-2">
        {job.state === "ready" && job.artifact_id ? (
          <Button asChild>
            <a href={`/api/v1/artifacts/${job.artifact_id}/download`}>
              Download
            </a>
          </Button>
        ) : null}
        {active || job.state === "queued" ? (
          <Button variant="outline" onClick={() => mutate("cancel")}>
            Cancel
          </Button>
        ) : null}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Job actions">
              <MoreVerticalIcon />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuGroup>
              <DropdownMenuItem onSelect={() => onOpen?.(job)}>
                View details
              </DropdownMenuItem>
              {job.state === "failed" || job.state === "cancelled" ? (
                <DropdownMenuItem onSelect={() => mutate("retry")}>
                  Retry
                </DropdownMenuItem>
              ) : null}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </article>
  )
}

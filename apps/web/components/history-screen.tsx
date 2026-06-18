"use client"

import { useMemo, useState } from "react"
import { SearchIcon } from "lucide-react"

import { JobDetailsDrawer } from "@/components/job-details-drawer"
import { Badge } from "@/components/ui/badge"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import { Field, FieldLabel } from "@/components/ui/field"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useJobs } from "@/hooks/use-jobs"
import { formatBytes, formatDate } from "@/lib/api"
import type { Job } from "@/lib/types"

export function HistoryScreen() {
  const { jobs } = useJobs(250)
  const [query, setQuery] = useState("")
  const [state, setState] = useState("all")
  const [selected, setSelected] = useState<Job | null>(null)
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return jobs.filter((job) => {
      if (state !== "all" && job.state !== state) return false
      if (!normalized) return true
      return `${job.title ?? ""} ${job.video_id} ${job.requested_format}`
        .toLowerCase()
        .includes(normalized)
    })
  }, [jobs, query, state])

  return (
    <section className="px-5 py-10 md:px-10 md:py-14">
      <div className="editorial-rule flex flex-wrap items-end justify-between gap-8 border-b pb-8">
        <div>
          <h1 className="display-title text-6xl sm:text-7xl">
            Conversion history.
          </h1>
          <p className="mt-3 text-muted-foreground">
            A redacted record of local and email jobs.
          </p>
        </div>
        <div className="grid min-w-0 gap-4 sm:grid-cols-[minmax(16rem,1fr)_11rem]">
          <Field>
            <FieldLabel htmlFor="history-search" className="sr-only">
              Search history
            </FieldLabel>
            <InputGroup>
              <InputGroupInput
                id="history-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search title or video ID"
              />
              <InputGroupAddon>
                <SearchIcon />
              </InputGroupAddon>
            </InputGroup>
          </Field>
          <Select value={state} onValueChange={setState}>
            <SelectTrigger aria-label="Filter by state">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {[
                  "all",
                  "ready",
                  "failed",
                  "queued",
                  "downloading",
                  "cancelled",
                  "expired",
                ].map((value) => (
                  <SelectItem key={value} value={value} className="capitalize">
                    {value}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
      </div>
      {filtered.length ? (
        <Table className="mt-6">
          <TableHeader>
            <TableRow>
              <TableHead>File</TableHead>
              <TableHead>Format</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Size</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((job) => (
              <TableRow
                key={job.id}
                data-job-id={job.id}
                tabIndex={0}
                aria-label={`Open ${job.title || job.video_id}`}
                className="cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                onClick={() => setSelected(job)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault()
                    setSelected(job)
                  }
                }}
              >
                <TableCell>
                  <div className="max-w-md truncate font-medium">
                    {job.title || `YouTube ${job.video_id}`}
                  </div>
                  <div className="mt-1 font-mono text-xs text-muted-foreground">
                    {job.video_id}
                  </div>
                </TableCell>
                <TableCell>
                  {job.requested_format.toUpperCase()} · {job.requested_quality}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={
                      job.state === "failed" ? "destructive" : "secondary"
                    }
                    className="capitalize"
                  >
                    {job.state}
                  </Badge>
                </TableCell>
                <TableCell>{formatBytes(job.size_bytes)}</TableCell>
                <TableCell>{formatDate(job.created_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <Empty className="min-h-96">
          <EmptyHeader>
            <EmptyTitle>No matching conversions</EmptyTitle>
            <EmptyDescription>
              Adjust the search or create a new job from Convert.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
      <JobDetailsDrawer
        job={selected}
        open={Boolean(selected)}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </section>
  )
}

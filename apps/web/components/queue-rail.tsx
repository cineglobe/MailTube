"use client"

import { useMemo, useState } from "react"
import { RefreshCwIcon } from "lucide-react"

import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { Job } from "@/lib/types"
import { JobRow } from "@/components/job-row"
import { JobDetailsDrawer } from "@/components/job-details-drawer"

type Filter = "all" | "active" | "completed"
const activeStates = new Set([
  "queued",
  "inspecting",
  "downloading",
  "processing",
  "uploading",
])

type QueueRailProps = {
  jobs: Job[]
  isLoading: boolean
  onChanged: () => void
}

export function QueueRail({ jobs, isLoading, onChanged }: QueueRailProps) {
  const [filter, setFilter] = useState<Filter>("all")
  const [selected, setSelected] = useState<Job | null>(null)
  const filtered = useMemo(
    () =>
      jobs.filter((job) => {
        if (filter === "active") return activeStates.has(job.state)
        if (filter === "completed") return !activeStates.has(job.state)
        return true
      }),
    [filter, jobs]
  )

  return (
    <aside className="editorial-rule min-w-0 border-t px-5 py-8 lg:border-t-0 lg:border-l lg:px-9 xl:px-12">
      <div className="editorial-rule flex items-end justify-between border-b pb-4">
        <h2 className="font-heading text-4xl">Queue</h2>
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          Auto-refresh{" "}
          <RefreshCwIcon className={isLoading ? "animate-spin" : undefined} />
        </p>
      </div>
      <Tabs
        value={filter}
        onValueChange={(value) => setFilter(value as Filter)}
      >
        <TabsList className="editorial-rule h-auto w-full justify-start rounded-none border-b bg-transparent p-0">
          <TabsTrigger value="all" className="rounded-none px-4 py-4">
            All ({jobs.length})
          </TabsTrigger>
          <TabsTrigger value="active" className="rounded-none px-4 py-4">
            Active
          </TabsTrigger>
          <TabsTrigger value="completed" className="rounded-none px-4 py-4">
            Completed
          </TabsTrigger>
        </TabsList>
      </Tabs>
      {filtered.length ? (
        <div>
          {filtered.map((job, index) => (
            <JobRow
              key={job.id}
              job={job}
              index={index}
              onChanged={onChanged}
              onOpen={setSelected}
            />
          ))}
        </div>
      ) : (
        <Empty className="min-h-72">
          <EmptyHeader>
            <EmptyTitle>No conversions here</EmptyTitle>
            <EmptyDescription>
              New jobs will appear as soon as you start a conversion.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
      <JobDetailsDrawer
        job={selected}
        open={Boolean(selected)}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </aside>
  )
}

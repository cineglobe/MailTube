"use client"

import { ConverterWorkbench } from "@/components/converter-workbench"
import { QueueRail } from "@/components/queue-rail"
import { useJobs } from "@/hooks/use-jobs"

export function ConvertScreen() {
  const { jobs, mutate, isLoading } = useJobs(50)
  return (
    <div className="grid min-h-[calc(100svh-9rem)] lg:grid-cols-[minmax(0,3fr)_minmax(25rem,2fr)]">
      <ConverterWorkbench onCreated={() => mutate()} />
      <QueueRail jobs={jobs} isLoading={isLoading} onChanged={() => mutate()} />
    </div>
  )
}

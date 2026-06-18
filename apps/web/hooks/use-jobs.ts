"use client"

import { useEffect } from "react"
import useSWR from "swr"

import { fetcher } from "@/lib/api"
import type { Job } from "@/lib/types"

type JobsResponse = { items: Job[] }

export function useJobs(limit = 100) {
  const key = `/api/v1/jobs?limit=${limit}`
  const swr = useSWR<JobsResponse>(key, fetcher, {
    refreshInterval: 10_000,
    revalidateOnFocus: false,
  })
  const { mutate } = swr

  useEffect(() => {
    const events = new EventSource("/api/v1/jobs/events")
    const update = (event: MessageEvent<string>) => {
      try {
        mutate(
          { items: JSON.parse(event.data) as Job[] },
          { revalidate: false }
        )
      } catch {
        // The regular SWR interval remains the reliability fallback.
      }
    }
    events.addEventListener("jobs", update as EventListener)
    return () => events.close()
  }, [mutate])

  return { ...swr, jobs: swr.data?.items ?? [] }
}

"use client"

import { useEffect } from "react"
import { usePathname, useRouter } from "next/navigation"
import useSWR from "swr"

import { Spinner } from "@/components/ui/spinner"
import { fetcher, rememberSession } from "@/lib/api"
import type { Session } from "@/lib/types"

export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { data, error } = useSWR<Session>("/api/v1/auth/session", fetcher, {
    revalidateOnFocus: false,
    refreshInterval: 60_000,
    shouldRetryOnError: false,
  })

  useEffect(() => {
    if (data) rememberSession(data)
  }, [data])

  useEffect(() => {
    if (error) router.replace(`/login/?next=${encodeURIComponent(pathname)}`)
  }, [error, pathname, router])

  if (!data) {
    return (
      <main
        className="grid min-h-svh place-items-center"
        aria-label="Checking session"
      >
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Spinner /> Checking your MailTube session
        </div>
      </main>
    )
  }

  return children
}

"use client"

import useSWR from "swr"
import { CheckCircle2Icon, CircleAlertIcon, RefreshCwIcon } from "lucide-react"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { apiFetch, fetcher, formatBytes } from "@/lib/api"
import type { HealthDetails } from "@/lib/types"

export function HealthScreen() {
  const { data, mutate, isLoading } = useSWR<HealthDetails>(
    "/api/v1/health/details",
    fetcher,
    { refreshInterval: 15_000 }
  )
  const checks = data
    ? ([
        ["Database", data.database],
        ["Downloader", data.downloader],
        ["JavaScript runtime", data.javascript],
        ["Storage", data.storage],
        ["Email", data.email],
      ] as const)
    : []

  async function runDiagnostic(name: "email" | "storage" | "downloader") {
    try {
      const result = await apiFetch<{ ok: boolean; detail: string }>(
        `/api/v1/diagnostics/${name}`,
        { method: "POST" }
      )
      if (result.ok) toast.success(result.detail)
      else toast.error(result.detail)
      mutate()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Diagnostic failed")
    }
  }

  return (
    <section className="mx-auto max-w-6xl px-5 py-10 md:px-10 md:py-14">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="display-title text-6xl sm:text-7xl">System health.</h1>
          <p className="mt-3 text-muted-foreground">
            Dependency checks expose status, never credentials.
          </p>
        </div>
        <Button variant="outline" onClick={() => mutate()} disabled={isLoading}>
          <RefreshCwIcon data-icon="inline-start" />
          Refresh
        </Button>
      </div>
      <Separator className="my-9" />
      <div className="editorial-rule editorial-rule divide-y border-y">
        {checks.map(([name, check]) => (
          <div
            key={name}
            className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-4 py-6"
          >
            {check.ok ? (
              <CheckCircle2Icon className="text-ready" />
            ) : (
              <CircleAlertIcon className="text-destructive" />
            )}
            <div>
              <h2 className="font-semibold">{name}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {check.detail}
              </p>
            </div>
            {!["Database", "JavaScript runtime"].includes(name) ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  runDiagnostic(
                    name.toLowerCase() as "email" | "storage" | "downloader"
                  )
                }
              >
                Test
              </Button>
            ) : null}
          </div>
        ))}
      </div>
      {data ? (
        <Alert className="mt-8">
          {data.disk.ok ? <CheckCircle2Icon /> : <CircleAlertIcon />}
          <AlertTitle>
            {formatBytes(data.disk.free_bytes)} free on the work volume
          </AlertTitle>
          <AlertDescription>
            MailTube requires at least one configured maximum file size of free
            space before accepting work.
          </AlertDescription>
        </Alert>
      ) : null}
      <p className="mt-8 font-mono text-xs text-muted-foreground">
        MailTube {data?.version ?? "—"}
      </p>
    </section>
  )
}

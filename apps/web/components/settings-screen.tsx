"use client"

import { useState } from "react"
import useSWR from "swr"
import { toast } from "sonner"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { apiFetch, fetcher } from "@/lib/api"
import type { RuntimeSettings } from "@/lib/types"

export function SettingsScreen() {
  const { data, mutate } = useSWR<RuntimeSettings>("/api/v1/settings", fetcher)
  if (!data) {
    return (
      <section className="mx-auto max-w-5xl px-5 py-14 text-sm text-muted-foreground">
        Loading settings…
      </section>
    )
  }
  return (
    <SettingsForm key={JSON.stringify(data)} data={data} onSaved={mutate} />
  )
}

function SettingsForm({
  data,
  onSaved,
}: {
  data: RuntimeSettings
  onSaved: () => Promise<unknown>
}) {
  const [allowAny, setAllowAny] = useState(data.sender_policy === "any")
  const [allowlist, setAllowlist] = useState(data.sender_allowlist.join(", "))
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [retention, setRetention] = useState(String(data.retention_hours))
  const [maxUrls, setMaxUrls] = useState(String(data.max_urls_per_batch))

  async function save(policy = allowAny) {
    try {
      await apiFetch("/api/v1/settings", {
        method: "PATCH",
        body: JSON.stringify({
          sender_policy: policy ? "any" : "allowlist",
          sender_allowlist: allowlist
            .split(",")
            .map((value) => value.trim().toLowerCase())
            .filter(Boolean),
          retention_hours: Number(retention),
          max_urls_per_batch: Number(maxUrls),
        }),
      })
      await onSaved()
      toast.success("Settings saved")
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not save settings"
      )
    }
  }

  function toggleAny(checked: boolean) {
    if (checked) setConfirmOpen(true)
    else setAllowAny(false)
  }

  return (
    <section className="mx-auto max-w-5xl px-5 py-10 md:px-10 md:py-14">
      <h1 className="display-title text-6xl sm:text-7xl">Instance settings.</h1>
      <p className="mt-3 text-muted-foreground">
        Operational controls are stored locally. Credentials remain TUI-only.
      </p>
      <Separator className="my-10" />
      <FieldGroup>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="font-heading text-3xl">Email access</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Choose who can submit conversion requests.
            </p>
          </div>
          <Badge variant={allowAny ? "destructive" : "secondary"}>
            {allowAny ? "Any sender" : "Allowlist only"}
          </Badge>
        </div>
        <Field orientation="horizontal">
          <Switch
            id="any-sender"
            checked={allowAny}
            onCheckedChange={toggleAny}
          />
          <FieldContent>
            <FieldLabel htmlFor="any-sender">
              Accept email from any sender
            </FieldLabel>
            <FieldDescription>
              Hard batch, duration, file-size, and concurrency limits remain
              active.
            </FieldDescription>
          </FieldContent>
        </Field>
        <Field>
          <FieldLabel htmlFor="allowlist">Allowed sender addresses</FieldLabel>
          <Input
            id="allowlist"
            value={allowlist}
            onChange={(event) => setAllowlist(event.target.value)}
            placeholder="you@example.com, family@example.com"
            disabled={allowAny}
          />
          <FieldDescription>
            Comma-separated. Address matching is case-insensitive.
          </FieldDescription>
        </Field>
        <Separator />
        <h2 className="font-heading text-3xl">Limits & retention</h2>
        <div className="grid gap-6 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="retention">Retention hours</FieldLabel>
            <Input
              id="retention"
              type="number"
              min={1}
              max={168}
              value={retention}
              onChange={(event) => setRetention(event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="max-urls">Links per batch</FieldLabel>
            <Input
              id="max-urls"
              type="number"
              min={1}
              max={25}
              value={maxUrls}
              onChange={(event) => setMaxUrls(event.target.value)}
            />
          </Field>
        </div>
        <Separator />
        <div className="grid gap-4 text-sm sm:grid-cols-3">
          <div>
            <p className="text-muted-foreground">Email</p>
            <p className="mt-1 font-medium">
              {data.email_enabled ? "Enabled" : "Disabled"}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">Delivery</p>
            <p className="mt-1 font-medium capitalize">{data.delivery_mode}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Storage</p>
            <p className="mt-1 font-medium uppercase">{data.storage_backend}</p>
          </div>
        </div>
        <Button onClick={() => save()} className="self-start">
          Save settings
        </Button>
      </FieldGroup>
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Accept requests from anyone?</AlertDialogTitle>
            <AlertDialogDescription>
              This can expose your mailbox, bandwidth, and object storage to
              abuse. Per-sender and global limits remain enforced, but allowlist
              mode is safer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep allowlist</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setAllowAny(true)
                save(true)
              }}
            >
              Enable any sender
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}

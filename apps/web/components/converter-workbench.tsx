"use client"

import { useMemo, useRef, useState } from "react"
import { DownloadIcon, InfoIcon } from "lucide-react"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldSet,
  FieldLegend,
} from "@/components/ui/field"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupTextarea,
  InputGroupText,
} from "@/components/ui/input-group"
import { Spinner } from "@/components/ui/spinner"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { apiFetch } from "@/lib/api"

type OutputFormat = "mp4" | "mp3" | "wav"
const qualities: Record<OutputFormat, string[]> = {
  mp4: ["360p", "480p", "720p", "1080p", "1440p", "2160p", "best"],
  mp3: ["128k", "192k", "256k", "320k"],
  wav: ["44.1khz", "48khz"],
}
const defaults: Record<OutputFormat, string> = {
  mp4: "720p",
  mp3: "192k",
  wav: "44.1khz",
}
const urlPattern = /https?:\/\/[^\s<>\"]+/i

export function parseDraft(
  text: string,
  fallbackFormat: OutputFormat,
  fallbackQuality: string
) {
  const seen = new Set<string>()
  const items: Array<{ url: string; format: OutputFormat; quality: string }> =
    []
  for (const line of text.split(/\r?\n/)) {
    const match = line.match(urlPattern)
    if (!match) continue
    const suffix = line
      .slice((match.index ?? 0) + match[0].length)
      .toLowerCase()
    const explicitFormat = (["mp4", "mp3", "wav"] as OutputFormat[]).find(
      (value) => new RegExp(`\\b${value}\\b`).test(suffix)
    )
    const format = explicitFormat ?? fallbackFormat
    const explicitQuality = qualities[format].find((value) =>
      suffix.includes(value)
    )
    const quality =
      explicitQuality ??
      (format === fallbackFormat ? fallbackQuality : defaults[format])
    const key = `${match[0]}:${format}:${quality}`
    if (!seen.has(key)) {
      seen.add(key)
      items.push({ url: match[0], format, quality })
    }
  }
  return items
}

export function ConverterWorkbench({ onCreated }: { onCreated: () => void }) {
  const formRef = useRef<HTMLFormElement>(null)
  const [draft, setDraft] = useState("")
  const [format, setFormat] = useState<OutputFormat>("mp4")
  const [quality, setQuality] = useState(defaults.mp4)
  const [pending, setPending] = useState(false)
  const parsed = useMemo(
    () => parseDraft(draft, format, quality),
    [draft, format, quality]
  )

  function selectFormat(value: string) {
    if (!value) return
    const next = value as OutputFormat
    setFormat(next)
    setQuality(defaults[next])
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!parsed.length) {
      toast.error("Add at least one valid YouTube link")
      return
    }
    setPending(true)
    try {
      await apiFetch("/api/v1/jobs", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ items: parsed }),
      })
      setDraft("")
      toast.success(
        `${parsed.length} conversion${parsed.length === 1 ? "" : "s"} queued`
      )
      onCreated()
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not start the conversion"
      )
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="px-5 py-10 md:px-10 md:py-14 xl:px-14 xl:py-16">
      <h1 className="display-title max-w-4xl text-4xl leading-tight sm:text-5xl xl:text-6xl">
        Turn a link into a file.
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground md:text-base">
        Paste one or more YouTube links. Choose the format and MailTube will
        handle the rest.
      </p>
      <form ref={formRef} onSubmit={submit} className="mt-10 max-w-4xl">
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="youtube-links">YouTube links</FieldLabel>
            <InputGroup>
              <InputGroupTextarea
                id="youtube-links"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    (event.ctrlKey || event.metaKey) &&
                    event.key === "Enter"
                  ) {
                    event.preventDefault()
                    formRef.current?.requestSubmit()
                  }
                }}
                placeholder={
                  "https://www.youtube.com/watch?v=dQw4w9WgXcQ\nhttps://youtu.be/9bZkp7q19f0 mp3 320k"
                }
                rows={5}
                className="min-h-36 font-mono text-base leading-8"
              />
              <InputGroupAddon align="block-end">
                <InputGroupText>
                  {parsed.length} request{parsed.length === 1 ? "" : "s"}
                </InputGroupText>
              </InputGroupAddon>
            </InputGroup>
            <FieldDescription>
              One link per line. Add a format and quality after a link to
              override the controls below.
            </FieldDescription>
          </Field>
          <div className="grid gap-8 md:grid-cols-[minmax(15rem,0.8fr)_minmax(20rem,1.2fr)]">
            <FieldSet>
              <FieldLegend variant="label">Format</FieldLegend>
              <ToggleGroup
                type="single"
                value={format}
                onValueChange={selectFormat}
                variant="outline"
                className="w-full"
              >
                {(["mp4", "mp3", "wav"] as const).map((value) => (
                  <ToggleGroupItem
                    key={value}
                    value={value}
                    className="flex-1 uppercase"
                  >
                    {value}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </FieldSet>
            <FieldSet>
              <FieldLegend variant="label">Quality</FieldLegend>
              <ToggleGroup
                type="single"
                value={quality}
                onValueChange={(value) => value && setQuality(value)}
                variant="outline"
                className="flex-wrap justify-start"
              >
                {qualities[format].map((value) => (
                  <ToggleGroupItem key={value} value={value}>
                    {value}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </FieldSet>
          </div>
          <details className="group editorial-rule border-y py-4">
            <summary className="cursor-pointer text-sm font-medium">
              Advanced request syntax
            </summary>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
              Mix formats in one batch with{" "}
              <span className="font-mono">URL mp4 1080p</span>,{" "}
              <span className="font-mono">URL mp3 320k</span>, or{" "}
              <span className="font-mono">URL wav 48khz</span>.
            </p>
          </details>
          <div className="flex flex-wrap items-center gap-5">
            <Button type="submit" size="lg" disabled={pending}>
              {pending ? (
                <Spinner data-icon="inline-start" />
              ) : (
                <DownloadIcon data-icon="inline-start" />
              )}
              {pending ? "Starting…" : "Start conversion"}
            </Button>
            <p className="text-xs text-muted-foreground">
              Press <kbd className="border px-1.5 py-0.5 font-mono">Ctrl ↵</kbd>{" "}
              to start
            </p>
          </div>
          <Alert>
            <InfoIcon />
            <AlertTitle>Files expire after 24 hours.</AlertTitle>
            <AlertDescription>
              Completed files are automatically removed to save disk space and
              protect privacy.
            </AlertDescription>
          </Alert>
        </FieldGroup>
      </form>
    </section>
  )
}

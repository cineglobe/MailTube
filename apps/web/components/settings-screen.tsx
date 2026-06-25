"use client"

import { useState } from "react"
import {
  DatabaseIcon,
  GaugeIcon,
  KeyRoundIcon,
  MailIcon,
  SaveIcon,
  ServerCogIcon,
  Trash2Icon,
  UploadIcon,
} from "lucide-react"
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { apiFetch, fetcher } from "@/lib/api"
import type { RuntimeSettings } from "@/lib/types"

const EDITABLE_KEYS = [
  "admin_username",
  "sender_policy",
  "sender_allowlist",
  "retention_hours",
  "max_urls_per_batch",
  "max_concurrent_jobs",
  "max_duration_seconds",
  "max_file_mb",
  "job_timeout_seconds",
  "inactivity_timeout_seconds",
  "default_format",
  "default_mp4_quality",
  "default_mp3_quality",
  "default_wav_quality",
  "email_enabled",
  "poll_interval_seconds",
  "imap_host",
  "imap_port",
  "imap_folder",
  "imap_username",
  "smtp_host",
  "smtp_port",
  "smtp_security",
  "smtp_username",
  "smtp_from",
  "smtp_from_name",
  "delivery_mode",
  "max_attachment_mb",
  "max_email_requests_per_hour",
  "email_success_template_html",
  "email_partial_template_html",
  "email_failure_template_html",
  "email_error_template_html",
  "storage_backend",
  "s3_endpoint",
  "s3_region",
  "s3_bucket",
  "s3_access_key_id",
  "s3_force_path_style",
  "pot_provider_url",
  "update_channel",
] as const

type SecretDraft = {
  admin_password: string
  imap_password: string
  smtp_password: string
  s3_secret_access_key: string
}

const EMPTY_SECRETS: SecretDraft = {
  admin_password: "",
  imap_password: "",
  smtp_password: "",
  s3_secret_access_key: "",
}

const RESULT_TEMPLATE_PLACEHOLDERS = [
  "{{ status_heading }}",
  "{{ status_message }}",
  "{{ retention_hours }}",
  "{{ subject }}",
  "{% for item in items %}",
  "{{ item.title }}",
  "{{ item.format }}",
  "{{ item.quality }}",
  "{{ item.size }}",
  "{{ item.url }}",
  "{{ item.error }}",
]

const ERROR_TEMPLATE_PLACEHOLDERS = ["{{ reason }}", "{{ subject }}"]

export function SettingsScreen() {
  const { data, error, mutate } = useSWR<RuntimeSettings>(
    "/api/v1/settings",
    fetcher
  )
  if (error) {
    return (
      <section className="mx-auto max-w-6xl px-5 py-14 md:px-10">
        <Alert variant="destructive">
          <ServerCogIcon />
          <AlertTitle>Settings could not be loaded</AlertTitle>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      </section>
    )
  }
  if (!data) {
    return (
      <section className="mx-auto flex max-w-6xl items-center gap-3 px-5 py-14 text-sm text-muted-foreground md:px-10">
        <Spinner /> Loading settings
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
  const [draft, setDraft] = useState(data)
  const [secrets, setSecrets] = useState<SecretDraft>(EMPTY_SECRETS)
  const [allowlistText, setAllowlistText] = useState(
    data.sender_allowlist.join(", ")
  )
  const [saving, setSaving] = useState(false)
  const [cookiesFile, setCookiesFile] = useState<File | null>(null)
  const [cookiesBusy, setCookiesBusy] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  function update<K extends keyof RuntimeSettings>(
    key: K,
    value: RuntimeSettings[K]
  ) {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  function updateSecret(key: keyof SecretDraft, value: string) {
    setSecrets((current) => ({ ...current, [key]: value }))
  }

  async function save(policy = draft.sender_policy) {
    setSaving(true)
    try {
      const payload: Record<string, unknown> = {}
      for (const key of EDITABLE_KEYS) payload[key] = draft[key]
      payload.sender_policy = policy
      payload.sender_allowlist = allowlistText
        .split(",")
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean)
      for (const [key, value] of Object.entries(secrets)) {
        if (value) payload[key] = value
      }
      await apiFetch("/api/v1/settings", {
        method: "PATCH",
        body: JSON.stringify(payload),
      })
      setSecrets(EMPTY_SECRETS)
      await onSaved()
      toast.success("Settings applied")
    } catch (saveError) {
      toast.error(
        saveError instanceof Error
          ? saveError.message
          : "Could not save settings"
      )
    } finally {
      setSaving(false)
    }
  }

  function toggleAny(checked: boolean) {
    if (checked) setConfirmOpen(true)
    else update("sender_policy", "allowlist")
  }

  async function runDiagnostic(name: "email" | "storage") {
    try {
      const result = await apiFetch<{ ok: boolean; detail: string }>(
        `/api/v1/diagnostics/${name}`,
        { method: "POST" }
      )
      if (result.ok) toast.success(result.detail)
      else toast.error(result.detail)
    } catch (diagnosticError) {
      toast.error(
        diagnosticError instanceof Error
          ? diagnosticError.message
          : "Diagnostic failed"
      )
    }
  }

  async function uploadCookies() {
    if (!cookiesFile) return
    setCookiesBusy(true)
    try {
      const body = new FormData()
      body.append("file", cookiesFile)
      await apiFetch("/api/v1/settings/youtube-cookies", {
        method: "POST",
        body,
      })
      setCookiesFile(null)
      await onSaved()
      toast.success("YouTube cookies installed")
    } catch (uploadError) {
      toast.error(
        uploadError instanceof Error
          ? uploadError.message
          : "Could not upload YouTube cookies"
      )
    } finally {
      setCookiesBusy(false)
    }
  }

  async function removeCookies() {
    setCookiesBusy(true)
    try {
      await apiFetch("/api/v1/settings/youtube-cookies", {
        method: "DELETE",
      })
      setCookiesFile(null)
      await onSaved()
      toast.success("YouTube cookies removed")
    } catch (removeError) {
      toast.error(
        removeError instanceof Error
          ? removeError.message
          : "Could not remove YouTube cookies"
      )
    } finally {
      setCookiesBusy(false)
    }
  }

  return (
    <section className="mx-auto max-w-6xl px-5 py-10 md:px-10 md:py-14">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="display-title text-5xl sm:text-6xl">
            Instance settings.
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            Runtime changes apply immediately and survive container restarts.
            New passwords are encrypted before they are stored.
          </p>
        </div>
        <Button type="button" onClick={() => save()} disabled={saving}>
          {saving ? <Spinner data-icon="inline-start" /> : <SaveIcon />}
          {saving ? "Applying…" : "Apply changes"}
        </Button>
      </div>

      <Tabs defaultValue="email" className="mt-10">
        <TabsList
          className="h-auto w-full flex-wrap justify-start"
          variant="line"
        >
          <TabsTrigger value="email">
            <MailIcon data-icon="inline-start" /> Email
          </TabsTrigger>
          <TabsTrigger value="storage">
            <DatabaseIcon data-icon="inline-start" /> Storage
          </TabsTrigger>
          <TabsTrigger value="conversion">
            <GaugeIcon data-icon="inline-start" /> Conversion
          </TabsTrigger>
          <TabsTrigger value="access">
            <KeyRoundIcon data-icon="inline-start" /> Access
          </TabsTrigger>
          <TabsTrigger value="system">
            <ServerCogIcon data-icon="inline-start" /> System
          </TabsTrigger>
        </TabsList>

        <TabsContent value="email" className="mt-6 flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Gmail or IMAP mailbox</CardTitle>
              <CardDescription>
                MailTube checks unread messages every 15 seconds by default.
              </CardDescription>
              <CardAction>
                <Badge variant={draft.email_enabled ? "secondary" : "outline"}>
                  {draft.email_enabled ? "Enabled" : "Disabled"}
                </Badge>
              </CardAction>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <Field orientation="horizontal">
                  <Switch
                    id="email-enabled"
                    checked={draft.email_enabled}
                    onCheckedChange={(value) => update("email_enabled", value)}
                  />
                  <FieldContent>
                    <FieldLabel htmlFor="email-enabled">
                      Process requests from this mailbox
                    </FieldLabel>
                    <FieldDescription>
                      Gmail uses imap.gmail.com on port 993.
                    </FieldDescription>
                  </FieldContent>
                </Field>
                <div className="grid gap-5 md:grid-cols-[1fr_9rem]">
                  <TextField
                    id="imap-host"
                    label="IMAP host"
                    value={draft.imap_host}
                    onChange={(value) => update("imap_host", value)}
                  />
                  <NumberField
                    id="imap-port"
                    label="Port"
                    value={draft.imap_port}
                    min={1}
                    max={65535}
                    onChange={(value) => update("imap_port", value)}
                  />
                </div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <TextField
                    id="imap-folder"
                    label="Mailbox folder"
                    value={draft.imap_folder}
                    onChange={(value) => update("imap_folder", value)}
                  />
                  <NumberField
                    id="poll-interval"
                    label="Check interval (seconds)"
                    value={draft.poll_interval_seconds}
                    min={5}
                    max={3600}
                    onChange={(value) => update("poll_interval_seconds", value)}
                  />
                </div>
                <TextField
                  id="imap-username"
                  label="IMAP username"
                  value={draft.imap_username}
                  onChange={(value) => update("imap_username", value)}
                  autoComplete="username"
                />
                <SecretField
                  id="imap-password"
                  label="IMAP password"
                  configured={data.has_imap_password}
                  value={secrets.imap_password}
                  onChange={(value) => updateSecret("imap_password", value)}
                />
              </FieldGroup>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Outgoing SMTP</CardTitle>
              <CardDescription>
                Gmail uses smtp.gmail.com on port 587 with STARTTLS.
              </CardDescription>
              <CardAction>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => runDiagnostic("email")}
                >
                  Test email
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <div className="grid gap-5 md:grid-cols-[1fr_9rem_12rem]">
                  <TextField
                    id="smtp-host"
                    label="SMTP host"
                    value={draft.smtp_host}
                    onChange={(value) => update("smtp_host", value)}
                  />
                  <NumberField
                    id="smtp-port"
                    label="Port"
                    value={draft.smtp_port}
                    min={1}
                    max={65535}
                    onChange={(value) => update("smtp_port", value)}
                  />
                  <SelectField
                    id="smtp-security"
                    label="Security"
                    value={draft.smtp_security}
                    options={[
                      ["starttls", "STARTTLS"],
                      ["tls", "Implicit TLS"],
                    ]}
                    onChange={(value) =>
                      update("smtp_security", value as "starttls" | "tls")
                    }
                  />
                </div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <TextField
                    id="smtp-username"
                    label="SMTP username"
                    value={draft.smtp_username}
                    onChange={(value) => update("smtp_username", value)}
                    autoComplete="username"
                  />
                  <SecretField
                    id="smtp-password"
                    label="SMTP password"
                    configured={data.has_smtp_password}
                    value={secrets.smtp_password}
                    onChange={(value) => updateSecret("smtp_password", value)}
                  />
                </div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <TextField
                    id="smtp-from"
                    label="From address"
                    value={draft.smtp_from}
                    onChange={(value) => update("smtp_from", value)}
                  />
                  <TextField
                    id="smtp-from-name"
                    label="From name"
                    value={draft.smtp_from_name}
                    onChange={(value) => update("smtp_from_name", value)}
                  />
                </div>
              </FieldGroup>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Sender policy</CardTitle>
              <CardDescription>
                Control who may create download jobs through email.
              </CardDescription>
              <CardAction>
                <Badge
                  variant={
                    draft.sender_policy === "any" ? "destructive" : "secondary"
                  }
                >
                  {draft.sender_policy === "any" ? "Any sender" : "Allowlist"}
                </Badge>
              </CardAction>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <Field orientation="horizontal">
                  <Switch
                    id="any-sender"
                    checked={draft.sender_policy === "any"}
                    onCheckedChange={toggleAny}
                  />
                  <FieldContent>
                    <FieldLabel htmlFor="any-sender">
                      Accept requests from any sender
                    </FieldLabel>
                    <FieldDescription>
                      Allowlist mode is strongly recommended.
                    </FieldDescription>
                  </FieldContent>
                </Field>
                <Field>
                  <FieldLabel htmlFor="allowlist">Allowed addresses</FieldLabel>
                  <Input
                    id="allowlist"
                    value={allowlistText}
                    disabled={draft.sender_policy === "any"}
                    placeholder="you@example.com, family@example.com"
                    onChange={(event) => setAllowlistText(event.target.value)}
                  />
                  <FieldDescription>
                    Comma-separated email addresses.
                  </FieldDescription>
                </Field>
                <NumberField
                  id="email-hourly-limit"
                  label="Requests per sender per hour"
                  value={draft.max_email_requests_per_hour}
                  min={1}
                  max={1000}
                  onChange={(value) =>
                    update("max_email_requests_per_hour", value)
                  }
                />
              </FieldGroup>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Reply HTML</CardTitle>
              <CardDescription>
                Customize the HTML sent back for completed, partial, failed, and
                rejected requests.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <TemplateField
                  id="email-success-template"
                  label="Success email"
                  value={draft.email_success_template_html}
                  placeholders={RESULT_TEMPLATE_PLACEHOLDERS}
                  onChange={(value) =>
                    update("email_success_template_html", value)
                  }
                />
                <TemplateField
                  id="email-partial-template"
                  label="Partial success email"
                  value={draft.email_partial_template_html}
                  placeholders={RESULT_TEMPLATE_PLACEHOLDERS}
                  onChange={(value) =>
                    update("email_partial_template_html", value)
                  }
                />
                <TemplateField
                  id="email-failure-template"
                  label="Failed conversion email"
                  value={draft.email_failure_template_html}
                  placeholders={RESULT_TEMPLATE_PLACEHOLDERS}
                  onChange={(value) =>
                    update("email_failure_template_html", value)
                  }
                />
                <TemplateField
                  id="email-error-template"
                  label="Request rejected email"
                  value={draft.email_error_template_html}
                  placeholders={ERROR_TEMPLATE_PLACEHOLDERS}
                  onChange={(value) =>
                    update("email_error_template_html", value)
                  }
                />
              </FieldGroup>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="storage" className="mt-6 flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Delivery and retention</CardTitle>
              <CardDescription>
                Choose attachments, private object links, or a hybrid strategy.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <div className="grid gap-5 sm:grid-cols-3">
                  <SelectField
                    id="delivery-mode"
                    label="Delivery mode"
                    value={draft.delivery_mode}
                    options={[
                      ["links", "S3 links"],
                      ["hybrid", "Hybrid"],
                      ["attachments", "Attachments"],
                    ]}
                    onChange={(value) =>
                      update(
                        "delivery_mode",
                        value as RuntimeSettings["delivery_mode"]
                      )
                    }
                  />
                  <NumberField
                    id="attachment-limit"
                    label="Attachment limit (MiB)"
                    value={draft.max_attachment_mb}
                    min={1}
                    max={24}
                    onChange={(value) => update("max_attachment_mb", value)}
                  />
                  <NumberField
                    id="retention"
                    label="Retention (hours)"
                    value={draft.retention_hours}
                    min={1}
                    max={168}
                    onChange={(value) => update("retention_hours", value)}
                  />
                </div>
              </FieldGroup>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>S3-compatible object storage</CardTitle>
              <CardDescription>
                Supports Cloudflare R2, Amazon S3, MinIO, and compatible
                services.
              </CardDescription>
              <CardAction>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => runDiagnostic("storage")}
                >
                  Test storage
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <SelectField
                  id="storage-backend"
                  label="Storage backend"
                  value={draft.storage_backend}
                  options={[
                    ["local", "Local only"],
                    ["s3", "S3 compatible"],
                  ]}
                  onChange={(value) =>
                    update("storage_backend", value as "local" | "s3")
                  }
                />
                <div className="grid gap-5 sm:grid-cols-2">
                  <TextField
                    id="s3-endpoint"
                    label="Endpoint URL"
                    value={draft.s3_endpoint ?? ""}
                    placeholder="https://account.r2.cloudflarestorage.com"
                    onChange={(value) => update("s3_endpoint", value || null)}
                  />
                  <TextField
                    id="s3-region"
                    label="Region"
                    value={draft.s3_region}
                    onChange={(value) => update("s3_region", value)}
                  />
                </div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <TextField
                    id="s3-bucket"
                    label="Bucket"
                    value={draft.s3_bucket}
                    onChange={(value) => update("s3_bucket", value)}
                  />
                  <TextField
                    id="s3-access-key"
                    label="Access key ID"
                    value={draft.s3_access_key_id}
                    onChange={(value) => update("s3_access_key_id", value)}
                  />
                </div>
                <SecretField
                  id="s3-secret-key"
                  label="Secret access key"
                  configured={data.has_s3_secret_access_key}
                  value={secrets.s3_secret_access_key}
                  onChange={(value) =>
                    updateSecret("s3_secret_access_key", value)
                  }
                />
                <Field orientation="horizontal">
                  <Switch
                    id="s3-path-style"
                    checked={draft.s3_force_path_style}
                    onCheckedChange={(value) =>
                      update("s3_force_path_style", value)
                    }
                  />
                  <FieldContent>
                    <FieldLabel htmlFor="s3-path-style">
                      Force path-style addressing
                    </FieldLabel>
                    <FieldDescription>
                      Commonly required by local MinIO installations.
                    </FieldDescription>
                  </FieldContent>
                </Field>
              </FieldGroup>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="conversion" className="mt-6 flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Capacity and safety limits</CardTitle>
              <CardDescription>
                Keep Raspberry Pi and small-server resource usage bounded.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
                  <NumberField
                    id="concurrency"
                    label="Concurrent jobs"
                    value={draft.max_concurrent_jobs}
                    min={1}
                    max={8}
                    onChange={(value) => update("max_concurrent_jobs", value)}
                  />
                  <NumberField
                    id="batch-limit"
                    label="Links per batch"
                    value={draft.max_urls_per_batch}
                    min={1}
                    max={25}
                    onChange={(value) => update("max_urls_per_batch", value)}
                  />
                  <NumberField
                    id="file-limit"
                    label="Maximum file (MiB)"
                    value={draft.max_file_mb}
                    min={25}
                    max={10240}
                    onChange={(value) => update("max_file_mb", value)}
                  />
                  <NumberField
                    id="duration-limit"
                    label="Maximum duration (sec)"
                    value={draft.max_duration_seconds}
                    min={60}
                    max={86400}
                    onChange={(value) => update("max_duration_seconds", value)}
                  />
                </div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <NumberField
                    id="job-timeout"
                    label="Job timeout (seconds)"
                    value={draft.job_timeout_seconds}
                    min={60}
                    max={86400}
                    onChange={(value) => update("job_timeout_seconds", value)}
                  />
                  <NumberField
                    id="idle-timeout"
                    label="Inactivity timeout (seconds)"
                    value={draft.inactivity_timeout_seconds}
                    min={30}
                    max={3600}
                    onChange={(value) =>
                      update("inactivity_timeout_seconds", value)
                    }
                  />
                </div>
              </FieldGroup>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Default output choices</CardTitle>
              <CardDescription>
                Used when a dashboard or email request does not specify an
                override.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
                  <SelectField
                    id="default-format"
                    label="Format"
                    value={draft.default_format}
                    options={[
                      ["mp4", "MP4"],
                      ["mp3", "MP3"],
                      ["wav", "WAV"],
                    ]}
                    onChange={(value) =>
                      update(
                        "default_format",
                        value as RuntimeSettings["default_format"]
                      )
                    }
                  />
                  <SelectField
                    id="default-mp4"
                    label="MP4 quality"
                    value={draft.default_mp4_quality}
                    options={[
                      "360p",
                      "480p",
                      "720p",
                      "1080p",
                      "1440p",
                      "2160p",
                      "best",
                    ].map((value) => [value, value])}
                    onChange={(value) => update("default_mp4_quality", value)}
                  />
                  <SelectField
                    id="default-mp3"
                    label="MP3 quality"
                    value={draft.default_mp3_quality}
                    options={["128k", "192k", "256k", "320k"].map((value) => [
                      value,
                      value,
                    ])}
                    onChange={(value) => update("default_mp3_quality", value)}
                  />
                  <SelectField
                    id="default-wav"
                    label="WAV quality"
                    value={draft.default_wav_quality}
                    options={[
                      ["44.1khz", "44.1 kHz"],
                      ["48khz", "48 kHz"],
                    ]}
                    onChange={(value) => update("default_wav_quality", value)}
                  />
                </div>
              </FieldGroup>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="access" className="mt-6 flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Administrator account</CardTitle>
              <CardDescription>
                Changing the password does not reveal or reuse the existing one.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <TextField
                  id="admin-username"
                  label="Username"
                  value={draft.admin_username}
                  onChange={(value) => update("admin_username", value)}
                  autoComplete="username"
                />
                <SecretField
                  id="admin-password"
                  label="New password"
                  configured
                  value={secrets.admin_password}
                  onChange={(value) => updateSecret("admin_password", value)}
                />
              </FieldGroup>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Network publication</CardTitle>
              <CardDescription>
                These values describe the current Docker and Tailscale setup.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-5 text-sm sm:grid-cols-2">
                <ReadOnlyValue label="Public URL" value={draft.public_url} />
                <ReadOnlyValue
                  label="Internal container port"
                  value={String(draft.internal_port)}
                />
                <ReadOnlyValue
                  label="Allowed hosts"
                  value={draft.allowed_hosts.join(", ")}
                />
                <ReadOnlyValue
                  label="Session cookies"
                  value={draft.secure_cookies ? "HTTPS only" : "HTTP or HTTPS"}
                />
              </div>
            </CardContent>
            <CardFooter>
              <p className="text-xs text-muted-foreground">
                Run the installer again to safely change host ports, LAN
                binding, Tailscale Serve, allowed hosts, or cookie transport.
                The container intentionally has no Docker-socket access.
              </p>
            </CardFooter>
          </Card>
        </TabsContent>

        <TabsContent value="system" className="mt-6 flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Compatibility and updates</CardTitle>
              <CardDescription>
                Downloader compatibility options and release channel.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <SelectField
                  id="update-channel"
                  label="Update channel"
                  value={draft.update_channel}
                  options={[
                    ["stable", "Stable"],
                    ["off", "Disabled"],
                  ]}
                  onChange={(value) =>
                    update("update_channel", value as "stable" | "off")
                  }
                />
                <TextField
                  id="pot-provider"
                  label="PO-token provider URL"
                  value={draft.pot_provider_url ?? ""}
                  placeholder="http://pot-provider:4416"
                  onChange={(value) =>
                    update("pot_provider_url", value || null)
                  }
                />
                <Field>
                  <FieldLabel htmlFor="youtube-cookies">
                    YouTube cookies
                  </FieldLabel>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <Input
                      id="youtube-cookies"
                      type="file"
                      accept=".txt,text/plain"
                      disabled={cookiesBusy}
                      onChange={(event) =>
                        setCookiesFile(event.target.files?.[0] ?? null)
                      }
                    />
                    <Button
                      type="button"
                      variant="outline"
                      disabled={!cookiesFile || cookiesBusy}
                      onClick={uploadCookies}
                    >
                      {cookiesBusy ? <Spinner /> : <UploadIcon />}
                      Upload
                    </Button>
                    {draft.cookies_configured ? (
                      <Button
                        type="button"
                        variant="outline"
                        disabled={cookiesBusy}
                        onClick={removeCookies}
                      >
                        <Trash2Icon /> Remove
                      </Button>
                    ) : null}
                  </div>
                  <FieldDescription>
                    {draft.cookies_configured
                      ? "A cookies file is configured. Uploading replaces it."
                      : "Upload a Netscape cookies.txt export, up to 2 MiB."}
                  </FieldDescription>
                </Field>
              </FieldGroup>
            </CardContent>
            <CardFooter>
              <div className="space-y-2 text-xs text-muted-foreground">
                <p>
                  Updates are performed by the signed host updater, not by the
                  web container. Run{" "}
                  <code>systemctl --user start mailtube-update.service</code>
                  {" "}on a Linux host to force an installed updater to check
                  now.
                </p>
                <p>
                  Use cookies from a dedicated account. The file grants access
                  to its YouTube session and is stored encrypted at rest only
                  if the Docker volume itself uses disk encryption.
                </p>
              </div>
            </CardFooter>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="mt-8 flex justify-end">
        <Button
          type="button"
          size="lg"
          onClick={() => save()}
          disabled={saving}
        >
          {saving ? <Spinner data-icon="inline-start" /> : <SaveIcon />}
          {saving ? "Applying…" : "Apply all changes"}
        </Button>
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Accept requests from anyone?</AlertDialogTitle>
            <AlertDialogDescription>
              This can expose mailbox, bandwidth, and object-storage resources
              to abuse. Rate, duration, batch, concurrency, and file-size limits
              remain enforced.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep allowlist</AlertDialogCancel>
            <AlertDialogAction onClick={() => update("sender_policy", "any")}>
              Enable any sender
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}

function TextField({
  id,
  label,
  value,
  onChange,
  placeholder,
  autoComplete,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  autoComplete?: string
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        value={value}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  )
}

function TemplateField({
  id,
  label,
  value,
  placeholders,
  onChange,
}: {
  id: string
  label: string
  value: string
  placeholders: string[]
  onChange: (value: string) => void
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Textarea
        id={id}
        value={value}
        spellCheck={false}
        className="min-h-52 resize-y font-mono text-xs leading-relaxed"
        onChange={(event) => onChange(event.target.value)}
      />
      <FieldDescription>
        <span className="mb-2 block">Available placeholders</span>
        <span className="flex flex-wrap gap-2">
          {placeholders.map((placeholder) => (
            <Badge key={placeholder} variant="outline">
              {placeholder}
            </Badge>
          ))}
        </span>
      </FieldDescription>
    </Field>
  )
}

function SecretField({
  id,
  label,
  configured,
  value,
  onChange,
}: {
  id: string
  label: string
  configured: boolean
  value: string
  onChange: (value: string) => void
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        type="password"
        autoComplete="new-password"
        value={value}
        placeholder={
          configured ? "Configured — leave blank to keep" : "Not configured"
        }
        onChange={(event) => onChange(event.target.value)}
      />
      <FieldDescription>
        Stored encrypted; existing values are never returned to the browser.
      </FieldDescription>
    </Field>
  )
}

function NumberField({
  id,
  label,
  value,
  min,
  max,
  onChange,
}: {
  id: string
  label: string
  value: number
  min: number
  max: number
  onChange: (value: number) => void
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </Field>
  )
}

function SelectField({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string
  label: string
  value: string
  options: string[][]
  onChange: (value: string) => void
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {options.map(([optionValue, optionLabel]) => (
              <SelectItem key={optionValue} value={optionValue}>
                {optionLabel}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </Field>
  )
}

function ReadOnlyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-muted/30 p-4">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </p>
      <p className="mt-2 font-mono text-xs break-words">{value || "—"}</p>
    </div>
  )
}

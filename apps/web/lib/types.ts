export type JobState =
  | "queued"
  | "inspecting"
  | "downloading"
  | "processing"
  | "uploading"
  | "ready"
  | "failed"
  | "cancelled"
  | "expired"

export type Job = {
  id: string
  batch_id: string
  source: "web" | "email"
  input_url: string
  video_id: string
  requested_format: "mp4" | "mp3" | "wav"
  requested_quality: string
  actual_format?: string | null
  actual_quality?: string | null
  title?: string | null
  progress: number
  state: JobState
  error_message?: string | null
  created_at: string
  finished_at?: string | null
  expires_at?: string | null
  artifact_id?: string | null
  filename?: string | null
  content_type?: string | null
  size_bytes?: number | null
}

export type Session = {
  username: string
  csrf_token: string
  expires_at: string
}

export type HealthDetails = {
  ok: boolean
  version: string
  database: { ok: boolean; detail: string }
  downloader: { ok: boolean; detail: string }
  javascript: { ok: boolean; detail: string }
  storage: { ok: boolean; detail: string }
  email: { ok: boolean; detail: string }
  disk: { ok: boolean; free_bytes: number; total_bytes: number }
}

export type RuntimeSettings = {
  sender_policy: "allowlist" | "any"
  sender_allowlist: string[]
  retention_hours: number
  max_urls_per_batch: number
  max_concurrent_jobs: number
  email_enabled: boolean
  delivery_mode: string
  storage_backend: string
  update_channel: string
}

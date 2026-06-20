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
  email: {
    ok: boolean
    detail: string
    last_poll_at?: string | null
    last_poll_error?: string | null
    last_poll_message_count?: number
    poll_interval_seconds?: number
  }
  disk: { ok: boolean; free_bytes: number; total_bytes: number }
}

export type RuntimeSettings = {
  admin_username: string
  sender_policy: "allowlist" | "any"
  sender_allowlist: string[]
  retention_hours: number
  max_urls_per_batch: number
  max_concurrent_jobs: number
  max_duration_seconds: number
  max_file_mb: number
  job_timeout_seconds: number
  inactivity_timeout_seconds: number
  default_format: "mp4" | "mp3" | "wav"
  default_mp4_quality: string
  default_mp3_quality: string
  default_wav_quality: string
  email_enabled: boolean
  poll_interval_seconds: number
  imap_host: string
  imap_port: number
  imap_folder: string
  imap_username: string
  smtp_host: string
  smtp_port: number
  smtp_security: "starttls" | "tls"
  smtp_username: string
  smtp_from: string
  smtp_from_name: string
  delivery_mode: "links" | "hybrid" | "attachments"
  max_attachment_mb: number
  max_email_requests_per_hour: number
  storage_backend: "local" | "s3"
  s3_endpoint: string | null
  s3_region: string
  s3_bucket: string
  s3_access_key_id: string
  s3_force_path_style: boolean
  pot_provider_url: string | null
  update_channel: "stable" | "off"
  public_url: string
  allowed_hosts: string[]
  secure_cookies: boolean
  internal_port: number
  cookies_configured: boolean
  has_imap_password: boolean
  has_smtp_password: boolean
  has_s3_secret_access_key: boolean
}

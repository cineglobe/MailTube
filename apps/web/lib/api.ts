import type { Session } from "@/lib/types"

const CSRF_KEY = "mailtube-csrf"

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number
  ) {
    super(message)
  }
}

export function rememberSession(session: Session) {
  sessionStorage.setItem(CSRF_KEY, session.csrf_token)
}

export function clearSession() {
  sessionStorage.removeItem(CSRF_KEY)
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json")
  if (init.method && !["GET", "HEAD"].includes(init.method.toUpperCase())) {
    const csrf = sessionStorage.getItem(CSRF_KEY)
    if (csrf) headers.set("X-CSRF-Token", csrf)
  }
  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "same-origin",
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string
    } | null
    throw new ApiError(
      body?.detail || `Request failed (${response.status})`,
      response.status
    )
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function fetcher<T>(path: string): Promise<T> {
  return apiFetch<T>(path)
}

export function formatBytes(value?: number | null) {
  if (!value) return "—"
  const units = ["B", "KB", "MB", "GB"]
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

export function formatDate(value?: string | null) {
  if (!value) return "—"
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

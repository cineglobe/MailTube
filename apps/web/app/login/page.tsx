"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { ArrowRightIcon, LockKeyholeIcon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { apiFetch, rememberSession } from "@/lib/api"
import type { Session } from "@/lib/types"

export default function LoginPage() {
  const router = useRouter()
  const [username, setUsername] = useState("admin")
  const [password, setPassword] = useState("")
  const [pending, setPending] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    try {
      const session = await apiFetch<Session>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      })
      rememberSession(session)
      router.replace("/convert/")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not sign in")
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="grid min-h-svh lg:grid-cols-[1.15fr_0.85fr]">
      <section className="editorial-rule flex min-h-[42svh] flex-col justify-between border-b p-7 sm:p-12 lg:min-h-svh lg:border-r lg:border-b-0">
        <div className="display-title text-4xl">MailTube</div>
        <div className="max-w-3xl py-14">
          <h1 className="display-title text-6xl leading-[0.98] sm:text-7xl xl:text-8xl">
            Your media stays yours.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
            A private conversion desk for your home network. No accounts,
            analytics, or third-party conversion service.
          </p>
        </div>
        <p className="text-xs text-muted-foreground">
          Self-hosted · Local-first · AGPL-3.0
        </p>
      </section>
      <section className="flex items-center px-7 py-14 sm:px-12 lg:px-16">
        <form onSubmit={submit} className="w-full max-w-md">
          <LockKeyholeIcon className="mb-7" aria-hidden="true" />
          <h2 className="font-heading text-4xl">Administrator sign in</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            Use the local credentials created by the MailTube setup wizard.
          </p>
          <FieldGroup className="mt-8">
            <Field>
              <FieldLabel htmlFor="username">Username</FieldLabel>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <FieldDescription>
                Login attempts are rate-limited.
              </FieldDescription>
            </Field>
            <Button type="submit" size="lg" disabled={pending}>
              {pending ? <Spinner data-icon="inline-start" /> : null}
              Sign in
              {!pending ? <ArrowRightIcon data-icon="inline-end" /> : null}
            </Button>
          </FieldGroup>
        </form>
      </section>
    </main>
  )
}

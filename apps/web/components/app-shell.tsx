"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { ChevronDownIcon, LogOutIcon, UserRoundIcon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { apiFetch, clearSession } from "@/lib/api"
import { cn } from "@/lib/utils"

const navigation = [
  { href: "/convert/", label: "Convert" },
  { href: "/history/", label: "History" },
  { href: "/settings/", label: "Settings" },
  { href: "/health/", label: "Health" },
] as const

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()

  async function logout() {
    try {
      await apiFetch<void>("/api/v1/auth/logout", { method: "POST" })
      clearSession()
      router.replace("/login/")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not sign out")
    }
  }

  return (
    <div className="flex min-h-svh flex-col">
      <header className="editorial-rule border-b">
        <div className="flex min-h-16 flex-wrap items-stretch px-5 sm:min-h-20 sm:flex-nowrap sm:gap-5 md:gap-10 md:px-10">
          <Link
            href="/convert/"
            className="display-title flex flex-1 items-center text-3xl sm:flex-none md:text-4xl"
          >
            MailTube
          </Link>
          <nav
            className="order-3 -mx-5 flex min-w-0 basis-[calc(100%+2.5rem)] items-stretch border-t sm:order-none sm:mx-0 sm:flex-1 sm:basis-auto sm:border-t-0"
            aria-label="Primary navigation"
          >
            {navigation.map((item) => {
              const active = pathname.startsWith(item.href)
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "relative flex flex-1 items-center justify-center px-1 py-3 text-xs font-medium whitespace-nowrap transition-colors sm:flex-none sm:px-3 sm:py-0 sm:text-sm md:px-5 md:text-base",
                    active
                      ? "text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                    active &&
                      "after:absolute after:inset-x-3 after:bottom-0 after:h-1 after:bg-primary md:after:inset-x-5"
                  )}
                >
                  {item.label}
                </Link>
              )
            })}
          </nav>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                className="my-auto"
                aria-label="Admin menu"
              >
                <UserRoundIcon data-icon="inline-start" />
                <span className="hidden sm:inline">Admin</span>
                <ChevronDownIcon
                  className="hidden sm:block"
                  data-icon="inline-end"
                />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Local administrator</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuItem onSelect={logout}>
                  <LogOutIcon /> Sign out
                </DropdownMenuItem>
              </DropdownMenuGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>
      <main className="min-h-0 flex-1">{children}</main>
      <footer className="editorial-rule border-t px-5 py-5 text-xs text-muted-foreground md:px-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p>MailTube · Self-hosted · No telemetry</p>
          <div className="flex gap-5">
            <Link href="/health/">System health</Link>
            <Link href="/settings/">Instance settings</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

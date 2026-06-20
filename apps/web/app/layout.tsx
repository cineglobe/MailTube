import "@fontsource-variable/fraunces/wght.css"
import "@fontsource-variable/ibm-plex-sans/wght.css"
import "@fontsource/ibm-plex-mono/400.css"
import type { Metadata } from "next"

import { ThemeProvider } from "@/components/theme-provider"
import { Toaster } from "@/components/ui/sonner"

import "./globals.css"

export const metadata: Metadata = {
  title: "MailTube",
  description: "Private, self-hosted YouTube conversion for web and email.",
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider>
          {children}
          <Toaster position="bottom-right" richColors closeButton />
        </ThemeProvider>
      </body>
    </html>
  )
}

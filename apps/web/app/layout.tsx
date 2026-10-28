import type { Metadata } from "next"

import { Providers } from "@/components/layout/providers"

import "./globals.css"

export const metadata: Metadata = {
  title: { default: "Orchestrator", template: "%s · Orchestrator" },
  description: "Enterprise AI orchestration platform",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className="h-full antialiased">
      <body className="min-h-full bg-background text-foreground">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}

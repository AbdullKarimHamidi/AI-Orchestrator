export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center bg-muted/40 p-4">
      <div className="flex w-full flex-col items-center gap-6">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <span className="grid size-7 place-items-center rounded bg-primary text-xs text-primary-foreground">O</span>
          Orchestrator
        </div>
        {children}
      </div>
    </main>
  )
}

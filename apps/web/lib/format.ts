export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "—"
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return `${Math.max(0, Math.round(diff))}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return fmtDate(iso)
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—"
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`
}

export function fmtUsd(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—"
  return v === 0 ? "$0.00" : v < 0.01 ? `$${v.toFixed(5)}` : `$${v.toFixed(2)}`
}

export function fmtInt(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : v.toLocaleString()
}

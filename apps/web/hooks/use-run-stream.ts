"use client"

import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"

import { streamUrl } from "@/lib/api-client"
import { runEventSchema, type RunEvent } from "@/lib/schemas"

type StreamState = "connecting" | "open" | "ended" | "error"

/** Live run events over SSE. EventSource reconnects automatically and resends
 * Last-Event-ID, which the API uses to resume without duplicates. */
export function useRunStream(runId: string, workspaceId: string | null, enabled = true) {
  const key = `${workspaceId}:${runId}`
  // State is tagged with the stream key so switching runs never shows stale events
  // (and no synchronous reset inside the effect is needed).
  const [store, setStore] = useState<{ key: string; events: RunEvent[]; state: StreamState }>({ key, events: [], state: "connecting" })
  const seen = useRef(new Set<number>())
  const qc = useQueryClient()

  useEffect(() => {
    if (!enabled || !workspaceId || !runId) return
    seen.current = new Set()
    const setState = (st: StreamState) => setStore((p) => (p.key === key ? { ...p, state: st } : { key, events: [], state: st }))
    const es = new EventSource(streamUrl(`/runs/${runId}/stream`))
    es.onopen = () => setState("open")
    es.addEventListener("run_event", (msg) => {
      const parsed = runEventSchema.safeParse(JSON.parse((msg as MessageEvent).data))
      if (!parsed.success || seen.current.has(parsed.data.seq)) return
      seen.current.add(parsed.data.seq)
      setStore((p) => {
        const base = p.key === key ? p : { key, events: [], state: "open" as StreamState }
        return { ...base, events: [...base.events, parsed.data].sort((a, b) => a.seq - b.seq) }
      })
      qc.invalidateQueries({ queryKey: ["run", workspaceId, runId] })
    })
    es.addEventListener("end", () => {
      setState("ended")
      es.close()
      qc.invalidateQueries({ queryKey: ["run", workspaceId, runId] })
      qc.invalidateQueries({ queryKey: ["runs", workspaceId] })
    })
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) setState("error")
    }
    return () => es.close()
  }, [key, runId, workspaceId, enabled, qc])

  return store.key === key ? { events: store.events, state: store.state } : { events: [] as RunEvent[], state: "connecting" as StreamState }
}

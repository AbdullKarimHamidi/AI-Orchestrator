export type CaseRow = { id: string; input: string; expected: string }

/** Accepts a JSON array, JSON Lines, or "input | expected" lines. */
export function parseCases(text: string): CaseRow[] {
  const t = text.trim()
  if (!t) return []
  const toRow = (o: Record<string, unknown>, i: number): CaseRow => ({
    id: String(o.id ?? `case_${i + 1}`),
    input: String(o.input ?? o.question ?? ""),
    expected: String(o.expected ?? o.answer ?? ""),
  })
  if (t.startsWith("[")) return (JSON.parse(t) as Record<string, unknown>[]).map(toRow)
  if (t.startsWith("{")) return t.split("\n").filter((l) => l.trim()).map((l, i) => toRow(JSON.parse(l), i))
  return t.split("\n").filter((l) => l.trim()).map((l, i) => {
    const [input, ...rest] = l.split("|")
    return { id: `case_${i + 1}`, input: input.trim(), expected: rest.join("|").trim() }
  })
}

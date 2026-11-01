/** Turns the project's files into one HTML document for a sandboxed preview iframe.
 * Local stylesheets, scripts and images referenced by the page are inlined, because the iframe has
 * no server to fetch them from. CDN links are left alone. */

export type PreviewFile = { path: string; content: string }

const MIME: Record<string, string> = { svg: "image/svg+xml", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", webp: "image/webp", json: "application/json" }

export function previewEntry(files: PreviewFile[]): PreviewFile | undefined {
  const html = files.filter((f) => f.path.toLowerCase().endsWith(".html"))
  return html.find((f) => f.path === "web/index.html") ?? html.find((f) => f.path.endsWith("/index.html") || f.path === "index.html") ?? html[0]
}

function resolve(from: string, ref: string): string | null {
  if (/^(?:[a-z][a-z0-9+.-]*:|\/\/|#|data:)/i.test(ref)) return null
  const clean = ref.split(/[?#]/)[0]
  const base = clean.startsWith("/") ? [] : from.split("/").slice(0, -1)
  for (const part of clean.replace(/^\//, "").split("/")) {
    if (part === "" || part === ".") continue
    if (part === "..") base.pop()
    else base.push(part)
  }
  return base.join("/")
}

const escAttr = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;")

export function buildPreview(files: PreviewFile[]): string | null {
  const entry = previewEntry(files)
  if (!entry) return null
  const byPath = new Map(files.map((f) => [f.path, f.content]))
  const find = (ref: string) => {
    const p = resolve(entry.path, ref)
    return p != null && byPath.has(p) ? { path: p, content: byPath.get(p)! } : null
  }
  let html = entry.content
  html = html.replace(/<link\b[^>]*?href=["']([^"']+)["'][^>]*>/gi, (tag, href: string) => {
    if (!/stylesheet/i.test(tag)) return tag
    const f = find(href)
    return f ? `<style data-file="${escAttr(f.path)}">\n${f.content}\n</style>` : tag
  })
  html = html.replace(/<script\b([^>]*?)\bsrc=["']([^"']+)["']([^>]*)>\s*<\/script>/gi, (tag, pre: string, src: string, post: string) => {
    const f = find(src)
    if (!f) return tag
    const attrs = `${pre} ${post}`.replace(/\s+/g, " ").trim()
    return `<script ${attrs} data-file="${escAttr(f.path)}">\n${f.content.replace(/<\/script/gi, "<\\/script")}\n</script>`
  })
  html = html.replace(/(<img\b[^>]*?\bsrc=["'])([^"']+)(["'])/gi, (tag, a: string, src: string, b: string) => {
    const f = find(src)
    const ext = f?.path.split(".").pop()?.toLowerCase() ?? ""
    if (!f || ext !== "svg") return tag
    return `${a}data:${MIME.svg};charset=utf-8,${encodeURIComponent(f.content)}${b}`
  })
  return html
}

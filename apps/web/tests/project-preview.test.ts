import { describe, expect, it } from "vitest"

import { buildPreview, previewEntry } from "@/lib/project-preview"

describe("project preview", () => {
  const files = [
    { path: "backend/app.py", content: "print(1)" },
    { path: "web/index.html", content: '<html><head><link rel="stylesheet" href="style.css"><link rel="stylesheet" href="https://cdn.example/x.css"></head><body><img src="./logo.svg"><script src="js/app.js"></script><script src="https://cdn.example/lib.js"></script></body></html>' },
    { path: "web/style.css", content: "h1{color:red}" },
    { path: "web/js/app.js", content: "document.title='x'</script>" },
    { path: "web/logo.svg", content: "<svg></svg>" },
  ]
  it("picks web/index.html as the entry page", () => {
    expect(previewEntry(files)?.path).toBe("web/index.html")
    expect(buildPreview([{ path: "a.md", content: "" }])).toBeNull()
  })
  it("inlines local css, js and svg and keeps CDN links", () => {
    const html = buildPreview(files)!
    expect(html).toContain('<style data-file="web/style.css">')
    expect(html).toContain("h1{color:red}")
    expect(html).toContain('data-file="web/js/app.js"')
    expect(html).toContain("<\\/script>")
    expect(html).toContain("https://cdn.example/x.css")
    expect(html).toContain('<script src="https://cdn.example/lib.js"></script>')
    expect(html).toContain("data:image/svg+xml")
  })
})

import axe from "axe-core"

/** Runs axe-core against a rendered container and returns violation summaries.
 * color-contrast is disabled because jsdom does not compute styles. */
export async function axeViolations(container: Element): Promise<string[]> {
  const res = await axe.run(container, { rules: { "color-contrast": { enabled: false } } })
  return res.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)
}

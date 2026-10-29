import {
  Activity, BarChart3, Bot, Boxes, BrainCircuit, Cpu, FlaskConical, GitBranch, KeyRound, LayoutDashboard, FolderKanban,
  Library, Plug, Settings, Shield, Wrench, type LucideIcon,
} from "lucide-react"

export interface NavItem {
  href: string
  label: string
  icon: LucideIcon
  /** "available" modules are backed by real FastAPI endpoints; others render an honest in-development page. */
  status: "available" | "partial" | "in_development"
}

export const NAV_SECTIONS: { title: string; items: NavItem[] }[] = [
  { title: "Overview", items: [{ href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, status: "available" }] },
  {
    title: "Build",
    items: [
      { href: "/agents", label: "Agents", icon: Bot, status: "available" },
      { href: "/workflows", label: "Workflows", icon: GitBranch, status: "available" },\n      { href: "/projects", label: "Project Creator", icon: FolderKanban, status: "available" },
      { href: "/tools", label: "Tools", icon: Wrench, status: "available" },
      { href: "/integrations", label: "Integrations", icon: Plug, status: "available" },
      { href: "/knowledge", label: "Knowledge", icon: Library, status: "available" },
      { href: "/memory", label: "Memory", icon: BrainCircuit, status: "available" },
    ],
  },
  {
    title: "Operate",
    items: [
      { href: "/runs", label: "Runs", icon: Activity, status: "available" },
      { href: "/models", label: "Models", icon: Cpu, status: "available" },
      { href: "/analytics", label: "Analytics", icon: BarChart3, status: "available" },
      { href: "/evaluations", label: "Evaluations", icon: FlaskConical, status: "available" },
    ],
  },
  {
    title: "Govern",
    items: [
      { href: "/security", label: "Security", icon: Shield, status: "available" },
      { href: "/settings", label: "Settings", icon: Settings, status: "available" },
    ],
  },
]

export const ICONS = { Boxes, KeyRound }

const LABELS: Record<string, string> = {
  dashboard: "Dashboard", agents: "Agents", new: "New", edit: "Edit", versions: "Versions", test: "Test console",
  workflows: "Workflows", projects: "Project Creator", runs: "Runs", models: "Models", tools: "Tools", integrations: "Integrations", mcp: "MCP",
  knowledge: "Knowledge", bases: "Bases", documents: "Documents", memory: "Memory", security: "Security",
  users: "Users", roles: "Roles", account: "Account", "api-keys": "API keys", invite: "Invitation", audit: "Audit log", settings: "Settings", workspace: "Workspace", billing: "Billing",
  analytics: "Analytics", evaluations: "Evaluations", datasets: "Datasets", compare: "Compare",
}

export function breadcrumbsFor(pathname: string): { href: string; label: string }[] {
  const parts = pathname.split("/").filter(Boolean)
  return parts.map((p, i) => ({ href: "/" + parts.slice(0, i + 1).join("/"), label: LABELS[p] ?? (p.length > 14 ? p.slice(0, 10) + "…" : p) }))
}

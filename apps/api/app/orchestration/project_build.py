"""Project build: turns an approved project plan into a team of agents that writes the project.

Pure helpers (no database) so they can be unit tested:

- ``build_definition`` makes the workflow: a main agent (director) hands tasks to task coordinators
  (team leads), each lead hands them to its team's agents (UI, backend, database, ...), and plan
  reviewers check the work against the plan before the director delivers. A final plan check step
  reports whether the delivered project matches the plan.
- ``build_brief`` is the message the director receives: the file protocol, the plan, the current
  files and the user's change request.
- ``extract_files`` reads the files the agents wrote out of their replies.

Agents write every file as a fenced block whose info string names the path::

    ```file:web/index.html
    <!doctype html>...
    ```
"""
from __future__ import annotations

import re
from typing import Any

TEAM_KINDS = {
    "ui": "UI / frontend",
    "backend": "Backend",
    "database": "Database",
    "other": "Specialists",
}

FILE_PROTOCOL = """HOW TO DELIVER WORK (every agent must follow this):
- Write every file in full, each in its own fenced block whose first line names the path, exactly like:
```file:web/index.html
<!doctype html>
...
```
- Paths are relative to the project root. Never shorten a file with "..." or "rest unchanged": a file you \
send replaces the old one completely.
- The browser UI lives in web/: web/index.html plus web/*.css and web/*.js, plain HTML/CSS/JavaScript that \
runs without a build step (libraries may be loaded from a CDN). This is what the live preview shows.
- Backend code goes in backend/, database schema, migrations and seed data in database/.
- After the files, add a short note of what you did and anything left open."""

REVIEWER_ROLE = ("Plan compliance reviewer. Compare the work you are given with the project plan. List every "
                 "requirement that is missing, wrong or incomplete, file by file, and say exactly what to fix. "
                 "End with 'VERDICT: COMPLETE' or 'VERDICT: INCOMPLETE'.")
DIRECTOR_ROLE = ("Main agent. Owns the plan, splits it into tasks for the team coordinators, has the plan "
                 "reviewers check the results, sends fixes back, and delivers the finished project.")

_FENCE = re.compile(
    r"^```[ \t]*(?:file:[ \t]*(?P<p1>[^\s`]+)|[\w+#.-]*[ \t]+(?:file|path|filename)=[\"']?(?P<p2>[^\s\"'`]+)[\"']?)"
    r"[^\n]*\n(?P<body>.*?)^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_.\-/]{1,200}$")
MAX_FILES = 200
MAX_FILE_CHARS = 200_000


def clean_path(path: str) -> str | None:
    p = path.strip().strip("/").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if not p or not _SAFE_PATH.match(p) or any(part in ("", ".", "..") for part in p.split("/")):
        return None
    return p


def extract_files(text: str) -> dict[str, str]:
    """Files written in ``file:`` fenced blocks, later blocks for the same path winning."""
    files: dict[str, str] = {}
    for m in _FENCE.finditer(text or ""):
        path = clean_path(m.group("p1") or m.group("p2") or "")
        if path and len(files) < MAX_FILES:
            files[path] = m.group("body")[:MAX_FILE_CHARS]
    return files


def file_steps(definition: dict) -> list[str]:
    """Step ids whose replies hold project files, supervisors first."""
    steps = [s for s in definition.get("steps") or [] if s.get("role") != REVIEWER_ROLE]
    return [s["id"] for s in steps if s["type"] == "supervisor"] + [s["id"] for s in steps if s["type"] == "agent"]


def files_from_output(output: dict[str, Any] | None, order: list[str]) -> dict[str, str]:
    """Collects files from a finished build run, reading the step outputs in ``order``: the director
    and coordinators first, then the agents who wrote the files, whose latest version wins. Reviewer
    steps are left out of ``order`` so code quoted in a review never becomes a project file."""
    if not output:
        return {}
    files: dict[str, str] = {}
    steps = output.get("steps") or {}
    for sid in order:
        out = steps.get(sid)
        if isinstance(out, dict):
            files.update(extract_files(str(out.get("text") or "")))
    return files


def _slug(value: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    base = re.sub(r"^[^a-z]+", "", base)[:30] or "step"
    sid, n = base, 2
    while sid in taken or sid == "end":
        sid = f"{base[:27]}_{n}"
        n += 1
    taken.add(sid)
    return sid


def build_definition(project: dict, agent_names: dict[str, str]) -> dict:
    """The workflow definition (dict, validated later by WorkflowDefinition) for a project build."""
    director_id = project.get("director_agent_id") or (project.get("supervisor_agent_ids") or [None])[0] \
        or (project.get("planning_agent_ids") or [None])[0]
    if not director_id:
        raise ValueError("Choose a main agent for the build")
    model = project.get("planning_model")
    model_ref = {"provider_id": model["provider_id"], "model": model["model"]} if model else None
    taken: set[str] = set()
    steps: list[dict] = []

    def step(kind: str, sid: str, agent_id: str, name: str, role: str, **extra: Any) -> dict:
        s = {"id": sid, "type": kind, "name": name[:120], "agent_id": agent_id, "role": role[:1000], **extra}
        if model_ref:
            s["model"] = model_ref
        steps.append(s)
        return s

    director = step("supervisor", _slug("director", taken), director_id, "Main agent", DIRECTOR_ROLE,
                    message="{{ input.message }}", delegates=[], max_rounds=4, parallelism=8)
    for team in project.get("teams") or []:
        agents = [a for a in team.get("agent_ids") or [] if a]
        if not agents:
            continue
        label = team.get("name") or TEAM_KINDS.get(team.get("kind") or "other", "Team")
        role = f"{TEAM_KINDS.get(team.get('kind') or 'other', 'Team')} team: {team.get('responsibility') or ''}"
        lead_agent = team.get("lead_agent_id")
        if len(agents) == 1 and not lead_agent:
            member = step("agent", _slug(label, taken), agents[0], label, role)
            director["delegates"].append(member["id"])
            continue
        lead = step("supervisor", _slug(f"{label}_coordinator", taken), lead_agent or director_id,
                    f"{label} coordinator", f"Task coordinator for the {label} team. Splits the director's task "
                    f"between the team's agents, checks their files fit together, returns all files. {role}",
                    delegates=[], max_rounds=2, parallelism=max(1, min(50, int(team.get("parallelism") or 5))))
        director["delegates"].append(lead["id"])
        for i, agent_id in enumerate(agents):
            name = f"{label} · {agent_names.get(agent_id, f'agent {i + 1}')}" if len(agents) > 1 else label
            member = step("agent", _slug(f"{label}_{i + 1}", taken), agent_id, name, role)
            lead["delegates"].append(member["id"])
    reviewers = [r for r in project.get("reviewer_agent_ids") or [] if r]
    for i, agent_id in enumerate(reviewers):
        r = step("agent", _slug(f"plan_reviewer_{i + 1}", taken), agent_id, f"Plan reviewer {i + 1}", REVIEWER_ROLE)
        director["delegates"].append(r["id"])
    if not director["delegates"]:
        raise ValueError("Add at least one team with agents before starting the build")
    if len(steps) >= 50:
        raise ValueError("A build can have at most 48 agents; make the teams smaller")
    if reviewers:
        check = step("agent", _slug("plan_check", taken), reviewers[0], "Final plan check", REVIEWER_ROLE,
                     message="Check the delivered project against the plan and report what is done and missing.\n\n"
                             "<plan_and_brief>\n{{ input.message }}\n</plan_and_brief>\n\n"
                             "<delivered>\n{{ steps.director.text }}\n</delivered>")
        director["next"] = check["id"]
        check["next"] = "end"
    else:
        director["next"] = "end"
    return {"steps": steps, "max_step_executions": 60, "max_delegations": 300}


def build_brief(project: dict, files: dict[str, str], instructions: str) -> str:
    approved = [d for d in project.get("documents") or [] if d.get("status") == "approved"]
    docs = approved or list(project.get("documents") or [])
    plan = "\n\n".join(f"## {d.get('title', '')}\n{d.get('content', '')}" for d in docs)[:30_000]
    teams = "\n".join(f"- {t.get('name')}: {TEAM_KINDS.get(t.get('kind') or 'other')}, {t.get('responsibility', '')}"
                      for t in project.get("teams") or [])
    parts = [FILE_PROTOCOL, f"PROJECT: {project['name']}\n\nIDEA:\n{project['idea']}",
             f"APPROVED PLAN:\n{plan or '(no plan documents yet; work from the idea)'}"]
    if teams:
        parts.append(f"TEAMS:\n{teams}")
    if files:
        listing = "\n".join(f"- {p} ({len(c)} chars)" for p, c in sorted(files.items()))
        current = "".join(f"\n```file:{p}\n{c}\n```\n" for p, c in sorted(files.items()))
        if len(current) > 40_000:
            current = "\n(Files are too large to include in full; ask the owning team to resend what they change.)"
        parts.append(f"CURRENT PROJECT FILES (already built; change only what is needed):\n{listing}\n{current}")
    parts.append("WHAT TO DO NOW:\n" + (instructions.strip() or
                 "Build the complete project from the plan. Hand the UI, backend and database work to the "
                 "coordinators in parallel, have the plan reviewers check the result, fix what they find, then "
                 "deliver every file."))
    return "\n\n".join(parts)

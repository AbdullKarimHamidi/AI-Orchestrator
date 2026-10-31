"""Hierarchical teams: a supervisor agent plans, delegates tasks to team members, reviews their
results and delivers the final answer. Pure helpers (prompts and parsing) live here so they can be
tested without a database; the execution loop is ``WorkflowExecutor._supervise``.

Protocol: every round the supervisor replies with JSON, either
``{"thoughts": "...", "tasks": [{"to": "<member id>", "task": "..."}]}`` to delegate (tasks of one
round run in parallel) or ``{"thoughts": "...", "final": "..."}`` to finish. A reply that is not
JSON is taken as the final answer, so a supervisor never gets stuck on formatting.
"""
import json
from dataclasses import dataclass, field

RESULT_CHARS = 6000  # per member result shown to the supervisor
TASK_CHARS = 8000


@dataclass
class Member:
    id: str
    name: str
    role: str
    leads_team: bool = False


@dataclass
class Task:
    to: str
    task: str


@dataclass
class Decision:
    thoughts: str = ""
    tasks: list[Task] = field(default_factory=list)
    final: str | None = None
    raw_was_json: bool = True


@dataclass
class Report:
    round: int
    to: str
    task: str
    ok: bool
    text: str


PROTOCOL = """You are the lead of a team of AI agents working together on one project. Do not do the \
work yourself. Split it into concrete tasks, delegate each task to the best-suited team member, \
review what they send back, then either delegate follow-up tasks (fixes, integration, review) or \
deliver the final result.

Team members (use the id exactly as written):
{roster}

Reply with JSON only, no other text, in exactly one of these two shapes:
{{"thoughts": "your short plan", "tasks": [{{"to": "<member id>", "task": "complete, self-contained instructions"}}]}}
{{"thoughts": "why you are done", "final": "the complete final deliverable for the user"}}

Rules:
- Tasks in the same reply run in parallel, so they must not depend on each other. Put dependent work \
in a later round.
- Members only see the task text you write: include every requirement, name, interface and \
constraint they need.
- You may give several tasks to the same member in one reply.
- The final deliverable must merge the members' work into one complete answer, not a summary of who \
did what.
This is round {round} of at most {max_rounds}.{last_round}"""

LAST_ROUND = " Delegation is over: reply with \"final\" now, using the results you have."
LAST_DELEGATION = " This is the last round in which you can delegate; next you must deliver \"final\"."


def roster_text(members: list[Member]) -> str:
    lines = []
    for m in members:
        lead = " (leads a sub-team; give it a whole area of work)" if m.leads_team else ""
        role = f": {m.role}" if m.role else ""
        lines.append(f'- "{m.id}" ({m.name}){lead}{role}')
    return "\n".join(lines)


def supervisor_message(brief: str, members: list[Member], reports: list[Report], round_: int,
                       max_rounds: int, force_final: bool = False) -> str:
    head = PROTOCOL.format(roster=roster_text(members), round=round_, max_rounds=max_rounds,
                           last_round=LAST_ROUND if force_final else LAST_DELEGATION if round_ >= max_rounds else "")
    parts = [head, f"<project_brief>\n{brief}\n</project_brief>"]
    if reports:
        done = []
        for r in reports:
            status = "done" if r.ok else "FAILED"
            text = r.text if len(r.text) <= RESULT_CHARS else r.text[:RESULT_CHARS] + "\n[...truncated]"
            done.append(f'<result round="{r.round}" member="{r.to}" status="{status}">\n'
                        f"<task>{r.task[:1000]}</task>\n{text}\n</result>")
        parts.append("Results from your team so far:\n" + "\n".join(done))
    return "\n\n".join(parts)


def fallback_final(reports: list[Report]) -> str:
    """When a supervisor will not finish, deliver its team's latest successful work."""
    latest: dict[str, Report] = {}
    for r in reports:
        if r.ok:
            latest[r.to] = r
    return "\n\n".join(f"## {r.to}\n{r.text}" for r in latest.values())


def member_message(brief: str, task: str, member: Member, lead_name: str) -> str:
    role = f"\nYour role on the team: {member.role}" if member.role else ""
    return (f"You are {member.name}, a member of a team led by {lead_name}.{role}\n\n"
            f"Your assignment:\n{task}\n\n"
            f"Context, the overall project brief (do only your assignment):\n<project_brief>\n{brief[:TASK_CHARS]}\n"
            "</project_brief>\n\nReply with your complete work product.")


def _find_json(text: str) -> object:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("\n") + 1:] if "\n" in t else t
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object")
    try:  # the whole remainder first, then the outermost braces
        return json.loads(t[start:])
    except ValueError:
        return json.loads(t[start:t.rfind("}") + 1])


def parse_decision(text: str, member_ids: set[str]) -> Decision:
    """Reads a supervisor reply. Unknown member ids are kept (they come back as failed results so
    the supervisor can correct itself); empty tasks are dropped."""
    try:
        data = _find_json(text)
    except ValueError:
        return Decision(final=text.strip(), raw_was_json=False)
    if not isinstance(data, dict):
        return Decision(final=text.strip(), raw_was_json=False)
    thoughts = str(data.get("thoughts") or data.get("plan") or "")[:2000]
    tasks: list[Task] = []
    raw_tasks = data.get("tasks") or data.get("delegate") or []
    if isinstance(raw_tasks, list):
        for t in raw_tasks:
            if not isinstance(t, dict):
                continue
            to = str(t.get("to") or t.get("member") or t.get("agent") or "").strip().strip('"')
            body = t.get("task") or t.get("instructions") or t.get("instruction") or ""
            body = body if isinstance(body, str) else json.dumps(body)
            if to and body.strip():
                tasks.append(Task(to=to, task=body.strip()[:TASK_CHARS]))
    final = data.get("final")
    if final is not None and not isinstance(final, str):
        final = json.dumps(final, indent=2)
    if tasks:
        return Decision(thoughts=thoughts, tasks=tasks)
    if final and final.strip():
        return Decision(thoughts=thoughts, final=final.strip())
    return Decision(thoughts=thoughts, final=text.strip(), raw_was_json=False)


def resolve_member(name: str, members: list[Member]) -> Member | None:
    """Exact id first, then a case-insensitive id or display-name match (models paraphrase)."""
    by_id = {m.id: m for m in members}
    if name in by_id:
        return by_id[name]
    low = name.lower()
    for m in members:
        if m.id.lower() == low or m.name.lower() == low:
            return m
    return None

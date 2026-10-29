from fastapi import APIRouter

from app.api.v1 import (
    agents,
    auth,
    billing,
    evaluations,
    health,
    knowledge,
    memory,
    projects,
    providers,
    runs,
    tools,
    workflows,
    workspaces,
)

api_router = APIRouter(prefix="/api/v1")
for r in (
    health.router, auth.router, workspaces.router, agents.router, providers.router, runs.router,
    tools.router, knowledge.router, workflows.router, projects.router,
    evaluations.router, memory.router, billing.router,
):
    api_router.include_router(r)

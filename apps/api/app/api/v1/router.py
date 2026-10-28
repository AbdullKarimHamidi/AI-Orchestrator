from fastapi import APIRouter

from app.api.v1 import agents, auth, health, knowledge, providers, runs, tools, workspaces

api_router = APIRouter(prefix="/api/v1")
for r in (health.router, auth.router, workspaces.router, agents.router, providers.router, runs.router,
          tools.router, knowledge.router):
    api_router.include_router(r)

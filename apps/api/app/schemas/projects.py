"""Schemas for durable, workspace-scoped AI project planning and teams."""
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.schemas.agents import ModelRef
from app.schemas.common import ApiModel, OutModel

ProjectStatus = Literal["planning", "ready", "in_progress", "blocked", "completed", "archived"]
DocumentStatus = Literal["draft", "in_review", "approved", "superseded"]


class SpecialistTeam(ApiModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    responsibility: str = Field(min_length=1, max_length=1000)
    agent_ids: list[str] = Field(default_factory=list, max_length=100)
    parallelism: int = Field(default=5, ge=1, le=100)


class ProjectCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    idea: str = Field(min_length=10, max_length=20000)
    description: str = Field(default="", max_length=4000)
    planning_agent_ids: list[str] = Field(min_length=1, max_length=2)
    supervisor_agent_ids: list[str] = Field(default_factory=list, max_length=3)
    teams: list[SpecialistTeam] = Field(default_factory=list, max_length=30)
    # Provider and model the planning agents run on. None keeps each agent's own published model.
    planning_model: ModelRef | None = None

    @model_validator(mode="after")
    def unique_assignments(self):
        if len(set(self.planning_agent_ids)) != len(self.planning_agent_ids):
            raise ValueError("planning_agent_ids must be unique")
        if len(set(self.supervisor_agent_ids)) != len(self.supervisor_agent_ids):
            raise ValueError("supervisor_agent_ids must be unique")
        ids = [team.id for team in self.teams]
        if len(set(ids)) != len(ids):
            raise ValueError("team ids must be unique")
        return self


class ProjectUpdate(ApiModel):
    revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    idea: str | None = Field(default=None, min_length=10, max_length=20000)
    description: str | None = Field(default=None, max_length=4000)
    status: ProjectStatus | None = None
    planning_agent_ids: list[str] | None = Field(default=None, min_length=1, max_length=2)
    supervisor_agent_ids: list[str] | None = Field(default=None, max_length=3)
    teams: list[SpecialistTeam] | None = Field(default=None, max_length=30)
    planning_model: ModelRef | None = None
    clear_planning_model: bool = False  # True switches back to each agent's own model


class ProjectDocumentCreate(ApiModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="specification", max_length=64)
    content: str = Field(default="", max_length=100000)
    feedback: str = Field(default="", max_length=20000)
    status: DocumentStatus = "draft"


class ProjectDocumentUpdate(ApiModel):
    revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, max_length=100000)
    feedback: str | None = Field(default=None, max_length=20000)
    status: DocumentStatus | None = None


class ProjectDocumentOut(OutModel):
    id: str
    title: str
    kind: str
    content: str
    feedback: str
    status: DocumentStatus
    revision: int
    created_at: datetime
    updated_at: datetime


class ProjectOut(OutModel):
    id: str
    workspace_id: str
    name: str
    idea: str
    description: str
    status: ProjectStatus
    planning_agent_ids: list[str]
    supervisor_agent_ids: list[str]
    teams: list[dict[str, Any]]
    documents: list[ProjectDocumentOut]
    planning_runs: list[dict[str, Any]]
    planning_model: dict[str, Any] | None = None
    revision: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class ProjectPlanStart(ApiModel):
    feedback: str = Field(default="", max_length=20000)
    document_ids: list[str] = Field(default_factory=list, max_length=30)
    # Overrides the project's planning model for this run and becomes the new project default.
    planning_model: ModelRef | None = None


class ProjectPlanStartOut(OutModel):
    project_id: str
    run_ids: list[str]
    message: str

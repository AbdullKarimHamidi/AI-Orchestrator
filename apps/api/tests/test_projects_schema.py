import pytest
from pydantic import ValidationError

from app.schemas.projects import ProjectCreate, ProjectDocumentUpdate, SpecialistTeam


def test_project_requires_one_or_two_unique_planning_agents():
    with pytest.raises(ValidationError):
        ProjectCreate(name="Demo", idea="Build a demo application", planning_agent_ids=[])
    with pytest.raises(ValidationError):
        ProjectCreate(name="Demo", idea="Build a demo application", planning_agent_ids=["agt_1", "agt_1"])
    with pytest.raises(ValidationError):
        ProjectCreate(name="Demo", idea="Build a demo application", planning_agent_ids=["a", "b", "c"])


def test_specialist_team_has_configurable_bounded_parallelism():
    team = SpecialistTeam(id="ui_team", name="UI/UX", responsibility="Build accessible screens",
                          agent_ids=["agt_1", "agt_2"], parallelism=5)
    assert team.parallelism == 5
    assert len(team.agent_ids) == 2
    with pytest.raises(ValidationError):
        SpecialistTeam(id="bad", name="Bad", responsibility="Test", parallelism=0)


def test_document_feedback_and_revision_are_validated():
    req = ProjectDocumentUpdate(revision=3, feedback="Please include API examples", status="in_review")
    assert req.revision == 3
    assert req.feedback == "Please include API examples"
    with pytest.raises(ValidationError):
        ProjectDocumentUpdate(revision=0)

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from jb_orchestrator.domain import ProjectStatus, RequestStatus, RunStatus
from jb_orchestrator.infrastructure.database import (
    Base,
    ProjectRecord,
    RunRecord,
    UserRequestRecord,
)


def test_metadata_creates_initial_domain_schema() -> None:
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "events",
        "node_executions",
        "projects",
        "runs",
        "user_requests",
        "workflow_definitions",
        "workflow_executions",
    }
    assert {index["name"] for index in inspector.get_indexes("runs")} >= {
        "ix_runs_request_id",
        "ix_runs_status_created_at",
    }
    assert {index["name"] for index in inspector.get_indexes("node_executions")} >= {
        "ix_node_executions_lease_expiry",
        "ix_node_executions_status_updated",
    }


def test_records_persist_domain_enum_values() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    project = ProjectRecord(
        key="jb-orchestrator",
        name="JB Orchestrator",
        repository_url="https://github.com/example/jb-orchestrator.git",
        status=ProjectStatus.ACTIVE,
    )
    request = UserRequestRecord(
        project=project,
        prompt="Build the orchestration core",
        status=RequestStatus.RECEIVED,
    )
    run = RunRecord(request=request, attempt=1, status=RunStatus.QUEUED)

    with Session(engine) as session:
        session.add(run)
        session.commit()
        session.refresh(run)

        assert run.status is RunStatus.QUEUED
        assert run.request.status is RequestStatus.RECEIVED
        assert run.request.project.status is ProjectStatus.ACTIVE

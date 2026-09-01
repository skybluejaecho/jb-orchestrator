from datetime import UTC, datetime

import pytest

from jb_orchestrator.domain import DomainValidationError, Project, ProjectStatus


def test_project_normalizes_values_and_can_be_archived() -> None:
    project = Project(
        key="jb-orchestrator",
        name="  JB Orchestrator  ",
        repository_url="  https://github.com/example/jb-orchestrator.git  ",
    )
    archived_at = datetime(2026, 9, 1, tzinfo=UTC)

    project.archive(at=archived_at)

    assert project.name == "JB Orchestrator"
    assert project.repository_url == "https://github.com/example/jb-orchestrator.git"
    assert project.status is ProjectStatus.ARCHIVED
    assert project.updated_at == archived_at


@pytest.mark.parametrize("key", ["", "A-project", "ab", "project_1", "-project"])
def test_project_rejects_invalid_key(key: str) -> None:
    with pytest.raises(DomainValidationError):
        Project(key=key, name="Project", repository_url="https://example.test/repo.git")

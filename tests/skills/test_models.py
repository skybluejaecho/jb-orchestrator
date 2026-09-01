import pytest

from jb_orchestrator.domain.exceptions import DomainValidationError
from jb_orchestrator.skills import SkillDefinition, SkillSourceKind


def test_skill_definition_requires_content_addressed_digest() -> None:
    with pytest.raises(DomainValidationError, match="sha256"):
        SkillDefinition(
            key="review",
            version=1,
            name="Review",
            description="Review code",
            source_kind=SkillSourceKind.GIT,
            source_uri="https://example.com/skills.git",
            content_digest="latest",
            source_revision="abc123",
        )


def test_skill_definition_rejects_unsafe_entrypoint() -> None:
    with pytest.raises(DomainValidationError, match="safe relative"):
        SkillDefinition(
            key="review",
            version=1,
            name="Review",
            description="Review code",
            source_kind=SkillSourceKind.LOCAL,
            source_uri="skills/review",
            content_digest="sha256:" + "d" * 64,
            entrypoint="../SKILL.md",
        )

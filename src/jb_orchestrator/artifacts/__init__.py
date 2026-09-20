"""Immutable outputs passed between workflow task nodes."""

from jb_orchestrator.artifacts.models import TaskArtifact
from jb_orchestrator.artifacts.repositories import TaskArtifactRepository

__all__ = ["TaskArtifact", "TaskArtifactRepository"]

"""SQLAlchemy persistence adapters."""

from jb_orchestrator.infrastructure.database.base import Base
from jb_orchestrator.infrastructure.database.models import (
    EventRecord,
    NodeExecutionRecord,
    ProjectRecord,
    RunRecord,
    SkillDefinitionRecord,
    UserRequestRecord,
    WorkflowDefinitionRecord,
    WorkflowExecutionRecord,
)
from jb_orchestrator.infrastructure.database.repositories import (
    SqlAlchemyEventRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemyRunRepository,
    SqlAlchemyUserRequestRepository,
)
from jb_orchestrator.infrastructure.database.session import create_session_factory
from jb_orchestrator.infrastructure.database.skill_repositories import SqlAlchemySkillRepository
from jb_orchestrator.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from jb_orchestrator.infrastructure.database.workflow_repositories import (
    SqlAlchemyWorkflowDefinitionRepository,
    SqlAlchemyWorkflowExecutionRepository,
)

__all__ = [
    "Base",
    "EventRecord",
    "NodeExecutionRecord",
    "ProjectRecord",
    "RunRecord",
    "SkillDefinitionRecord",
    "SqlAlchemyEventRepository",
    "SqlAlchemyProjectRepository",
    "SqlAlchemyRunRepository",
    "SqlAlchemySkillRepository",
    "SqlAlchemyUnitOfWork",
    "SqlAlchemyUserRequestRepository",
    "SqlAlchemyWorkflowDefinitionRepository",
    "SqlAlchemyWorkflowExecutionRepository",
    "UserRequestRecord",
    "WorkflowDefinitionRecord",
    "WorkflowExecutionRecord",
    "create_session_factory",
]

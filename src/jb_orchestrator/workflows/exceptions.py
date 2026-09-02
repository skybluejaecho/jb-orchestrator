"""Workflow-specific failures."""


class WorkflowError(Exception):
    """Base class for expected workflow failures."""


class WorkflowDefinitionError(WorkflowError, ValueError):
    """Raised when a workflow graph is structurally invalid."""


class WorkflowExecutionError(WorkflowError):
    """Raised when an execution command conflicts with current workflow state."""

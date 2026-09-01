"""Application-level failures exposed to interface adapters."""


class ApplicationError(Exception):
    """Base class for expected use-case failures."""


class ResourceNotFound(ApplicationError):
    """Raised when a requested aggregate does not exist."""


class ResourceConflict(ApplicationError):
    """Raised when a command conflicts with current durable state."""

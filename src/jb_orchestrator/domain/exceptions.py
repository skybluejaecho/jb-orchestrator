"""Domain-specific exceptions."""


class DomainError(Exception):
    """Base class for expected domain failures."""


class DomainValidationError(DomainError, ValueError):
    """Raised when a domain object cannot be created from invalid values."""


class InvalidStateTransition(DomainError):
    """Raised when an aggregate is moved through an invalid lifecycle transition."""

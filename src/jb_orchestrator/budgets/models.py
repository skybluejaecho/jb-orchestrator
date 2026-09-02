"""Project budget accounts, idempotent reservations, and append-only usage records."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError, InvalidStateTransition


def money(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


class BudgetReservationStatus(StrEnum):
    RESERVED = "reserved"
    SETTLED = "settled"
    FORFEITED = "forfeited"
    RELEASED = "released"


class UsageKind(StrEnum):
    ACTUAL = "actual"
    ESTIMATED_FORFEIT = "estimated_forfeit"


@dataclass(slots=True, kw_only=True)
class BudgetAccount:
    project_id: UUID
    limit_usd: Decimal
    id: UUID = field(default_factory=uuid4)
    reserved_usd: Decimal = Decimal("0")
    spent_usd: Decimal = Decimal("0")
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.limit_usd = money(self.limit_usd)
        self.reserved_usd = money(self.reserved_usd)
        self.spent_usd = money(self.spent_usd)
        if min(self.limit_usd, self.reserved_usd, self.spent_usd) < 0:
            raise DomainValidationError("budget amounts must not be negative")

    @property
    def available_usd(self) -> Decimal:
        return money(self.limit_usd - self.reserved_usd - self.spent_usd)

    def set_limit(self, limit_usd: Decimal, *, at: datetime | None = None) -> None:
        value = money(limit_usd)
        if value < self.reserved_usd + self.spent_usd:
            raise DomainValidationError("budget limit cannot be below current commitments")
        self.limit_usd = value
        self._touch(at)

    def reserve(self, amount_usd: Decimal, *, at: datetime | None = None) -> None:
        amount = money(amount_usd)
        if amount < 0:
            raise DomainValidationError("reservation amount must not be negative")
        if amount > self.available_usd:
            raise BudgetLimitExceeded(
                f"budget requires {amount} USD but only {self.available_usd} USD is available"
            )
        self.reserved_usd = money(self.reserved_usd + amount)
        self._touch(at)

    def settle(
        self,
        reserved_usd: Decimal,
        actual_usd: Decimal,
        *,
        at: datetime | None = None,
    ) -> None:
        reserved = money(reserved_usd)
        actual = money(actual_usd)
        if actual < 0 or reserved < 0 or reserved > self.reserved_usd:
            raise DomainValidationError("budget settlement amounts are invalid")
        self.reserved_usd = money(self.reserved_usd - reserved)
        self.spent_usd = money(self.spent_usd + actual)
        self._touch(at)

    def release(self, amount_usd: Decimal, *, at: datetime | None = None) -> None:
        amount = money(amount_usd)
        if amount < 0 or amount > self.reserved_usd:
            raise DomainValidationError("budget release amount is invalid")
        self.reserved_usd = money(self.reserved_usd - amount)
        self._touch(at)

    def _touch(self, at: datetime | None) -> None:
        self.version += 1
        self.updated_at = at or datetime.now(UTC)


class BudgetLimitExceeded(RuntimeError):
    """A new reservation would exceed configured project budget."""


@dataclass(slots=True, kw_only=True)
class BudgetReservation:
    account_id: UUID
    project_id: UUID
    run_id: UUID
    execution_id: UUID
    node_key: str
    idempotency_key: str
    reserved_usd: Decimal
    id: UUID = field(default_factory=uuid4)
    status: BudgetReservationStatus = BudgetReservationStatus.RESERVED
    actual_usd: Decimal | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finalized_at: datetime | None = None

    def __post_init__(self) -> None:
        self.reserved_usd = money(self.reserved_usd)
        if self.reserved_usd < 0:
            raise DomainValidationError("reserved_usd must not be negative")
        if not self.node_key.strip() or not self.idempotency_key.strip():
            raise DomainValidationError("reservation keys must not be empty")

    def settle(self, actual_usd: Decimal, *, at: datetime | None = None) -> None:
        self._finalize(BudgetReservationStatus.SETTLED, actual_usd, at)

    def forfeit(self, *, at: datetime | None = None) -> None:
        self._finalize(BudgetReservationStatus.FORFEITED, self.reserved_usd, at)

    def release(self, *, at: datetime | None = None) -> None:
        self._finalize(BudgetReservationStatus.RELEASED, Decimal("0"), at)

    def _finalize(
        self,
        status: BudgetReservationStatus,
        actual_usd: Decimal,
        at: datetime | None,
    ) -> None:
        if self.status is not BudgetReservationStatus.RESERVED:
            raise InvalidStateTransition(f"cannot finalize reservation from {self.status}")
        value = money(actual_usd)
        if value < 0:
            raise DomainValidationError("actual_usd must not be negative")
        self.status = status
        self.actual_usd = value
        self.finalized_at = at or datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class UsageRecord:
    reservation_id: UUID
    account_id: UUID
    project_id: UUID
    run_id: UUID
    execution_id: UUID
    node_key: str
    kind: UsageKind
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    model_profile_key: str
    model_profile_version: int
    id: UUID = field(default_factory=uuid4)
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise DomainValidationError("usage tokens must not be negative")
        if money(self.cost_usd) < 0:
            raise DomainValidationError("usage cost must not be negative")
        object.__setattr__(self, "cost_usd", money(self.cost_usd))

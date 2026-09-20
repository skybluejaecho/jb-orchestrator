from datetime import UTC, datetime
from uuid import uuid4

import pytest

from jb_orchestrator.domain import DomainValidationError, RequestDispatchReceipt


def test_dispatch_receipt_requires_valid_key_and_digest() -> None:
    with pytest.raises(DomainValidationError, match="idempotency key"):
        RequestDispatchReceipt(
            project_id=uuid4(), idempotency_key="  ", payload_digest="sha256:" + "a" * 64
        )
    with pytest.raises(DomainValidationError, match="SHA-256"):
        RequestDispatchReceipt(
            project_id=uuid4(), idempotency_key="request-1", payload_digest="sha256:not-a-digest"
        )
    with pytest.raises(DomainValidationError, match="ingress key"):
        RequestDispatchReceipt(
            project_id=uuid4(),
            ingress_key="OpenClaw",
            idempotency_key="request-1",
            payload_digest="sha256:" + "a" * 64,
        )


def test_dispatch_receipt_completes_with_all_result_identifiers() -> None:
    receipt = RequestDispatchReceipt(
        project_id=uuid4(),
        idempotency_key=" request-1 ",
        payload_digest="sha256:" + "a" * 64,
    )
    request_id = uuid4()
    run_id = uuid4()
    execution_id = uuid4()
    completed_at = datetime(2026, 9, 3, tzinfo=UTC)

    receipt.complete(
        request_id=request_id,
        run_id=run_id,
        workflow_execution_id=execution_id,
        at=completed_at,
    )

    assert receipt.idempotency_key == "request-1"
    assert receipt.is_complete
    assert (receipt.request_id, receipt.run_id, receipt.workflow_execution_id) == (
        request_id,
        run_id,
        execution_id,
    )
    assert receipt.completed_at == completed_at

from jb_orchestrator.application import ExternalExecutionService, ScmPublicationService
from jb_orchestrator.scm import (
    ScmPublicationFailureCode,
    ScmPublicationRequest,
    ScmPublicationResult,
    ScmPublicationStatus,
    ScmPublisherFailure,
    ScmPublisherRegistry,
)
from jb_orchestrator.scm.runtime import ScmPublicationRuntime
from tests.scm.test_publication_service import managed_execution
from tests.support import MemoryStore, MemoryUnitOfWork


class RecordingPublisher:
    def __init__(self, *, mismatch: str | None = None, failure: str | None = None) -> None:
        self.requests: list[ScmPublicationRequest] = []
        self._mismatch = mismatch
        self._failure = failure

    async def publish_review(self, request: ScmPublicationRequest) -> ScmPublicationResult:
        self.requests.append(request)
        if self._failure is not None:
            raise RuntimeError(self._failure)
        return ScmPublicationResult(
            provider=self._mismatch or "github",
            repository=request.repository,
            source_branch=request.source_branch,
            target_branch=request.target_branch,
            review_url="https://github.com/example/project/pull/1",
            review_id="1",
        )


async def queued_publication(
    store: MemoryStore, publisher: RecordingPublisher
) -> tuple[ScmPublicationRuntime, ScmPublicationService]:
    execution = await managed_execution(store)
    uow = lambda: MemoryUnitOfWork(store)  # noqa: E731
    publications = ScmPublicationService(uow)
    await publications.request(
        execution.id,
        provider_key="github",
        target_branch="develop",
        title="Review feature",
        body="Please review.",
        idempotency_key="publish-1",
        requested_by="jarvis",
    )
    runtime = ScmPublicationRuntime(
        "scm-worker-a",
        "git-worktree:scope-a",
        publications,
        ExternalExecutionService(uow),
        ScmPublisherRegistry({"github": publisher}),
        lease_seconds=30,
        operation_timeout_seconds=10,
    )
    return runtime, publications


async def test_runtime_publishes_claim_and_persists_provider_result() -> None:
    store = MemoryStore()
    publisher = RecordingPublisher()
    runtime, publications = await queued_publication(store, publisher)

    assert await runtime.run_once()

    [request] = publisher.requests
    assert request.workspace_path == "C:/worktrees/task"
    assert request.source_branch == "feature/review"
    [completed] = await publications.list_for_execution(
        next(iter(store.external_executions.values())).id
    )
    assert completed.status is ScmPublicationStatus.SUCCEEDED
    assert completed.result == {
        "provider": "github",
        "repository": "https://github.com/example/project.git",
        "source_branch": "feature/review",
        "target_branch": "develop",
        "review_url": "https://github.com/example/project/pull/1",
        "review_id": "1",
    }


async def test_runtime_records_adapter_failure() -> None:
    store = MemoryStore()
    runtime, publications = await queued_publication(
        store, RecordingPublisher(failure="provider unavailable")
    )

    assert await runtime.run_once()

    [failed] = await publications.list_for_execution(
        next(iter(store.external_executions.values())).id
    )
    assert failed.status is ScmPublicationStatus.FAILED
    assert failed.failure_reason == "provider unavailable"
    assert failed.failure_code is ScmPublicationFailureCode.UNEXPECTED
    assert failed.failure_retryable is False


async def test_runtime_preserves_typed_retryable_adapter_failure() -> None:
    class RetryablePublisher(RecordingPublisher):
        async def publish_review(self, request: ScmPublicationRequest) -> ScmPublicationResult:
            raise ScmPublisherFailure(
                "provider temporarily unavailable",
                code=ScmPublicationFailureCode.PROVIDER_UNAVAILABLE,
                retryable=True,
            )

    store = MemoryStore()
    runtime, publications = await queued_publication(store, RetryablePublisher())

    assert await runtime.run_once()

    [failed] = await publications.list_for_execution(
        next(iter(store.external_executions.values())).id
    )
    assert failed.failure_code is ScmPublicationFailureCode.PROVIDER_UNAVAILABLE
    assert failed.failure_retryable is True


async def test_runtime_rejects_mismatched_provider_result() -> None:
    store = MemoryStore()
    runtime, publications = await queued_publication(store, RecordingPublisher(mismatch="gitlab"))

    assert await runtime.run_once()

    [failed] = await publications.list_for_execution(
        next(iter(store.external_executions.values())).id
    )
    assert failed.status is ScmPublicationStatus.FAILED
    assert failed.failure_reason == "SCM publisher result mismatched: provider"
    assert failed.failure_code is ScmPublicationFailureCode.RESULT_MISMATCH
    assert failed.failure_retryable is False


async def test_runtime_does_not_claim_another_workspace_scope() -> None:
    store = MemoryStore()
    execution = await managed_execution(store)
    uow = lambda: MemoryUnitOfWork(store)  # noqa: E731
    publications = ScmPublicationService(uow)
    await publications.request(
        execution.id,
        provider_key="github",
        target_branch="develop",
        title="Review feature",
        body="",
        idempotency_key="publish-1",
        requested_by="jarvis",
    )
    runtime = ScmPublicationRuntime(
        "scm-worker-b",
        "git-worktree:scope-b",
        publications,
        ExternalExecutionService(uow),
        ScmPublisherRegistry({"github": RecordingPublisher()}),
        lease_seconds=30,
        operation_timeout_seconds=10,
    )

    assert not await runtime.run_once()
    [pending] = await publications.list_for_execution(execution.id)
    assert pending.status is ScmPublicationStatus.PENDING


def test_runtime_requires_timeout_shorter_than_lease() -> None:
    store = MemoryStore()
    uow = lambda: MemoryUnitOfWork(store)  # noqa: E731
    try:
        ScmPublicationRuntime(
            "scm-worker-a",
            "git-worktree:scope-a",
            ScmPublicationService(uow),
            ExternalExecutionService(uow),
            ScmPublisherRegistry({"github": RecordingPublisher()}),
            lease_seconds=30,
            operation_timeout_seconds=30,
        )
    except ValueError as exc:
        assert str(exc) == "SCM publication timeout must be shorter than its lease"
    else:
        raise AssertionError("runtime accepted an operation timeout equal to its lease")

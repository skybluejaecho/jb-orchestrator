from uuid import uuid4

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from starlette.types import Message

from jb_orchestrator.api.event_streams import (
    encode_server_sent_event,
    external_execution_event_stream,
)
from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import ExternalExecutionService
from jb_orchestrator.application.exceptions import ResourceNotFound
from jb_orchestrator.worker import TaskClaim
from tests.support import MemoryStore, MemoryUnitOfWork


async def connected_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


def task_claim() -> TaskClaim:
    return TaskClaim(
        execution_id=uuid4(),
        run_id=uuid4(),
        node_key="review",
        executor_key="openclaw",
        worker_id="worker-a",
        lease_token=uuid4(),
        idempotency_key="execution:review:sse",
        visit_count=1,
        attempt_count=1,
        timeout_seconds=300,
        workflow_key="delivery",
        workflow_version=1,
        instructions="Review the implementation.",
        configuration={},
        skills=(),
    )


async def test_external_execution_events_resume_after_last_event_id() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    claim = task_claim()
    await service.prepare(claim, session_key="agent:review", agent_id="reviewer")
    await service.accept(claim.idempotency_key, "openclaw-run-1")
    events = await service.list_events(limit=1)

    resumed = await service.list_events(after_event_id=events[0].id)

    assert [event.event_type for event in resumed] == ["external_execution.accepted"]
    with pytest.raises(ResourceNotFound):
        await service.list_events(after_event_id=uuid4())


async def test_sse_message_contains_resume_id_and_compact_json() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    claim = task_claim()
    await service.prepare(claim, session_key="agent:review", agent_id="reviewer")
    event = (await service.list_events())[0]

    message = encode_server_sent_event(event)

    assert message.startswith(f"id: {event.id}\nevent: external_execution.prepared\n")
    assert f'"external_execution_id":"{event.aggregate_id}"' in message
    assert message.endswith("\n\n")


async def test_event_stream_replays_persisted_event_before_tailing() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    claim = task_claim()
    await service.prepare(claim, session_key="agent:review", agent_id="reviewer")
    events = await service.list_events()
    request = Request(
        {"type": "http", "method": "GET", "path": "/", "headers": []},
        receive=connected_receive,
    )
    stream = external_execution_event_stream(
        request=request,
        service=service,
        initial_events=events,
        cursor=None,
        poll_interval_seconds=0.01,
        heartbeat_interval_seconds=1,
    )

    message = await anext(stream)
    await stream.aclose()

    assert f"id: {events[0].id}" in message


async def test_event_stream_emits_heartbeat_while_idle() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    request = Request(
        {"type": "http", "method": "GET", "path": "/", "headers": []},
        receive=connected_receive,
    )
    stream = external_execution_event_stream(
        request=request,
        service=service,
        initial_events=[],
        cursor=None,
        poll_interval_seconds=0.01,
        heartbeat_interval_seconds=0,
    )

    message = await anext(stream)
    await stream.aclose()

    assert message == ": heartbeat\n\n"


async def test_sse_endpoint_rejects_unknown_or_conflicting_cursor() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    app = create_app(external_execution_service=service)
    first_cursor = uuid4()
    second_cursor = uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unknown = await client.get(
            "/v1/external-executions/events/stream", params={"after": str(first_cursor)}
        )
        conflicting = await client.get(
            "/v1/external-executions/events/stream",
            params={"after": str(first_cursor)},
            headers={"Last-Event-ID": str(second_cursor)},
        )

    assert unknown.status_code == 404
    assert conflicting.status_code == 422

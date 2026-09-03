"""Server-Sent Events transport for durable external execution events."""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from time import monotonic
from uuid import UUID

from fastapi import Request

from jb_orchestrator.application import ExternalExecutionService
from jb_orchestrator.domain import DomainEvent


def encode_server_sent_event(event: DomainEvent) -> str:
    """Encode one durable event as a resumable SSE message."""

    data = json.dumps(
        {
            "id": str(event.id),
            "sequence": event.sequence,
            "type": event.event_type,
            "external_execution_id": str(event.aggregate_id),
            "occurred_at": event.occurred_at.isoformat(),
            "payload": event.payload,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"id: {event.id}\nevent: {event.event_type}\ndata: {data}\n\n"


async def external_execution_event_stream(
    *,
    request: Request,
    service: ExternalExecutionService,
    initial_events: Sequence[DomainEvent],
    cursor: UUID | None,
    poll_interval_seconds: float,
    heartbeat_interval_seconds: float,
) -> AsyncIterator[str]:
    """Replay persisted events, then tail the event ledger until disconnect."""

    events = initial_events
    last_message_at = monotonic()
    while True:
        if events:
            for event in events:
                cursor = event.id
                last_message_at = monotonic()
                yield encode_server_sent_event(event)
            if await request.is_disconnected():
                return
            events = await service.list_events(after_event_id=cursor)
            continue

        if await request.is_disconnected():
            return
        if monotonic() - last_message_at >= heartbeat_interval_seconds:
            last_message_at = monotonic()
            yield ": heartbeat\n\n"
        await asyncio.sleep(poll_interval_seconds)
        events = await service.list_events(after_event_id=cursor)

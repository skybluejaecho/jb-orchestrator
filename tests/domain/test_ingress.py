import pytest

from jb_orchestrator.domain import DomainValidationError, RequestOrigin


def test_request_origin_normalizes_transport_identifiers() -> None:
    origin = RequestOrigin(
        ingress_key=" openclaw ",
        external_request_id=" message-42 ",
        actor_id=" user-7 ",
        conversation_id=" chat-3 ",
    )

    assert origin == RequestOrigin(
        ingress_key="openclaw",
        external_request_id="message-42",
        actor_id="user-7",
        conversation_id="chat-3",
    )


@pytest.mark.parametrize("ingress_key", ["", "OpenClaw", "1openclaw", "open claw"])
def test_request_origin_rejects_invalid_ingress_keys(ingress_key: str) -> None:
    with pytest.raises(DomainValidationError, match="ingress key"):
        RequestOrigin(ingress_key=ingress_key, external_request_id="message-42")


def test_request_origin_rejects_empty_external_request_id() -> None:
    with pytest.raises(DomainValidationError, match="external request ID"):
        RequestOrigin(ingress_key="openclaw", external_request_id=" ")

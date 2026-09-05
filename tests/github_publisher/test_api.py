from collections.abc import Callable

import httpx
import pytest
from jb_github_publisher.api import GitHubApiClient, GitHubApiError
from jb_github_publisher.repository import GitHubRepository

from jb_orchestrator.scm import ScmPublicationFailureCode


def test_api_allows_http_only_for_explicit_loopback_fixture() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        GitHubApiClient("token", api_url="http://127.0.0.1:8080")
    with pytest.raises(ValueError, match="HTTPS"):
        GitHubApiClient(
            "token",
            api_url="http://github.example",
            allow_insecure_loopback=True,
        )

    GitHubApiClient(
        "token",
        api_url="http://127.0.0.1:8080",
        allow_insecure_loopback=True,
    )


def client(handler: Callable[[httpx.Request], httpx.Response]) -> GitHubApiClient:
    return GitHubApiClient(
        "secret-token",
        api_url="https://api.github.test",
        transport=httpx.MockTransport(handler),
    )


def pull_request(number: int) -> dict[str, object]:
    return {
        "number": number,
        "html_url": f"https://github.com/example/project/pull/{number}",
        "head": {"ref": "feature/work"},
        "base": {"ref": "develop"},
    }


async def test_existing_pull_request_is_reused_without_post() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[pull_request(51)],
        )

    result = await client(handler).find_or_create_pull_request(
        GitHubRepository("example", "project"),
        source_branch="feature/work",
        target_branch="develop",
        title="Review work",
        body="Details",
    )

    assert result.number == 51
    assert [request.method for request in requests] == ["GET"]
    assert requests[0].url.params["head"] == "example:feature/work"
    assert requests[0].headers["authorization"] == "Bearer secret-token"


async def test_missing_pull_request_is_created() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(
            201,
            json=pull_request(52),
        )

    result = await client(handler).find_or_create_pull_request(
        GitHubRepository("example", "project"),
        source_branch="feature/work",
        target_branch="develop",
        title="Review work",
        body="Details",
    )

    assert result.number == 52
    assert [request.method for request in requests] == ["GET", "POST"]
    assert requests[1].read() == (
        b'{"title":"Review work","head":"feature/work","base":"develop","body":"Details"}'
    )


async def test_create_validation_race_rechecks_existing_pull_request() -> None:
    get_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_count
        if request.method == "POST":
            return httpx.Response(422)
        get_count += 1
        payload = [] if get_count == 1 else [pull_request(53)]
        return httpx.Response(200, json=payload)

    result = await client(handler).find_or_create_pull_request(
        GitHubRepository("example", "project"),
        source_branch="feature/work",
        target_branch="develop",
        title="Review work",
        body="",
    )

    assert result.number == 53
    assert get_count == 2


async def test_api_errors_expose_status_and_request_id_without_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"x-github-request-id": "safe-id"},
            json={"message": "response could contain sensitive installation details"},
        )

    with pytest.raises(GitHubApiError, match="HTTP 403, request_id=safe-id") as error:
        await client(handler).find_or_create_pull_request(
            GitHubRepository("example", "project"),
            source_branch="feature/work",
            target_branch="develop",
            title="Review work",
            body="",
        )

    assert "sensitive" not in str(error.value)
    assert error.value.code is ScmPublicationFailureCode.PROVIDER_REJECTED
    assert error.value.retryable is False


async def test_api_marks_provider_outage_as_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(GitHubApiError, match="HTTP 503") as error:
        await client(handler).find_or_create_pull_request(
            GitHubRepository("example", "project"),
            source_branch="feature/work",
            target_branch="develop",
            title="Review work",
            body="",
        )

    assert error.value.code is ScmPublicationFailureCode.PROVIDER_UNAVAILABLE
    assert error.value.retryable is True


async def test_api_sanitizes_and_classifies_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sensitive endpoint detail", request=request)

    with pytest.raises(GitHubApiError, match="ConnectError") as error:
        await client(handler).find_or_create_pull_request(
            GitHubRepository("example", "project"),
            source_branch="feature/work",
            target_branch="develop",
            title="Review work",
            body="",
        )

    assert "sensitive" not in str(error.value)
    assert error.value.code is ScmPublicationFailureCode.PROVIDER_UNAVAILABLE
    assert error.value.retryable is True


async def test_api_rejects_pull_request_for_another_branch() -> None:
    payload = pull_request(54)
    payload["head"] = {"ref": "feature/other"}

    with pytest.raises(GitHubApiError, match="mismatched head"):
        await client(
            lambda request: httpx.Response(200, json=[payload])
        ).find_or_create_pull_request(
            GitHubRepository("example", "project"),
            source_branch="feature/work",
            target_branch="develop",
            title="Review work",
            body="",
        )

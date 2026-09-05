"""Minimal authenticated GitHub pull-request REST client."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from jb_github_publisher.repository import GitHubRepository


class GitHubApiError(RuntimeError):
    """GitHub returned an unexpected or malformed response."""


@dataclass(frozen=True, slots=True)
class GitHubPullRequest:
    number: int
    html_url: str
    source_branch: str
    target_branch: str


class GitHubApiClient:
    def __init__(
        self,
        token: str,
        *,
        api_url: str = "https://api.github.com",
        api_version: str = "2026-03-10",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_insecure_loopback: bool = False,
    ) -> None:
        normalized_token = token.strip()
        normalized_url = api_url.strip().rstrip("/")
        if not normalized_token:
            raise ValueError("GitHub token must not be empty")
        parsed_url = urlparse(normalized_url)
        insecure_loopback = (
            allow_insecure_loopback
            and parsed_url.scheme == "http"
            and parsed_url.hostname in {"127.0.0.1", "localhost", "::1"}
        )
        if parsed_url.scheme != "https" and not insecure_loopback:
            raise ValueError("GitHub API URL must use HTTPS, except test-only loopback HTTP")
        if not api_version.strip() or timeout_seconds <= 0:
            raise ValueError("GitHub API version and positive timeout are required")
        self._token = normalized_token
        self._api_url = normalized_url
        self._api_version = api_version.strip()
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def find_or_create_pull_request(
        self,
        repository: GitHubRepository,
        *,
        source_branch: str,
        target_branch: str,
        title: str,
        body: str,
    ) -> GitHubPullRequest:
        async with httpx.AsyncClient(
            base_url=self._api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": self._api_version,
                "User-Agent": "jb-orchestrator-github-publisher",
            },
            timeout=self._timeout_seconds,
            transport=self._transport,
        ) as client:
            existing = await self._find(
                client,
                repository,
                source_branch=source_branch,
                target_branch=target_branch,
            )
            if existing is not None:
                return existing
            response = await client.post(
                f"/repos/{repository.owner}/{repository.name}/pulls",
                json={
                    "title": title,
                    "head": source_branch,
                    "base": target_branch,
                    "body": body,
                },
            )
            if response.status_code == 201:
                return self._pull_request(
                    response.json(),
                    source_branch=source_branch,
                    target_branch=target_branch,
                )
            if response.status_code == 422:
                existing = await self._find(
                    client,
                    repository,
                    source_branch=source_branch,
                    target_branch=target_branch,
                )
                if existing is not None:
                    return existing
            raise self._error("create pull request", response)

    @classmethod
    async def _find(
        cls,
        client: httpx.AsyncClient,
        repository: GitHubRepository,
        *,
        source_branch: str,
        target_branch: str,
    ) -> GitHubPullRequest | None:
        response = await client.get(
            f"/repos/{repository.owner}/{repository.name}/pulls",
            params={
                "state": "open",
                "head": f"{repository.owner}:{source_branch}",
                "base": target_branch,
                "per_page": 100,
            },
        )
        if response.status_code != 200:
            raise cls._error("list pull requests", response)
        payload = response.json()
        if not isinstance(payload, list):
            raise GitHubApiError("GitHub list pull requests response must be an array")
        if not payload:
            return None
        return cls._pull_request(
            payload[0],
            source_branch=source_branch,
            target_branch=target_branch,
        )

    @staticmethod
    def _pull_request(payload: Any, *, source_branch: str, target_branch: str) -> GitHubPullRequest:
        if not isinstance(payload, dict):
            raise GitHubApiError("GitHub pull request response must be an object")
        number = payload.get("number")
        html_url = payload.get("html_url")
        head = payload.get("head")
        base = payload.get("base")
        if not isinstance(number, int) or number <= 0:
            raise GitHubApiError("GitHub pull request response has no valid number")
        if not isinstance(html_url, str) or urlparse(html_url).scheme != "https":
            raise GitHubApiError("GitHub pull request response has no valid HTTPS URL")
        if not isinstance(head, dict) or head.get("ref") != source_branch:
            raise GitHubApiError("GitHub pull request response has a mismatched head branch")
        if not isinstance(base, dict) or base.get("ref") != target_branch:
            raise GitHubApiError("GitHub pull request response has a mismatched base branch")
        return GitHubPullRequest(
            number=number,
            html_url=html_url,
            source_branch=source_branch,
            target_branch=target_branch,
        )

    @staticmethod
    def _error(action: str, response: httpx.Response) -> GitHubApiError:
        request_id = response.headers.get("x-github-request-id")
        suffix = f", request_id={request_id}" if request_id else ""
        return GitHubApiError(f"GitHub {action} failed with HTTP {response.status_code}{suffix}")

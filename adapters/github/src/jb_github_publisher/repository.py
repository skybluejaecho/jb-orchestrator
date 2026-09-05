"""Strict GitHub repository identity parsing."""

import re
from dataclasses import dataclass
from urllib.parse import urlparse


class GitHubRepositoryError(ValueError):
    """A repository URL cannot be safely mapped to the configured GitHub host."""


REPOSITORY_PART = re.compile(r"^[A-Za-z0-9_.-]+$")
SCP_REMOTE = re.compile(
    r"^(?P<user>[^@:/]+)@(?P<host>[^:/]+):(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"
)


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


def parse_github_repository(value: str, *, web_host: str) -> GitHubRepository:
    """Parse HTTPS, ssh://, or SCP-like Git remotes without accepting credentials."""

    normalized = value.strip()
    host = web_host.strip().lower()
    if not normalized or not host:
        raise GitHubRepositoryError("GitHub repository and web host must not be empty")

    scp_match = SCP_REMOTE.fullmatch(normalized)
    if scp_match is not None:
        if scp_match.group("host").lower() != host:
            raise GitHubRepositoryError("GitHub repository host is not allowed")
        return _repository(scp_match.group("owner"), scp_match.group("repo"))

    parsed = urlparse(normalized)
    if parsed.scheme not in {"https", "ssh"} or not parsed.hostname:
        raise GitHubRepositoryError("GitHub repository URL must use HTTPS or SSH")
    if parsed.hostname.lower() != host:
        raise GitHubRepositoryError("GitHub repository host is not allowed")
    has_invalid_user = (
        parsed.username is not None
        if parsed.scheme == "https"
        else parsed.username not in {None, "git"}
    )
    if has_invalid_user or parsed.password is not None:
        raise GitHubRepositoryError("GitHub repository URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise GitHubRepositoryError("GitHub repository URL must not contain query or fragment")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise GitHubRepositoryError("GitHub repository URL must identify owner/repository")
    return _repository(parts[0], parts[1])


def _repository(owner: str, name: str) -> GitHubRepository:
    repository_name = name.removesuffix(".git")
    if not REPOSITORY_PART.fullmatch(owner) or not REPOSITORY_PART.fullmatch(repository_name):
        raise GitHubRepositoryError("GitHub repository owner or name is invalid")
    return GitHubRepository(owner=owner, name=repository_name)

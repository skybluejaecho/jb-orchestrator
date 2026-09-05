import pytest
from jb_github_publisher.repository import GitHubRepositoryError, parse_github_repository


@pytest.mark.parametrize(
    ("value", "slug"),
    [
        ("https://github.com/example/project.git", "example/project"),
        ("ssh://git@github.com/example/project.git", "example/project"),
        ("git@github.com:example/project.git", "example/project"),
    ],
)
def test_repository_parser_accepts_supported_github_remotes(value: str, slug: str) -> None:
    assert parse_github_repository(value, web_host="github.com").slug == slug


@pytest.mark.parametrize(
    "value",
    [
        "http://github.com/example/project.git",
        "https://token@github.com/example/project.git",
        "https://git@github.com/example/project.git",
        "https://gitlab.com/example/project.git",
        "https://github.com/example/project.git?token=secret",
        "https://github.com/example/project/extra",
        "example/project",
    ],
)
def test_repository_parser_rejects_unsafe_or_unrelated_values(value: str) -> None:
    with pytest.raises(GitHubRepositoryError):
        parse_github_repository(value, web_host="github.com")

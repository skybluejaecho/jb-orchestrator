"""Installable GitHub pull-request publisher adapter."""

from jb_github_publisher.factory import create_publisher
from jb_github_publisher.publisher import GitHubPublisher

__all__ = ["GitHubPublisher", "create_publisher"]

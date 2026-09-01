"""Secure skill source materialization and content-addressed caching."""

import asyncio
import hashlib
import shutil
import tarfile
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from http.client import HTTPMessage
from pathlib import Path
from typing import IO, Protocol
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from jb_orchestrator.skills import SkillDefinition, SkillSourceKind


class SkillMaterializationError(RuntimeError):
    """A skill source could not be fetched or verified safely."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterializedSkill:
    key: str
    version: int
    root_path: Path
    entrypoint_path: Path
    content_digest: str


class SkillSourceFetcher(Protocol):
    async def fetch(self, skill: SkillDefinition, destination: Path) -> None: ...


def compute_directory_digest(root: Path) -> str:
    """Hash paths and bytes in a platform-independent canonical order."""

    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise NotADirectoryError(root)
    files: list[tuple[str, Path]] = []
    for path in resolved.rglob("*"):
        if path.is_symlink():
            raise SkillMaterializationError(f"skill packages cannot contain symlinks: {path}")
        if path.is_file():
            files.append((path.relative_to(resolved).as_posix(), path))
    digest = hashlib.sha256()
    for relative, path in sorted(files):
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        size = path.stat().st_size
        digest.update(size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _resolve_within(root: Path, value: str) -> Path:
    resolved_root = root.resolve(strict=True)
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else resolved_root / candidate).resolve(
        strict=True
    )
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise SkillMaterializationError(f"skill source escapes configured root: {value}") from exc
    return resolved


class LocalSkillFetcher:
    def __init__(self, source_root: Path) -> None:
        self._source_root = source_root

    async def fetch(self, skill: SkillDefinition, destination: Path) -> None:
        source = _resolve_within(self._source_root, skill.source_uri)
        if not source.is_dir():
            raise SkillMaterializationError(f"local skill source is not a directory: {source}")
        await asyncio.to_thread(shutil.copytree, source, destination)


async def _run_git(*args: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip()
        raise SkillMaterializationError(f"git command failed: {detail}")


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None:
        raise SkillMaterializationError("archive downloads cannot follow redirects")


class GitSkillFetcher:
    def __init__(self, allowed_remote_hosts: frozenset[str] = frozenset()) -> None:
        self._allowed_remote_hosts = allowed_remote_hosts

    async def fetch(self, skill: SkillDefinition, destination: Path) -> None:
        if not skill.source_revision:
            raise SkillMaterializationError("git skill has no pinned source revision")
        parsed = urlparse(skill.source_uri)
        if (
            parsed.scheme not in {"http", "https", "ssh"}
            or parsed.hostname not in self._allowed_remote_hosts
        ):
            raise SkillMaterializationError("git skill remote is not in the allowed host list")
        await _run_git(
            "-c",
            "http.followRedirects=false",
            "clone",
            "--no-checkout",
            "--filter=blob:none",
            skill.source_uri,
            str(destination),
        )
        await _run_git("-C", str(destination), "checkout", "--detach", skill.source_revision)
        await asyncio.to_thread(shutil.rmtree, destination / ".git")


class ArchiveSkillFetcher:
    def __init__(
        self,
        local_root: Path,
        *,
        max_archive_bytes: int = 50 * 1024 * 1024,
        max_extracted_bytes: int = 200 * 1024 * 1024,
        allowed_remote_hosts: frozenset[str] = frozenset(),
    ) -> None:
        self._local_root = local_root
        self._max_archive_bytes = max_archive_bytes
        self._max_extracted_bytes = max_extracted_bytes
        self._allowed_remote_hosts = allowed_remote_hosts

    async def fetch(self, skill: SkillDefinition, destination: Path) -> None:
        await asyncio.to_thread(self._fetch_sync, skill.source_uri, destination)

    def _fetch_sync(self, source_uri: str, destination: Path) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "skill.archive"
            parsed = urlparse(source_uri)
            if parsed.scheme in {"http", "https"}:
                if parsed.hostname not in self._allowed_remote_hosts:
                    raise SkillMaterializationError(
                        "archive remote is not in the allowed host list"
                    )
                self._download(source_uri, archive)
            elif parsed.scheme:
                raise SkillMaterializationError(f"unsupported archive URI scheme: {parsed.scheme}")
            else:
                source = _resolve_within(self._local_root, source_uri)
                if source.stat().st_size > self._max_archive_bytes:
                    raise SkillMaterializationError("skill archive exceeds size limit")
                shutil.copyfile(source, archive)
            destination.mkdir()
            if zipfile.is_zipfile(archive):
                self._extract_zip(archive, destination)
            elif tarfile.is_tarfile(archive):
                self._extract_tar(archive, destination)
            else:
                raise SkillMaterializationError("skill archive format is unsupported")

    def _download(self, uri: str, target: Path) -> None:
        total = 0
        opener = build_opener(_RejectRedirects())
        with opener.open(uri, timeout=30) as response, target.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > self._max_archive_bytes:
                    raise SkillMaterializationError("skill archive exceeds size limit")
                output.write(chunk)

    @staticmethod
    def _safe_target(root: Path, name: str) -> Path:
        if "\\" in name:
            raise SkillMaterializationError(
                f"archive member must use POSIX path separators: {name}"
            )
        target = (root / name).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError as exc:
            raise SkillMaterializationError(f"archive member escapes destination: {name}") from exc
        return target

    def _extract_zip(self, archive: Path, destination: Path) -> None:
        total = 0
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                total += member.file_size
                if total > self._max_extracted_bytes:
                    raise SkillMaterializationError("extracted skill exceeds size limit")
                target = self._safe_target(destination, member.filename)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                mode = member.external_attr >> 16
                if mode & 0o170000 == 0o120000:
                    raise SkillMaterializationError("skill archives cannot contain symlinks")
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

    def _extract_tar(self, archive: Path, destination: Path) -> None:
        total = 0
        with tarfile.open(archive) as package:
            for member in package.getmembers():
                if not (member.isfile() or member.isdir()):
                    raise SkillMaterializationError(
                        "skill archives may contain only files and directories"
                    )
                total += member.size
                if total > self._max_extracted_bytes:
                    raise SkillMaterializationError("extracted skill exceeds size limit")
                target = self._safe_target(destination, member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = package.extractfile(member)
                if source is None:
                    raise SkillMaterializationError(f"cannot read archive member: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)


class SkillMaterializer:
    def __init__(
        self,
        cache_root: Path,
        fetchers: Mapping[SkillSourceKind, SkillSourceFetcher],
    ) -> None:
        self._cache_root = cache_root
        self._fetchers = dict(fetchers)

    async def materialize(self, skill: SkillDefinition) -> MaterializedSkill:
        cache_key = skill.content_digest.removeprefix("sha256:")
        target = self._cache_root / cache_key
        if target.exists():
            return await asyncio.to_thread(self._verify, skill, target)
        self._cache_root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".staging-", dir=self._cache_root))
        payload = temporary / "payload"
        try:
            try:
                fetcher = self._fetchers[skill.source_kind]
            except KeyError as exc:
                raise SkillMaterializationError(
                    f"no fetcher configured for skill source: {skill.source_kind}"
                ) from exc
            await fetcher.fetch(skill, payload)
            await asyncio.to_thread(self._verify, skill, payload)
            try:
                payload.rename(target)
            except OSError:
                if not target.exists():
                    raise
            return await asyncio.to_thread(self._verify, skill, target)
        finally:
            await asyncio.to_thread(shutil.rmtree, temporary, True)

    async def materialize_all(
        self, skills: tuple[SkillDefinition, ...]
    ) -> tuple[MaterializedSkill, ...]:
        return tuple(await asyncio.gather(*(self.materialize(skill) for skill in skills)))

    @staticmethod
    def _verify(skill: SkillDefinition, root: Path) -> MaterializedSkill:
        actual = compute_directory_digest(root)
        if actual != skill.content_digest:
            raise SkillMaterializationError(
                f"skill digest mismatch for {skill.key}@{skill.version}: expected "
                f"{skill.content_digest}, got {actual}"
            )
        entrypoint = root / skill.entrypoint
        if not entrypoint.is_file() or entrypoint.is_symlink():
            raise SkillMaterializationError(f"skill entrypoint does not exist: {skill.entrypoint}")
        return MaterializedSkill(
            key=skill.key,
            version=skill.version,
            root_path=root,
            entrypoint_path=entrypoint,
            content_digest=actual,
        )

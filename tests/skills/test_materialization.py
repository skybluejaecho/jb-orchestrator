import zipfile
from pathlib import Path

import pytest

from jb_orchestrator.skills import SkillDefinition, SkillSourceKind
from jb_orchestrator.skills.materialization import (
    ArchiveSkillFetcher,
    GitSkillFetcher,
    LocalSkillFetcher,
    SkillMaterializationError,
    SkillMaterializer,
    compute_directory_digest,
)


def local_skill(source_root: Path, key: str = "review") -> SkillDefinition:
    source = source_root / key
    source.mkdir()
    (source / "SKILL.md").write_text("# Review\n", encoding="utf-8")
    (source / "examples").mkdir()
    (source / "examples" / "one.md").write_text("Example\n", encoding="utf-8")
    return SkillDefinition(
        key=key,
        version=1,
        name="Review",
        description="Review changes",
        source_kind=SkillSourceKind.LOCAL,
        source_uri=key,
        content_digest=compute_directory_digest(source),
    )


async def test_local_skill_is_verified_and_reused_from_digest_cache(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    skill = local_skill(source_root)
    materializer = SkillMaterializer(
        tmp_path / "cache", {SkillSourceKind.LOCAL: LocalSkillFetcher(source_root)}
    )

    first = await materializer.materialize(skill)
    (source_root / "review" / "SKILL.md").write_text("changed", encoding="utf-8")
    second = await materializer.materialize(skill)

    assert first.root_path == second.root_path
    assert second.entrypoint_path.read_text(encoding="utf-8") == "# Review\n"


async def test_digest_mismatch_never_populates_cache(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    skill = local_skill(source_root)
    invalid = SkillDefinition(
        key=skill.key,
        version=skill.version,
        name=skill.name,
        description=skill.description,
        source_kind=skill.source_kind,
        source_uri=skill.source_uri,
        content_digest="sha256:" + "0" * 64,
    )
    cache = tmp_path / "cache"
    materializer = SkillMaterializer(cache, {SkillSourceKind.LOCAL: LocalSkillFetcher(source_root)})

    with pytest.raises(SkillMaterializationError, match="digest mismatch"):
        await materializer.materialize(invalid)

    assert not (cache / ("0" * 64)).exists()
    assert not list(cache.glob(".staging-*"))


async def test_local_source_cannot_escape_configured_root(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text("outside", encoding="utf-8")
    skill = SkillDefinition(
        key="escape",
        version=1,
        name="Escape",
        description="Invalid source",
        source_kind=SkillSourceKind.LOCAL,
        source_uri="../outside",
        content_digest=compute_directory_digest(outside),
    )

    with pytest.raises(SkillMaterializationError, match="escapes"):
        await SkillMaterializer(
            tmp_path / "cache", {SkillSourceKind.LOCAL: LocalSkillFetcher(source_root)}
        ).materialize(skill)


async def test_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive_root = tmp_path / "archives"
    archive_root.mkdir()
    archive = archive_root / "bad.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("../escaped.txt", "bad")
    skill = SkillDefinition(
        key="archive",
        version=1,
        name="Archive",
        description="Invalid archive",
        source_kind=SkillSourceKind.ARCHIVE,
        source_uri="bad.zip",
        content_digest="sha256:" + "1" * 64,
    )

    with pytest.raises(SkillMaterializationError, match="escapes"):
        await SkillMaterializer(
            tmp_path / "cache",
            {SkillSourceKind.ARCHIVE: ArchiveSkillFetcher(archive_root)},
        ).materialize(skill)


async def test_archive_skill_is_extracted_and_verified(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    (package_root / "SKILL.md").write_text("# Archive\n", encoding="utf-8")
    archive_root = tmp_path / "archives"
    archive_root.mkdir()
    archive = archive_root / "skill.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.write(package_root / "SKILL.md", "SKILL.md")
    skill = SkillDefinition(
        key="archive",
        version=1,
        name="Archive",
        description="Archived skill",
        source_kind=SkillSourceKind.ARCHIVE,
        source_uri="skill.zip",
        content_digest=compute_directory_digest(package_root),
    )

    result = await SkillMaterializer(
        tmp_path / "cache",
        {SkillSourceKind.ARCHIVE: ArchiveSkillFetcher(archive_root)},
    ).materialize(skill)

    assert result.entrypoint_path.read_text(encoding="utf-8") == "# Archive\n"


async def test_archive_rejects_backslash_path_separator(tmp_path: Path) -> None:
    archive_root = tmp_path / "archives"
    archive_root.mkdir()
    archive = archive_root / "bad.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("..\\escaped.txt", "bad")
    skill = SkillDefinition(
        key="archive",
        version=1,
        name="Archive",
        description="Invalid archive",
        source_kind=SkillSourceKind.ARCHIVE,
        source_uri="bad.zip",
        content_digest="sha256:" + "1" * 64,
    )

    with pytest.raises(SkillMaterializationError, match=r"POSIX|escapes"):
        await SkillMaterializer(
            tmp_path / "cache",
            {SkillSourceKind.ARCHIVE: ArchiveSkillFetcher(archive_root)},
        ).materialize(skill)


async def test_git_remote_requires_explicitly_allowed_host(tmp_path: Path) -> None:
    skill = SkillDefinition(
        key="remote",
        version=1,
        name="Remote",
        description="Remote skill",
        source_kind=SkillSourceKind.GIT,
        source_uri="https://example.com/skills/review.git",
        source_revision="0123456789abcdef",
        content_digest="sha256:" + "1" * 64,
    )

    with pytest.raises(SkillMaterializationError, match="allowed host"):
        await GitSkillFetcher().fetch(skill, tmp_path / "destination")

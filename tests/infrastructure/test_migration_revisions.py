from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_revision_ids_fit_the_default_alembic_version_column() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    configuration = Config(repository_root / "alembic.ini")
    configuration.set_main_option("script_location", str(repository_root / "migrations"))
    scripts = ScriptDirectory.from_config(configuration)

    revisions = list(scripts.walk_revisions(base="base", head="heads"))

    assert revisions
    assert all(len(revision.revision) <= 32 for revision in revisions)

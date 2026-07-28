"""Alembic chain integrity — no database required.

Phase 1 shipped a migration whose parent existed only as an UNTRACKED file on
one machine. `alembic heads` was happy locally and the SQLite test suite never
touches real migrations, so nothing caught it; a fresh clone or a deploy would
have died with "Can't locate revision". These tests read the chain the way a
fresh clone sees it — through git's index, not the working directory.

The companion check (actually running `alembic upgrade head` against a real
Postgres) lives in .github/workflows/ci.yml, because the migrations use JSONB,
partial indexes and ROW LEVEL SECURITY and cannot run on SQLite.
"""
import subprocess
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(cfg)


def _tracked_migration_files() -> set[str]:
    """Migration filenames git actually knows about.

    `git ls-files` is the point of this whole module: an untracked file is
    present on disk and invisible to a clone, so anything reading the directory
    listing — including alembic itself — cannot see the problem.
    """
    out = subprocess.run(
        ["git", "ls-files", "alembic/versions"],
        cwd=BACKEND, capture_output=True, text=True, check=True,
    ).stdout.split()
    return {Path(p).name for p in out if p.endswith(".py")}


def test_exactly_one_head():
    heads = _script_dir().get_heads()
    assert len(heads) == 1, f"expected a single head, found {len(heads)}: {heads}"


def test_every_migration_file_is_tracked_by_git():
    tracked = _tracked_migration_files()
    on_disk = {p.name for p in VERSIONS.glob("*.py") if p.name != "__init__.py"}
    untracked = on_disk - tracked
    assert not untracked, (
        "these migrations exist on disk but are NOT committed, so a fresh clone "
        f"cannot build the chain: {sorted(untracked)}"
    )


def test_every_down_revision_resolves_to_a_tracked_migration():
    script = _script_dir()
    tracked = _tracked_migration_files()
    revisions = list(script.walk_revisions())
    by_id = {r.revision: r for r in revisions}

    problems = []
    for rev in revisions:
        parents = rev.down_revision
        if parents is None:
            continue
        for parent in ((parents,) if isinstance(parents, str) else tuple(parents)):
            if parent not in by_id:
                problems.append(f"{rev.revision} -> missing parent {parent}")
                continue
            parent_file = Path(by_id[parent].path).name
            if parent_file not in tracked:
                problems.append(
                    f"{rev.revision} -> parent {parent} lives in UNTRACKED {parent_file}"
                )
    assert not problems, "broken migration chain: " + "; ".join(problems)


def test_chain_reaches_base_from_head():
    """A head that cannot walk back to base means a severed chain."""
    script = _script_dir()
    head = script.get_current_head()
    walked = [r.revision for r in script.walk_revisions(base="base", head=head)]
    total = len([p for p in VERSIONS.glob("*.py") if p.name != "__init__.py"])
    assert len(walked) == total, (
        f"head walks back through {len(walked)} revisions but {total} migration "
        "files exist — some are orphaned from the chain"
    )


def test_no_duplicate_revision_ids():
    """A copy-pasted revision id silently shadows another migration."""
    script = _script_dir()
    ids = [r.revision for r in script.walk_revisions()]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate revision ids: {sorted(dupes)}"

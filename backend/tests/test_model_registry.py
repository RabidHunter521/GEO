"""Importing app.models must register every table.

OutcomeAction has a ForeignKey to work_log_entries, but nothing the worker
loaded imported WorkLogEntry, so the first OutcomeAction flush after each
deploy failed and that scan's recommended actions were lost. Run in a fresh
interpreter: inside the test session other tests have already imported every
model, which hides exactly this bug.
"""
import subprocess
import sys
from pathlib import Path

_CHECK = """
import app.models
from app.models.base import Base
unresolved = []
for table in Base.metadata.tables.values():
    for fk in table.foreign_keys:
        try:
            fk.column
        except Exception as exc:
            unresolved.append(f"{table.name}: {exc}")
print("\\n".join(unresolved))
raise SystemExit(1 if unresolved else 0)
"""


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=120,
    )


def test_every_foreign_key_resolves_after_importing_app_models():
    result = _run(_CHECK)
    assert result.returncode == 0, result.stdout + result.stderr


def test_worker_startup_registers_work_log_entries():
    result = _run(
        "import workers.celery_app\n"
        "from app.models.base import Base\n"
        "assert 'work_log_entries' in Base.metadata.tables\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr

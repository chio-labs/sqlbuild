"""Fake project runs for the differential harness running tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scripts.compiler_differential.models import (
    CommandOutcome,
    CorpusProject,
    DifferentialOptions,
    ProjectRun,
)

ORDERS_TEST_SQL: str = "SELECT order_id FROM orders\n"


def fake_run_project(*, exit_code: int) -> Callable[..., ProjectRun]:
    """Return a `run_project` that leaves one compiled test and exits with `exit_code`."""

    def run_project(
        *,
        project: CorpusProject,
        source_dir: Path,
        case_dir: Path,
        options: DifferentialOptions,
    ) -> ProjectRun:
        del project, source_dir, options
        target: Path = case_dir / "project" / "target"
        tests_dir: Path = target / "compiled" / "tests" / "orders"
        tests_dir.mkdir(parents=True)
        _ = (tests_dir / "test_orders.sql").write_text(ORDERS_TEST_SQL, encoding="utf-8")
        _ = (target / "sql-test-artifacts.json").write_text("{}", encoding="utf-8")
        return ProjectRun(
            outcomes=(
                CommandOutcome(
                    label="compile-warm",
                    exit_code=exit_code,
                    stdout="{}",
                    stderr="Compiling orders\n",
                ),
            ),
            compiled={},
            manifest=None,
        )

    return run_project


def first_stat_paths(*, evidence_dir: Path) -> list[str]:
    """The first compiled-test path the kept stat listing records, if evidence was kept."""

    return [
        listing.read_text(encoding="utf-8").splitlines()[1].split("\t")[0]
        for listing in evidence_dir.glob("example__orders/compiled-tests-stat.tsv")
    ]


def kept_files(root: Path) -> tuple[str, ...]:
    """Every file below `root` as sorted relative POSIX paths."""

    return tuple(
        sorted(path.relative_to(root).as_posix() for path in filter(Path.is_file, root.rglob("*")))
    )

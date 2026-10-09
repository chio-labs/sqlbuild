"""Fake engine runs for the differential harness running tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scripts.compiler_differential.models import (
    CommandOutcome,
    CorpusProject,
    DifferentialOptions,
    EngineRun,
)

ORDERS_TEST_SQL: str = "SELECT order_id FROM orders\n"


def fake_run_engine(*, stderr_by_engine: dict[str, str]) -> Callable[..., EngineRun]:
    """Return a `run_engine` that leaves one compiled test and prints the engine's stderr."""

    def run_engine(
        *,
        project: CorpusProject,
        source_dir: Path,
        case_dir: Path,
        engine: str,
        side: str,
        options: DifferentialOptions,
    ) -> EngineRun:
        del project, source_dir, side, options
        tests_dir: Path = case_dir / engine / "target" / "compiled" / "tests" / "orders"
        tests_dir.mkdir(parents=True)
        _ = (tests_dir / "test_orders.sql").write_text(ORDERS_TEST_SQL, encoding="utf-8")
        _ = (case_dir / engine / "target" / "sql-test-artifacts.json").write_text(
            "{}", encoding="utf-8"
        )
        return EngineRun(
            engine=engine,
            outcomes=(
                CommandOutcome(
                    label="compile-warm",
                    exit_code=0,
                    stdout="{}",
                    stderr=stderr_by_engine[engine],
                ),
            ),
            compiled={},
            manifest=None,
            dag=None,
        )

    return run_engine


def first_stat_paths(*, evidence_dir: Path, engines: tuple[str, ...]) -> list[str]:
    """The first compiled-test path each engine's stat listing records."""

    return [
        (evidence_dir / "example__orders" / engine / "compiled-tests-stat.tsv")
        .read_text(encoding="utf-8")
        .splitlines()[1]
        .split("\t")[0]
        for engine in engines
    ]


def kept_files(root: Path) -> tuple[str, ...]:
    """Every file below `root` as sorted relative POSIX paths."""

    return tuple(
        sorted(path.relative_to(root).as_posix() for path in filter(Path.is_file, root.rglob("*")))
    )

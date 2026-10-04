"""Shared builders for lint helper unit tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.lint._helpers.headers import scan_headers, sql_body_ranges
from sqlbuild.lint.models import HeaderSpan, LintBody
from sqlbuild.lint.types import NativeLintPreparationRequest, NativePreparedSql


def lint_bodies_for(*, file_path: Path, contents: str) -> tuple[LintBody, ...]:
    """Build unexpanded lint bodies for every SQL body in the contents."""

    headers: tuple[HeaderSpan, ...] = scan_headers(contents=contents)
    bodies: list[LintBody] = []
    body_start: int
    body_end: int
    for body_start, body_end in sql_body_ranges(contents=contents, headers=headers):
        bodies.append(
            LintBody(
                file_path=file_path,
                body_start=body_start,
                body_end=body_end,
                lint_text=contents[body_start:body_end],
                passes=(),
            )
        )
    return tuple(bodies)


def unused_cte_orders_file(
    *, tmp_path: Path, prefix: str, file_index: int, unused_cte_count: int
) -> tuple[Path, str, LintBody]:
    """Build one multi-line file, offset by its index, whose body declares many unused CTEs."""

    target: Path = tmp_path / f"orders_{file_index}.sql"
    sql: str = (
        "WITH\n"
        + "".join(
            f"  unused_{index:03d} AS (\n    SELECT {index} AS order_id\n  ),\n"
            for index in range(unused_cte_count)
        )
        + "  final AS (SELECT 1 AS order_id)\nSELECT order_id\nFROM final\n"
    )
    header: str = prefix + "-- order history\n" * file_index
    contents: str = header + sql
    body: LintBody = LintBody(
        file_path=target,
        body_start=len(header),
        body_end=len(contents),
        lint_text=sql,
        passes=(),
    )
    return target, contents, body


def authored_positions(*, contents: str, needles: tuple[str, ...]) -> list[tuple[int, int]]:
    """One-based line and column of each needle's first occurrence."""

    positions: list[tuple[int, int]] = []
    for needle in needles:
        offset: int = contents.index(needle)
        positions.append(
            (contents.count("\n", 0, offset) + 1, offset - contents.rfind("\n", 0, offset))
        )
    return positions


def write_lint_project(*, root: Path, files: dict[str, str]) -> None:
    """Write a DuckDB project containing the given relative files."""

    (root / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    for relative_path, contents in files.items():
        path: Path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")


def prepare_nothing_in_batch(
    requests: list[NativeLintPreparationRequest],
) -> list[tuple[bool, NativePreparedSql | None]]:
    """Report every body as unprepared so each one takes the per-body native call."""

    return [(False, None) for _request in requests]


def refuse_preparation(request: NativeLintPreparationRequest) -> NativePreparedSql | None:
    """Fail the per-body native preparation of any body."""

    raise ValueError(f"cannot prepare {request['dialect']} body")

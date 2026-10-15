"""Caller-held adapter lexical syntax reaches lint and format SQL scanning."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from unittest.mock import Mock

import pytest

import sqlbuild._native as fixture_formatting_module
import sqlbuild._native as native_module
from sqlbuild._native import discover_project_inputs
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.unit.src.sqlbuild.lint._test_types import PassedAdapterSyntaxTestCase
from tests.unit.src.sqlbuild.lint.helpers import write_fixture_format_project

_CUSTOM_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax(
    triple_quoted_strings=True, line_comment_prefixes=frozenset({"--", "#"})
)


class _CustomSyntaxDuckDbAdapter(DuckDbAdapter):
    sql_lexical_syntax: ClassVar[SqlLexicalSyntax] = _CUSTOM_SYNTAX


@pytest.mark.parametrize(
    "test_case",
    [PassedAdapterSyntaxTestCase("fixture formatting uses the passed syntax", _CUSTOM_SYNTAX)],
    ids=lambda case: case.description,
)
def test_given_passed_syntax_when_formatting_fixture_nulls_then_scanner_uses_it(
    test_case: PassedAdapterSyntaxTestCase,
    tmp_path: Path,
) -> None:
    test_file: Path = write_fixture_format_project(
        tmp_path=tmp_path,
        fixture_sql="SELECT\n  1 AS id,\n  CAST(NULL AS BOOLEAN) AS flag\nWHERE TRUE\n  # ) custom comment\n",
    )
    inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)

    updated: dict[Path, str] = fixture_formatting_module.format_redundant_fixture_nulls(
        files={test_file.resolve(): test_file.read_text(encoding="utf-8")},
        project_dir=tmp_path,
        discovered_inputs=inputs,
        sql_lexical_syntax=test_case.expected_syntax,
    )

    assert "CAST(NULL AS BOOLEAN)" not in updated[test_file.resolve()]
    assert "# ) custom comment" in updated[test_file.resolve()]


@pytest.mark.parametrize(
    "test_case",
    [PassedAdapterSyntaxTestCase("expansion scope uses the renderer syntax", _CUSTOM_SYNTAX)],
    ids=lambda case: case.description,
)
def test_given_value_renderer_when_building_expansion_context_then_scope_uses_its_syntax(
    test_case: PassedAdapterSyntaxTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = write_fixture_format_project(tmp_path=tmp_path, fixture_sql="SELECT 1 AS id, TRUE AS flag")
    build_scope: Mock = Mock(wraps=native_module.build_declaration_scope)
    monkeypatch.setattr(native_module, "build_declaration_scope", build_scope)

    _ = native_module.build_sql_expansion_context(
        project_dir=tmp_path, value_renderer=_CustomSyntaxDuckDbAdapter()
    )

    assert build_scope.call_args.kwargs["sql_lexical_syntax"] is test_case.expected_syntax


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])

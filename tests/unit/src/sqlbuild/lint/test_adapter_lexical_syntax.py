"""Caller-held adapter lexical syntax reaches lint and format SQL scanning."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from unittest.mock import Mock

import pytest

import sqlbuild.compiler.compile.main.sql_expansion_context as expansion_context_module
import sqlbuild.compiler.planner._helpers.sql_tests.fixture_formatting as fixture_formatting_module
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_file: Path = write_fixture_format_project(
        tmp_path=tmp_path, fixture_sql="SELECT 1 AS id, CAST(NULL AS BOOLEAN) AS flag"
    )
    inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    extract: Mock = Mock(wraps=fixture_formatting_module.SqlTestCteExtractor.extract)
    monkeypatch.setattr(fixture_formatting_module.SqlTestCteExtractor, "extract", extract)

    _ = fixture_formatting_module.format_redundant_fixture_nulls(
        files={test_file.resolve(): test_file.read_text(encoding="utf-8")},
        project_dir=tmp_path,
        discovered_inputs=inputs,
        sql_lexical_syntax=test_case.expected_syntax,
    )

    assert extract.call_args.kwargs["syntax"] is test_case.expected_syntax


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
    build_scope: Mock = Mock(wraps=expansion_context_module.build_declaration_scope)
    monkeypatch.setattr(expansion_context_module, "build_declaration_scope", build_scope)

    _ = expansion_context_module.build_sql_expansion_context(
        project_dir=tmp_path, value_renderer=_CustomSyntaxDuckDbAdapter()
    )

    assert build_scope.call_args.kwargs["sql_lexical_syntax"] is test_case.expected_syntax


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])

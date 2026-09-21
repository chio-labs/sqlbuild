"""Compiler-backed safe fixture-null source rewrites."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner._helpers.sql_tests.fixture_formatting import (
    format_redundant_fixture_nulls,
)


class FixtureNullAutofix:
    """Apply fixture-null rewrites proven safe by planner completion."""

    @staticmethod
    def apply(
        *,
        files: dict[Path, str],
        project_dir: Path,
        project: CompiledProject,
        adapter: BaseAdapter,
    ) -> dict[Path, str]:
        """Return contract-safe fixture source rewrites."""

        return format_redundant_fixture_nulls(
            files=files,
            project_dir=project_dir,
            project=project,
            adapter=adapter,
        )

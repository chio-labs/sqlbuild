"""Compiler-backed safe fixture-null source rewrites."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
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
        discovered_inputs: DiscoveredProjectInputs,
    ) -> dict[Path, str]:
        """Return contract-safe fixture source rewrites."""

        return format_redundant_fixture_nulls(
            files=files,
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
        )

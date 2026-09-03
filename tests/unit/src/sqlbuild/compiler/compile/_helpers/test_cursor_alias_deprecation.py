from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile._helpers.config.deprecation import (
    build_cursor_alias_diagnostics,
)
from sqlbuild.compiler.compile.models import (
    CompileModelConfig,
    CompileModelInput,
    CompilerDiagnostic,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    CursorAliasWarningTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorAliasWarningTestCase(
            description="cursor inputs emit no legacy alias warning",
            config_values=(
                {"cursor_inputs": {"orders": "event_time"}},
                {"cursor_inputs": {"shipments": "event_time"}},
            ),
            expected_warning_count=0,
        ),
        CursorAliasWarningTestCase(
            description="removed cursor role names emit no deprecation warning",
            config_values=(
                {"cursor_filter_inputs": {"orders": "event_time"}},
                {"cursor_watermark_inputs": {"raw_orders": "loaded_at"}},
            ),
            expected_warning_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_cursor_roles_when_building_diagnostics_then_warning_cardinality_is_exact(
    test_case: CursorAliasWarningTestCase,
) -> None:
    model_file: DiscoveredSqlModelFile = DiscoveredSqlModelFile(
        file_path=Path("models/orders.sql"),
        relative_path=Path("models/orders.sql"),
        contents="SELECT 1",
        header_values={},
        header_column_locations={},
        output_column_locations={},
        query_sql="SELECT 1",
    )
    model_inputs: tuple[CompileModelInput, ...] = tuple(
        CompileModelInput(model_file=model_file, config=CompileModelConfig(values=values))
        for values in test_case.config_values
    )

    diagnostics: tuple[CompilerDiagnostic, ...] = build_cursor_alias_diagnostics(
        model_inputs=model_inputs
    )

    assert len(diagnostics) == test_case.expected_warning_count


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])

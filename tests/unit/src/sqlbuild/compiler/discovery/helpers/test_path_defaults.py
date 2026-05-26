from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.helpers.discovery_validation import (
    _validate_path_defaults_match_models,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    ValidatePathDefaultsMatchModelsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ValidatePathDefaultsMatchModelsTestCase(
            description="accepts Windows-style model paths that match path defaults",
            model_relative_paths=("models\\staging\\orders.sql",),
            path_defaults={"staging": {}},
            expected_model_file_count=1,
        )
    ],
    ids=["accepts Windows-style model paths that match path defaults"],
)
def test_given_windows_style_model_paths_when_validating_path_defaults_then_they_match(
    test_case: ValidatePathDefaultsMatchModelsTestCase,
) -> None:
    model_files: tuple[DiscoveredSqlModelFile, ...] = tuple(
        DiscoveredSqlModelFile(
            file_path=Path("/repo") / relative_path,
            relative_path=Path(relative_path),
            contents="MODEL ();\n\nselect 1\n",
            header_values={},
            header_column_locations={},
            output_column_locations={},
            query_sql="select 1",
        )
        for relative_path in test_case.model_relative_paths
    )

    _validate_path_defaults_match_models(
        path_defaults=test_case.path_defaults,
        model_files=model_files,
    )

    assert len(model_files) == test_case.expected_model_file_count

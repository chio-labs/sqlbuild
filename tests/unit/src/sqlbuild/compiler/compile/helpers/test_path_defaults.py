from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.helpers.attachment import find_matching_path_default
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    FindMatchingPathDefaultTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FindMatchingPathDefaultTestCase(
            description="matches Windows-style model path against nested path default",
            model_relative_path="models\\staging\\nested\\orders.sql",
            path_defaults={"staging": {}, "staging/nested": {}},
            expected_path_default="staging/nested",
        )
    ],
    ids=["matches Windows-style model path against nested path default"],
)
def test_given_windows_style_model_path_when_finding_path_default_then_returns_nearest_match(
    test_case: FindMatchingPathDefaultTestCase,
) -> None:
    model_file: DiscoveredSqlModelFile = DiscoveredSqlModelFile(
        file_path=Path("/repo") / test_case.model_relative_path,
        relative_path=Path(test_case.model_relative_path),
        contents="MODEL ();\n\nselect 1\n",
        header_values={},
        header_column_locations={},
        output_column_locations={},
        query_sql="select 1",
    )

    path_default: str | None = find_matching_path_default(
        model_file=model_file,
        path_defaults=test_case.path_defaults,
    )

    assert path_default == test_case.expected_path_default

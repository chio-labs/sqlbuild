from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.validation.discovery import (
    _validate_path_defaults_match_models,
)
from sqlbuild.compiler.discovery.exceptions import DiscoveryConflictError
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    ValidatePathDefaultsMatchModelsErrorTestCase,
    ValidatePathDefaultsMatchModelsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        ValidatePathDefaultsMatchModelsTestCase(
            description="accepts Windows-style model paths that match path defaults",
            model_relative_paths=("models\\staging\\orders.sql",),
            path_defaults={"staging": {}},
            expected_model_file_count=1,
        ),
        ValidatePathDefaultsMatchModelsTestCase(
            description="accepts recursive glob matching nested staging prefix",
            model_relative_paths=("models/market/germantote/staging/orders.sql",),
            path_defaults={"market/**/staging": {}},
            expected_model_file_count=1,
        ),
        ValidatePathDefaultsMatchModelsTestCase(
            description="accepts recursive glob matching zero segments",
            model_relative_paths=("models/market/staging/orders.sql",),
            path_defaults={"market/**/staging": {}},
            expected_model_file_count=1,
        ),
        ValidatePathDefaultsMatchModelsTestCase(
            description="counts broad glob as matched when a literal wins selection",
            model_relative_paths=("models/market/germantote/staging/orders.sql",),
            path_defaults={
                "market/**/staging": {},
                "market/germantote/staging": {},
            },
            expected_model_file_count=1,
        ),
    ),
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    (
        ValidatePathDefaultsMatchModelsErrorTestCase(
            description="rejects recursive glob matching no model paths",
            model_relative_paths=("models/market/germantote/marts/orders.sql",),
            path_defaults={"market/**/staging": {}},
            expected_error_fragment=(
                r"path_defaults\['market/\*\*/staging'\] does not match any model paths"
            ),
        ),
        ValidatePathDefaultsMatchModelsErrorTestCase(
            description="rejects equally specific matching globs during discovery",
            model_relative_paths=("models/market/eu/staging/orders.sql",),
            path_defaults={"market/*/staging": {}, "market/eu/*": {}},
            expected_error_fragment="matches equally specific path_defaults keys",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_glob_matches_when_validating_path_defaults_then_raises_conflict(
    test_case: ValidatePathDefaultsMatchModelsErrorTestCase,
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

    with pytest.raises(DiscoveryConflictError, match=test_case.expected_error_fragment):
        _validate_path_defaults_match_models(
            path_defaults=test_case.path_defaults,
            model_files=model_files,
        )

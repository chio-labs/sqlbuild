from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile._helpers.attachment.core import find_matching_path_default
from sqlbuild.compiler.discovery.exceptions import DiscoveryConflictError
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    FindMatchingPathDefaultErrorTestCase,
    FindMatchingPathDefaultTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        FindMatchingPathDefaultTestCase(
            description="matches Windows-style model path against nested path default",
            model_relative_path="models\\staging\\nested\\orders.sql",
            path_defaults={"staging": {}, "staging/nested": {}},
            expected_path_default="staging/nested",
        ),
        FindMatchingPathDefaultTestCase(
            description="recursive glob matches a staging directory prefix",
            model_relative_path="models/market/germantote/staging/orders.sql",
            path_defaults={"market/**/staging": {}},
            expected_path_default="market/**/staging",
        ),
        FindMatchingPathDefaultTestCase(
            description="recursive glob matches zero path segments",
            model_relative_path="models/market/staging/orders.sql",
            path_defaults={"market/**/staging": {}},
            expected_path_default="market/**/staging",
        ),
        FindMatchingPathDefaultTestCase(
            description="single glob consumes exactly one path segment",
            model_relative_path="models/market/germantote/staging/orders.sql",
            path_defaults={"market/*/staging": {}},
            expected_path_default="market/*/staging",
        ),
        FindMatchingPathDefaultTestCase(
            description="single glob does not consume multiple path segments",
            model_relative_path="models/market/eu/germantote/staging/orders.sql",
            path_defaults={"market/*/staging": {}},
            expected_path_default=None,
        ),
        FindMatchingPathDefaultTestCase(
            description="literal prefix outranks a matching recursive glob",
            model_relative_path="models/market/germantote/staging/orders.sql",
            path_defaults={
                "market/**/staging": {},
                "market/germantote/staging": {},
            },
            expected_path_default="market/germantote/staging",
        ),
        FindMatchingPathDefaultTestCase(
            description="single segment glob outranks recursive glob",
            model_relative_path="models/market/germantote/staging/orders.sql",
            path_defaults={
                "market/**/staging": {},
                "market/*/staging": {},
            },
            expected_path_default="market/*/staging",
        ),
        FindMatchingPathDefaultTestCase(
            description="recursive glob matches Windows-style model path",
            model_relative_path="models\\market\\germantote\\staging\\orders.sql",
            path_defaults={"market/**/staging": {}},
            expected_path_default="market/**/staging",
        ),
    ),
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    (
        FindMatchingPathDefaultErrorTestCase(
            description="equally specific matching globs are ambiguous regardless of values",
            model_relative_path="models/market/eu/staging/orders.sql",
            path_defaults={
                "market/*/staging": {"schema": "shared"},
                "market/eu/*": {"schema": "shared"},
            },
            expected_error_fragment=(
                r"matches equally specific path_defaults keys: "
                r"'market/\*/staging', 'market/eu/\*'"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_ambiguous_globs_when_finding_path_default_then_raises_structured_error(
    test_case: FindMatchingPathDefaultErrorTestCase,
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

    with pytest.raises(DiscoveryConflictError, match=test_case.expected_error_fragment) as error:
        find_matching_path_default(
            model_file=model_file,
            path_defaults=test_case.path_defaults,
        )

    assert error.value.code == "D007"
    assert error.value.help is not None

"""Native cross-file validation raises the discovery errors Python raised, with their text."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    ProjectValidationTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    stage_outcome,
    write_project,
)

_MODEL: tuple[str, bytes] = ("models/orders.sql", b"MODEL ();\nSELECT 1 AS order_id")


def _seed_files(*, header: bytes, settings: bytes = b"") -> tuple[tuple[str, bytes], ...]:
    return (
        _MODEL,
        ("seeds/countries.csv", header + b"\nGB,United Kingdom\n"),
        (
            "seeds/countries.yml",
            b"seeds:\n  - name: countries\n"
            + settings
            + b"    columns:\n      - name: code\n        type: VARCHAR\n"
            b"      - name: label\n        type: VARCHAR\n",
        ),
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectValidationTestCase(
            description="a seed header that differs from its declared columns",
            files=_seed_files(header=b"code,name"),
            expected_error_type="SeedDiscoveryError",
            expected_message=(
                "seeds/countries.csv header ('code', 'name') does not match declared seed "
                "columns ('code', 'label') for 'countries'"
            ),
        ),
        ProjectValidationTestCase(
            description="a quoted seed header honours the declared quotechar",
            files=_seed_files(
                header=b'"code";"label";"extra"',
                settings=b"    csv_settings:\n      delimiter: ';'\n      quotechar: '\"'\n",
            ),
            expected_error_type="SeedDiscoveryError",
            expected_message=(
                "seeds/countries.csv header ('code', 'label', 'extra') does not match declared "
                "seed columns ('code', 'label') for 'countries'"
            ),
        ),
        ProjectValidationTestCase(
            description="a seed CSV without a declaration",
            files=(_MODEL, ("seeds/regions.csv", b"code\nEU\n")),
            expected_error_type="SeedDiscoveryError",
            expected_message=(
                "Seed CSV seeds/regions.csv has no matching declaration for seed 'regions' under "
                "seeds/**/*.yml"
            ),
        ),
        ProjectValidationTestCase(
            description="two model files with one name",
            files=(_MODEL, ("models/marts/orders.sql", b"MODEL ();\nSELECT 2 AS order_id")),
            expected_error_type="DiscoveryConflictError",
            expected_message=(
                "Duplicate model file name found for 'orders' in models/marts/orders.sql and "
                "models/orders.sql"
            ),
        ),
        ProjectValidationTestCase(
            description="a non-canonical model identity",
            files=(("models/Orders.sql", b"MODEL ();\nSELECT 1 AS order_id"),),
            expected_error_type="ResourceIdentityError",
            expected_message=(
                "Invalid model identity 'Orders' in models/Orders.sql; use snake_case 'orders'"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_conflicting_project_files_when_discovering_then_raises_the_discovery_error(
    test_case: ProjectValidationTestCase, tmp_path: Path
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)

    outcome: tuple[object, ...] = stage_outcome(project_dir=tmp_path)

    assert outcome[1:] == (test_case.expected_error_type, test_case.expected_message)


def test_given_an_empty_seed_quotechar_when_discovering_then_raises_the_csv_type_error(
    tmp_path: Path,
) -> None:
    write_project(
        project_dir=tmp_path,
        files=_seed_files(
            header=b"code,label", settings=b"    csv_settings:\n      quotechar: ''\n"
        ),
    )

    with pytest.raises(TypeError, match='"quotechar" must be a 1-character string'):
        discover_project_inputs(project_dir=tmp_path)

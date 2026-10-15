from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild._native import resolve_raw_dbt_profile_connection
from sqlbuild.integrations.dbt.exceptions import DbtProfileError
from sqlbuild.integrations.dbt.models import NormalizedDbtProfileConnection
from tests.unit.src.sqlbuild.integrations.dbt.profile._test_types import (
    DbtProfileConnectionErrorTestCase,
    DbtProfileConnectionTestCase,
    DbtYamlFilesTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.profile.helpers import (
    dbt_workspace_project_config,
    replace_dbt_workspace_file,
    write_duckdb_dbt_workspace,
)

_TWO_TARGETS: str = (
    "shop:\n  target: ' dev '\n  outputs:\n"
    "    ' dev': {type: duckdb, path: first.duckdb}\n"
    "    prod: {type: duckdb, path: prod.duckdb}\n"
    "    'dev ': {type: duckdb, path: last.duckdb}\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtProfileConnectionTestCase(
            description="the project's dbt profile resolves to adapter config",
            raw_config={"source": "dbt_profile", "target": " dev "},
            adapter_name="duckdb",
            expected_connection={"database": "warehouse.duckdb"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_raw_connection_when_resolving_dbt_profile_then_returns_expected_connection(
    test_case: DbtProfileConnectionTestCase, tmp_path: Path
) -> None:
    write_duckdb_dbt_workspace(tmp_path)

    resolved: NormalizedDbtProfileConnection | None = resolve_raw_dbt_profile_connection(
        raw_config=test_case.raw_config,
        project_dir=tmp_path,
        adapter_name=test_case.adapter_name,
        project_config=dbt_workspace_project_config(adapter_name=test_case.adapter_name),
    )

    assert resolved is not None
    assert resolved.connection == test_case.expected_connection


@pytest.mark.parametrize(
    "test_case",
    [
        DbtProfileConnectionTestCase(
            description="a connection without the dbt_profile source is not resolved",
            raw_config={"database": "orders.duckdb"},
            adapter_name="duckdb",
            expected_connection=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_profile_connection_when_resolving_dbt_profile_then_returns_none(
    test_case: DbtProfileConnectionTestCase, tmp_path: Path
) -> None:
    resolved: NormalizedDbtProfileConnection | None = resolve_raw_dbt_profile_connection(
        raw_config=test_case.raw_config,
        project_dir=tmp_path,
        adapter_name=test_case.adapter_name,
        project_config=dbt_workspace_project_config(adapter_name=test_case.adapter_name),
    )

    assert resolved == test_case.expected_connection


@pytest.mark.parametrize(
    "test_case",
    [
        DbtProfileConnectionErrorTestCase(
            description="a blank profile name is rejected",
            raw_config={"source": "dbt_profile", "profile": "  "},
            adapter_name="duckdb",
            expected_error_fragment="dbt_profile connection values must be non-empty strings",
        ),
        DbtProfileConnectionErrorTestCase(
            description="a profile for another adapter is rejected",
            raw_config={"source": "dbt_profile"},
            adapter_name="snowflake",
            expected_error_fragment="dbt=duckdb, sqlbuild=snowflake",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_dbt_profile_reference_when_resolving_then_raises_profile_error(
    test_case: DbtProfileConnectionErrorTestCase, tmp_path: Path
) -> None:
    write_duckdb_dbt_workspace(tmp_path)

    with pytest.raises(DbtProfileError, match=test_case.expected_error_fragment) as captured:
        resolve_raw_dbt_profile_connection(
            raw_config=test_case.raw_config,
            project_dir=tmp_path,
            adapter_name=test_case.adapter_name,
            project_config=dbt_workspace_project_config(adapter_name=test_case.adapter_name),
        )

    assert captured.value.code == "C242"


@pytest.mark.parametrize(
    "test_case",
    [
        DbtYamlFilesTestCase(
            description="padded and repeated output names select the last output",
            relative_path="profiles/profiles.yml",
            contents=_TWO_TARGETS,
            raw_config={"source": "dbt_profile"},
            expected_connection={"database": "last.duckdb"},
        ),
        DbtYamlFilesTestCase(
            description="a requested target overrides the default",
            relative_path="profiles/profiles.yml",
            contents=_TWO_TARGETS,
            raw_config={"source": "dbt_profile", "target": "prod"},
            expected_connection={"database": "prod.duckdb"},
        ),
        DbtYamlFilesTestCase(
            description="an explicit profile skips the project's profile name",
            relative_path="dbt_project/dbt_project.yml",
            contents="name: shop\nprofile: other\n",
            raw_config={"source": "dbt_profile", "profile": "shop"},
            expected_connection={"database": "warehouse.duckdb"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_yaml_files_when_resolving_dbt_profile_then_selected_output_is_used(
    test_case: DbtYamlFilesTestCase, tmp_path: Path
) -> None:
    write_duckdb_dbt_workspace(tmp_path)
    replace_dbt_workspace_file(
        root=tmp_path, relative_path=test_case.relative_path, contents=test_case.contents
    )

    resolved: NormalizedDbtProfileConnection | None = resolve_raw_dbt_profile_connection(
        raw_config=test_case.raw_config,
        project_dir=tmp_path,
        adapter_name="duckdb",
        project_config=dbt_workspace_project_config(adapter_name="duckdb"),
    )

    assert resolved is not None
    assert resolved.connection == test_case.expected_connection


@pytest.mark.parametrize(
    "test_case",
    [
        DbtYamlFilesTestCase(
            description="a project file that is not a mapping is rejected",
            relative_path="dbt_project/dbt_project.yml",
            contents="- shop\n",
            raw_config={"source": "dbt_profile"},
            expected_error_fragment="dbt_project.yml must contain a top-level mapping",
        ),
        DbtYamlFilesTestCase(
            description="invalid project YAML names the file",
            relative_path="dbt_project/dbt_project.yml",
            contents="name: [shop\n",
            raw_config={"source": "dbt_profile"},
            expected_error_fragment="dbt_project.yml contains invalid YAML",
        ),
        DbtYamlFilesTestCase(
            description="a project without a profile name is rejected",
            relative_path="dbt_project/dbt_project.yml",
            contents="name: shop\n",
            raw_config={"source": "dbt_profile"},
            expected_error_fragment="must define non-empty string 'profile'",
        ),
        DbtYamlFilesTestCase(
            description="an undefined profile is rejected",
            relative_path="profiles/profiles.yml",
            contents="other:\n  outputs:\n    dev: {type: duckdb}\n",
            raw_config={"source": "dbt_profile"},
            expected_error_fragment="does not define dbt profile 'shop'",
        ),
        DbtYamlFilesTestCase(
            description="empty outputs are rejected",
            relative_path="profiles/profiles.yml",
            contents="shop:\n  target: dev\n  outputs: {}\n",
            raw_config={"source": "dbt_profile"},
            expected_error_fragment="dbt profile 'shop' must define non-empty outputs",
        ),
        DbtYamlFilesTestCase(
            description="a non-string output name is rejected",
            relative_path="profiles/profiles.yml",
            contents="shop:\n  target: dev\n  outputs:\n    1: {type: duckdb}\n",
            raw_config={"source": "dbt_profile"},
            expected_error_fragment="dbt profile 'shop' contains an invalid output name",
        ),
        DbtYamlFilesTestCase(
            description="no default target asks for one",
            relative_path="profiles/profiles.yml",
            contents="shop:\n  outputs:\n    dev: {type: duckdb}\n",
            raw_config={"source": "dbt_profile"},
            expected_error_fragment="does not define a default target; pass --target",
        ),
        DbtYamlFilesTestCase(
            description="an unknown target lists the sorted targets",
            relative_path="profiles/profiles.yml",
            contents="shop:\n  target: qa\n  outputs:\n    zeta: {type: duckdb}\n"
            "    alpha: {type: duckdb}\n",
            raw_config={"source": "dbt_profile"},
            expected_error_fragment="Available targets: alpha, zeta",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_malformed_dbt_yaml_files_when_resolving_dbt_profile_then_raises_profile_error(
    test_case: DbtYamlFilesTestCase, tmp_path: Path
) -> None:
    write_duckdb_dbt_workspace(tmp_path)
    replace_dbt_workspace_file(
        root=tmp_path, relative_path=test_case.relative_path, contents=test_case.contents
    )

    with pytest.raises(DbtProfileError) as captured:
        resolve_raw_dbt_profile_connection(
            raw_config=test_case.raw_config,
            project_dir=tmp_path,
            adapter_name="duckdb",
            project_config=dbt_workspace_project_config(adapter_name="duckdb"),
        )

    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in str(captured.value)
    assert captured.value.code == "C242"

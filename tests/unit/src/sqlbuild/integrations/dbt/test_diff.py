from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.executor.diff.models import DiffExecutionResult, ModelDiffResult
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError, DbtInteropConfigError
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.pipeline.helpers.diff import (
    DbtDiffOptions,
    execute_dbt_diff,
    parse_dbt_diff_options,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtDiffBoundedCursorErrorTestCase,
    DbtDiffBoundedCursorTestCase,
    DbtDiffExecuteErrorTestCase,
    DbtDiffExecuteTestCase,
    DbtDiffOptionsErrorTestCase,
    DbtDiffOptionsTestCase,
    DbtDiffUniqueKeyErrorTestCase,
    DbtDiffUniqueKeyTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    assert_dbt_diff_execution_result,
    build_dbt_diff_bounded_options,
    build_dbt_diff_full_options,
    build_dbt_diff_ls_node,
    build_dbt_diff_manifest_index,
    build_dbt_diff_schema_only_options,
    create_dbt_diff_cursor_relation,
    create_dbt_diff_relation,
    create_dbt_diff_relation_when_requested,
    create_dbt_diff_relation_with_columns,
    create_dbt_diff_unique_key_relation,
)

DIFF_OPTIONS_TEST_CASES: tuple[DbtDiffOptionsTestCase, ...] = (
    DbtDiffOptionsTestCase(
        description="parses schema only with single select",
        args=("--select", "dbt_orders", "--schema-only"),
        expected_select=("dbt_orders",),
        expected_exclude=(),
        expected_full=False,
        expected_schema_only=True,
        expected_bounded=None,
        expected_verbose=False,
        expected_max_column_examples=3,
        expected_max_row_only_examples=3,
        expected_dbt_args=("--select", "dbt_orders"),
    ),
    DbtDiffOptionsTestCase(
        description="parses full with multi select and exclude",
        args=("--select", "a", "b", "--exclude", "c", "--full"),
        expected_select=("a", "b"),
        expected_exclude=("c",),
        expected_full=True,
        expected_schema_only=False,
        expected_bounded=None,
        expected_verbose=False,
        expected_max_column_examples=3,
        expected_max_row_only_examples=3,
        expected_dbt_args=("--select", "a", "b", "--exclude", "c"),
    ),
    DbtDiffOptionsTestCase(
        description="parses bounded duration",
        args=("--select", "dbt_orders", "--bounded", "7d"),
        expected_select=("dbt_orders",),
        expected_exclude=(),
        expected_full=False,
        expected_schema_only=False,
        expected_bounded="7d",
        expected_verbose=False,
        expected_max_column_examples=3,
        expected_max_row_only_examples=3,
        expected_dbt_args=("--select", "dbt_orders"),
    ),
    DbtDiffOptionsTestCase(
        description="verbose raises example caps",
        args=("--select", "dbt_orders", "--full", "--verbose"),
        expected_select=("dbt_orders",),
        expected_exclude=(),
        expected_full=True,
        expected_schema_only=False,
        expected_bounded=None,
        expected_verbose=True,
        expected_max_column_examples=10,
        expected_max_row_only_examples=10,
        expected_dbt_args=("--select", "dbt_orders"),
    ),
    DbtDiffOptionsTestCase(
        description="parses explicit example caps and forwards dbt flags",
        args=(
            "--select",
            "dbt_orders",
            "--full",
            "--max-column-examples",
            "7",
            "--max-row-only-examples",
            "9",
            "--target",
            "prod",
            "--profiles-dir",
            "profiles",
        ),
        expected_select=("dbt_orders",),
        expected_exclude=(),
        expected_full=True,
        expected_schema_only=False,
        expected_bounded=None,
        expected_verbose=False,
        expected_max_column_examples=7,
        expected_max_row_only_examples=9,
        expected_dbt_args=(
            "--select",
            "dbt_orders",
            "--target",
            "prod",
            "--profiles-dir",
            "profiles",
        ),
    ),
)

DIFF_OPTIONS_ERROR_TEST_CASES: tuple[DbtDiffOptionsErrorTestCase, ...] = (
    DbtDiffOptionsErrorTestCase(
        description="rejects no mode",
        args=("--select", "dbt_orders"),
        expected_error_fragment="exactly one of --full, --schema-only, or --bounded",
        expected_code="C201",
    ),
    DbtDiffOptionsErrorTestCase(
        description="rejects two modes",
        args=("--select", "dbt_orders", "--full", "--schema-only"),
        expected_error_fragment="exactly one of --full, --schema-only, or --bounded",
        expected_code="C201",
    ),
    DbtDiffOptionsErrorTestCase(
        description="rejects three modes",
        args=("--select", "dbt_orders", "--full", "--schema-only", "--bounded", "7d"),
        expected_error_fragment="exactly one of --full, --schema-only, or --bounded",
        expected_code="C201",
    ),
    DbtDiffOptionsErrorTestCase(
        description="rejects non positive column examples",
        args=("--select", "dbt_orders", "--full", "--max-column-examples", "0"),
        expected_error_fragment="--max-column-examples must be positive",
        expected_code="C202",
    ),
)

DIFF_UNIQUE_KEY_TEST_CASES: tuple[DbtDiffUniqueKeyTestCase, ...] = (
    DbtDiffUniqueKeyTestCase(
        description="uses string unique key",
        config={"unique_key": "order_id"},
        expected_unique_key=("order_id",),
    ),
    DbtDiffUniqueKeyTestCase(
        description="uses list unique key",
        config={"unique_key": ["order_id", "line_id"]},
        expected_unique_key=("order_id", "line_id"),
    ),
)

DIFF_UNIQUE_KEY_ERROR_TEST_CASES: tuple[DbtDiffUniqueKeyErrorTestCase, ...] = (
    DbtDiffUniqueKeyErrorTestCase(
        description="missing unique key errors",
        config={},
        expected_error_fragment="requires model 'dbt_orders' to define config.unique_key",
        expected_code="C341",
    ),
    DbtDiffUniqueKeyErrorTestCase(
        description="empty string unique key errors",
        config={"unique_key": ""},
        expected_error_fragment="requires model 'dbt_orders' to define config.unique_key",
        expected_code="C341",
    ),
)

DIFF_BOUNDED_CURSOR_TEST_CASES: tuple[DbtDiffBoundedCursorTestCase, ...] = (
    DbtDiffBoundedCursorTestCase(
        description="timestamp cursor from node meta",
        node_meta={"sqlbuild": {"cursor": "updated_at", "cursor_type": "timestamp"}},
        config_meta=None,
        bounded="7d",
        expected_cursor_column="updated_at",
        expected_cursor_kind="timestamp",
        expected_has_end_cursor=True,
    ),
    DbtDiffBoundedCursorTestCase(
        description="integer cursor from config meta fallback",
        node_meta=None,
        config_meta={"sqlbuild": {"cursor": "batch_id", "cursor_type": "integer"}},
        bounded="1000",
        expected_cursor_column="batch_id",
        expected_cursor_kind="integer",
        expected_has_end_cursor=False,
    ),
)

DIFF_BOUNDED_CURSOR_ERROR_TEST_CASES: tuple[DbtDiffBoundedCursorErrorTestCase, ...] = (
    DbtDiffBoundedCursorErrorTestCase(
        description="missing sqlbuild meta errors",
        node_meta=None,
        config_meta=None,
        bounded="7d",
        expected_error_fragment="requires model 'dbt_orders' to define SQLBuild cursor metadata",
        expected_code="C342",
    ),
    DbtDiffBoundedCursorErrorTestCase(
        description="bad cursor type errors",
        node_meta={"sqlbuild": {"cursor": "updated_at", "cursor_type": "weird"}},
        config_meta=None,
        bounded="7d",
        expected_error_fragment="requires model 'dbt_orders' to define SQLBuild cursor metadata",
        expected_code="C342",
    ),
    DbtDiffBoundedCursorErrorTestCase(
        description="bad timestamp duration errors",
        node_meta={"sqlbuild": {"cursor": "updated_at", "cursor_type": "timestamp"}},
        config_meta=None,
        bounded="seven",
        expected_error_fragment="requires duration like 30d, 12h, or 15m",
        expected_code="C344",
    ),
    DbtDiffBoundedCursorErrorTestCase(
        description="bad integer bound errors",
        node_meta={"sqlbuild": {"cursor": "batch_id", "cursor_type": "integer"}},
        config_meta=None,
        bounded="lots",
        expected_error_fragment="requires an integer bound",
        expected_code="C343",
    ),
)

DIFF_EXECUTE_TEST_CASES: tuple[DbtDiffExecuteTestCase, ...] = (
    DbtDiffExecuteTestCase(
        description="schema only path skips row diff",
        options_args=("--select", "dbt_orders", "--schema-only"),
        current_rows=((1, 111),),
        reuse_rows=((1, 900),),
        node_resource_type="model",
        expected_model_names=("dbt_orders",),
        expected_has_row_result=False,
        expected_unequal_count=0,
        expected_left_only_count=0,
        expected_right_only_count=0,
        expected_has_failures=False,
    ),
    DbtDiffExecuteTestCase(
        description="full path reports row differences",
        options_args=("--select", "dbt_orders", "--full"),
        current_rows=((1, 111), (3, 777), (4, 400)),
        reuse_rows=((1, 900), (2, 250)),
        node_resource_type="model",
        expected_model_names=("dbt_orders",),
        expected_has_row_result=True,
        expected_unequal_count=1,
        expected_left_only_count=1,
        expected_right_only_count=2,
        expected_has_failures=True,
    ),
    DbtDiffExecuteTestCase(
        description="non model nodes are skipped",
        options_args=("--select", "dbt_orders", "--schema-only"),
        current_rows=((1, 111),),
        reuse_rows=((1, 900),),
        node_resource_type="test",
        expected_model_names=(),
        expected_has_row_result=False,
        expected_unequal_count=0,
        expected_left_only_count=0,
        expected_right_only_count=0,
        expected_has_failures=False,
    ),
)

DIFF_EXECUTE_ERROR_TEST_CASES: tuple[DbtDiffExecuteErrorTestCase, ...] = (
    DbtDiffExecuteErrorTestCase(
        description="missing reuse relation errors",
        schema_only=True,
        create_current_relation=True,
        create_reuse_relation=False,
        expected_error_fragment="relation for model 'dbt_orders' does not exist",
        expected_code="C340",
    ),
    DbtDiffExecuteErrorTestCase(
        description="missing current relation errors",
        schema_only=True,
        create_current_relation=False,
        create_reuse_relation=True,
        expected_error_fragment="relation for model 'dbt_orders' does not exist",
        expected_code="C340",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    DIFF_OPTIONS_TEST_CASES,
    ids=[case.description for case in DIFF_OPTIONS_TEST_CASES],
)
def test_given_diff_args_when_parsing_then_returns_expected_options(
    test_case: DbtDiffOptionsTestCase,
) -> None:
    parsed: DbtDiffOptions = parse_dbt_diff_options(test_case.args)

    assert parsed.select == test_case.expected_select
    assert parsed.exclude == test_case.expected_exclude
    assert parsed.full == test_case.expected_full
    assert parsed.schema_only == test_case.expected_schema_only
    assert parsed.bounded == test_case.expected_bounded
    assert parsed.verbose == test_case.expected_verbose
    assert parsed.max_column_examples == test_case.expected_max_column_examples
    assert parsed.max_row_only_examples == test_case.expected_max_row_only_examples
    assert parsed.dbt_args == test_case.expected_dbt_args


@pytest.mark.parametrize(
    "test_case",
    DIFF_OPTIONS_ERROR_TEST_CASES,
    ids=[case.description for case in DIFF_OPTIONS_ERROR_TEST_CASES],
)
def test_given_invalid_diff_args_when_parsing_then_raises_clear_error(
    test_case: DbtDiffOptionsErrorTestCase,
) -> None:
    with pytest.raises(DbtInteropArgumentError) as exc_info:
        parse_dbt_diff_options(test_case.args)

    assert test_case.expected_error_fragment in str(exc_info.value)
    assert exc_info.value.code == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    DIFF_UNIQUE_KEY_TEST_CASES,
    ids=[case.description for case in DIFF_UNIQUE_KEY_TEST_CASES],
)
def test_given_dbt_model_unique_key_when_diffing_full_then_uses_expected_key(
    test_case: DbtDiffUniqueKeyTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "diff.duckdb")})
    try:
        create_dbt_diff_unique_key_relation(
            adapter=adapter,
            connection=connection,
            schema="prod",
            amount_cents=900,
        )
        create_dbt_diff_unique_key_relation(
            adapter=adapter,
            connection=connection,
            schema="main",
            amount_cents=111,
        )
        current_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="main",
            relation_name="main.dbt_orders",
            config=test_case.config,
        )
        reuse_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="prod",
            relation_name="prod.dbt_orders",
            config=test_case.config,
        )
        result: DiffExecutionResult = execute_dbt_diff(
            adapter=adapter,
            connection=connection,
            current_manifest=current_index,
            reuse_manifest=reuse_index,
            selected_nodes=(build_dbt_diff_ls_node(),),
            options=build_dbt_diff_full_options(),
        )

        model_result: ModelDiffResult = result.model_results[0]
        assert model_result.unique_key == test_case.expected_unique_key
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    DIFF_UNIQUE_KEY_ERROR_TEST_CASES,
    ids=[case.description for case in DIFF_UNIQUE_KEY_ERROR_TEST_CASES],
)
def test_given_missing_unique_key_when_diffing_full_then_raises_clear_error(
    test_case: DbtDiffUniqueKeyErrorTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "diff.duckdb")})
    try:
        create_dbt_diff_relation(
            adapter=adapter,
            connection=connection,
            schema="prod",
            name="dbt_orders",
            rows=((1, 900),),
        )
        create_dbt_diff_relation(
            adapter=adapter,
            connection=connection,
            schema="main",
            name="dbt_orders",
            rows=((1, 111),),
        )
        current_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="main",
            relation_name="main.dbt_orders",
            config=test_case.config,
        )
        reuse_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="prod",
            relation_name="prod.dbt_orders",
            config=test_case.config,
        )
        with pytest.raises(DbtInteropConfigError) as exc_info:
            execute_dbt_diff(
                adapter=adapter,
                connection=connection,
                current_manifest=current_index,
                reuse_manifest=reuse_index,
                selected_nodes=(build_dbt_diff_ls_node(),),
                options=build_dbt_diff_full_options(),
            )

        assert test_case.expected_error_fragment in str(exc_info.value)
        assert exc_info.value.code == test_case.expected_code
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    DIFF_BOUNDED_CURSOR_TEST_CASES,
    ids=[case.description for case in DIFF_BOUNDED_CURSOR_TEST_CASES],
)
def test_given_bounded_cursor_metadata_when_diffing_then_runs_without_error(
    test_case: DbtDiffBoundedCursorTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "diff.duckdb")})
    try:
        create_dbt_diff_cursor_relation(
            adapter=adapter,
            connection=connection,
            schema="prod",
            cursor_column=test_case.expected_cursor_column,
            cursor_kind=test_case.expected_cursor_kind,
        )
        create_dbt_diff_cursor_relation(
            adapter=adapter,
            connection=connection,
            schema="main",
            cursor_column=test_case.expected_cursor_column,
            cursor_kind=test_case.expected_cursor_kind,
        )
        current_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="main",
            relation_name="main.dbt_orders",
            config={"unique_key": "order_id"},
            node_meta=test_case.node_meta,
            config_meta=test_case.config_meta,
        )
        reuse_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="prod",
            relation_name="prod.dbt_orders",
            config={"unique_key": "order_id"},
            node_meta=test_case.node_meta,
            config_meta=test_case.config_meta,
        )
        result: DiffExecutionResult = execute_dbt_diff(
            adapter=adapter,
            connection=connection,
            current_manifest=current_index,
            reuse_manifest=reuse_index,
            selected_nodes=(build_dbt_diff_ls_node(),),
            options=build_dbt_diff_bounded_options(test_case.bounded),
        )

        assert result.model_results[0].row_result is not None
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    DIFF_BOUNDED_CURSOR_ERROR_TEST_CASES,
    ids=[case.description for case in DIFF_BOUNDED_CURSOR_ERROR_TEST_CASES],
)
def test_given_bad_bounded_cursor_metadata_when_diffing_then_raises_clear_error(
    test_case: DbtDiffBoundedCursorErrorTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "diff.duckdb")})
    try:
        create_dbt_diff_relation(
            adapter=adapter,
            connection=connection,
            schema="prod",
            name="dbt_orders",
            rows=((1, 900),),
        )
        create_dbt_diff_relation(
            adapter=adapter,
            connection=connection,
            schema="main",
            name="dbt_orders",
            rows=((1, 111),),
        )
        current_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="main",
            relation_name="main.dbt_orders",
            config={"unique_key": "order_id"},
            node_meta=test_case.node_meta,
            config_meta=test_case.config_meta,
        )
        reuse_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="prod",
            relation_name="prod.dbt_orders",
            config={"unique_key": "order_id"},
            node_meta=test_case.node_meta,
            config_meta=test_case.config_meta,
        )
        with pytest.raises((DbtInteropConfigError, DbtInteropArgumentError)) as exc_info:
            execute_dbt_diff(
                adapter=adapter,
                connection=connection,
                current_manifest=current_index,
                reuse_manifest=reuse_index,
                selected_nodes=(build_dbt_diff_ls_node(),),
                options=build_dbt_diff_bounded_options(test_case.bounded),
            )

        assert test_case.expected_error_fragment in str(exc_info.value)
        assert exc_info.value.code == test_case.expected_code
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    DIFF_EXECUTE_TEST_CASES,
    ids=[case.description for case in DIFF_EXECUTE_TEST_CASES],
)
def test_given_dbt_relations_when_executing_diff_then_returns_expected_result(
    test_case: DbtDiffExecuteTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "diff.duckdb")})
    try:
        create_dbt_diff_relation(
            adapter=adapter,
            connection=connection,
            schema="prod",
            name="dbt_orders",
            rows=test_case.reuse_rows,
        )
        create_dbt_diff_relation(
            adapter=adapter,
            connection=connection,
            schema="main",
            name="dbt_orders",
            rows=test_case.current_rows,
        )
        current_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="main",
            relation_name="main.dbt_orders",
            config={"unique_key": "order_id"},
        )
        reuse_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="prod",
            relation_name="prod.dbt_orders",
            config={"unique_key": "order_id"},
        )
        result: DiffExecutionResult = execute_dbt_diff(
            adapter=adapter,
            connection=connection,
            current_manifest=current_index,
            reuse_manifest=reuse_index,
            selected_nodes=(build_dbt_diff_ls_node(resource_type=test_case.node_resource_type),),
            options=parse_dbt_diff_options(test_case.options_args),
        )

        assert_dbt_diff_execution_result(
            result=result,
            expected_model_names=test_case.expected_model_names,
            expected_has_row_result=test_case.expected_has_row_result,
            expected_unequal_count=test_case.expected_unequal_count,
            expected_left_only_count=test_case.expected_left_only_count,
            expected_right_only_count=test_case.expected_right_only_count,
            expected_has_failures=test_case.expected_has_failures,
        )
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    DIFF_EXECUTE_ERROR_TEST_CASES,
    ids=[case.description for case in DIFF_EXECUTE_ERROR_TEST_CASES],
)
def test_given_missing_relation_when_executing_diff_then_raises_clear_error(
    test_case: DbtDiffExecuteErrorTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "diff.duckdb")})
    try:
        create_dbt_diff_relation_when_requested(
            adapter=adapter,
            connection=connection,
            schema="prod",
            create=test_case.create_reuse_relation,
        )
        create_dbt_diff_relation_when_requested(
            adapter=adapter,
            connection=connection,
            schema="main",
            create=test_case.create_current_relation,
        )
        current_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="main",
            relation_name="main.dbt_orders",
            config={"unique_key": "order_id"},
        )
        reuse_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="prod",
            relation_name="prod.dbt_orders",
            config={"unique_key": "order_id"},
        )
        with pytest.raises(DbtInteropConfigError) as exc_info:
            execute_dbt_diff(
                adapter=adapter,
                connection=connection,
                current_manifest=current_index,
                reuse_manifest=reuse_index,
                selected_nodes=(build_dbt_diff_ls_node(),),
                options=build_dbt_diff_schema_only_options(),
            )

        assert test_case.expected_error_fragment in str(exc_info.value)
        assert exc_info.value.code == test_case.expected_code
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtDiffExecuteTestCase(
            description="schema only detects added column as a failure",
            options_args=("--select", "dbt_orders", "--schema-only"),
            current_rows=(),
            reuse_rows=(),
            node_resource_type="model",
            expected_model_names=("dbt_orders",),
            expected_has_row_result=False,
            expected_unequal_count=0,
            expected_left_only_count=0,
            expected_right_only_count=0,
            expected_has_failures=True,
        )
    ],
    ids=["schema only detects added column as a failure"],
)
def test_given_schema_difference_when_diffing_then_reports_failure(
    test_case: DbtDiffExecuteTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "diff.duckdb")})
    try:
        create_dbt_diff_relation_with_columns(
            adapter=adapter,
            connection=connection,
            schema="prod",
            column_sql="1 AS order_id, 900 AS amount_cents",
        )
        create_dbt_diff_relation_with_columns(
            adapter=adapter,
            connection=connection,
            schema="main",
            column_sql="1 AS order_id, 900 AS amount_cents, 'usd' AS currency",
        )
        current_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="main",
            relation_name="main.dbt_orders",
            config={"unique_key": "order_id"},
        )
        reuse_index: DbtManifestIndex = build_dbt_diff_manifest_index(
            schema="prod",
            relation_name="prod.dbt_orders",
            config={"unique_key": "order_id"},
        )
        result: DiffExecutionResult = execute_dbt_diff(
            adapter=adapter,
            connection=connection,
            current_manifest=current_index,
            reuse_manifest=reuse_index,
            selected_nodes=(build_dbt_diff_ls_node(),),
            options=parse_dbt_diff_options(test_case.options_args),
        )

        assert_dbt_diff_execution_result(
            result=result,
            expected_model_names=test_case.expected_model_names,
            expected_has_row_result=test_case.expected_has_row_result,
            expected_unequal_count=test_case.expected_unequal_count,
            expected_left_only_count=test_case.expected_left_only_count,
            expected_right_only_count=test_case.expected_right_only_count,
            expected_has_failures=test_case.expected_has_failures,
        )
        assert result.model_results[0].schema_result.added_columns
    finally:
        adapter.close(connection)

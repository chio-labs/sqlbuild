from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild import _native
from sqlbuild.compiler.discovery._helpers.filesystem.core import discover_model_files
from sqlbuild.compiler.discovery._helpers.sql import model_files as model_file_helpers
from sqlbuild.compiler.discovery._helpers.sql.model_files import (
    model_header_column_locations,
    model_output_column_locations,
    parse_model_sql,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlModelFile,
    DiscoveryFileFault,
    NamedSqlHookEntry,
    PythonHookEntry,
    SqlHookEntry,
)
from sqlbuild.spec.contracts.models import SourceLocation
from sqlbuild.sql_values.models import AuthoredSqlSet, AuthoredSqlValueCall
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    DeferredModelOutputLocationTestCase,
    ModelHeaderColumnLocationTestCase,
    ModelOutputColumnLocationTestCase,
    ParseModelSqlErrorTestCase,
    ParseModelSqlHeaderTestCase,
)


def test_given_unique_model_headers_when_discovering_then_native_tokenization_is_batched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models_dir: Path = tmp_path / "models"
    models_dir.mkdir()
    first_header = "batch_marker_first one, columns (café (type INTEGER))"
    second_header = "batch_marker_second two, columns (total (type DECIMAL(10,2)))"
    (models_dir / "first.sql").write_text(
        f"MODEL ({first_header});\nSELECT 1 AS café\n", encoding="utf-8"
    )
    (models_dir / "second.sql").write_text(
        f"MODEL ({second_header});\nSELECT 2 AS total\n", encoding="utf-8"
    )
    native_calls: list[list[str]] = []
    native_parse = _native.parse_model_headers

    def recording_tokenize(
        headers: list[str],
    ) -> list[
        tuple[
            dict[str, object] | None,
            list[tuple[str, int, int]] | None,
            str | None,
        ]
    ]:
        native_calls.append(headers)
        return native_parse(headers)

    monkeypatch.setattr(model_file_helpers._native, "parse_model_headers", recording_tokenize)

    discovered = discover_model_files(project_dir=tmp_path)

    assert native_calls == [[first_header, second_header]]
    assert [model.header_values for model in discovered] == [
        {"batch_marker_first": "one", "columns": {"café": {"type": "INTEGER"}}},
        {
            "batch_marker_second": "two",
            "columns": {"total": {"type": "DECIMAL(10,2)"}},
        },
    ]
    assert discovered[0].header_column_locations["café"] == SourceLocation(
        path=Path("models/first.sql"), line=1, column=41, end_line=1, end_column=45
    )


def test_given_native_pool_construction_error_when_preparing_headers_then_error_is_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def rejecting_tokenize(_headers: list[str]) -> object:
        raise ValueError("MODEL header worker pool construction failed")

    monkeypatch.setattr(model_file_helpers._native, "parse_model_headers", rejecting_tokenize)

    with pytest.raises(ValueError, match="MODEL header worker pool construction failed"):
        model_file_helpers.prepare_model_header_tokens(["pool_error_marker value"])


def test_given_cached_model_header_when_parsing_twice_then_top_level_dictionaries_are_fresh() -> (
    None
):
    contents = "MODEL (config (transient true), tags [core]); SELECT 1"

    first, _ = parse_model_sql(contents=contents, file_path=Path("first.sql"))
    second, _ = parse_model_sql(contents=contents, file_path=Path("second.sql"))
    first["added"] = "value"

    assert first is not second
    assert "added" not in second


def test_given_generated_header_corpus_when_native_parsing_then_parent_behavior_is_exact() -> None:
    headers: list[str] = [
        "config (columns (nested (type INTEGER))), columns (top (type INTEGER))",
        "config (columns (nested (type INTEGER)))",
    ]
    for index in range(9_998):
        suffix: str = str(index)
        variant: int = index % 10
        if variant == 0:
            headers.append(
                f"name model_{suffix}, enabled true, columns (col_{suffix} "
                '(type DECIMAL(10,2), nullable false, description "Order total"))'
            )
        elif variant == 1:
            headers.append(
                f"constants (_set_{suffix} {{FR, GB, FR}}, "
                f"_array_{suffix} constant(value [1, 2], render_as array))"
            )
        elif variant == 2:
            headers.append(
                f'pre_hooks [inline_sql("select {index}"), sql("record_{suffix}", '
                'table: "orders"), python("notify", attempts: 2, urgent: true)]'
            )
        elif variant == 3:
            headers.append(
                f"audits [rate_{suffix} (thresholds (warn (outside -1.5 2.5)))], "
                f'parent __ref("orders_{suffix}")'
            )
        elif variant == 4:
            headers.append(
                f"schema dev_${{user_{suffix}}}, tags [core, 'daily orders'], value null"
            )
        elif variant == 5:
            headers.append(
                f"columns (café_{suffix} (type TIMESTAMP_NTZ(9), audits "
                "[accepted_values (values [placed, completed])]))"
            )
        elif variant == 6:
            numeric_variant: int = (index // 10) % 6
            if numeric_variant == 0:
                headers.append(f"unicode_integer_{suffix} +١٢٣")
            elif numeric_variant == 1:
                headers.append(f"unicode_integer_{suffix} -१२३")
            elif numeric_variant == 2:
                headers.append(f"unicode_float_{suffix} ١٢.٥")
            elif numeric_variant == 3:
                headers.append(f"unicode_float_{suffix} -१२.५")
            elif numeric_variant == 4:
                headers.append(f"numeric_character_{suffix} ²")
            else:
                headers.append(f"large_{suffix} {10**40 + index}, ratio_{suffix} +.25")
        elif variant == 7:
            headers.append(f'description "escaped \\"value_{suffix}\\"", config (x [a, b])')
        elif variant == 8:
            if index % 20 == 8:
                headers.append(f"duplicate_{suffix} one, duplicate_{suffix} two")
            else:
                headers.append('post_hooks [python("\u001c")]')
        else:
            headers.append(f"columns (col_{suffix} (type DECIMAL(10,2))")

    native_results = _native.parse_model_headers(headers)
    for header, (native_values, native_offsets, native_error) in zip(
        headers, native_results, strict=True
    ):
        try:
            parent_values: dict[str, object] | None = model_file_helpers._ModelHeaderParser(
                header=header
            ).parse()
            parent_error: str | None = None
        except model_file_helpers.ModelHeaderSyntaxError as error:
            parent_values = None
            parent_error = str(error)
        assert native_error == parent_error
        if native_values is None:
            assert parent_values is None
            assert native_offsets is None
            continue
        assert model_file_helpers._project_native_header_map(native_values) == parent_values
        assert native_offsets == _parent_column_offsets(header)


def _parent_column_offsets(header: str) -> list[tuple[str, int, int]]:
    tokens = model_file_helpers._tokenize_model_header_for_spans(header)
    offsets: list[tuple[str, int, int]] = []
    depth: int = 0
    in_columns: bool = False
    for index, token in enumerate(tokens):
        if token.kind == "end":
            break
        if token.kind == "word" and token.value == "columns" and depth == 0:
            in_columns = tokens[index + 1].value == "("
        elif in_columns and token.kind == "word" and depth == 1:
            offsets.append((token.value, token.position, len(token.value)))
        if token.kind == "symbol" and token.value == "(":
            depth += 1
        elif token.kind == "symbol" and token.value == ")":
            depth -= 1
            if in_columns and depth == 0:
                break
    return offsets


def test_given_multiple_invalid_model_headers_when_discovering_then_fault_order_is_preserved(
    tmp_path: Path,
) -> None:
    models_dir: Path = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "first.sql").write_text(
        'MODEL (schema "unterminated); SELECT 1', encoding="utf-8"
    )
    (models_dir / "second.sql").write_text("MODEL (schema ${MISSING); SELECT 2", encoding="utf-8")
    faults: list[DiscoveryFileFault] = []

    discovered = discover_model_files(project_dir=tmp_path, on_fault=faults.append)

    assert discovered == ()
    assert [fault.path for fault in faults] == [
        Path("models/first.sql"),
        Path("models/second.sql"),
    ]
    assert "unterminated double-quoted string at position 7" in faults[0].message
    assert "unterminated template value at position 7" in faults[1].message


@pytest.mark.parametrize(
    "test_case",
    [
        DeferredModelOutputLocationTestCase(
            description="defers output locations without implicit alias extraction",
            expected_extract_implicit_alias_columns=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_deferred_output_locations_when_discovering_models_then_projection_scan_is_skipped(
    tmp_path: Path,
    test_case: DeferredModelOutputLocationTestCase,
) -> None:
    models_dir: Path = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "orders.sql").write_text(
        "MODEL (materialized view);\n\nSELECT 1 AS order_id\n",
        encoding="utf-8",
    )

    model_file: DiscoveredSqlModelFile = discover_model_files(
        project_dir=tmp_path,
        extract_implicit_alias_columns=(test_case.expected_extract_implicit_alias_columns),
        extract_output_column_locations=False,
    )[0]

    assert model_file.output_column_locations == {}
    assert model_file.output_column_locations_extracted is False
    assert (
        model_file.extract_implicit_alias_columns
        is test_case.expected_extract_implicit_alias_columns
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ParseModelSqlHeaderTestCase(
            description="preserves authored set and typed constant calls",
            contents="""
        MODEL (
          constants (
            _countries {"FR", "GB", "FR"},
            _array constant(value [1, 2], render_as array),
          ),
        );

        SELECT 1
        """,
            expected_header_values={
                "constants": {
                    "_countries": AuthoredSqlSet(("FR", "GB", "FR")),
                    "_array": AuthoredSqlValueCall(
                        arguments=(("value", [1, 2]), ("render_as", "array"))
                    ),
                }
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts an empty model header",
            contents="""
        MODEL ();

        SELECT 1 AS order_id
        """,
            expected_header_values={},
            expected_query="SELECT 1 AS order_id",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts nested map and list header values",
            contents="""
        MODEL (
          materialized incremental,
          unique_key [order_id],
          config (
            cluster_by [event_day],
            transient true,
          ),
          row_diff_tolerances (
            revenue bounded-30d,
            order_count full,
          ),
        );

        SELECT order_id, event_day FROM raw_orders
        """,
            expected_header_values={
                "materialized": "incremental",
                "unique_key": ["order_id"],
                "config": {
                    "cluster_by": ["event_day"],
                    "transient": True,
                },
                "row_diff_tolerances": {
                    "revenue": "bounded-30d",
                    "order_count": "full",
                },
            },
            expected_query="SELECT order_id, event_day FROM raw_orders",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts blank lines and indentation inside the header",
            contents="""

        MODEL (
            materialized table,

            tags [core],
            enabled true,
        );

        SELECT 1
        """,
            expected_header_values={
                "materialized": "table",
                "tags": ["core"],
                "enabled": True,
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts quoted and unquoted string scalars",
            contents="""
        MODEL (
          materialized table,
          schema analytics,
          database preserve,
          replay_on_change bounded-30d,
        );

        SELECT 1
        """,
            expected_header_values={
                "materialized": "table",
                "schema": "analytics",
                "database": "preserve",
                "replay_on_change": "bounded-30d",
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts an unquoted parameterized column type",
            contents="""
        MODEL (
          columns (
            amount (type DECIMAL(10,2), nullable false),
            observed_at (type TIMESTAMP_NTZ(9)),
            legacy_amount (type "DECIMAL(12,3)"),
          ),
        );

        SELECT 1 AS amount, CURRENT_TIMESTAMP AS observed_at
        """,
            expected_header_values={
                "columns": {
                    "amount": {"type": "DECIMAL(10,2)", "nullable": False},
                    "observed_at": {"type": "TIMESTAMP_NTZ(9)"},
                    "legacy_amount": {"type": "DECIMAL(12,3)"},
                }
            },
            expected_query="SELECT 1 AS amount, CURRENT_TIMESTAMP AS observed_at",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts effective batch size token",
            contents="""
        MODEL (
          materialized incremental,
          incremental_mode microbatch,
          batch_size effective,
        );

        SELECT 1
        """,
            expected_header_values={
                "materialized": "incremental",
                "incremental_mode": "microbatch",
                "batch_size": "effective",
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts quoted, unquoted, and mixed string lists",
            contents="""
        MODEL (
          tags [core, 'finance', "data platform", marts],
          unique_key [order_id, customer_id],
        );

        SELECT 1
        """,
            expected_header_values={
                "tags": ["core", "finance", "data platform", "marts"],
                "unique_key": ["order_id", "customer_id"],
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts double quoted strings and escapes",
            contents="""
        MODEL (
          schema "analytics mart",
          description "Bob said \\"hello\\"",
          post_hooks [inline_sql("grant select on @@CTX:destination.qualified to role analytics")],
        );

        SELECT 1
        """,
            expected_header_values={
                "schema": "analytics mart",
                "description": 'Bob said "hello"',
                "post_hooks": [
                    SqlHookEntry(
                        statement="grant select on @@CTX:destination.qualified to role analytics"
                    )
                ],
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts template-like strings when quoted",
            contents="""
        MODEL (
          schema 'dev_${user}',
          database 'ci_${ENV:GITHUB_RUN_ID}_${CTX:schema}',
          alias fact_orders,
        );

        SELECT 1
        """,
            expected_header_values={
                "schema": "dev_${user}",
                "database": "ci_${ENV:GITHUB_RUN_ID}_${CTX:schema}",
                "alias": "fact_orders",
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts nested maps with mixed quoted and unquoted strings",
            contents="""
        MODEL (
          row_diff_tolerances (
            revenue bounded-30d,
            order_count full,
          ),
          config (
            cluster_by [event_day, 'region'],
            transient true,
          ),
        );

        SELECT 1
        """,
            expected_header_values={
                "row_diff_tolerances": {
                    "revenue": "bounded-30d",
                    "order_count": "full",
                },
                "config": {
                    "cluster_by": ["event_day", "region"],
                    "transient": True,
                },
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts booleans and integers from unquoted scalars",
            contents="""
        MODEL (
          enabled false,
          batch_concurrency 4,
          config (
            transient true,
          ),
        );

        SELECT 1
        """,
            expected_header_values={
                "enabled": False,
                "batch_concurrency": 4,
                "config": {
                    "transient": True,
                },
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts callable audit entries in header lists",
            contents="""
        MODEL (
          columns (
            status (
              audits [accepted_values (values ["placed", "completed"])],
            ),
          ),
        );

        SELECT 1
        """,
            expected_header_values={
                "columns": {
                    "status": {
                        "audits": [
                            {"accepted_values": {"values": ["placed", "completed"]}},
                        ],
                    },
                },
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts ordinary outside audit argument",
            contents="MODEL (audits [custom_check (outside 5)]); SELECT 1",
            expected_header_values={
                "audits": [{"custom_check": {"outside": 5}}],
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts outside threshold shorthand in threshold policy",
            contents=("MODEL (audits [rate (thresholds (warn (outside 1 5)))]); SELECT 1"),
            expected_header_values={
                "audits": [
                    {"rate": {"thresholds": {"warn": {"outside": (1, 5)}}}},
                ],
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts relation calls as audit argument values",
            contents="""
        MODEL (
          columns (
            customer_id (
              audits [relationships (to __ref("dim_customers"), field customer_id)],
            ),
          ),
        );

        SELECT 1
        """,
            expected_header_values={
                "columns": {
                    "customer_id": {
                        "audits": [
                            {
                                "relationships": {
                                    "to": '__ref("dim_customers")',
                                    "field": "customer_id",
                                }
                            },
                        ],
                    },
                },
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts typed SQL and Python lifecycle hooks",
            contents="""
        MODEL (
          pre_hooks [
            inline_sql("insert into audit_log select 'starting'"),
            sql("record_start", table: "audit_log"),
            python("notify", channel: "#data", attempts: 2, urgent: true),
          ],
          post_hooks [
            python("notify_success", message: "@@CTX:destination.qualified"),
            inline_sql("grant select on @@CTX:destination.qualified to role analytics"),
          ],
        );

        SELECT 1
        """,
            expected_header_values={
                "pre_hooks": [
                    SqlHookEntry(statement="insert into audit_log select 'starting'"),
                    NamedSqlHookEntry(name="record_start", kwargs={"table": "audit_log"}),
                    PythonHookEntry(
                        name="notify",
                        kwargs={"channel": "#data", "attempts": 2, "urgent": True},
                    ),
                ],
                "post_hooks": [
                    PythonHookEntry(
                        name="notify_success",
                        kwargs={"message": "@@CTX:destination.qualified"},
                    ),
                    SqlHookEntry(
                        statement="grant select on @@CTX:destination.qualified to role analytics"
                    ),
                ],
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts python-only lifecycle hook list",
            contents="""
        MODEL (
          post_hooks [python("notify", channel: "alerts")]
        );

        SELECT 1
        """,
            expected_header_values={
                "post_hooks": [
                    PythonHookEntry(name="notify", kwargs={"channel": "alerts"}),
                ],
            },
            expected_query="SELECT 1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_model_header_variants_when_parsing_then_it_returns_expected_header_and_query(
    test_case: ParseModelSqlHeaderTestCase,
) -> None:
    header_values: dict[str, object]
    query: str
    header_values, query = parse_model_sql(
        contents=test_case.contents, file_path=Path("orders.sql")
    )

    assert header_values == test_case.expected_header_values
    assert query == test_case.expected_query


@pytest.mark.parametrize(
    "test_case",
    [
        ParseModelSqlErrorTestCase(
            description="raises when the model header is missing",
            contents="SELECT 1\n",
            expected_error_fragment="must start with a MODEL",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when the model body is empty",
            contents="MODEL ();\n",
            expected_error_fragment="must contain SQL after MODEL(...)",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when the model header does not start with a key",
            contents="""
        MODEL ([core, finance]);

        SELECT 1
        """,
            expected_error_fragment="expected key",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when the model header contains old colon syntax",
            contents="""
        MODEL (
          tags: [core, finance]
        );

        SELECT 1
        """,
            expected_error_fragment="use SQLBuild syntax 'tags value'",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when the model header contains an unterminated list",
            contents="""
        MODEL (
          tags [core, finance
        );

        SELECT 1
        """,
            expected_error_fragment="expected value",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when a double quoted string is unterminated",
            contents="""
        MODEL (
          schema "analytics
        );

        SELECT 1
        """,
            expected_error_fragment="unterminated double-quoted string",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when a quote appears inside a bare value",
            contents="""
        MODEL (
          schema analytics"mart
        );

        SELECT 1
        """,
            expected_error_fragment="quote the whole value",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when a value with spaces is not quoted",
            contents="""
        MODEL (
          schema analytics mart
        );

        SELECT 1
        """,
            expected_error_fragment="quote values with spaces",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when sql hook receives extra arguments",
            contents="""
        MODEL (
          pre_hooks [inline_sql("select 1", label: "extra")]
        );

        SELECT 1
        """,
            expected_error_fragment="does not accept additional arguments",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when python hook name is not quoted",
            contents="""
        MODEL (
          post_hooks [python(notify)]
        );

        SELECT 1
        """,
            expected_error_fragment="requires a quoted hook name",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when python hook kwarg does not use colon syntax",
            contents="""
        MODEL (
          post_hooks [python("notify", channel "#data")]
        );

        SELECT 1
        """,
            expected_error_fragment="expected ':'",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when hook list uses unknown constructor",
            contents="""
        MODEL (
          post_hooks [notify("done")]
        );

        SELECT 1
        """,
            expected_error_fragment="post_hooks entries must use typed inline_sql",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when hook list uses uppercase constructor",
            contents="""
        MODEL (
          pre_hooks [SQL("SELECT 1")]
        );

        SELECT 1
        """,
            expected_error_fragment="pre_hooks entries must use typed inline_sql",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_model_contents_when_parsing_then_it_raises_clear_errors(
    test_case: ParseModelSqlErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        parse_model_sql(contents=test_case.contents, file_path=Path("orders.sql"))


@pytest.mark.parametrize(
    "test_case",
    (
        ModelHeaderColumnLocationTestCase(
            description="locates top level model column declarations",
            contents=(
                "MODEL (\n"
                "  materialized view,\n"
                "  columns (\n"
                "    order_id (),\n"
                "    customer_id (type INTEGER),\n"
                "  ),\n"
                ");\n\n"
                "SELECT order_id FROM raw_orders\n"
            ),
            expected_locations={
                "order_id": (Path("models/orders.sql"), 4, 5, 4, 13),
                "customer_id": (Path("models/orders.sql"), 5, 5, 5, 16),
            },
        ),
        ModelHeaderColumnLocationTestCase(
            description="ignores nested metadata keys inside column declarations",
            contents=(
                "MODEL (\n"
                "  columns (\n"
                "    status (\n"
                '      description "Order status",\n'
                "      audits [accepted_values (values [placed, completed])],\n"
                "    ),\n"
                "  ),\n"
                ");\n\n"
                "SELECT status FROM raw_orders\n"
            ),
            expected_locations={
                "status": (Path("models/orders.sql"), 3, 5, 3, 11),
            },
        ),
        ModelHeaderColumnLocationTestCase(
            description="ignores nested columns maps before root model columns",
            contents=(
                "MODEL (config (columns (nested (type INTEGER))), "
                "columns (top (type INTEGER))); SELECT 1"
            ),
            expected_locations={
                "top": (Path("models/orders.sql"), 1, 59, 1, 62),
            },
        ),
        ModelHeaderColumnLocationTestCase(
            description="ignores nested columns maps without root model columns",
            contents="MODEL (config (columns (nested (type INTEGER)))); SELECT 1",
            expected_locations={},
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_model_header_columns_when_locating_then_returns_expected_locations(
    test_case: ModelHeaderColumnLocationTestCase,
) -> None:
    locations: dict[str, SourceLocation] = model_header_column_locations(
        contents=test_case.contents,
        relative_path=Path("models/orders.sql"),
    )

    assert {
        name: (
            location.path,
            location.line,
            location.column,
            location.end_line,
            location.end_column,
        )
        for name, location in locations.items()
    } == test_case.expected_locations


@pytest.mark.parametrize(
    "test_case",
    (
        ModelOutputColumnLocationTestCase(
            description="locates direct and aliased top level select outputs",
            contents=(
                "MODEL ();\n\n"
                "SELECT\n"
                "  o.order_id,\n"
                "  CAST(o.amount AS VARCHAR) AS amount_text\n"
                "FROM raw_orders o\n"
            ),
            expected_locations={
                "order_id": (Path("models/orders.sql"), 4, 3, 4, 13),
                "amount_text": (Path("models/orders.sql"), 5, 3, 5, 43),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="keeps commas inside expressions within one output span",
            contents=(
                "MODEL ();\n\n"
                "SELECT\n"
                "  COALESCE(first_name, last_name, 'unknown') AS display_name,\n"
                "  customer_id\n"
                "FROM raw_customers\n"
            ),
            expected_locations={
                "display_name": (Path("models/orders.sql"), 4, 3, 4, 61),
                "customer_id": (Path("models/orders.sql"), 5, 3, 5, 14),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="locates outer select outputs after ctes",
            contents=(
                "MODEL ();\n\n"
                "WITH prepared AS (\n"
                "  SELECT order_id, amount_cents FROM raw_orders\n"
                ")\n"
                "SELECT\n"
                "  order_id,\n"
                "  amount_cents AS total_cents\n"
                "FROM prepared\n"
            ),
            expected_locations={
                "order_id": (Path("models/orders.sql"), 7, 3, 7, 11),
                "total_cents": (Path("models/orders.sql"), 8, 3, 8, 30),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="locates quoted output aliases",
            contents=('MODEL ();\n\nSELECT\n  amount_cents AS "amount cents"\nFROM raw_orders\n'),
            expected_locations={
                "amount cents": (Path("models/orders.sql"), 4, 3, 4, 33),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="locates expressions containing nested select text inside parentheses",
            contents=(
                "MODEL ();\n\n"
                "SELECT\n"
                "  (SELECT MAX(amount_cents) FROM raw_payments) AS max_payment_cents\n"
                "FROM raw_orders\n"
            ),
            expected_locations={
                "max_payment_cents": (Path("models/orders.sql"), 4, 3, 4, 68),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="skips wildcard outputs",
            contents="MODEL ();\n\nSELECT * FROM raw_orders\n",
            expected_locations={},
        ),
        ModelOutputColumnLocationTestCase(
            description="locates alias without AS using sql_analysis projection identity",
            contents=(
                "MODEL ();\n\nSELECT\n  CAST(amount AS VARCHAR) amount_text\nFROM raw_orders\n"
            ),
            expected_locations={
                "amount_text": (Path("models/orders.sql"), 4, 3, 4, 38),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="locates select without from using sql_analysis projection identity",
            contents="MODEL ();\n\nSELECT 1 AS one\n",
            expected_locations={
                "one": (Path("models/orders.sql"), 3, 8, 3, 16),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="skips sql_analysis-only aliases when sql_analysis is disabled",
            contents=(
                "MODEL ();\n\nSELECT\n  CAST(amount AS VARCHAR) amount_text\nFROM raw_orders\n"
            ),
            expected_locations={},
            extract_implicit_alias_columns=False,
        ),
        ModelOutputColumnLocationTestCase(
            description="skips union query after first branch because it is ambiguous",
            contents=("MODEL ();\n\nSELECT id FROM raw_a\nUNION ALL\nSELECT id FROM raw_b\n"),
            expected_locations={},
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_model_select_outputs_when_locating_then_returns_expected_locations(
    test_case: ModelOutputColumnLocationTestCase,
) -> None:
    locations: dict[str, SourceLocation] = model_output_column_locations(
        contents=test_case.contents,
        relative_path=Path("models/orders.sql"),
        extract_implicit_alias_columns=test_case.extract_implicit_alias_columns,
    )

    assert {
        name: (
            location.path,
            location.line,
            location.column,
            location.end_line,
            location.end_column,
        )
        for name, location in locations.items()
    } == test_case.expected_locations

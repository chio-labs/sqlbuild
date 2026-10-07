"""Render captures are classified into the input kinds the seed corpus must exercise."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.coverage.render import (
    project_render_kinds,
    render_capture_problems,
    rendered_input_kinds,
    required_render_kinds,
)
from scripts.compiler_differential.constants import RENDER_NON_COLLECTION_FIELDS
from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.frontier._helpers.stage_capture import render_stage_capture
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig
from tests.unit.scripts.compiler_differential._helpers.coverage._test_types import (
    CaptureProblemsTestCase,
    RenderCaptureKindsTestCase,
    RenderEncodedInputsTestCase,
    RequiredKindsTestCase,
)
from tests.unit.scripts.compiler_differential._helpers.coverage.helpers import (
    audit_input,
    empty_render_capture,
    granted_usage,
    private_usage,
    reference,
    usage,
)

_HOOK: str = "sqlbuild.compiler.discovery.models"
_TARGET: str = "sqlbuild.compiler.compile.types:AttachedAuditTargetKind"
_TEST_MODE: str = "sqlbuild.compiler.compile.types:SqlTestMode"
_SCOPE: str = "sqlbuild.compiler.scopes.types:ScopeKind"
_VALUE_KIND: str = "sqlbuild.sql_values.types:SqlValueKind"
_SHARED_MACRO_FILE: str = (
    "import os\n\n\n"
    "def round_it(ctx, value):\n    return f\"ROUND({value}) + {ctx.vars['x']}\"\n\n\n"
    "def region_tag():\n    return os.environ.get('REGION', 'east')\n"
)
_TYPED_MACRO_FILE: str = (
    "from sqlbuild.refs import SqlResourceRef\n\n\n"
    "def union_ids(relations: list[SqlResourceRef]) -> str:\n"
    '    return " UNION ALL ".join(f"SELECT id FROM {item}" for item in relations)\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderCaptureKindsTestCase(
            description="macro_calls_rendered_in_a_model",
            capture=empty_render_capture(
                model_inputs=[
                    {
                        "macro_source_sql": (
                            'SELECT @round_it(@double("amount")) AS amount\n'
                            'FROM @union_ids([__ref("orders"), __ref("returns")])\n'
                            "JOIN @legacy_customers() c ON TRUE"
                        ),
                        "query_sql": (
                            "SELECT ROUND(amount * 2) AS amount\n"
                            'FROM (SELECT id FROM __ref("orders") UNION ALL '
                            'SELECT id FROM __ref("returns"))\n'
                            'JOIN __ref("customers") c ON TRUE'
                        ),
                        "references": [
                            reference(kind="REF", name="orders"),
                            reference(kind="REF", name="returns"),
                            reference(kind="REF", name="customers"),
                        ],
                        "macro_usages": [
                            usage(kind="MACRO", name="round_it"),
                            usage(kind="MACRO", name="union_ids"),
                        ],
                    }
                ],
                loaded_macros={
                    "round_it": {
                        "name": "round_it",
                        "raw_source": _SHARED_MACRO_FILE,
                        "dependencies": [{"kind": "macro", "name": "base"}],
                    },
                    "region_tag": {
                        "name": "region_tag",
                        "raw_source": _SHARED_MACRO_FILE,
                        "dependencies": [{"kind": "macro", "name": "base"}],
                    },
                    "union_ids": {
                        "name": "union_ids",
                        "raw_source": _TYPED_MACRO_FILE,
                        "dependencies": [],
                    },
                },
            ),
            expected_present=frozenset(
                {
                    "model_inputs",
                    "loaded_macros",
                    "macro_in_model",
                    "nested_macro_call",
                    "typed_reference_argument",
                    "macro_generated_reference",
                    "cross_file_macro_import",
                    "macro_reads_vars",
                    "reference_ref",
                }
            ),
            expected_absent=frozenset({"macro_reads_environment", "macro_in_test"}),
        ),
        RenderCaptureKindsTestCase(
            description="unused_or_untyped_macros_prove_nothing",
            capture=empty_render_capture(
                model_inputs=[
                    {
                        "macro_source_sql": 'SELECT * FROM @round_it(__ref("orders"))',
                        "query_sql": 'SELECT * FROM ROUND(__ref("orders"))',
                        "references": [reference(kind="REF", name="orders")],
                    }
                ],
                loaded_macros={
                    "round_it": {
                        "name": "round_it",
                        "raw_source": _SHARED_MACRO_FILE,
                        "dependencies": [{"kind": "macro", "name": "base"}],
                    },
                },
            ),
            expected_present=frozenset({"model_inputs", "reference_ref"}),
            expected_absent=frozenset(
                {
                    "typed_reference_argument",
                    "cross_file_macro_import",
                    "macro_reads_vars",
                    "macro_reads_environment",
                }
            ),
        ),
        RenderCaptureKindsTestCase(
            description="unexpanded_macro_text_proves_nothing",
            capture=empty_render_capture(
                model_inputs=[
                    {
                        "macro_source_sql": 'SELECT @round_it(@double("amount")) FROM t',
                        "query_sql": 'SELECT @round_it(@double("amount")) FROM t',
                    }
                ]
            ),
            expected_present=frozenset({"model_inputs"}),
            expected_absent=frozenset(
                {"nested_macro_call", "typed_reference_argument", "macro_generated_reference"}
            ),
        ),
        RenderCaptureKindsTestCase(
            description="interpolated_templates",
            capture=empty_render_capture(
                model_inputs=[
                    {
                        "model_file": {
                            "query_sql": "SELECT '@@site' AS site, '@@ENV:CHANNEL' AS channel"
                        },
                        "query_sql": (
                            "SELECT 'north' AS site, 'web' AS channel\n"
                            "WHERE d >= __cursor_start() AND d >= @@@window_start"
                        ),
                        "config": {
                            "values": {
                                "materialized": "incremental",
                                "cursor": "d",
                                "placeholders": {"window_start": "'2026-01-01'"},
                            }
                        },
                        "schema_entry": {
                            "name": "orders",
                            "audits": [],
                            "columns": [
                                {
                                    "name": "amount",
                                    "audits": [
                                        {"definition_name": "floor", "arguments": {"floor": -17}}
                                    ],
                                }
                            ],
                        },
                    }
                ],
                source_inputs=[
                    {"source_entry": {"name": "orders", "expression": "(SELECT 0.5 AS rate)"}}
                ],
                audit_inputs=[
                    audit_input(
                        definition="floor",
                        template="SELECT * FROM t WHERE @column < @floor",
                        rendered="SELECT * FROM t WHERE amount < -17",
                    )
                ],
                discovered_inputs={
                    "source_files": [
                        {
                            "source_entries": [
                                {"name": "orders", "expression": "(SELECT @@rate AS rate)"}
                            ]
                        }
                    ]
                },
            ),
            expected_present=frozenset(
                {
                    "project_variable",
                    "environment_variable",
                    "cursor_intrinsic",
                    "runtime_placeholder",
                    "source_expression_rendered",
                    "audit_arguments",
                    "model_column_audit",
                }
            ),
            expected_absent=frozenset({"model_audit", "singular_audit"}),
        ),
        RenderCaptureKindsTestCase(
            description="surviving_tokens_without_config_and_built_in_audit_tokens_prove_nothing",
            capture=empty_render_capture(
                model_inputs=[
                    {
                        "query_sql": "SELECT __cursor_start() AS s, @@@window_start AS w",
                        "config": {"values": {"materialized": "view"}},
                        "schema_entry": {
                            "name": "orders",
                            "audits": [],
                            "columns": [
                                {
                                    "name": "amount",
                                    "audits": [{"definition_name": "not_null", "arguments": {}}],
                                }
                            ],
                        },
                    }
                ],
                audit_inputs=[
                    audit_input(
                        definition="not_null",
                        template="SELECT @column FROM @relation WHERE @column IS NULL",
                        rendered='SELECT amount FROM __ref("orders") WHERE amount IS NULL',
                    )
                ],
            ),
            expected_present=frozenset({"model_column_audit"}),
            expected_absent=frozenset(
                {"cursor_intrinsic", "runtime_placeholder", "audit_arguments"}
            ),
        ),
        RenderCaptureKindsTestCase(
            description="unsubstituted_variables_prove_nothing",
            capture=empty_render_capture(
                model_inputs=[
                    {
                        "model_file": {"query_sql": "SELECT '@@site', '@@ENV:CHANNEL'"},
                        "query_sql": "SELECT '@@site', '@@ENV:CHANNEL'",
                    }
                ]
            ),
            expected_present=frozenset({"model_inputs"}),
            expected_absent=frozenset({"project_variable", "environment_variable"}),
        ),
        RenderCaptureKindsTestCase(
            description="hooks_rendered_from_their_authored_entries",
            capture=empty_render_capture(
                model_inputs=[
                    {
                        "model_file": {
                            "header_values": {
                                "post_hooks": [
                                    {
                                        "__type__": f"{_HOOK}:SqlHookEntry",
                                        "statement": "SELECT @note('@@CTX:destination.qualified')",
                                    },
                                    {
                                        "__type__": f"{_HOOK}:NamedSqlHookEntry",
                                        "kwargs": {"label": "orders"},
                                    },
                                    {"__type__": f"{_HOOK}:PythonHookEntry", "name": "log"},
                                ]
                            }
                        },
                        "config": {
                            "values": {
                                "post_hooks": [
                                    {
                                        "__type__": f"{_HOOK}:SqlHookEntry",
                                        "statement": "SELECT 'refreshed main.orders'",
                                        "definition_sql": None,
                                    },
                                    {
                                        "__type__": f"{_HOOK}:SqlHookEntry",
                                        "statement": "SELECT 'orders' AS label",
                                        "definition_sql": "SELECT @'label' AS label",
                                        "kwargs": {"label": "orders"},
                                    },
                                    {"__type__": f"{_HOOK}:PythonHookEntry", "name": "log"},
                                ]
                            },
                            "matched_path_default": "marts",
                        },
                    }
                ]
            ),
            expected_present=frozenset(
                {
                    "inline_sql_hook",
                    "named_sql_hook",
                    "python_hook",
                    "hook_context_variable",
                    "macro_in_hook",
                    "named_hook_arguments",
                    "path_default",
                }
            ),
            expected_absent=frozenset(),
        ),
        RenderCaptureKindsTestCase(
            description="declarations_used_by_resources",
            capture=empty_render_capture(
                model_inputs=[
                    {
                        "declaration_usages": [
                            usage(kind="ENUM", name="status", enum_member="OPEN"),
                            usage(kind="CONSTANT", name="weights"),
                            private_usage(kind="CONSTANT", name="_floor", owner="orders"),
                        ],
                        "enum_columns": {"status": {"name": "status"}},
                    }
                ],
                test_inputs=[
                    {
                        "mode": {"__enum__": f"{_TEST_MODE}.MACRO"},
                        "declaration_usages": [
                            granted_usage(kind="MACRO", name="double", through="orders")
                        ],
                        "case_name": "small",
                    }
                ],
                public_constants={
                    "weights": {
                        "name": "weights",
                        "value": {"logical_type": {"kind": {"__enum__": f"{_VALUE_KIND}.LIST"}}},
                    }
                },
                scope_index={
                    "declarations": [
                        {
                            "identity": usage(kind="ENUM", name="status")["declaration"],
                            "scope": {"__enum__": f"{_SCOPE}.INHERITED"},
                        }
                    ]
                },
            ),
            expected_present=frozenset(
                {
                    "enum_member",
                    "list_constant",
                    "scope_private_use",
                    "scope_inherited_use",
                    "enum_column_contract",
                    "macro_in_test",
                    "tested_macro",
                    "macro_test",
                    "expected_model_grant",
                    "parameterized_test_case",
                }
            ),
            expected_absent=frozenset({"scope_local_use", "scope_global_use"}),
        ),
        RenderCaptureKindsTestCase(
            description="encoded_empty_collections",
            capture=empty_render_capture(
                loaded_macros={},
                public_enums={"__mapping__": []},
                model_inputs=[{"enum_columns": {"__mapping__": []}}],
            ),
            expected_present=frozenset({"model_inputs"}),
            expected_absent=frozenset({"loaded_macros", "public_enums", "enum_column_contract"}),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_render_capture_when_classifying_then_only_rendered_inputs_are_credited(
    test_case: RenderCaptureKindsTestCase,
) -> None:
    kinds: frozenset[str] = rendered_input_kinds(json.dumps(test_case.capture))

    assert test_case.expected_present <= kinds, test_case.expected_present - kinds
    assert not test_case.expected_absent & kinds, test_case.expected_absent & kinds


@pytest.mark.parametrize(
    "test_case",
    [
        RenderEncodedInputsTestCase(
            description="empty_project",
            inputs=CompileProjectInputs(
                project_config=ProjectConfig(name="orders", adapter="duckdb"),
                local_config=LocalConfig(),
                discovered_inputs=DiscoveredProjectInputs(
                    project_config=ProjectConfig(name="orders", adapter="duckdb"),
                    local_config=LocalConfig(),
                ),
                sql_lexical_syntax=SqlLexicalSyntax(),
            ),
            expected_kinds=frozenset(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_encoded_compile_inputs_when_classifying_then_encoded_empty_values_prove_nothing(
    test_case: RenderEncodedInputsTestCase, tmp_path: Path
) -> None:
    capture: str = render_stage_capture(test_case.inputs)
    capture_path: Path = tmp_path / "002-compile_project_inputs.json"
    _ = capture_path.write_text(capture, encoding="utf-8")

    assert rendered_input_kinds(capture) == test_case.expected_kinds
    assert project_render_kinds({"0-compile": {capture_path.name: capture_path}}) == (
        test_case.expected_kinds
    )


@pytest.mark.parametrize(
    "test_case",
    [
        RequiredKindsTestCase(
            description="every_rendered_collection",
            expected_required=frozenset(
                field.name for field in dataclasses.fields(CompileProjectInputs)
            )
            - RENDER_NON_COLLECTION_FIELDS,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compile_project_inputs_when_listing_required_kinds_then_collections_are_required(
    test_case: RequiredKindsTestCase,
) -> None:
    assert test_case.expected_required <= set(required_render_kinds())


@pytest.mark.parametrize(
    "test_case",
    [
        CaptureProblemsTestCase(
            description="sound_capture",
            capture=empty_render_capture(
                loaded_macros={"double": {"function": {"__callable__": "macros.math:double"}}}
            ),
            expected_problem_count=0,
        ),
        CaptureProblemsTestCase(
            description="opaque_value_and_unnamed_callable",
            capture=empty_render_capture(
                loaded_macros={"double": {"function": {"__opaque__": "macros.math:Doubler"}}}
            ),
            expected_problem_count=2,
        ),
        CaptureProblemsTestCase(
            description="missing_field",
            capture={"__type__": "CompileProjectInputs", "model_inputs": []},
            expected_problem_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_render_capture_when_checking_then_incomplete_or_opaque_parts_are_reported(
    test_case: CaptureProblemsTestCase,
) -> None:
    problems: tuple[str, ...] = render_capture_problems(json.dumps(test_case.capture))

    assert len(problems) == test_case.expected_problem_count, problems


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])

"""Every attachment kind compiles like Python natively, with macros through the bridge."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.frontier.types import CompilerEngine
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    AttachmentProjectTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    attachment_engine_outcome,
)

_BRIDGED_CONSUMERS: frozenset[str] = frozenset(
    {
        "bridged:<built-in>/audits/generic/accepted_values.sql",
        "bridged:<built-in>/audits/generic/not_null.sql",
        "bridged:<project>/audits/generic/amount_floor.sql",
        "bridged:<project>/functions/sql/order_label.sql",
        "bridged:<project>/models/orders.sql",
        "bridged:<project>/sources/events.yml",
        "bridged:<project>/tests/scenarios/orders_scenario.sql",
        "bridged:<project>/tests/unit/test_orders.sql",
    }
)
_NATIVE_ONLY_ENTRIES: frozenset[str] = (
    frozenset(
        {
            "pair_seed_files",
            "render_attached_generic_audit",
            "expand_config_templates",
            "scan_test_parameter_references",
            "omitted_ceremonial_select",
            "extract_sql_scenario_json",
            "SqlTestTargetCatalog",
        }
    )
    | _BRIDGED_CONSUMERS
)
_ATTACHMENT_ENTRIES: frozenset[str] = frozenset(
    {
        "pair_seed_files",
        "render_attached_generic_audit",
        "expand_config_templates",
        "substitute_static_project_vars",
        "scan_sql_declaration_references",
        "scan_test_parameter_references",
        "omitted_ceremonial_select",
        "extract_sql_scenario_json",
        "SqlTestTargetCatalog",
    }
)
_SCENARIO: str = "tests/scenarios/orders_scenario.sql"
_SCENARIO_HEADER: str = 'SCENARIO (\n  description "Orders join their channel"\n);\n\n'
_UNIT_TEST: str = "tests/unit/test_orders.sql"
_HELPER_TEST_MOCKS: str = (
    "TEST();\n\nWITH\n__seed__channel_codes AS (SELECT 1 AS id, 'web' AS label),\n"
    "__source__order_events AS (SELECT 1 AS id, 'north' AS region),\n"
)
_HELPER_TEST_EXPECTED: str = "__expected__orders AS (SELECT 1 AS id, 1.5 AS amount, 'web' AS label)"


@pytest.mark.parametrize(
    "test_case",
    [
        AttachmentProjectTestCase(
            description="macros in every attachment kind, seeds, templates and generic audits",
            overrides={},
            expected_native_entries=_ATTACHMENT_ENTRIES | _BRIDGED_CONSUMERS,
            expected_outcome_fragment="((CompileSeedInput(",
        ),
        AttachmentProjectTestCase(
            description="a scenario check CTE reading a project source",
            overrides={
                _SCENARIO: _SCENARIO_HEADER
                + "WITH\n__seed__channel_codes AS (SELECT 1 AS id, 'web' AS label),\n"
                + '__expected__orders AS (SELECT id, 1.5 AS amount, label FROM __source("order_events"))\n'
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="error: SQL scenario file tests/scenarios/orders_scenario.sql CTE",
        ),
        AttachmentProjectTestCase(
            description="a scenario helper reading an unknown source",
            overrides={
                _SCENARIO: _SCENARIO_HEADER
                + 'WITH\nhelper AS (SELECT * FROM __source("missing_events")),\n'
                + "__seed__channel_codes AS (SELECT 1 AS id, 'web' AS label),\n"
                + "__expected__orders AS (SELECT 1 AS id, 1.5 AS amount, 'web' AS label)\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="error: SQL scenario file tests/scenarios/orders_scenario.sql "
            "references unknown source 'missing_events'",
        ),
        AttachmentProjectTestCase(
            description="a check CTE reading a source before a later malformed reference call",
            overrides={
                _SCENARIO: _SCENARIO_HEADER
                + "WITH\n__seed__channel_codes AS (SELECT 1 AS id, 'web' AS label),\n"
                + '__expected__orders AS (SELECT id, 1.5 AS amount, label FROM __source("order_events")),\n'
                + "__assert__no_rows AS (SELECT 1 FROM __source(order_events))\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="error: SQL scenario file tests/scenarios/orders_scenario.sql CTE "
            "'__expected__orders' must not reference project source",
        ),
        AttachmentProjectTestCase(
            description="a malformed call in a check CTE leaves the unknown helper source first",
            overrides={
                _SCENARIO: _SCENARIO_HEADER
                + 'WITH\nhelper AS (SELECT * FROM __source("missing_events")),\n'
                + "__seed__channel_codes AS (SELECT 1 AS id, 'web' AS label),\n"
                + "__expected__orders AS (SELECT 1 AS id FROM __source(order_events))\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="error: SQL scenario file tests/scenarios/orders_scenario.sql "
            "references unknown source 'missing_events'",
        ),
        AttachmentProjectTestCase(
            description="an unknown helper source before a later malformed fixture call",
            overrides={
                _SCENARIO: _SCENARIO_HEADER
                + 'WITH\nhelper AS (SELECT * FROM __source("missing_events")),\n'
                + "__seed__channel_codes AS (SELECT 1 AS id FROM __source(order_events)),\n"
                + "__expected__orders AS (SELECT 1 AS id, 1.5 AS amount, 'web' AS label)\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="error: SQL scenario file tests/scenarios/orders_scenario.sql "
            "references unknown source 'missing_events'",
        ),
        AttachmentProjectTestCase(
            description="a scenario fixture without a target name",
            overrides={
                _SCENARIO: _SCENARIO_HEADER
                + "WITH\n__seed__ AS (SELECT 1 AS id, 'web' AS label),\n"
                + "__expected__orders AS (SELECT 1 AS id, 1.5 AS amount, 'web' AS label)\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="error: SQL scenario 'tests/scenarios/orders_scenario.sql' "
            "must use __seed__<seed> to identify a target",
        ),
        AttachmentProjectTestCase(
            description="a scenario macro mock",
            overrides={
                _SCENARIO: _SCENARIO_HEADER
                + "WITH\n__seed__channel_codes AS (SELECT 1 AS id, 'web' AS label),\n"
                + "__macro__tidy AS (SELECT 'x'),\n"
                + "__expected__orders AS (SELECT 1 AS id, 1.5 AS amount, 'web' AS label)\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="does not support macro mock CTE '__macro__tidy'",
        ),
        AttachmentProjectTestCase(
            description="a scenario whose expected result depends on an assertion",
            overrides={
                _SCENARIO: _SCENARIO_HEADER
                + "WITH\n__seed__channel_codes AS (SELECT 1 AS id, 'web' AS label),\n"
                + "__assert__no_rows AS (SELECT 1 FROM __seed__channel_codes WHERE id IS NULL),\n"
                + "__expected__orders AS (SELECT 1 AS id, 1.5 AS amount, 'web' AS label "
                + "FROM __assert__no_rows)\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="check CTE '__expected__orders' must not depend on "
            "'__assert__no_rows'",
        ),
        AttachmentProjectTestCase(
            description="a helper CTE reading a model through __ref and read by an assertion",
            overrides={
                _UNIT_TEST: _HELPER_TEST_MOCKS
                + 'built_orders AS (SELECT id FROM __ref("orders")),\n'
                + _HELPER_TEST_EXPECTED
                + ",\n__assert__has_rows AS (SELECT 1 FROM built_orders WHERE id IS NULL)\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="reference_target_model_names=('orders',)",
        ),
        AttachmentProjectTestCase(
            description="a helper chain where one helper reads another",
            overrides={
                _UNIT_TEST: _HELPER_TEST_MOCKS
                + 'built_orders AS (SELECT id FROM __ref("orders")),\n'
                + "built_ids AS (SELECT id FROM built_orders),\n"
                + _HELPER_TEST_EXPECTED
                + ",\n__assert__has_ids AS (SELECT 1 FROM built_ids WHERE id IS NULL)\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="reference_target_model_names=('orders',)",
        ),
        AttachmentProjectTestCase(
            description="an unread helper referencing an unknown model",
            overrides={
                _UNIT_TEST: _HELPER_TEST_MOCKS
                + 'unused_returns AS (SELECT id FROM __ref("returns")),\n'
                + _HELPER_TEST_EXPECTED
                + "\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="read_helper_names=(), reference_target_model_names=()",
        ),
        AttachmentProjectTestCase(
            description="a read helper referencing an unknown model reports P013",
            overrides={
                _UNIT_TEST: _HELPER_TEST_MOCKS
                + 'built_returns AS (SELECT id FROM __ref("returns")),\n'
                + _HELPER_TEST_EXPECTED
                + ",\n__assert__no_returns AS (SELECT 1 FROM built_returns)\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="P013",
        ),
        AttachmentProjectTestCase(
            description="a model test expecting an unknown model",
            overrides={
                _UNIT_TEST: "TEST();\n\nWITH\n__seed__channel_codes AS (SELECT 1 AS id),\n"
                "__expected__returns AS (SELECT 1 AS id)\n"
            },
            expected_native_entries=frozenset({"SqlTestTargetCatalog"}),
            expected_outcome_fragment="error: SQL test file tests/unit/test_orders.sql expects "
            "unknown model 'returns'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_attachment_project_when_building_inputs_then_native_engines_match_python(
    test_case: AttachmentProjectTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcomes: dict[CompilerEngine, tuple[frozenset[str], str]] = {
        engine: attachment_engine_outcome(
            project_dir=tmp_path / engine.value,
            engine=engine,
            overrides=test_case.overrides,
            monkeypatch=monkeypatch,
        )
        for engine in CompilerEngine
    }
    python_called, python_outcome = outcomes[CompilerEngine.PYTHON]
    native_called, native_outcome = outcomes[CompilerEngine.NATIVE]
    preview_called, preview_outcome = outcomes[CompilerEngine.NATIVE_PREVIEW]

    assert (
        preview_outcome.replace(CompilerEngine.NATIVE_PREVIEW.value, "python"),
        native_outcome.replace(CompilerEngine.NATIVE.value, "python"),
        test_case.expected_outcome_fragment in python_outcome,
        native_called >= test_case.expected_native_entries,
        preview_called >= test_case.expected_native_entries,
        python_called & _NATIVE_ONLY_ENTRIES,
    ) == (python_outcome, python_outcome, True, True, True, frozenset()), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])

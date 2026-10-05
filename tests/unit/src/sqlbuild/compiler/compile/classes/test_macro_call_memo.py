"""Macro calls replay only reference-free output, and report the same input reads again."""

import pytest

from sqlbuild.compiler.compile._helpers.macro_memo.call_reads import replay_macro_call_reads
from sqlbuild.compiler.compile.classes.compile_input_reads import CompileInputReads
from sqlbuild.compiler.compile.classes.macro_call_memo import MacroCallMemo
from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS
from sqlbuild.compiler.compile.models import MemoizedMacroCall
from sqlbuild.compiler.scopes.models import ResourceIdentity
from sqlbuild.compiler.scopes.types import ResourceKind
from tests.unit.src.sqlbuild.compiler.compile.classes._test_types import (
    MacroCallDiagnosticTestCase,
    MacroCallMemoTestCase,
    MacroCallReadsTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile.classes.helpers import (
    REGION_ENV_VAR,
    macro_call_reading_environment,
    macro_call_reading_run_id,
    macro_call_reporting_diagnostic,
    macro_call_without_reads,
    remembered_macro_call,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MacroCallMemoTestCase("plain SQL", "CAST(amount * 100 AS BIGINT)", True),
        MacroCallMemoTestCase("model reference", 'SELECT * FROM __ref("orders")', False),
        MacroCallMemoTestCase("source reference", "SELECT * FROM __source('raw_orders')", False),
        MacroCallMemoTestCase("seed reference", 'SELECT * FROM __seed("regions")', False),
        MacroCallMemoTestCase("dbt reference", 'SELECT * FROM __dbt_ref("shop", "orders")', False),
        MacroCallMemoTestCase("function reference", '__udf("order_total")(amount)', False),
        MacroCallMemoTestCase(
            "table function reference", 'SELECT * FROM __table_fn("order_lines")(1)', False
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_macro_output_when_remembering_then_only_reference_free_calls_replay(
    test_case: MacroCallMemoTestCase,
) -> None:
    memo: MacroCallMemo = MacroCallMemo()
    consumer: ResourceIdentity = ResourceIdentity(ResourceKind.MODEL, "orders_summary")

    memo.remember(
        macro_name="orders_sql",
        arguments="'amount'",
        call=MemoizedMacroCall(
            sql=test_case.macro_sql,
            consumer=consumer,
            dependencies=(),
            usages=(),
            call_site_refs=(),
        ),
    )

    assert (memo.calls_for("orders_sql") is not None) is test_case.expected_remembered


@pytest.mark.parametrize(
    "test_case",
    [
        MacroCallReadsTestCase("no volatile reads", macro_call_without_reads, (), False),
        MacroCallReadsTestCase(
            "environment reads",
            macro_call_reading_environment,
            ("ORDERS_CURRENCY", REGION_ENV_VAR),
            False,
        ),
        MacroCallReadsTestCase("run identity read", macro_call_reading_run_id, (), True),
    ],
    ids=lambda case: case.description,
)
def test_given_remembered_macro_call_when_replaying_then_next_model_records_the_same_reads(
    test_case: MacroCallReadsTestCase,
) -> None:
    remembered: dict[str, MemoizedMacroCall] | None = remembered_macro_call(test_case.macro_call)
    assert remembered is not None

    replayed: CompileInputReads
    with COMPILE_INPUT_READS.recording() as replayed:
        replay_macro_call_reads(remembered["'amount'"])

    assert replayed.environment_names == test_case.expected_environment_names
    assert replayed.read_run_id is test_case.expected_read_run_id


@pytest.mark.parametrize(
    "test_case",
    [
        MacroCallDiagnosticTestCase("no diagnostic", macro_call_without_reads, True),
        MacroCallDiagnosticTestCase("reported diagnostic", macro_call_reporting_diagnostic, False),
    ],
    ids=lambda case: case.description,
)
def test_given_macro_call_diagnostics_when_remembering_then_only_diagnostic_free_calls_replay(
    test_case: MacroCallDiagnosticTestCase,
) -> None:
    remembered: dict[str, MemoizedMacroCall] | None = remembered_macro_call(test_case.macro_call)

    assert (remembered is not None) is test_case.expected_remembered


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))

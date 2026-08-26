"""Kata text and JSON rendering parity tests."""

import json
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.kata_engine.main.render_result import format_result
from sqlbuild.kata_engine.models import KataFault, KataResult
from tests.unit.src.sqlbuild.kata_engine.main.render_result._test_types import (
    RenderResultParityTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        RenderResultParityTestCase(
            description="text and JSON contain identical complete fault facts",
            result=KataResult(
                faults=(
                    KataFault(
                        code="SQBKS001",
                        path=Path("models/mart/market__mart__prices.sql"),
                        line=3,
                        column=7,
                        message="model SQL must keep transformation logic in top-level CTEs",
                        remediation=(
                            "Move transformation logic into named top-level CTEs before the terminal SELECT."
                        ),
                    ),
                ),
                evaluated_models=1,
                cache_hits=0,
                cache_misses=1,
            ),
            expected_fault_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_kata_faults_when_rendering_json_and_text_then_both_contain_identical_facts(
    test_case: RenderResultParityTestCase,
) -> None:
    result: KataResult = test_case.result

    text_output: str = format_result(result=result, json_output=False)
    json_payload: dict[str, Any] = json.loads(format_result(result=result, json_output=True))

    assert json_payload["fault_count"] == test_case.expected_fault_count
    for fault in json_payload["faults"]:
        assert (
            f"{fault['path']}:{fault['line']}:{fault['column']} "
            f"[{fault['code']}] {fault['message']}"
        ) in text_output
        assert f"  Remediation: {fault['remediation']}" in text_output

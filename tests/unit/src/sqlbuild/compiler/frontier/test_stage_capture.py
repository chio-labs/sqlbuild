"""Stage captures render frontier objects as deterministic, comparable JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.compiler.frontier._helpers.stage_capture import render_stage_capture
from sqlbuild.compiler.frontier.constants import (
    COMPILER_ENGINE_ENV_VAR,
    STAGE_CAPTURE_DIR_ENV_VAR,
    STAGE_CAPTURE_UNORDERED_ATTRIBUTES,
)
from sqlbuild.compiler.frontier.main._compile_frontier import compile_frontier
from sqlbuild.compiler.frontier.types import CompilerEngine, CompilerStage
from tests.unit.src.sqlbuild.compiler.frontier._test_types import (
    FrontierCaptureTestCase,
    StageCaptureOrderTestCase,
    StageCaptureTestCase,
    UnorderedAttributeTestCase,
)
from tests.unit.src.sqlbuild.compiler.frontier.helpers import (
    HELPERS_MODULE,
    linked_customer,
    memo_catalog,
    order_line,
    order_total,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StageCaptureTestCase(
            description="dataclass_enum_and_path",
            value=order_line,
            expected_capture={
                "__type__": f"{HELPERS_MODULE}:OrderLine",
                "order_id": 7,
                "status": {"__enum__": f"{HELPERS_MODULE}:OrderStatus.PLACED"},
                "path": {"__path__": "models/a.sql"},
            },
        ),
        StageCaptureTestCase(
            description="callable_becomes_qualified_name",
            value=lambda: {"total": order_total},
            expected_capture={"total": {"__callable__": f"{HELPERS_MODULE}:order_total"}},
        ),
        StageCaptureTestCase(
            description="sets_are_sorted",
            value=lambda: frozenset({"orders", "customers", "products"}),
            expected_capture={"__set__": ["customers", "orders", "products"]},
        ),
        StageCaptureTestCase(
            description="non_string_keys_are_pairs_in_insertion_order",
            value=lambda: {2: "second", 1: "first"},
            expected_capture={"__mapping__": [[2, "second"], [1, "first"]]},
        ),
        StageCaptureTestCase(
            description="cycles_are_cut",
            value=linked_customer,
            expected_capture={
                "__type__": f"{HELPERS_MODULE}:LinkedCustomer",
                "name": "customer",
                "peer": {"__cycle__": f"{HELPERS_MODULE}:LinkedCustomer"},
            },
        ),
        StageCaptureTestCase(
            description="non_finite_float_and_bytes",
            value=lambda: (float("inf"), b"orders"),
            expected_capture=[
                {"__float__": "inf"},
                {
                    "__bytes__": 6,
                    "sha256": "1c168adb00d208e42f93314529f1fa9c0427eb63233ceda95a5db52b7012a719",
                },
            ],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_frontier_value_when_rendering_capture_then_json_is_canonical(
    test_case: StageCaptureTestCase,
) -> None:
    assert json.loads(render_stage_capture(test_case.value())) == test_case.expected_capture


@pytest.mark.parametrize(
    "test_case",
    [
        StageCaptureOrderTestCase(
            description="mapping_insertion_order_is_visible",
            first=lambda: {"orders": 1, "customers": 2},
            second=lambda: {"customers": 2, "orders": 1},
            expected_identical=False,
        ),
        StageCaptureOrderTestCase(
            description="non_string_key_insertion_order_is_visible",
            first=lambda: {1: "orders", 2: "customers"},
            second=lambda: {2: "customers", 1: "orders"},
            expected_identical=False,
        ),
        StageCaptureOrderTestCase(
            description="tuple_order_is_visible",
            first=lambda: ("orders", "customers"),
            second=lambda: ("customers", "orders"),
            expected_identical=False,
        ),
        StageCaptureOrderTestCase(
            description="set_order_is_not_visible",
            first=lambda: frozenset(("orders", "customers", "products")),
            second=lambda: frozenset(("products", "customers", "orders")),
            expected_identical=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_reordered_value_when_rendering_capture_then_only_unordered_collections_match(
    test_case: StageCaptureOrderTestCase,
) -> None:
    assert (
        render_stage_capture(test_case.first()) == render_stage_capture(test_case.second())
    ) is test_case.expected_identical


@pytest.mark.parametrize(
    "test_case",
    [
        UnorderedAttributeTestCase(
            description="memo_fill_order_is_not_visible",
            first_memo_keys=("orders", "customers"),
            second_memo_keys=("customers", "orders"),
            first_ordered_keys=("orders", "customers"),
            second_ordered_keys=("orders", "customers"),
            expected_identical=True,
        ),
        UnorderedAttributeTestCase(
            description="other_attribute_order_stays_visible",
            first_memo_keys=("orders", "customers"),
            second_memo_keys=("orders", "customers"),
            first_ordered_keys=("orders", "customers"),
            second_ordered_keys=("customers", "orders"),
            expected_identical=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_declared_memo_attribute_when_rendering_capture_then_only_it_is_sorted(
    test_case: UnorderedAttributeTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        STAGE_CAPTURE_UNORDERED_ATTRIBUTES, f"{HELPERS_MODULE}:MemoCatalog", frozenset({"memo"})
    )
    first: str = render_stage_capture(
        memo_catalog(memo_keys=test_case.first_memo_keys, ordered_keys=test_case.first_ordered_keys)
    )
    second: str = render_stage_capture(
        memo_catalog(
            memo_keys=test_case.second_memo_keys, ordered_keys=test_case.second_ordered_keys
        )
    )

    assert (first == second) is test_case.expected_identical


@pytest.mark.parametrize(
    "test_case",
    [
        FrontierCaptureTestCase(
            description=engine.value,
            engine=engine,
            stages=(CompilerStage.DISCOVERED_PROJECT_INPUTS, CompilerStage.COMPILED_PROJECT),
            expected_results=(
                "discovered_project_inputs-result",
                "compiled_project-result",
            ),
            expected_files=("discovered_project_inputs.json", "compiled_project.json"),
        )
        for engine in CompilerEngine
    ],
    ids=lambda case: case.description,
)
def test_given_capture_directory_when_compiling_frontier_then_each_stage_is_captured_in_order(
    test_case: FrontierCaptureTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.engine.value)
    monkeypatch.setenv(STAGE_CAPTURE_DIR_ENV_VAR, str(tmp_path))

    results: tuple[object, ...] = tuple(
        compile_frontier(until=stage, python_stage=lambda stage=stage: f"{stage.value}-result")
        for stage in test_case.stages
    )

    captures: list[Path] = sorted(tmp_path.iterdir())
    assert results == test_case.expected_results
    assert tuple(path.name.split("-", 1)[1] for path in captures) == test_case.expected_files
    assert tuple(json.loads(path.read_text(encoding="utf-8")) for path in captures) == (
        test_case.expected_results
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])

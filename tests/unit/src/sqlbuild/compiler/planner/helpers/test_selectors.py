from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner.helpers.selectors import (
    parse_selector,
    resolve_selectors,
)
from sqlbuild.compiler.planner.models import ParsedSelector
from sqlbuild.compiler.planner.types import SelectorKind
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    ParseSelectorErrorTestCase,
    ParseSelectorTestCase,
    ResolveSelectorErrorTestCase,
    ResolveSelectorTestCase,
)

PARSE_SELECTOR_TEST_CASES: list[ParseSelectorTestCase] = [
    ParseSelectorTestCase(
        description="parses bare model name",
        raw="orders",
        expected_result=ParsedSelector(kind=SelectorKind.NAME, value="orders"),
    ),
    ParseSelectorTestCase(
        description="parses upstream expansion",
        raw="+orders",
        expected_result=ParsedSelector(kind=SelectorKind.NAME, value="orders", upstream=True),
    ),
    ParseSelectorTestCase(
        description="parses downstream expansion",
        raw="orders+",
        expected_result=ParsedSelector(kind=SelectorKind.NAME, value="orders", downstream=True),
    ),
    ParseSelectorTestCase(
        description="parses bidirectional expansion",
        raw="+orders+",
        expected_result=ParsedSelector(
            kind=SelectorKind.NAME, value="orders", upstream=True, downstream=True
        ),
    ),
    ParseSelectorTestCase(
        description="parses seed typed selector",
        raw="seed:country_codes",
        expected_result=ParsedSelector(kind=SelectorKind.SEED, value="country_codes"),
    ),
    ParseSelectorTestCase(
        description="parses source typed selector",
        raw="source:raw_orders",
        expected_result=ParsedSelector(kind=SelectorKind.SOURCE, value="raw_orders"),
    ),
    ParseSelectorTestCase(
        description="parses tag typed selector",
        raw="tag:nightly",
        expected_result=ParsedSelector(kind=SelectorKind.TAG, value="nightly"),
    ),
    ParseSelectorTestCase(
        description="parses path typed selector",
        raw="path:models/staging",
        expected_result=ParsedSelector(kind=SelectorKind.PATH, value="models/staging"),
    ),
    ParseSelectorTestCase(
        description="parses typed selector with upstream expansion",
        raw="+seed:country_codes",
        expected_result=ParsedSelector(
            kind=SelectorKind.SEED, value="country_codes", upstream=True
        ),
    ),
    ParseSelectorTestCase(
        description="parses path selector as a~b tuple",
        raw="raw~orders",
        expected_result=("raw", "orders"),
    ),
]

PARSE_SELECTOR_ERROR_TEST_CASES: list[ParseSelectorErrorTestCase] = [
    ParseSelectorErrorTestCase(
        description="raises on empty selector",
        raw="",
        expected_error_type=ValueError,
    ),
    ParseSelectorErrorTestCase(
        description="raises when mixing tilde and plus",
        raw="+a~b",
        expected_error_type=ValueError,
    ),
    ParseSelectorErrorTestCase(
        description="raises on unknown typed prefix",
        raw="unknown:value",
        expected_error_type=ValueError,
    ),
    ParseSelectorErrorTestCase(
        description="raises on empty value after colon",
        raw="seed:",
        expected_error_type=ValueError,
    ),
    ParseSelectorErrorTestCase(
        description="raises on plus-only selector",
        raw="+",
        expected_error_type=ValueError,
    ),
    ParseSelectorErrorTestCase(
        description="raises on empty tilde side",
        raw="a~",
        expected_error_type=ValueError,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PARSE_SELECTOR_TEST_CASES,
    ids=[case.description for case in PARSE_SELECTOR_TEST_CASES],
)
def test_given_raw_selector_when_parsing_then_returns_expected_result(
    test_case: ParseSelectorTestCase,
) -> None:
    result: ParsedSelector | tuple[str, str] = parse_selector(test_case.raw)

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    PARSE_SELECTOR_ERROR_TEST_CASES,
    ids=[case.description for case in PARSE_SELECTOR_ERROR_TEST_CASES],
)
def test_given_invalid_selector_when_parsing_then_raises(
    test_case: ParseSelectorErrorTestCase,
) -> None:
    with pytest.raises(test_case.expected_error_type):
        parse_selector(test_case.raw)


RESOLVE_SELECTOR_TEST_CASES: list[ResolveSelectorTestCase] = [
    ResolveSelectorTestCase(
        description="selects single model by name",
        select=("orders",),
        exclude=(),
        expected_names=frozenset({"orders"}),
    ),
    ResolveSelectorTestCase(
        description="selects model with upstream expansion",
        select=("+joined",),
        exclude=(),
        expected_names=frozenset({"joined", "orders", "customers", "raw_orders", "raw_customers"}),
    ),
    ResolveSelectorTestCase(
        description="selects model with downstream expansion",
        select=("orders+",),
        exclude=(),
        expected_names=frozenset({"orders", "joined"}),
    ),
    ResolveSelectorTestCase(
        description="unions multiple select tokens",
        select=("orders", "customers"),
        exclude=(),
        expected_names=frozenset({"orders", "customers"}),
    ),
    ResolveSelectorTestCase(
        description="unions space-separated tokens in one select",
        select=("orders customers",),
        exclude=(),
        expected_names=frozenset({"orders", "customers"}),
    ),
    ResolveSelectorTestCase(
        description="subtracts excluded models from selected",
        select=("orders", "customers"),
        exclude=("customers",),
        expected_names=frozenset({"orders"}),
    ),
    ResolveSelectorTestCase(
        description="returns all keys when select is empty",
        select=(),
        exclude=(),
        expected_names=frozenset(
            {"orders", "customers", "joined", "raw_orders", "raw_customers", "codes"}
        ),
    ),
    ResolveSelectorTestCase(
        description="selects seed by typed selector",
        select=("seed:codes",),
        exclude=(),
        expected_names=frozenset({"codes"}),
    ),
    ResolveSelectorTestCase(
        description="selects source by typed selector",
        select=("source:raw_orders",),
        exclude=(),
        expected_names=frozenset({"raw_orders"}),
    ),
    ResolveSelectorTestCase(
        description="intersects comma-separated tokens",
        select=("orders+,+joined",),
        exclude=(),
        expected_names=frozenset({"orders", "joined"}),
    ),
    ResolveSelectorTestCase(
        description="selects bidirectional expansion",
        select=("+orders+",),
        exclude=(),
        expected_names=frozenset({"raw_orders", "orders", "joined"}),
    ),
    ResolveSelectorTestCase(
        description="resolves path selector through resolve flow",
        select=("raw_orders~joined",),
        exclude=(),
        expected_names=frozenset({"raw_orders", "orders", "joined"}),
    ),
    ResolveSelectorTestCase(
        description="subtracts expanded exclude from selected",
        select=("+joined",),
        exclude=("orders+",),
        expected_names=frozenset({"customers", "raw_customers", "raw_orders"}),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RESOLVE_SELECTOR_TEST_CASES,
    ids=[case.description for case in RESOLVE_SELECTOR_TEST_CASES],
)
def test_given_selectors_when_resolving_then_returns_expected_names(
    test_case: ResolveSelectorTestCase,
    diamond_graph: tuple[
        dict[str, CompiledObjectKey],
        dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
        dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    ],
) -> None:
    all_keys: dict[str, CompiledObjectKey] = diamond_graph[0]
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = diamond_graph[1]
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = diamond_graph[2]

    result: frozenset[CompiledObjectKey] = resolve_selectors(
        select=test_case.select,
        exclude=test_case.exclude,
        all_keys=all_keys,
        upstream=upstream,
        downstream=downstream,
    )
    result_names: frozenset[str] = frozenset(key.name for key in result)

    assert result_names == test_case.expected_names


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveSelectorErrorTestCase(
            description="raises when selector references unknown name",
            select=("nonexistent_model",),
            exclude=(),
            expected_error_type=ValueError,
        ),
    ],
    ids=["raises when selector references unknown name"],
)
def test_given_unknown_name_when_resolving_then_raises(
    test_case: ResolveSelectorErrorTestCase,
    diamond_graph: tuple[
        dict[str, CompiledObjectKey],
        dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
        dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    ],
) -> None:
    all_keys: dict[str, CompiledObjectKey] = diamond_graph[0]
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = diamond_graph[1]
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = diamond_graph[2]

    with pytest.raises(test_case.expected_error_type):
        resolve_selectors(
            select=test_case.select,
            exclude=test_case.exclude,
            all_keys=all_keys,
            upstream=upstream,
            downstream=downstream,
        )

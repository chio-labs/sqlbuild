from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.planner.helpers.graph.selectors import (
    parse_selector,
    resolve_selectors,
)
from sqlbuild.compiler.planner.models import ParsedSelector, PathSelector
from sqlbuild.compiler.planner.types import SelectorKind
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    BuildPathIndexTestCase,
    ParseSelectorErrorTestCase,
    ParseSelectorTestCase,
    ResolveSelectorErrorTestCase,
    ResolveSelectorTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import build_test_project

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
        expected_result=PathSelector(start_name="raw", end_name="orders"),
    ),
    ParseSelectorTestCase(
        description="parses path selector with upstream expansion",
        raw="+raw~orders",
        expected_result=PathSelector(start_name="raw", end_name="orders", upstream=True),
    ),
    ParseSelectorTestCase(
        description="parses path selector with downstream expansion",
        raw="raw~orders+",
        expected_result=PathSelector(start_name="raw", end_name="orders", downstream=True),
    ),
    ParseSelectorTestCase(
        description="parses path selector with endpoint expansion on both sides",
        raw="+raw~orders+",
        expected_result=PathSelector(
            start_name="raw", end_name="orders", upstream=True, downstream=True
        ),
    ),
    ParseSelectorTestCase(
        description="parses bare slash as path selector",
        raw="staging/",
        expected_result=ParsedSelector(kind=SelectorKind.PATH, value="staging"),
    ),
    ParseSelectorTestCase(
        description="parses leading bare slash as path selector",
        raw="/staging",
        expected_result=ParsedSelector(kind=SelectorKind.PATH, value="staging"),
    ),
    ParseSelectorTestCase(
        description="parses nested bare slash as path selector",
        raw="staging/orders/",
        expected_result=ParsedSelector(kind=SelectorKind.PATH, value="staging/orders"),
    ),
    ParseSelectorTestCase(
        description="parses bare slash without trailing slash as path selector",
        raw="staging/orders",
        expected_result=ParsedSelector(kind=SelectorKind.PATH, value="staging/orders"),
    ),
    ParseSelectorTestCase(
        description="parses bare slash with upstream expansion",
        raw="+staging/",
        expected_result=ParsedSelector(kind=SelectorKind.PATH, value="staging", upstream=True),
    ),
    ParseSelectorTestCase(
        description="parses bare slash with downstream expansion",
        raw="staging/+",
        expected_result=ParsedSelector(kind=SelectorKind.PATH, value="staging", downstream=True),
    ),
]

PARSE_SELECTOR_ERROR_TEST_CASES: list[ParseSelectorErrorTestCase] = [
    ParseSelectorErrorTestCase(
        description="raises on empty selector",
        raw="",
        expected_error_type=ValueError,
    ),
    ParseSelectorErrorTestCase(
        description="raises when plus appears inside path selector",
        raw="a~+b",
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
    result: ParsedSelector | PathSelector = parse_selector(test_case.raw)

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


RESOLVE_TAG_SELECTOR_TEST_CASES: list[ResolveSelectorTestCase] = [
    ResolveSelectorTestCase(
        description="selects models by tag",
        select=("tag:nightly",),
        exclude=(),
        expected_names=frozenset({"orders", "joined"}),
    ),
    ResolveSelectorTestCase(
        description="selects tag with downstream expansion",
        select=("tag:staging+",),
        exclude=(),
        expected_names=frozenset({"orders", "joined"}),
    ),
    ResolveSelectorTestCase(
        description="intersects tag with name selector",
        select=("tag:nightly,orders",),
        exclude=(),
        expected_names=frozenset({"orders"}),
    ),
    ResolveSelectorTestCase(
        description="excludes tag from selected",
        select=("orders", "customers", "joined"),
        exclude=("tag:nightly",),
        expected_names=frozenset({"customers"}),
    ),
]

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
        description="path selector with upstream expansion includes start upstreams",
        select=("+orders~joined",),
        exclude=(),
        expected_names=frozenset({"raw_orders", "orders", "joined"}),
    ),
    ResolveSelectorTestCase(
        description="path selector with downstream expansion includes end downstreams",
        select=("raw_orders~orders+",),
        exclude=(),
        expected_names=frozenset({"raw_orders", "orders", "joined"}),
    ),
    ResolveSelectorTestCase(
        description="path selector with endpoint expansion on both sides includes both expansions",
        select=("+raw_orders~orders+",),
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


@pytest.mark.parametrize(
    "test_case",
    RESOLVE_TAG_SELECTOR_TEST_CASES,
    ids=[case.description for case in RESOLVE_TAG_SELECTOR_TEST_CASES],
)
def test_given_tag_selectors_when_resolving_then_returns_expected_names(
    test_case: ResolveSelectorTestCase,
    diamond_graph: tuple[
        dict[str, CompiledObjectKey],
        dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
        dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    ],
    diamond_tag_index: dict[str, frozenset[CompiledObjectKey]],
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
        tag_index=diamond_tag_index,
    )
    result_names: frozenset[str] = frozenset(key.name for key in result)

    assert result_names == test_case.expected_names


RESOLVE_PATH_SELECTOR_TEST_CASES: list[ResolveSelectorTestCase] = [
    ResolveSelectorTestCase(
        description="selects models by path folder including nested subdirectories",
        select=("path:models/staging",),
        exclude=(),
        expected_names=frozenset({"stg_orders", "stg_customers", "stg_deep"}),
    ),
    ResolveSelectorTestCase(
        description="selects models root path",
        select=("path:models",),
        exclude=(),
        expected_names=frozenset(
            {"stg_orders", "stg_customers", "stg_deep", "int_enriched", "fact_orders"}
        ),
    ),
    ResolveSelectorTestCase(
        description="selects models by slash convention with explicit root",
        select=("models/staging/",),
        exclude=(),
        expected_names=frozenset({"stg_orders", "stg_customers", "stg_deep"}),
    ),
    ResolveSelectorTestCase(
        description="selects models by leading slash convention with explicit root",
        select=("/models/staging",),
        exclude=(),
        expected_names=frozenset({"stg_orders", "stg_customers", "stg_deep"}),
    ),
    ResolveSelectorTestCase(
        description="selects single folder with one model",
        select=("path:models/marts",),
        exclude=(),
        expected_names=frozenset({"fact_orders"}),
    ),
    ResolveSelectorTestCase(
        description="selects path with downstream expansion",
        select=("path:models/staging+",),
        exclude=(),
        expected_names=frozenset(
            {
                "stg_orders",
                "stg_customers",
                "stg_deep",
                "int_enriched",
                "fact_orders",
            }
        ),
    ),
    ResolveSelectorTestCase(
        description="selects path with upstream expansion",
        select=("+path:models/marts",),
        exclude=(),
        expected_names=frozenset(
            {
                "fact_orders",
                "int_enriched",
                "stg_orders",
                "stg_customers",
                "raw_orders",
                "raw_customers",
            }
        ),
    ),
    ResolveSelectorTestCase(
        description="intersects path with name selector",
        select=("path:models/staging,stg_orders",),
        exclude=(),
        expected_names=frozenset({"stg_orders"}),
    ),
    ResolveSelectorTestCase(
        description="excludes path from selected",
        select=("+fact_orders",),
        exclude=("path:models/staging",),
        expected_names=frozenset({"fact_orders", "int_enriched", "raw_orders", "raw_customers"}),
    ),
    ResolveSelectorTestCase(
        description="slash path with explicit root selects single-model folder",
        select=("models/intermediate/",),
        exclude=(),
        expected_names=frozenset({"int_enriched"}),
    ),
    ResolveSelectorTestCase(
        description="selects only nested subdirectory not parent",
        select=("path:models/staging/raw",),
        exclude=(),
        expected_names=frozenset({"stg_deep"}),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RESOLVE_PATH_SELECTOR_TEST_CASES,
    ids=[case.description for case in RESOLVE_PATH_SELECTOR_TEST_CASES],
)
def test_given_path_selectors_when_resolving_then_returns_expected_names(
    test_case: ResolveSelectorTestCase,
    path_graph: tuple[
        dict[str, CompiledObjectKey],
        dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
        dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
        dict[CompiledObjectKey, str],
    ],
) -> None:
    all_keys: dict[str, CompiledObjectKey] = path_graph[0]
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = path_graph[1]
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = path_graph[2]
    path_idx: dict[CompiledObjectKey, str] = path_graph[3]

    result: frozenset[CompiledObjectKey] = resolve_selectors(
        select=test_case.select,
        exclude=test_case.exclude,
        all_keys=all_keys,
        upstream=upstream,
        downstream=downstream,
        path_index=path_idx,
    )
    result_names: frozenset[str] = frozenset(key.name for key in result)

    assert result_names == test_case.expected_names


RESOLVE_PATH_SELECTOR_ERROR_TEST_CASES: list[ResolveSelectorErrorTestCase] = [
    ResolveSelectorErrorTestCase(
        description="raises when path omits explicit root",
        select=("path:nonexistent",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="path selectors require an explicit root",
    ),
    ResolveSelectorErrorTestCase(
        description="raises when slash path omits explicit root",
        select=("nonexistent/",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="path selectors require an explicit root",
    ),
    ResolveSelectorErrorTestCase(
        description="raises with folder name when explicit path matches no models",
        select=("path:models/nonexistent",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="no models found under path 'models/nonexistent'",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RESOLVE_PATH_SELECTOR_ERROR_TEST_CASES,
    ids=[case.description for case in RESOLVE_PATH_SELECTOR_ERROR_TEST_CASES],
)
def test_given_invalid_path_selector_when_resolving_then_raises_with_message(
    test_case: ResolveSelectorErrorTestCase,
    path_graph: tuple[
        dict[str, CompiledObjectKey],
        dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
        dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
        dict[CompiledObjectKey, str],
    ],
) -> None:
    all_keys: dict[str, CompiledObjectKey] = path_graph[0]
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = path_graph[1]
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = path_graph[2]
    path_idx: dict[CompiledObjectKey, str] = path_graph[3]

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        resolve_selectors(
            select=test_case.select,
            exclude=test_case.exclude,
            all_keys=all_keys,
            upstream=upstream,
            downstream=downstream,
            path_index=path_idx,
        )


BUILD_PATH_INDEX_TEST_CASES: list[BuildPathIndexTestCase] = [
    BuildPathIndexTestCase(
        description="strips models prefix from relative paths",
        model_paths={
            "stg_orders": "models/staging/stg_orders.sql",
            "fact_orders": "models/marts/fact_orders.sql",
        },
        expected_folders={
            "stg_orders": "staging",
            "fact_orders": "marts",
        },
    ),
    BuildPathIndexTestCase(
        description="handles nested subdirectories",
        model_paths={
            "deep_model": "models/staging/raw/deep_model.sql",
        },
        expected_folders={
            "deep_model": "staging/raw",
        },
    ),
    BuildPathIndexTestCase(
        description="handles models at top level models dir",
        model_paths={
            "top_model": "models/top_model.sql",
        },
        expected_folders={
            "top_model": "",
        },
    ),
]


@pytest.mark.parametrize(
    "test_case",
    BUILD_PATH_INDEX_TEST_CASES,
    ids=[case.description for case in BUILD_PATH_INDEX_TEST_CASES],
)
def test_given_model_paths_when_building_path_index_then_returns_expected_folders(
    test_case: BuildPathIndexTestCase,
) -> None:
    from sqlbuild.compiler.planner.helpers.output.plan_entry import build_path_index

    project: CompiledProject = build_test_project(
        model_deps={name: () for name in test_case.model_paths},
        model_paths=test_case.model_paths,
    )
    result: dict[CompiledObjectKey, str] = build_path_index(project)
    result_by_name: dict[str, str] = {key.name: folder for key, folder in result.items()}

    assert result_by_name == test_case.expected_folders

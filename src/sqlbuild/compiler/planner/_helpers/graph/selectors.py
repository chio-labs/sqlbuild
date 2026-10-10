"""Planner selector boundary over the native selector grammar and graph resolution."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.graph.main._compiled_graph_keys import compiled_graph_keys
from sqlbuild.compiler.graph.main._native_graph_from_views import native_graph_from_views
from sqlbuild.compiler.graph.main._native_graph_keys import native_graph_keys
from sqlbuild.compiler.planner.constants import (
    UNIT_TEST_SELECTOR_ERROR_CODE,
    UNIT_TEST_SELECTOR_ONLY_TEST_AND_BUILD,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import ParsedSelector, PathSelector
from sqlbuild.compiler.planner.types import SelectorKind

_KIND_SELECTOR: str = "kind"

type _Edges = Mapping[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
type _Failure = tuple[str, str, str | None]
type _Outcome = tuple[list[tuple[str, str]] | None, _Failure | None]


def parse_selector(raw: str) -> ParsedSelector | PathSelector:
    """Parse one raw selector token into a structured form."""

    parsed, failure = _native.parse_project_selector(raw)
    if parsed is None:
        raise _selector_error(failure)
    shape, first, second, upstream, downstream = parsed
    if shape == _KIND_SELECTOR:
        return ParsedSelector(
            kind=SelectorKind(first), value=second, upstream=upstream, downstream=downstream
        )
    return PathSelector(start_name=first, end_name=second, upstream=upstream, downstream=downstream)


def resolve_graph_selectors(
    *,
    graph: _native.NativeProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> frozenset[CompiledObjectKey]:
    """Resolve select/exclude strings against a native graph, adding required functions."""

    return _selected(graph.resolve(list(select), list(exclude)))


def resolve_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    all_keys: Mapping[str, CompiledObjectKey],
    upstream: _Edges,
    downstream: _Edges,
    tag_index: Mapping[str, Iterable[CompiledObjectKey]] | None = None,
    path_index: Mapping[CompiledObjectKey, str] | None = None,
) -> frozenset[CompiledObjectKey]:
    """Resolve raw select/exclude strings into a final set of object keys."""

    graph: _native.NativeProjectGraph = native_graph_from_views(
        all_keys=all_keys,
        upstream=upstream,
        downstream=downstream,
        tag_index=tag_index or {},
        path_index=path_index or {},
    )
    return resolve_graph_selectors(graph=graph, select=select, exclude=exclude)


def resolve_selector_tokens(
    *,
    selectors: tuple[str, ...],
    all_keys: Mapping[str, CompiledObjectKey],
    upstream: _Edges,
    downstream: _Edges,
    tag_index: Mapping[str, Iterable[CompiledObjectKey]],
    path_index: Mapping[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    """Union the keys matched by whitespace-separated selector tokens, without build expansion."""

    graph: _native.NativeProjectGraph = native_graph_from_views(
        all_keys=all_keys,
        upstream=upstream,
        downstream=downstream,
        tag_index=tag_index,
        path_index=path_index,
    )
    return _selected(graph.tokens(list(selectors)))


def match_selector_keys(
    *,
    parsed: ParsedSelector,
    all_keys: Mapping[str, CompiledObjectKey],
    tag_index: Mapping[str, Iterable[CompiledObjectKey]],
    path_index: Mapping[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    """Return the keys one parsed selector matches before `+` graph expansion."""

    graph: _native.NativeProjectGraph = native_graph_from_views(
        all_keys=all_keys, upstream={}, downstream={}, tag_index=tag_index, path_index=path_index
    )
    return _selected(graph.matched(str(parsed.kind), parsed.value))


def expand_required_build_resources(
    *,
    selected_keys: frozenset[CompiledObjectKey],
    upstream: _Edges,
    downstream: _Edges,
    include_upstream_functions: bool = True,
    include_upstream_seeds: bool = False,
    include_downstream_functions: bool = False,
) -> frozenset[CompiledObjectKey]:
    """Add non-model resources needed to build a coherent selected model scope."""

    graph: _native.NativeProjectGraph = native_graph_from_views(
        all_keys={}, upstream=upstream, downstream=downstream, tag_index={}, path_index={}
    )
    return compiled_graph_keys(
        graph.build_resources(
            native_graph_keys(selected_keys),
            (include_upstream_functions, include_upstream_seeds, include_downstream_functions),
        )
    )


def selector_name_help(*, value: str, candidates: Iterable[str]) -> str | None:
    """Suggest the nearest selectable names for an unknown selector name."""

    return _native.project_selector_name_help(value, list(candidates))


def unit_test_selector_rejection(*, selector: str) -> PlannerInputError:
    """The error for a unit-test selector given to a command that does not run unit tests."""

    return PlannerInputError(
        f"selector '{selector}' selects a unit test; {UNIT_TEST_SELECTOR_ONLY_TEST_AND_BUILD}",
        code=UNIT_TEST_SELECTOR_ERROR_CODE,
    )


def _selected(outcome: _Outcome) -> frozenset[CompiledObjectKey]:
    keys, failure = outcome
    if keys is None:
        raise _selector_error(failure)
    return compiled_graph_keys(keys)


def _selector_error(failure: _Failure | None) -> PlannerInputError:
    if failure is None:
        return PlannerInputError("selector resolution returned neither keys nor an error")
    code, message, help_text = failure
    return PlannerInputError(message, code=code, help=help_text)

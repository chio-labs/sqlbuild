"""Planner selector boundary over the native selector grammar and graph resolution."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping

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
_SURROGATE_START: int = 0xD800
_SURROGATE_END: int = 0xDFFF
_PRIVATE_USE_START: int = 0xF0000
_PRIVATE_USE_END: int = 0xFFFFE

type _Edges = Mapping[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
type _Failure = tuple[str, str, str | None]
type _Outcome = tuple[list[tuple[str, str]] | None, _Failure | None]


class _SurrogateCarrier:
    """Carry lone surrogates through the UTF-8 grammar as unused private-use characters."""

    def __init__(self, *, texts: Iterable[str], reserved: Callable[[], Iterable[str]]) -> None:
        joined: str = "".join(texts)
        surrogates: list[str] = sorted(
            {character for character in joined if _is_surrogate(character)}
        )
        self._sent: dict[str, str] = {}
        self._back: dict[str, str] = {}
        if not surrogates:
            return
        taken: set[str] = set(joined).union(*map(set, reserved()))
        candidates: Iterator[str] = (
            chr(point) for point in range(_PRIVATE_USE_START, _PRIVATE_USE_END)
        )
        for surrogate, carrier in zip(
            surrogates,
            (character for character in candidates if character not in taken),
            strict=False,
        ):
            self._sent[surrogate] = carrier
            self._back[carrier] = surrogate

    def send(self, text: str) -> str:
        return text.translate(str.maketrans(self._sent)) if self._sent else text

    def back(self, text: str | None) -> str | None:
        if text is None or not self._back:
            return text
        return text.translate(str.maketrans(self._back))

    def failure(self, failure: _Failure | None) -> _Failure | None:
        if failure is None:
            return None
        code, message, help_text = failure
        return (code, self.back(message) or "", self.back(help_text))


def _is_surrogate(character: str) -> bool:
    return _SURROGATE_START <= ord(character) <= _SURROGATE_END


def _graph_names(graph: _native.NativeProjectGraph) -> Callable[[], Iterable[str]]:
    return lambda: (name for name, _ in graph.names())


def parse_selector(raw: str) -> ParsedSelector | PathSelector:
    """Parse one raw selector token into a structured form."""

    carrier: _SurrogateCarrier = _SurrogateCarrier(texts=(raw,), reserved=tuple)
    parsed, failure = _native.parse_project_selector(carrier.send(raw))
    if parsed is None:
        raise _selector_error(carrier.failure(failure))
    shape, first, second, upstream, downstream = parsed
    if shape == _KIND_SELECTOR:
        return ParsedSelector(
            kind=SelectorKind(first),
            value=carrier.back(second) or "",
            upstream=upstream,
            downstream=downstream,
        )
    return PathSelector(
        start_name=carrier.back(first) or "",
        end_name=carrier.back(second) or "",
        upstream=upstream,
        downstream=downstream,
    )


def resolve_graph_selectors(
    *,
    graph: _native.NativeProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> frozenset[CompiledObjectKey]:
    """Resolve select/exclude strings against a native graph, adding required functions."""

    carrier: _SurrogateCarrier = _SurrogateCarrier(
        texts=(*select, *exclude), reserved=_graph_names(graph)
    )
    return _selected(
        outcome=graph.resolve(list(map(carrier.send, select)), list(map(carrier.send, exclude))),
        carrier=carrier,
    )


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
    carrier: _SurrogateCarrier = _SurrogateCarrier(texts=selectors, reserved=_graph_names(graph))
    return _selected(outcome=graph.tokens(list(map(carrier.send, selectors))), carrier=carrier)


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
    carrier: _SurrogateCarrier = _SurrogateCarrier(
        texts=(parsed.value,), reserved=_graph_names(graph)
    )
    return _selected(
        outcome=graph.matched(str(parsed.kind), carrier.send(parsed.value)), carrier=carrier
    )


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

    names: list[str] = list(candidates)
    carrier: _SurrogateCarrier = _SurrogateCarrier(texts=(value,), reserved=lambda: names)
    return carrier.back(_native.project_selector_name_help(carrier.send(value), names))


def unit_test_selector_rejection(*, selector: str) -> PlannerInputError:
    """The error for a unit-test selector given to a command that does not run unit tests."""

    return PlannerInputError(
        f"selector '{selector}' selects a unit test; {UNIT_TEST_SELECTOR_ONLY_TEST_AND_BUILD}",
        code=UNIT_TEST_SELECTOR_ERROR_CODE,
    )


def _selected(*, outcome: _Outcome, carrier: _SurrogateCarrier) -> frozenset[CompiledObjectKey]:
    keys, failure = outcome
    if keys is None:
        raise _selector_error(carrier.failure(failure))
    return compiled_graph_keys(keys)


def _selector_error(failure: _Failure | None) -> PlannerInputError:
    if failure is None:
        return PlannerInputError("selector resolution returned neither keys nor an error")
    code, message, help_text = failure
    return PlannerInputError(message, code=code, help=help_text)

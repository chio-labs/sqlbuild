"""Locate imports between native binding helper modules that point against the layer order."""

from __future__ import annotations

import re
from collections.abc import Iterable

from scripts.fensu_policy._helpers.native_crossings import is_checked_binding
from scripts.fensu_policy.constants import (
    NATIVE_BUDGET_SEPARATOR,
    NATIVE_GROUP_CLOSE,
    NATIVE_GROUP_OPEN,
    NATIVE_GROUP_SEPARATOR,
    NATIVE_HELPERS_PATH,
    NATIVE_HELPERS_ROOT,
    NATIVE_LAYER_SIBLING_SEPARATOR,
    NATIVE_LINE_COMMENT,
    NATIVE_MODULE_FILE_STEM,
    NATIVE_MODULE_PATH_SEPARATOR,
    NATIVE_PATH_SELF,
    NATIVE_PATH_SEPARATOR,
    NATIVE_RUST_SUFFIX,
    NATIVE_STRING_QUOTE,
    NATIVE_TEST_MODULE_MARKER,
)
from scripts.fensu_policy.models import LayerPlan, LayerReference

_IDENTIFIER: re.Pattern[str] = re.compile(r"\s*([A-Za-z_]\w*)")


def layer_plan(*, order: Iterable[str], modules: Iterable[str]) -> LayerPlan:
    """Parse the ordered layer list and the `module/path=layer` assignments."""

    ranks: dict[str, int] = {}
    rank: int
    entry: str
    for rank, entry in enumerate(order):
        name: str
        for name in entry.split(NATIVE_LAYER_SIBLING_SEPARATOR):
            ranks[name.strip()] = rank
    assignments: dict[tuple[str, ...], str] = {}
    for entry in modules:
        path, _, named = entry.rpartition(NATIVE_BUDGET_SEPARATOR)
        layer: str = named.strip()
        if layer in ranks:
            module: str = path.strip().strip(NATIVE_MODULE_PATH_SEPARATOR)
            assignments[tuple(module.split(NATIVE_MODULE_PATH_SEPARATOR))] = layer
    return LayerPlan(assignments=assignments, ranks=ranks)


def helper_module(*, path: str) -> tuple[str, ...] | None:
    """The helper module path of a non-test bindings helper file, if `path` is one."""

    if not is_checked_binding(path=path) or not path.startswith(NATIVE_HELPERS_ROOT):
        return None
    parts: list[str] = path[len(NATIVE_HELPERS_ROOT) :].removesuffix(NATIVE_RUST_SUFFIX).split("/")
    if parts[-1] == NATIVE_MODULE_FILE_STEM:
        parts.pop()
    return tuple(parts) if parts else None


def _code_text(*, source: str) -> list[str]:
    lines: list[str] = []
    line: str
    for line in source.splitlines():
        stripped: str = line.strip()
        if stripped.startswith(NATIVE_TEST_MODULE_MARKER):
            break
        if stripped.startswith(NATIVE_LINE_COMMENT):
            lines.append("")
            continue
        lines.append(line if NATIVE_STRING_QUOTE in line else line.split(NATIVE_LINE_COMMENT, 1)[0])
    return lines


def helper_references(*, source: str) -> list[LayerReference]:
    """Every helper module path a Rust source names, with brace groups expanded."""

    lines: list[str] = _code_text(source=source)
    text: str = "\n".join(lines)
    starts: list[int] = [0]
    line: str
    for line in lines:
        starts.append(starts[-1] + len(line) + 1)
    references: list[LayerReference] = []
    position: int = text.find(NATIVE_HELPERS_PATH)
    while position >= 0:
        path_start: int = position + len(NATIVE_HELPERS_PATH)
        path: tuple[str, ...]
        offset: int
        for path, offset in _expand(text=text, position=path_start, base=()):
            number: int = _line_number(starts=starts, offset=offset)
            references.append(LayerReference(line=number, target=path))
        position = text.find(NATIVE_HELPERS_PATH, path_start)
    return references


def _line_number(*, starts: list[int], offset: int) -> int:
    low: int = 0
    high: int = len(starts) - 1
    while low < high:
        middle: int = (low + high + 1) // 2
        if starts[middle] <= offset:
            low = middle
        else:
            high = middle - 1
    return low + 1


def _expand(
    *, text: str, position: int, base: tuple[str, ...]
) -> list[tuple[tuple[str, ...], int]]:
    rest: str = text[position:]
    if rest.lstrip().startswith(NATIVE_GROUP_OPEN):
        return _expand_group(text=text, open_at=text.index(NATIVE_GROUP_OPEN, position), base=base)
    match: re.Match[str] | None = _IDENTIFIER.match(rest)
    if match is None:
        return [(base, position)] if base else []
    segment: str = match.group(1)
    after: int = position + match.end()
    if text.startswith(NATIVE_PATH_SEPARATOR, after):
        return _expand(
            text=text, position=after + len(NATIVE_PATH_SEPARATOR), base=(*base, segment)
        )
    if segment == NATIVE_PATH_SELF:
        return [(base, position)] if base else []
    return [((*base, segment), position + match.start(1))]


def _expand_group(
    *, text: str, open_at: int, base: tuple[str, ...]
) -> list[tuple[tuple[str, ...], int]]:
    found: list[tuple[tuple[str, ...], int]] = []
    depth: int = 1
    item_start: int = open_at + 1
    index: int = open_at + 1
    while index < len(text) and depth:
        character: str = text[index]
        if character == NATIVE_GROUP_OPEN:
            depth += 1
        elif character == NATIVE_GROUP_CLOSE:
            depth -= 1
        if (character == NATIVE_GROUP_SEPARATOR and depth == 1) or depth == 0:
            if text[item_start:index].strip():
                found.extend(_expand(text=text[:index], position=item_start, base=base))
            item_start = index + 1
        index += 1
    return found


def upward_reference_lines(*, path: str, source: str, plan: LayerPlan) -> list[int] | None:
    """Lines of references that point against the layer order; None for an unassigned module."""

    module: tuple[str, ...] | None = helper_module(path=path)
    if module is None:
        return []
    source_layer: str | None = plan.layer_of(module=module)
    if source_layer is None:
        return None
    found: list[int] = []
    reference: LayerReference
    for reference in helper_references(source=source):
        if reference.target[: len(module)] == module:
            continue
        target_layer: str | None = plan.layer_of(module=reference.target)
        if target_layer is not None and plan.points_upward(
            source=source_layer, target=target_layer
        ):
            found.append(reference.line)
    return found

"""Extract normalised function and method units from Python sources."""

from __future__ import annotations

import ast
import io
import keyword
import token
import tokenize
from bisect import bisect_left
from dataclasses import dataclass

from scripts.dupscore._helpers.clones.tokens import build_clone_unit
from scripts.dupscore.constants import (
    LANGUAGE_PYTHON,
    PLACEHOLDER_FSTRING,
    PLACEHOLDER_IDENTIFIER,
    PLACEHOLDER_NUMBER,
    PLACEHOLDER_STRING,
)
from scripts.dupscore.models import CloneUnit

_KEYWORDS: frozenset[str] = frozenset(keyword.kwlist)
_DROPPED_TYPES: frozenset[int] = frozenset(
    {tokenize.NL, tokenize.COMMENT, tokenize.ENDMARKER, tokenize.ENCODING}
)
_STRUCTURE_MARKERS: dict[int, str] = {
    tokenize.NEWLINE: "$nl",
    tokenize.INDENT: "$in",
    tokenize.DEDENT: "$de",
}
_LITERAL_PLACEHOLDERS: dict[int, str] = {
    tokenize.NUMBER: PLACEHOLDER_NUMBER,
    tokenize.STRING: PLACEHOLDER_STRING,
}
_FSTRING_START_TYPES: frozenset[int] = frozenset(
    getattr(token, name) for name in ("FSTRING_START", "TSTRING_START") if hasattr(token, name)
)
_FSTRING_BODY_TYPES: frozenset[int] = frozenset(
    getattr(token, name)
    for name in ("FSTRING_MIDDLE", "FSTRING_END", "TSTRING_MIDDLE", "TSTRING_END")
    if hasattr(token, name)
)
_RETURN_ARROW: str = "->"

type _Position = tuple[int, int]
type _Span = tuple[_Position, _Position]
type _FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True, slots=True)
class _IgnoredSpan:
    start: _Position
    end: _Position
    statement: bool


@dataclass(frozen=True, slots=True)
class _UnitNode:
    node: _FunctionNode
    qualified_name: str


def extract_python_units(*, relative_path: str, source: str) -> tuple[CloneUnit, ...]:
    """Return one unit per top-level function or class method, without decorators."""

    try:
        tree: ast.Module = ast.parse(source)
        tokens: list[tokenize.TokenInfo] = [
            item
            for item in tokenize.generate_tokens(io.StringIO(source).readline)
            if item.type not in _DROPPED_TYPES
        ]
    except (SyntaxError, tokenize.TokenError):
        return ()
    starts: list[_Position] = [item.start for item in tokens]
    normalized: list[str | None] = [_normalize(item) for item in tokens]
    for span in _ignored_spans(tree.body):
        end: int = bisect_left(starts, span.end)
        if span.statement and end < len(tokens) and tokens[end].type == tokenize.NEWLINE:
            end += 1
        for index in range(bisect_left(starts, span.start), end):
            normalized[index] = None
    units: list[CloneUnit] = []
    for unit_node in _collect_unit_nodes(body=tree.body, prefix=""):
        node: _FunctionNode = unit_node.node
        end_line: int = node.end_lineno if node.end_lineno is not None else node.lineno
        end_column: int = node.end_col_offset if node.end_col_offset is not None else 0
        first: int = bisect_left(starts, (node.lineno, node.col_offset))
        last: int = bisect_left(starts, (end_line, end_column))
        kept: list[tuple[str, str]] = [
            (text, tokens[index].string)
            for index in range(first, last)
            if (text := normalized[index]) is not None
        ]
        units.append(
            build_clone_unit(
                language=LANGUAGE_PYTHON,
                path=relative_path,
                name=unit_node.qualified_name,
                start_line=node.lineno,
                end_line=end_line,
                normalized=[text for text, _ in kept],
                concrete=[text for _, text in kept],
            )
        )
    return tuple(units)


def _normalize(item: tokenize.TokenInfo) -> str | None:
    if item.type == tokenize.NAME:
        return item.string if item.string in _KEYWORDS else PLACEHOLDER_IDENTIFIER
    if item.type == tokenize.OP:
        return None if item.string == _RETURN_ARROW else item.string
    if item.type in _FSTRING_BODY_TYPES:
        return None
    if item.type in _FSTRING_START_TYPES:
        return PLACEHOLDER_FSTRING
    marker: str | None = _STRUCTURE_MARKERS.get(item.type)
    if marker is not None:
        return marker
    return _LITERAL_PLACEHOLDERS.get(item.type, item.string)


def _collect_unit_nodes(*, body: list[ast.stmt], prefix: str) -> list[_UnitNode]:
    collected: list[_UnitNode] = []
    for statement in body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            collected.append(_UnitNode(node=statement, qualified_name=prefix + statement.name))
        elif isinstance(statement, ast.ClassDef):
            collected.extend(
                _collect_unit_nodes(body=statement.body, prefix=f"{prefix}{statement.name}.")
            )
        elif isinstance(statement, (ast.If, ast.Try)):
            collected.extend(_collect_unit_nodes(body=statement.body, prefix=prefix))
            collected.extend(_collect_unit_nodes(body=statement.orelse, prefix=prefix))
    return collected


def _ignored_spans(body: list[ast.stmt]) -> list[_IgnoredSpan]:
    spans: list[_IgnoredSpan] = []
    for statement in body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            docstring: ast.Expr | None = _docstring_expression(statement)
            if docstring is not None:
                docstring_start, docstring_end = _span_of(docstring)
                spans.append(_IgnoredSpan(start=docstring_start, end=docstring_end, statement=True))
        annotation_spans: list[_Span] = []
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotation_spans = _signature_annotation_spans(statement)
        elif isinstance(statement, ast.AnnAssign):
            annotation_spans = [
                _annotation_span(owner=statement.target, annotation=statement.annotation)
            ]
        spans.extend(
            _IgnoredSpan(start=start, end=end, statement=False) for start, end in annotation_spans
        )
        for child_body in _child_bodies(statement):
            spans.extend(_ignored_spans(child_body))
    return spans


def _child_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    bodies: list[list[ast.stmt]] = []
    for field_name in ("body", "orelse", "finalbody"):
        value: object = getattr(statement, field_name, None)
        if isinstance(value, list):
            bodies.append([item for item in value if isinstance(item, ast.stmt)])
    if isinstance(statement, (ast.Try, ast.TryStar)):
        bodies.extend(handler.body for handler in statement.handlers)
    elif isinstance(statement, ast.Match):
        bodies.extend(case.body for case in statement.cases)
    return bodies


def _signature_annotation_spans(node: _FunctionNode) -> list[_Span]:
    spans: list[_Span] = [_span_of(node.returns)] if node.returns is not None else []
    arguments: ast.arguments = node.args
    for argument in (
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
        *(item for item in (arguments.vararg, arguments.kwarg) if item is not None),
    ):
        if argument.annotation is not None:
            spans.append(_annotation_span(owner=argument, annotation=argument.annotation))
    return spans


def _annotation_span(*, owner: ast.expr | ast.arg, annotation: ast.expr) -> _Span:
    """Cover the ``:`` separator and the annotation that follow a name."""

    owner_end: _Position = (
        (owner.lineno, owner.col_offset + len(owner.arg))
        if isinstance(owner, ast.arg)
        else (
            owner.end_lineno if owner.end_lineno is not None else owner.lineno,
            owner.end_col_offset if owner.end_col_offset is not None else owner.col_offset,
        )
    )
    return (owner_end, _span_of(annotation)[1])


def _docstring_expression(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> ast.Expr | None:
    if not node.body:
        return None
    first: ast.stmt = node.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first
    return None


def _span_of(node: ast.expr | ast.stmt) -> _Span:
    end_line: int = node.end_lineno if node.end_lineno is not None else node.lineno
    end_column: int = node.end_col_offset if node.end_col_offset is not None else node.col_offset
    return ((node.lineno, node.col_offset), (end_line, end_column))

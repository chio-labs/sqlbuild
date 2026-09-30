"""Model and column references in source and seed YAML declarations."""

from __future__ import annotations

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from sqlbuild.compiler.refactoring._helpers.text.sql_sites import embedded_ref_spans
from sqlbuild.compiler.refactoring._helpers.text.text_edits import path_edits, text_edit
from sqlbuild.compiler.refactoring.constants import (
    RELATIONSHIPS_AUDIT,
    RELATIONSHIPS_FIELD_KEY,
    RELATIONSHIPS_TO_KEY,
)
from sqlbuild.compiler.refactoring.models import ProjectSqlFile, TextEdit, YamlRelationship
from sqlbuild.compiler.refactoring.types import EditKind


def yaml_model_edits(
    *, files: tuple[ProjectSqlFile, ...], old: str, new: str
) -> tuple[tuple[str, TextEdit], ...]:
    """Rename `__ref` calls in YAML strings and bare relationships targets naming a model."""

    edits: list[tuple[str, TextEdit]] = []
    item: ProjectSqlFile
    for item in files:
        root: Node | None = _compose(item.contents)
        if root is None:
            continue
        found: list[TextEdit] = []
        scalar: ScalarNode
        for scalar in _scalars(root):
            found.extend(
                text_edit(
                    text=item.contents,
                    start=_start(scalar) + start,
                    end=_start(scalar) + end,
                    replacement=new,
                    kind=EditKind.REFERENCE,
                )
                for start, end in embedded_ref_spans(
                    text=_raw(contents=item.contents, scalar=scalar), name=old
                )
            )
        found.extend(
            _rename_scalar(
                contents=item.contents,
                scalar=relationship.target,
                new=new,
                kind=EditKind.REFERENCE,
            )
            for relationship in _relationships(root)
            if relationship.target is not None and relationship.target.value == old
        )
        edits.extend(path_edits(path=item.relative_path, edits=tuple(found)))
    return tuple(edits)


def yaml_column_edits(
    *, files: tuple[ProjectSqlFile, ...], model: str, old: str, new: str
) -> tuple[tuple[str, TextEdit], ...]:
    """Rename relationships `field` values that point at a renamed column of a model."""

    edits: list[tuple[str, TextEdit]] = []
    item: ProjectSqlFile
    for item in files:
        root: Node | None = _compose(item.contents)
        if root is None:
            continue
        edits.extend(
            path_edits(
                path=item.relative_path,
                edits=tuple(
                    _rename_scalar(
                        contents=item.contents,
                        scalar=relationship.field,
                        new=new,
                        kind=EditKind.COLUMN,
                    )
                    for relationship in _relationships(root)
                    if relationship.field is not None
                    and relationship.field.value.lower() == old.lower()
                    and _targets(contents=item.contents, relationship=relationship, model=model)
                ),
            )
        )
    return tuple(edits)


def _compose(contents: str) -> Node | None:
    try:
        return yaml.compose(contents, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        return None


def _scalars(node: Node) -> tuple[ScalarNode, ...]:
    if isinstance(node, ScalarNode):
        return (node,)
    children: list[Node] = []
    if isinstance(node, SequenceNode):
        children.extend(node.value)
    if isinstance(node, MappingNode):
        children.extend(value for _, value in node.value)
    found: list[ScalarNode] = []
    child: Node
    for child in children:
        found.extend(_scalars(child))
    return tuple(found)


def _relationships(node: Node) -> tuple[YamlRelationship, ...]:
    found: list[YamlRelationship] = []
    if isinstance(node, MappingNode):
        key: Node
        value: Node
        for key, value in node.value:
            if (
                isinstance(key, ScalarNode)
                and key.value == RELATIONSHIPS_AUDIT
                and isinstance(value, MappingNode)
            ):
                found.append(_relationship(value))
            found.extend(_relationships(value))
    if isinstance(node, SequenceNode):
        child: Node
        for child in node.value:
            found.extend(_relationships(child))
    return tuple(found)


def _relationship(node: MappingNode) -> YamlRelationship:
    values: dict[str, ScalarNode] = {
        key.value: value
        for key, value in node.value
        if isinstance(key, ScalarNode) and isinstance(value, ScalarNode)
    }
    return YamlRelationship(
        target=values.get(RELATIONSHIPS_TO_KEY), field=values.get(RELATIONSHIPS_FIELD_KEY)
    )


def _targets(*, contents: str, relationship: YamlRelationship, model: str) -> bool:
    target: ScalarNode | None = relationship.target
    if target is None:
        return False
    return target.value == model or bool(
        embedded_ref_spans(text=_raw(contents=contents, scalar=target), name=model)
    )


def _rename_scalar(*, contents: str, scalar: ScalarNode, new: str, kind: EditKind) -> TextEdit:
    raw: str = _raw(contents=contents, scalar=scalar)
    offset: int = max(raw.lower().find(scalar.value.lower()), 0)
    start: int = _start(scalar) + offset
    return text_edit(
        text=contents,
        start=start,
        end=start + len(scalar.value),
        replacement=new,
        kind=kind,
    )


def _raw(*, contents: str, scalar: ScalarNode) -> str:
    end: int = scalar.end_mark.index if scalar.end_mark is not None else _start(scalar)
    return contents[_start(scalar) : end]


def _start(scalar: ScalarNode) -> int:
    return scalar.start_mark.index if scalar.start_mark is not None else 0

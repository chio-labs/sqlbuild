"""Conservative external column reads resolved through local query relations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlbuild.compiler.compile._helpers.analysis.columns import (
    _analysis_reference_name,
    _lineage_resource_type,
    _replace_refs_with_stubs,
)
from sqlbuild.compiler.compile._helpers.analysis.cte_facts import (
    _polyglot_direct_select_tables,
    _polyglot_top_level_ctes,
    _unwrap_polyglot_annotations,
)
from sqlbuild.compiler.compile.models import CompiledLineageSourceFact, CompileSqlReference
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_COLUMN,
    POLYGLOT_KIND_SELECT,
    POLYGLOT_KIND_TABLE,
    POLYGLOT_SET_OPERATION_KINDS,
)
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql

_POLYGLOT_KIND_SUBQUERY: str = "subquery"


@dataclass(frozen=True)
class _RelationReads:
    """External leaves represented by one local relation's output columns."""

    slots: tuple[tuple[str, tuple[CompiledLineageSourceFact, ...]], ...] = ()
    passthrough_resources: tuple[tuple[CompiledResourceType, str], ...] = ()

    def resolve(self, column_name: str) -> tuple[CompiledLineageSourceFact, ...]:
        _, leaves = self.resolve_with_presence(column_name)
        return leaves

    def resolve_with_presence(
        self, column_name: str
    ) -> tuple[bool, tuple[CompiledLineageSourceFact, ...]]:
        normalized_name: str = column_name.casefold()
        matching: tuple[CompiledLineageSourceFact, ...] | None = next(
            (leaves for name, leaves in reversed(self.slots) if name.casefold() == normalized_name),
            None,
        )
        if matching is not None:
            return True, matching
        leaves: tuple[CompiledLineageSourceFact, ...] = tuple(
            CompiledLineageSourceFact(
                resource_type=resource_type,
                resource_name=resource_name,
                column_name=column_name,
            )
            for resource_type, resource_name in self.passthrough_resources
        )
        return bool(self.passthrough_resources), leaves


def resolve_required_external_columns(
    *,
    query_sql: str,
    references: tuple[CompileSqlReference, ...],
    dialect: str | None,
) -> tuple[CompiledLineageSourceFact, ...]:
    """Resolve model column reads to external resources without expanding whole-query lineage."""

    polyglot_module: Any = import_polyglot_sql()
    try:
        parsed: Any = polyglot_module.parse_one(
            _replace_refs_with_stubs(query_sql),
            dialect=dialect or "generic",
        )
    except polyglot_module.PolyglotError:
        return ()
    relations: dict[str, _RelationReads] = {}
    for reference in references:
        resource_type: CompiledResourceType | None = _lineage_resource_type(reference)
        if resource_type is None:
            continue
        relations[_analysis_reference_name(reference).casefold()] = _RelationReads(
            passthrough_resources=((resource_type, reference.ref_name),)
        )
    _, required = _resolve_query_reads(
        query=parsed,
        inherited_relations=relations,
        outer_relations={},
    )
    return _deduplicated_sources(required)


def _resolve_query_reads(
    *,
    query: Any,
    inherited_relations: dict[str, _RelationReads],
    outer_relations: dict[str, _RelationReads],
) -> tuple[_RelationReads, tuple[CompiledLineageSourceFact, ...]]:
    query = _unwrap_polyglot_annotations(query)
    relations: dict[str, _RelationReads] = dict(inherited_relations)
    required: list[CompiledLineageSourceFact] = []
    for cte_name, cte_body, has_column_aliases in _polyglot_top_level_ctes(query):
        cte_reads: _RelationReads
        cte_required: tuple[CompiledLineageSourceFact, ...]
        cte_reads, cte_required = _resolve_query_reads(
            query=cte_body,
            inherited_relations=relations,
            outer_relations=outer_relations,
        )
        required.extend(cte_required)
        if has_column_aliases:
            cte_reads = _apply_cte_column_aliases(query=query, cte_name=cte_name, reads=cte_reads)
        relations[cte_name.casefold()] = cte_reads

    kind: str = str(getattr(query, "kind", ""))
    if kind in POLYGLOT_SET_OPERATION_KINDS:
        set_reads, set_required = _resolve_set_operation_reads(
            operation=query,
            inherited_relations=relations,
            outer_relations=outer_relations,
        )
        required.extend(set_required)
        return set_reads, _deduplicated_sources(required)
    if kind != POLYGLOT_KIND_SELECT:
        return _RelationReads(), _deduplicated_sources(required)

    local_relations: dict[str, _RelationReads] = {}
    for table in _polyglot_direct_select_tables(query):
        table_name: str = str(getattr(table, "name", "") or "")
        relation: _RelationReads | None = relations.get(table_name.casefold())
        if relation is None:
            continue
        local_relations[table_name.casefold()] = relation
        alias_or_name: str = str(getattr(table, "alias_or_name", "") or "")
        if alias_or_name:
            local_relations[alias_or_name.casefold()] = relation

    nested_required: list[CompiledLineageSourceFact] = []
    for nested_query, alias in _direct_nested_queries(query):
        nested_reads, reads = _resolve_query_reads(
            query=nested_query,
            inherited_relations=relations,
            outer_relations={**outer_relations, **local_relations},
        )
        nested_required.extend(reads)
        if alias:
            local_relations[alias.casefold()] = nested_reads
    shared_column_reads: dict[str, tuple[CompiledLineageSourceFact, ...]] = (
        _join_using_column_reads(select=query, local_relations=local_relations)
    )

    slots: list[tuple[str, tuple[CompiledLineageSourceFact, ...]]] = []
    projection_required: list[CompiledLineageSourceFact] = []
    passthrough_resources: list[tuple[CompiledResourceType, str]] = []
    for raw_projection in getattr(query, "expressions", ()):
        projection: Any = _unwrap_polyglot_annotations(raw_projection)
        if bool(getattr(projection, "is_star", False)):
            star_relations: tuple[_RelationReads, ...] = _star_projection_relations(
                projection=projection,
                local_relations=local_relations,
            )
            for relation in star_relations:
                slots.extend(relation.slots)
                passthrough_resources.extend(relation.passthrough_resources)
            slots.extend(
                _star_modifier_slots(
                    projection=projection,
                    local_relations=local_relations,
                    outer_relations=outer_relations,
                    shared_column_reads=shared_column_reads,
                )
            )
            continue
        output_name: str = str(getattr(projection, "output_name", "") or "")
        leaves: tuple[CompiledLineageSourceFact, ...] = _resolve_expression_reads(
            expression=projection,
            local_relations=local_relations,
            outer_relations=outer_relations,
            shared_column_reads=shared_column_reads,
        )
        projection_required.extend(leaves)
        if output_name:
            slots.append((output_name, leaves))

    required.extend(
        _resolve_clause_reads(
            select=query,
            output_slots=tuple(slots),
            local_relations=local_relations,
            outer_relations=outer_relations,
            shared_column_reads=shared_column_reads,
        )
    )
    for leaves in shared_column_reads.values():
        required.extend(leaves)
    for _, slot in slots:
        required.extend(slot)
    required.extend(projection_required)
    required.extend(nested_required)
    return (
        _RelationReads(
            slots=tuple(slots),
            passthrough_resources=_deduplicated_resources(passthrough_resources),
        ),
        _deduplicated_sources(required),
    )


def _resolve_set_operation_reads(
    *,
    operation: Any,
    inherited_relations: dict[str, _RelationReads],
    outer_relations: dict[str, _RelationReads],
) -> tuple[_RelationReads, tuple[CompiledLineageSourceFact, ...]]:
    branches: list[_RelationReads] = []
    required: list[CompiledLineageSourceFact] = []
    for side in ("left", "right"):
        branch: Any | None = getattr(operation, "args", {}).get(side)
        if branch is None:
            return _RelationReads(), _deduplicated_sources(required)
        branch_reads, branch_required = _resolve_query_reads(
            query=branch,
            inherited_relations=inherited_relations,
            outer_relations=outer_relations,
        )
        branches.append(branch_reads)
        required.extend(branch_required)
    left, right = branches
    if bool(getattr(operation, "args", {}).get("by_name")):
        right_by_name: dict[str, tuple[CompiledLineageSourceFact, ...]] = {
            name.casefold(): leaves for name, leaves in right.slots
        }
        slots: tuple[tuple[str, tuple[CompiledLineageSourceFact, ...]], ...] = tuple(
            (
                name,
                _deduplicated_sources([*leaves, *right_by_name.get(name.casefold(), ())]),
            )
            for name, leaves in left.slots
        )
    elif len(left.slots) == len(right.slots):
        slots = tuple(
            (left_name, _deduplicated_sources([*left_leaves, *right_leaves]))
            for (left_name, left_leaves), (_, right_leaves) in zip(
                left.slots,
                right.slots,
                strict=True,
            )
        )
    else:
        slots = ()
    passthrough_resources: tuple[tuple[CompiledResourceType, str], ...] = _deduplicated_resources(
        [*left.passthrough_resources, *right.passthrough_resources]
    )
    return (
        _RelationReads(slots=slots, passthrough_resources=passthrough_resources),
        _deduplicated_sources(required),
    )


def _resolve_expression_reads(
    *,
    expression: Any,
    local_relations: dict[str, _RelationReads],
    outer_relations: dict[str, _RelationReads],
    shared_column_reads: dict[str, tuple[CompiledLineageSourceFact, ...]],
) -> tuple[CompiledLineageSourceFact, ...]:
    resolved: list[CompiledLineageSourceFact] = []
    for column_name, table_name in _direct_column_refs(expression):
        if not column_name:
            continue
        if table_name:
            relation: _RelationReads | None = local_relations.get(
                table_name.casefold()
            ) or outer_relations.get(table_name.casefold())
            if relation is not None:
                resolved.extend(relation.resolve(column_name))
            continue
        resolved.extend(
            _resolve_unqualified_column(
                column_name=column_name,
                local_relations=local_relations,
                outer_relations=outer_relations,
                shared_column_reads=shared_column_reads,
            )
        )
    return _deduplicated_sources(resolved)


def _resolve_clause_reads(
    *,
    select: Any,
    output_slots: tuple[tuple[str, tuple[CompiledLineageSourceFact, ...]], ...],
    local_relations: dict[str, _RelationReads],
    outer_relations: dict[str, _RelationReads],
    shared_column_reads: dict[str, tuple[CompiledLineageSourceFact, ...]],
) -> tuple[CompiledLineageSourceFact, ...]:
    output_alias_first_clauses: frozenset[str] = frozenset({"order_by", "qualify"})
    output_alias_fallback_clauses: frozenset[str] = frozenset(
        {"cluster_by", "group_by", "having", "sort_by"}
    )
    clause_names: tuple[str, ...] = (
        "cluster_by",
        "connect",
        "distinct_on",
        "distribute_by",
        "group_by",
        "having",
        "joins",
        "order_by",
        "qualify",
        "sort_by",
        "where_clause",
        "windows",
    )
    resolved: list[CompiledLineageSourceFact] = []
    args: dict[str, object] = getattr(select, "args", {})
    for clause_name in clause_names:
        refs: tuple[tuple[str, str], ...] = _column_refs_in_payload(args.get(clause_name))
        for column_name, table_name in refs:
            if not column_name:
                continue
            if table_name:
                relation: _RelationReads | None = local_relations.get(
                    table_name.casefold()
                ) or outer_relations.get(table_name.casefold())
                if relation is not None:
                    resolved.extend(relation.resolve(column_name))
                continue
            output_match: tuple[bool, tuple[CompiledLineageSourceFact, ...]] = _output_slot_reads(
                column_name=column_name, output_slots=output_slots
            )
            if clause_name in output_alias_first_clauses and output_match[0]:
                resolved.extend(output_match[1])
                continue
            input_present, input_reads = _resolve_unqualified_column_with_presence(
                column_name=column_name,
                local_relations=local_relations,
                outer_relations=outer_relations,
                shared_column_reads=shared_column_reads,
            )
            if input_present:
                resolved.extend(input_reads)
                continue
            if clause_name in output_alias_fallback_clauses and output_match[0]:
                resolved.extend(output_match[1])
    return _deduplicated_sources(resolved)


def _output_slot_reads(
    *,
    column_name: str,
    output_slots: tuple[tuple[str, tuple[CompiledLineageSourceFact, ...]], ...],
) -> tuple[bool, tuple[CompiledLineageSourceFact, ...]]:
    normalized_name: str = column_name.casefold()
    for output_name, leaves in reversed(output_slots):
        if output_name.casefold() == normalized_name:
            return True, leaves
    return False, ()


def _column_refs_in_payload(payload: object) -> tuple[tuple[str, str], ...]:
    if isinstance(payload, list):
        refs: list[tuple[str, str]] = []
        for value in payload:
            refs.extend(_column_refs_in_payload(value))
        return tuple(refs)
    if not isinstance(payload, dict):
        return ()
    payload_dict: dict[str, object] = cast(dict[str, object], payload)
    if any(
        query_kind in payload_dict
        for query_kind in {
            _POLYGLOT_KIND_SUBQUERY,
            POLYGLOT_KIND_SELECT,
            *POLYGLOT_SET_OPERATION_KINDS,
        }
    ):
        return ()
    column_payload: object = payload_dict.get(POLYGLOT_KIND_COLUMN)
    if isinstance(column_payload, dict):
        column_dict: dict[str, object] = cast(dict[str, object], column_payload)
        column_name: str = _payload_name(column_dict.get("name"))
        table_name: str = _payload_name(column_dict.get("table"))
        return ((column_name, table_name),)
    refs = []
    for value in payload_dict.values():
        refs.extend(_column_refs_in_payload(value))
    return tuple(refs)


def _star_modifier_slots(
    *,
    projection: Any,
    local_relations: dict[str, _RelationReads],
    outer_relations: dict[str, _RelationReads],
    shared_column_reads: dict[str, tuple[CompiledLineageSourceFact, ...]],
) -> tuple[tuple[str, tuple[CompiledLineageSourceFact, ...]], ...]:
    slots: list[tuple[str, tuple[CompiledLineageSourceFact, ...]]] = []
    replacements: object = getattr(projection, "args", {}).get("replace")
    replacement_expressions: tuple[Any, ...] = tuple(projection.children())
    if isinstance(replacements, list) and len(replacements) == len(replacement_expressions):
        for replacement, expression in zip(
            replacements,
            replacement_expressions,
            strict=True,
        ):
            if not isinstance(replacement, dict):
                continue
            replacement_dict: dict[str, object] = cast(dict[str, object], replacement)
            output_name: str = _payload_name(replacement_dict.get("alias"))
            if not output_name:
                continue
            slots.append(
                (
                    output_name,
                    _resolve_expression_reads(
                        expression=expression,
                        local_relations=local_relations,
                        outer_relations=outer_relations,
                        shared_column_reads=shared_column_reads,
                    ),
                )
            )
    renames: object = getattr(projection, "args", {}).get("rename")
    if isinstance(renames, list):
        for rename in renames:
            if not isinstance(rename, list):
                continue
            try:
                input_payload, output_payload = rename
            except ValueError:
                continue
            input_name: str = _payload_name(input_payload)
            output_name = _payload_name(output_payload)
            if not input_name or not output_name:
                continue
            slots.append(
                (
                    output_name,
                    _resolve_unqualified_column(
                        column_name=input_name,
                        local_relations=local_relations,
                        outer_relations=outer_relations,
                        shared_column_reads=shared_column_reads,
                    ),
                )
            )
    return tuple(slots)


def _resolve_unqualified_column(
    *,
    column_name: str,
    local_relations: dict[str, _RelationReads],
    outer_relations: dict[str, _RelationReads],
    shared_column_reads: dict[str, tuple[CompiledLineageSourceFact, ...]],
) -> tuple[CompiledLineageSourceFact, ...]:
    _, leaves = _resolve_unqualified_column_with_presence(
        column_name=column_name,
        local_relations=local_relations,
        outer_relations=outer_relations,
        shared_column_reads=shared_column_reads,
    )
    return leaves


def _resolve_unqualified_column_with_presence(
    *,
    column_name: str,
    local_relations: dict[str, _RelationReads],
    outer_relations: dict[str, _RelationReads],
    shared_column_reads: dict[str, tuple[CompiledLineageSourceFact, ...]],
) -> tuple[bool, tuple[CompiledLineageSourceFact, ...]]:
    shared_reads: tuple[CompiledLineageSourceFact, ...] | None = shared_column_reads.get(
        column_name.casefold()
    )
    if shared_reads is not None:
        return True, shared_reads
    unique_relations: tuple[_RelationReads, ...] = _unique_relations(local_relations)
    candidates: list[tuple[CompiledLineageSourceFact, ...]] = []
    for relation in unique_relations:
        present, leaves = relation.resolve_with_presence(column_name)
        if present:
            candidates.append(leaves)
    if len(candidates) == 1:
        return True, candidates[0]
    if candidates:
        return True, ()
    outer_candidates: list[tuple[CompiledLineageSourceFact, ...]] = []
    for relation in _unique_relations(outer_relations):
        present, leaves = relation.resolve_with_presence(column_name)
        if present:
            outer_candidates.append(leaves)
    if len(outer_candidates) == 1:
        return True, outer_candidates[0]
    return bool(outer_candidates), ()


def _join_using_column_reads(
    *,
    select: Any,
    local_relations: dict[str, _RelationReads],
) -> dict[str, tuple[CompiledLineageSourceFact, ...]]:
    joins: object = getattr(select, "args", {}).get("joins")
    if not isinstance(joins, list):
        return {}
    relation_sequence: list[_RelationReads] = []
    for child in select.children():
        kind: str = str(getattr(child, "kind", ""))
        relation: _RelationReads | None = None
        if kind == POLYGLOT_KIND_TABLE:
            table_name: str = str(getattr(child, "name", "") or "")
            relation = local_relations.get(table_name.casefold())
        elif kind == _POLYGLOT_KIND_SUBQUERY:
            alias: str = str(getattr(child, "alias_or_name", "") or "")
            relation = local_relations.get(alias.casefold())
        if relation is not None:
            relation_sequence.append(relation)
    if not relation_sequence:
        return {}
    joined_relations: list[_RelationReads] = [relation_sequence[0]]
    joined_shared_reads: dict[str, tuple[CompiledLineageSourceFact, ...]] = {}
    reads_by_column: dict[str, list[CompiledLineageSourceFact]] = {}
    for index, join in enumerate(joins, start=1):
        if not isinstance(join, dict):
            continue
        join_dict: dict[str, object] = cast(dict[str, object], join)
        if index >= len(relation_sequence):
            break
        right_relation: _RelationReads = relation_sequence[index]
        using_columns: object = join_dict.get("using")
        if isinstance(using_columns, list):
            for column in using_columns:
                name: str = _payload_name(column)
                if not name:
                    continue
                normalized_name: str = name.casefold()
                column_reads: list[CompiledLineageSourceFact] = reads_by_column.setdefault(
                    normalized_name, []
                )
                left_reads: tuple[CompiledLineageSourceFact, ...] | None = joined_shared_reads.get(
                    normalized_name
                )
                if left_reads is None:
                    left_candidates: list[tuple[CompiledLineageSourceFact, ...]] = []
                    for relation in joined_relations:
                        present, leaves = relation.resolve_with_presence(name)
                        if present:
                            left_candidates.append(leaves)
                    left_reads = left_candidates[0] if len(left_candidates) == 1 else ()
                _, right_reads = right_relation.resolve_with_presence(name)
                combined_reads: tuple[CompiledLineageSourceFact, ...] = _deduplicated_sources(
                    [*left_reads, *right_reads]
                )
                joined_shared_reads[normalized_name] = combined_reads
                column_reads.extend(combined_reads)
        joined_relations.append(right_relation)
    return {
        name: _deduplicated_sources(column_reads) for name, column_reads in reads_by_column.items()
    }


def _payload_name(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    payload_dict: dict[str, object] = cast(dict[str, object], payload)
    name: object = payload_dict.get("name")
    return name if isinstance(name, str) else ""


def _direct_column_refs(expression: Any) -> tuple[tuple[str, str], ...]:
    kind: str = str(getattr(expression, "kind", ""))
    if kind == POLYGLOT_KIND_COLUMN:
        column_name: str = str(getattr(expression, "name", "") or "")
        table_name: str = ""
        table_payload: object = getattr(expression, "args", {}).get("table")
        if isinstance(table_payload, dict):
            raw_name: object = table_payload.get("name")
            if isinstance(raw_name, str):
                table_name = raw_name
        return ((column_name, table_name),)
    if kind == _POLYGLOT_KIND_SUBQUERY or kind == POLYGLOT_KIND_SELECT:
        return ()
    if kind in POLYGLOT_SET_OPERATION_KINDS:
        return ()
    refs: list[tuple[str, str]] = []
    for child in expression.children():
        refs.extend(_direct_column_refs(child))
    return tuple(refs)


def _direct_nested_queries(select: Any) -> tuple[tuple[Any, str], ...]:
    nested: list[tuple[Any, str]] = []
    for child in select.children():
        if str(getattr(child, "kind", "")) == POLYGLOT_KIND_TABLE:
            continue
        nested.extend(_nested_queries_in_expression(child))
    return tuple(nested)


def _nested_queries_in_expression(expression: Any) -> tuple[tuple[Any, str], ...]:
    kind: str = str(getattr(expression, "kind", ""))
    if kind == _POLYGLOT_KIND_SUBQUERY:
        body: Any | None = getattr(expression, "this", None)
        return (
            ((body, str(getattr(expression, "alias_or_name", "") or "")),)
            if body is not None
            else ()
        )
    if kind == POLYGLOT_KIND_SELECT or kind in POLYGLOT_SET_OPERATION_KINDS:
        return ((expression, ""),)
    nested: list[tuple[Any, str]] = []
    for child in expression.children():
        nested.extend(_nested_queries_in_expression(child))
    return tuple(nested)


def _star_projection_relations(
    *,
    projection: Any,
    local_relations: dict[str, _RelationReads],
) -> tuple[_RelationReads, ...]:
    table_payload: object = getattr(projection, "args", {}).get("table")
    table_name: str = ""
    if isinstance(table_payload, dict):
        raw_name: object = table_payload.get("name")
        if isinstance(raw_name, str):
            table_name = raw_name
    if table_name:
        relation: _RelationReads | None = local_relations.get(table_name.casefold())
        return (relation,) if relation is not None else ()
    return _unique_relations(local_relations)


def _apply_cte_column_aliases(
    *,
    query: Any,
    cte_name: str,
    reads: _RelationReads,
) -> _RelationReads:
    aliases: tuple[str, ...] = ()
    for raw_cte in _raw_cte_payloads(query):
        alias_payload: object = raw_cte.get("alias")
        if not isinstance(alias_payload, dict):
            continue
        alias_dict: dict[str, object] = cast(dict[str, object], alias_payload)
        if alias_dict.get("name") != cte_name:
            continue
        raw_columns: object = raw_cte.get("columns")
        if isinstance(raw_columns, list):
            aliases = tuple(
                str(cast(dict[str, object], column).get("name"))
                for column in raw_columns
                if isinstance(column, dict)
                and isinstance(cast(dict[str, object], column).get("name"), str)
            )
        break
    if len(aliases) != len(reads.slots):
        return _RelationReads()
    return _RelationReads(
        slots=tuple(
            (alias, leaves) for alias, (_, leaves) in zip(aliases, reads.slots, strict=True)
        )
    )


def _raw_cte_payloads(query: Any) -> tuple[dict[str, object], ...]:
    with_payload: object = getattr(query, "args", {}).get("with")
    if not isinstance(with_payload, dict):
        return ()
    raw_ctes: object = with_payload.get("ctes")
    if not isinstance(raw_ctes, list):
        return ()
    return tuple(raw_cte for raw_cte in raw_ctes if isinstance(raw_cte, dict))


def _unique_relations(relations: dict[str, _RelationReads]) -> tuple[_RelationReads, ...]:
    unique: list[_RelationReads] = []
    seen: set[int] = set()
    for relation in relations.values():
        identity: int = id(relation)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(relation)
    return tuple(unique)


def _deduplicated_resources(
    resources: list[tuple[CompiledResourceType, str]],
) -> tuple[tuple[CompiledResourceType, str], ...]:
    return tuple(dict.fromkeys(resources))


def _deduplicated_sources(
    sources: list[CompiledLineageSourceFact] | tuple[CompiledLineageSourceFact, ...],
) -> tuple[CompiledLineageSourceFact, ...]:
    unique: list[CompiledLineageSourceFact] = []
    seen: set[tuple[CompiledResourceType, str, str]] = set()
    for source in sources:
        key: tuple[CompiledResourceType, str, str] = (
            CompiledResourceType(source.resource_type),
            source.resource_name,
            source.column_name,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(source)
    return tuple(unique)

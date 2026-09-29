"""Exact sharing of binding-mode native analyses between models with equal inputs."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

from sqlbuild.compiler.compile._helpers.analysis.columns import (
    _analysis_reference_name,
    _lineage_resource_type,
    _qualified_reference_names,
)
from sqlbuild.compiler.compile.constants import (
    COMPACT_REFERENCE_MARKER_PATTERN,
    COMPACT_RELATION_STUB_PREFIX,
    COMPACT_UNSTUBBED_REFERENCE_KIND,
    MIN_SHARED_BINDING_QUERY_MEMBERS,
)
from sqlbuild.compiler.compile.models import (
    CompactBatchContext,
    CompactBatchInputs,
    CompileSqlReference,
    ModelSqlAnalysisRequest,
    NativeCompactAnalysis,
    PreparedBindingQuery,
    SharedBindingQuery,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.sql_analysis.constants import SQL_QUOTED_IDENTIFIER_DELIMITER
from sqlbuild.compiler.sql_analysis.main._normalize_analysis import normalize_analysis_sql
from sqlbuild.compiler.sql_analysis.models import SqlSchemaValidationRequest


def lineage_reference_map(
    references: tuple[CompileSqlReference, ...],
) -> dict[str, tuple[CompiledResourceType, str]]:
    reference_map: dict[str, tuple[CompiledResourceType, str]] = {}
    reference: CompileSqlReference
    for reference in references:
        resource_type: CompiledResourceType | None = _lineage_resource_type(reference)
        if resource_type is None:
            continue
        reference_map[_analysis_reference_name(reference)] = (
            resource_type,
            reference.ref_name,
        )
    return reference_map


def binding_share_prekey(*, query_sql: str, references: tuple[CompileSqlReference, ...]) -> str:
    """Return authored SQL with lineage relation markers replaced by their stub positions."""

    positions: dict[str, int] = {
        name: index for index, name in enumerate(lineage_reference_map(references))
    }

    def marker(match: re.Match[str]) -> str:
        position: int | None = positions.get(match.group(2))
        if position is None or match.group(1) == COMPACT_UNSTUBBED_REFERENCE_KIND:
            return match.group(0)
        return f"{COMPACT_RELATION_STUB_PREFIX}{position}"

    return COMPACT_REFERENCE_MARKER_PATTERN.sub(marker, query_sql)


def shareable_binding_prekeys(*, requests: Sequence[ModelSqlAnalysisRequest]) -> frozenset[str]:
    """Return binding pre-keys shared by at least two binding requests of a compile."""

    counts: Counter[str] = Counter(
        binding_share_prekey(query_sql=request.query_sql, references=request.model_input.references)
        for request in requests
        if request.binding_schema is not None
    )
    return frozenset(
        prekey for prekey, count in counts.items() if count >= MIN_SHARED_BINDING_QUERY_MEMBERS
    )


def prepare_binding_queries(
    *,
    binding_catalog: Any,
    inputs: CompactBatchInputs,
    cleaned_sqls: list[str],
    share: bool,
    shareable_prekeys: frozenset[str] | None,
) -> tuple[PreparedBindingQuery | None, ...]:
    """Prepare binding references in catalog order, with shared forms where keys can match."""

    binding_schemas: tuple[dict[str, dict[str, str]] | None, ...] = inputs.binding_schemas or ()
    dialect: str | None = inputs.inference_profile.sql_analysis_dialect
    prekeys: list[str | None] = [
        binding_share_prekey(query_sql=query_sql, references=query_references)
        if share and binding_schema is not None
        else None
        for query_sql, query_references, binding_schema in zip(
            inputs.query_sqls, inputs.references, binding_schemas, strict=True
        )
    ]
    candidates: frozenset[str] = (
        shareable_prekeys
        if shareable_prekeys is not None
        else frozenset(
            prekey
            for prekey, count in Counter(prekeys).items()
            if prekey is not None and count >= MIN_SHARED_BINDING_QUERY_MEMBERS
        )
    )
    prepared: list[PreparedBindingQuery | None] = []
    for index, binding_schema in enumerate(binding_schemas):
        if binding_schema is None:
            prepared.append(None)
            continue
        _, binding_references, overrides = binding_catalog.prepare(
            [
                SqlSchemaValidationRequest(
                    sql=cleaned_sqls[index], dialect=dialect, schema=binding_schema
                )
            ]
        )[0]
        prekey: str | None = prekeys[index]
        shared: SharedBindingQuery | None = None
        if prekey is not None and prekey in candidates:
            shared = _shared_binding_query(
                binding_catalog=binding_catalog,
                query=SqlSchemaValidationRequest(
                    sql=inputs.query_sqls[index], dialect=dialect, schema=binding_schema
                ),
                cleaned_sql=cleaned_sqls[index],
                references=inputs.references[index],
                placeholders=inputs.placeholders[index],
                overrides=overrides,
            )
        prepared.append(
            PreparedBindingQuery(references=binding_references, overrides=overrides, shared=shared)
        )
    if shareable_prekeys is not None:
        return tuple(prepared)
    counts: Counter[tuple[object, ...]] = Counter(
        query.shared.key for query in prepared if query is not None and query.shared is not None
    )
    return tuple(
        (
            PreparedBindingQuery(references=query.references, overrides=query.overrides)
            if query is not None
            and query.shared is not None
            and counts[query.shared.key] < MIN_SHARED_BINDING_QUERY_MEMBERS
            else query
        )
        for query in prepared
    )


def binding_query_fields(
    *,
    binding_query: PreparedBindingQuery,
    binding_catalog: Any,
) -> tuple[dict[str, object], dict[str, object]]:
    """Return native binding query fields and their identity payload."""

    binding_references: list[tuple[str, bool]] = binding_query.references
    fields: dict[str, object] = {}
    shared: SharedBindingQuery | None = binding_query.shared
    if shared is not None:
        stubs: dict[str, str] = shared.stubs
        binding_references = sorted(
            binding_references, key=lambda reference: stubs.get(reference[0], reference[0])
        )
        fields["binding_aliases"] = {
            name: stubs[name] for name, _ in binding_references if name in stubs
        }
    binding_payload: dict[str, object] = {"references": binding_references}
    fields["binding_references"] = binding_references
    if binding_query.overrides:
        override_id: int = binding_catalog.native.register_override(binding_query.overrides)
        fields["binding_override"] = override_id
        binding_payload["override"] = override_id
    return fields, binding_payload


def shared_result_is_exact(*, validation: object, template: object) -> bool:
    """Only a successful analysis without diagnostics is independent of relation names."""

    if isinstance(template, str):
        return False
    if validation is None:
        return True
    return isinstance(validation, dict) and cast(dict[str, object], validation).get("errors") == []


def relation_stubs_collide(*, cleaned_sql: str, names: Iterable[str]) -> bool:
    """Return whether authored SQL or relation names already use the relation stub prefix."""

    return (
        any(name.startswith(COMPACT_RELATION_STUB_PREFIX) for name in names)
        or COMPACT_RELATION_STUB_PREFIX.casefold() in cleaned_sql.casefold()
    )


def _shared_reference_names(
    *,
    cleaned_sql: str,
    references: tuple[CompileSqlReference, ...],
    binding_schema: Mapping[str, Mapping[str, str]],
) -> list[str] | None:
    names: list[str] = list(lineage_reference_map(references))
    if not names or len({name.casefold() for name in names}) != len(names):
        return None
    if relation_stubs_collide(cleaned_sql=cleaned_sql, names=names):
        return None
    if SQL_QUOTED_IDENTIFIER_DELIMITER in cleaned_sql:
        return None
    for relation, columns in binding_schema.items():
        if (
            SQL_QUOTED_IDENTIFIER_DELIMITER in relation
            or SQL_QUOTED_IDENTIFIER_DELIMITER in "".join(columns)
        ):
            return None
    if _qualified_reference_names(query_sql=cleaned_sql, reference_names=names):
        return None
    return names


def _shared_binding_query(
    *,
    binding_catalog: Any,
    query: SqlSchemaValidationRequest,
    cleaned_sql: str,
    references: tuple[CompileSqlReference, ...],
    placeholders: dict[str, str] | None,
    overrides: Mapping[str, Mapping[str, str]],
) -> SharedBindingQuery | None:
    names: list[str] | None = _shared_reference_names(
        cleaned_sql=cleaned_sql, references=references, binding_schema=query.schema
    )
    if names is None:
        return None
    stubs: dict[str, str] = {
        name: f"{COMPACT_RELATION_STUB_PREFIX}{index}" for index, name in enumerate(names)
    }
    sql: str = normalize_analysis_sql(
        sql=query.sql, dialect=query.dialect, stubs=stubs, placeholders=placeholders
    )
    analysis_shapes: list[tuple[object, ...]] = []
    for name in names:
        types, nullability = binding_catalog.analysis_shapes.get(name, ({}, {}))
        analysis_shapes.append((stubs[name], tuple(types.items()), tuple(nullability.items())))
    binding_shapes: list[tuple[object, ...]] = []
    for relation, columns in query.schema.items():
        effective: Mapping[str, str] = (
            overrides[relation]
            if relation in overrides
            else binding_catalog.schemas[relation]
            if columns
            else {}
        )
        binding_shapes.append(
            (stubs.get(relation, relation), bool(columns), tuple(effective.items()))
        )
    return SharedBindingQuery(
        sql=sql,
        stubs=stubs,
        key=(
            sql,
            query.dialect or "generic",
            tuple(analysis_shapes),
            tuple(sorted(binding_shapes)),
        ),
    )


def shared_result_keys(
    *, inputs: CompactBatchInputs, context: CompactBatchContext
) -> tuple[tuple[object, ...] | None, ...]:
    """Identify each shared member's complete native input, including its template."""

    function_return_types: tuple[tuple[str, str], ...] = tuple(
        inputs.inference_profile.function_return_types.items()
    )
    keys: list[tuple[object, ...] | None] = []
    for index, binding_query in enumerate(context.binding_queries):
        shared: SharedBindingQuery | None = (
            binding_query.shared if binding_query is not None else None
        )
        if shared is None:
            keys.append(None)
            continue
        query_references: tuple[CompileSqlReference, ...] = inputs.references[index]
        declared_column_order: tuple[str, ...] = (
            tuple(
                inputs.column_nullability_by_table.get(
                    _analysis_reference_name(query_references[0]), {}
                )
            )
            if len(query_references) == 1
            else ()
        )
        reference_types: tuple[tuple[str, str], ...] = tuple(
            (shared.stubs[name], resource_type.value)
            for name, (resource_type, _) in lineage_reference_map(query_references).items()
        )
        keys.append(
            (
                shared.key,
                inputs.recover_cte_facts[index],
                inputs.rich_type_inference,
                function_return_types,
                declared_column_order,
                reference_types,
            )
        )
    return tuple(keys)


def reused_shared_results(
    *,
    inputs: CompactBatchInputs,
    context: CompactBatchContext,
    keys: tuple[tuple[object, ...] | None, ...],
    memo: dict[object, object],
) -> dict[int, NativeCompactAnalysis]:
    """Project remembered exact shared results onto members with the same key."""

    reused: dict[int, NativeCompactAnalysis] = {}
    for index, key in enumerate(keys):
        representative: object = memo.get(key) if key is not None else None
        binding_query: PreparedBindingQuery | None = context.binding_queries[index]
        if not isinstance(representative, NativeCompactAnalysis) or binding_query is None:
            continue
        shared: SharedBindingQuery | None = binding_query.shared
        if shared is None:
            continue
        resource_names_by_stub: dict[str, str] = {
            shared.stubs[name]: resource_name
            for name, (_, resource_name) in lineage_reference_map(inputs.references[index]).items()
        }
        resource_names: dict[int, str] = {}
        for canonical_index in representative.resource_name_indexes:
            resource_name: str | None = resource_names_by_stub.get(
                representative.string_pool[canonical_index]
            )
            if resource_name is None:
                break
            resource_names[canonical_index] = resource_name
        else:
            reused[index] = replace(
                representative,
                cleaned_sql=context.normalized_sqls[index],
                resource_names=resource_names,
            )
    return reused


def remembered_shared_results(
    *,
    keys: tuple[tuple[object, ...] | None, ...],
    results: tuple[NativeCompactAnalysis, ...],
) -> dict[object, NativeCompactAnalysis]:
    """Select exact, fully projected shared results to remember for later batches."""

    remembered: dict[object, NativeCompactAnalysis] = {}
    for key, result in zip(keys, results, strict=True):
        if (
            key is not None
            and key not in remembered
            and result.projected
            and result.analysis is not None
            and result.compact_rows is not None
        ):
            remembered[key] = result
    return remembered

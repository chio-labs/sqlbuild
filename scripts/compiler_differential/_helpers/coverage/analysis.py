"""Classify `CompiledProject` captures into analysis kinds; only analysed evidence counts."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator
from pathlib import Path

from scripts.compiler_differential._helpers.comparing.compare import as_json_object
from scripts.compiler_differential._helpers.coverage.capture_values import (
    capture_problems,
    enum_name,
    has_content,
    records,
)
from scripts.compiler_differential.classes.capture_file import expand_capture_text
from scripts.compiler_differential.constants import (
    ANALYSIS_CALLABLE_CAPTURE_FIELDS,
    ANALYSIS_DETAIL_KINDS,
    ANALYSIS_EXPLICIT_WRITE_SCHEMA_DIALECTS,
    ANALYSIS_NON_COLLECTION_FIELDS,
    ANALYSIS_OPAQUE_CAPTURE_VALUES,
    ANALYSIS_STAGE_CAPTURE_SUFFIX,
    ANALYSIS_UPSTREAM_CHAIN_HOPS,
    COMPILED_PROJECT_CAPTURE_TYPE,
)
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.frontier.constants import STAGE_CAPTURE_OMITTED_ATTRIBUTES

_SET_OPERATION: re.Pattern[str] = re.compile(r"\b(?:UNION|INTERSECT|EXCEPT)\b", re.IGNORECASE)
_LEADING_CTE: re.Pattern[str] = re.compile(r"^\s*WITH\s+\w+\s+AS\s*\(", re.IGNORECASE)
_QUOTED_IDENTIFIER: re.Pattern[str] = re.compile(r'"([^"]+)"')
_SIZED_TYPE: re.Pattern[str] = re.compile(r"\((\d+)\)\s*$")
_RUNTIME_PLACEHOLDER: re.Pattern[str] = re.compile(r"@@@([A-Za-z_]\w*)")
_CURSOR_INTRINSIC: str = "__cursor_start()"
_HOOK_KEYS: tuple[str, ...] = ("pre_hooks", "post_hooks")
_EXPECTED_CTE_PREFIX: str = "__expected__"
_SQL_HOOK_TYPE: str = "SqlHookEntry"
_NON_NULL: str = "non_null"
_ENFORCED: str = "enforced"
_TABLE: str = "table"
_INCREMENTAL: str = "incremental"
_STAGED: str = "staged"
_MODEL_REFERENCE: str = "ref"
_SOURCE_REFERENCE: str = "source"
_SEED_REFERENCE: str = "seed"
_UDF_REFERENCE: str = "udf"
_TABLE_FUNCTION_REFERENCE: str = "table_function"
_AUDIT_KINDS: dict[str, str] = {
    "accepted_values": "accepted_values_audit",
    "relationships": "relationships_audit",
    "expression_is_true": "expression_audit",
}
_METADATA_COLUMN_KEYS: tuple[str, ...] = ("unique_key", "cursor", "partition_column")


@dataclasses.dataclass(frozen=True)
class _Project:
    """The parts of one `CompiledProject` capture the analysis kinds read."""

    capture: dict[str, object]
    models: dict[str, dict[str, object]]
    sources: dict[str, dict[str, object]]
    seeds: dict[str, dict[str, object]]
    functions: dict[str, dict[str, object]]


def required_analysis_kinds() -> tuple[str, ...]:
    """Return every `CompiledProject` collection field plus the finer required kinds."""

    return (*analysis_collection_kinds(), *ANALYSIS_DETAIL_KINDS)


def analysis_collection_kinds() -> tuple[str, ...]:
    """Return the `CompiledProject` fields that hold compiled resources or facts."""

    return tuple(
        field.name
        for field in dataclasses.fields(CompiledProject)
        if field.name not in ANALYSIS_NON_COLLECTION_FIELDS
    )


def project_analysis_kinds(captures: dict[str, dict[str, Path]]) -> frozenset[str]:
    """Return the analysis kinds every `CompiledProject` capture of one project proves."""

    kinds: set[str] = set()
    for files in captures.values():
        for name, path in files.items():
            if name.endswith(ANALYSIS_STAGE_CAPTURE_SUFFIX):
                kinds.update(analysed_input_kinds(path.read_text(encoding="utf-8")))
    return frozenset(kinds)


def analysis_capture_problems(capture_text: str) -> tuple[str, ...]:
    """Return why a compiled-project capture is unsound; the catalog's native handle is allowed."""

    return capture_problems(
        capture_text=ANALYSIS_OPAQUE_CAPTURE_VALUES.sub("null", capture_text),
        fields=tuple(
            field.name
            for field in dataclasses.fields(CompiledProject)
            if field.name not in _omitted_fields()
        ),
        callable_fields=ANALYSIS_CALLABLE_CAPTURE_FIELDS,
    )


def analysed_input_kinds(capture_text: str) -> frozenset[str]:
    """Return the analysis input kinds one canonical `CompiledProject` capture proves."""

    capture: dict[str, object] = as_json_object(expand_capture_text(capture_text)) or {}
    project: _Project = _Project(
        capture=capture,
        models=_by_name(capture.get("models")),
        sources={
            str((as_json_object(source.get("source_entry")) or {}).get("name")): source
            for source in records(capture.get("sources"))
        },
        seeds=_by_name(capture.get("seeds")),
        functions=_by_name(capture.get("functions")),
    )
    kinds: set[str] = {
        kind for kind in analysis_collection_kinds() if has_content(capture.get(kind))
    }
    kinds.update(_inference_kinds(project))
    kinds.update(_binding_path_kinds(project))
    kinds.update(_shape_publication_kinds(project))
    kinds.update(_input_resource_kinds(project))
    kinds.update(_configuration_kinds(project))
    kinds.update(_metadata_kinds(project))
    kinds.update(_attachment_kinds(project))
    dialect: object = capture.get("sql_analysis_dialect")
    if isinstance(dialect, str) and any(_analysed(model) for model in project.models.values()):
        kinds.add(f"dialect_{dialect}")
    return frozenset(kinds)


def _omitted_fields() -> frozenset[str]:
    return STAGE_CAPTURE_OMITTED_ATTRIBUTES.get(COMPILED_PROJECT_CAPTURE_TYPE, frozenset())


def _by_name(value: object) -> dict[str, dict[str, object]]:
    return {str(record.get("name")): record for record in records(value)}


def _analysed(model: dict[str, object]) -> bool:
    """Whether binding validation ran on the model's SQL."""

    return model.get("binding_validated") is True


def _columns(model: dict[str, object]) -> list[dict[str, object]]:
    return records(model.get("inferred_columns"))


def _values(resource: dict[str, object]) -> dict[str, object]:
    return as_json_object((as_json_object(resource.get("config")) or {}).get("values")) or {}


def _references(model: dict[str, object]) -> Iterator[tuple[str, str]]:
    for reference in records(model.get("references")):
        yield str(enum_name(reference.get("ref_kind"))), str(reference.get("ref_name"))


def _referenced(*, model: dict[str, object], kind: str) -> list[str]:
    return [name for ref_kind, name in _references(model) if ref_kind == kind]


def _contract_enforced(model: dict[str, object]) -> bool:
    return _values(model).get("contract") == _ENFORCED


def _schema_columns(resource: dict[str, object]) -> list[dict[str, object]]:
    return records((as_json_object(resource.get("schema_entry")) or {}).get("columns"))


def _nullability(column: dict[str, object]) -> str | None:
    return enum_name(column.get("nullability"))


def _inference_kinds(project: _Project) -> set[str]:
    kinds: set[str] = set()
    for model in project.models.values():
        if not _analysed(model):
            continue
        columns: list[dict[str, object]] = _columns(model)
        if any(column.get("type") is not None for column in columns):
            kinds.add("typed_column")
        if any(column.get("type") is None for column in columns):
            kinds.add("untyped_column")
        upstream_models: list[str] = [
            name
            for name in _referenced(model=model, kind=_MODEL_REFERENCE)
            if name in project.models
        ]
        if model.get("fast_lineage_has_star") is True:
            if model.get("fast_lineage_star_resolved") is not True:
                if model.get("dynamic_column_contract") is None:
                    kinds.add("star_unresolved")
            elif upstream_models:
                kinds.add("star_over_published_shape")
            else:
                kinds.add("star_over_complete_input")
        query: str = str(model.get("query_sql", ""))
        if _SET_OPERATION.search(query) and upstream_models and columns:
            kinds.add("set_operation")
        if _LEADING_CTE.search(query) and columns:
            kinds.add("cte")
            if _passes_cte_type_through(project=project, model=model, upstream=upstream_models):
                kinds.add("cte_passthrough_type")
        if _QUOTED_IDENTIFIER.search(query) and _quoted_case_folded(
            project=project, model=model, upstream=upstream_models
        ):
            kinds.add("quoted_identifier_case")
        proof: dict[str, object] = as_json_object(model.get("dynamic_column_contract")) or {}
        if proof.get("output_proven") is True and records(proof.get("families")):
            kinds.add("dynamic_column_proof")
        values: dict[str, object] = _values(model)
        if (
            _CURSOR_INTRINSIC in query
            and values.get("materialized") == _INCREMENTAL
            and values.get("cursor") is not None
        ):
            kinds.add("cursor_intrinsic")
        placeholders: set[str] = set(_RUNTIME_PLACEHOLDER.findall(query))
        defaults: dict[str, object] = as_json_object(values.get("placeholders")) or {}
        if placeholders and placeholders <= set(defaults):
            kinds.add("runtime_placeholder")
    return kinds


def _passes_cte_type_through(
    *, project: _Project, model: dict[str, object], upstream: list[str]
) -> bool:
    """Whether a CTE model keeps an upstream column's exact inferred type."""

    upstream_types: set[tuple[str, str]] = set().union(
        *(_typed_columns(project.models[name]) for name in upstream)
    )
    return bool(_typed_columns(model) & upstream_types)


def _typed_columns(model: dict[str, object]) -> set[tuple[str, str]]:
    """Return the model's `(name, type)` pairs for every inferred column with a type."""

    return {
        (str(column.get("name")), str(column.get("type")))
        for column in _columns(model)
        if column.get("type") is not None
    }


def _quoted_case_folded(
    *, project: _Project, model: dict[str, object], upstream: list[str]
) -> bool:
    """Whether a quoted identifier bound to an upstream column only by ignoring its case."""

    names: set[str] = set().union(*(_column_names_of(project.models[name]) for name in upstream))
    folded: set[str] = {name.casefold() for name in names}
    return not records(model.get("binding_diagnostics")) and any(
        quoted not in names and quoted.casefold() in folded
        for quoted in _QUOTED_IDENTIFIER.findall(str(model.get("query_sql", "")))
    )


def _column_names_of(model: dict[str, object]) -> set[str]:
    return {str(column.get("name")) for column in _columns(model)}


def _binding_path_kinds(project: _Project) -> set[str]:
    """Distinguish the dependency-ordered binding dataflow from the one-batch path."""

    kinds: set[str] = set()
    analysed: list[dict[str, object]] = [
        model for model in project.models.values() if _analysed(model)
    ]
    complete: list[bool] = [
        _reads_complete_inputs(project=project, model=model) for model in analysed
    ]
    if analysed and all(complete):
        kinds.add("batch_binding")
    if not all(complete):
        kinds.add("dataflow_binding")
    analysable: list[dict[str, object]] = [
        model
        for model in project.models.values()
        if _values(model).get("sql_analysis") is not False and records(model.get("references"))
    ]
    if analysed and any(
        model.get("inferred_columns") is None and not _analysed(model) for model in analysable
    ):
        kinds.add("select_limited_analysis")
    if (
        project.models
        and not analysed
        and all(
            model.get("inferred_columns") is None
            for model in analysable
            if model.get("dynamic_column_contract") is None
        )
    ):
        kinds.add("sql_analysis_disabled")
    if _longest_analysed_chain(project) >= ANALYSIS_UPSTREAM_CHAIN_HOPS:
        kinds.add("upstream_chain")
    return kinds


def _reads_complete_inputs(*, project: _Project, model: dict[str, object]) -> bool:
    """Whether every relation the model reads has a schema known before any model is analysed."""

    for kind, name in _references(model):
        if kind == _MODEL_REFERENCE:
            upstream: dict[str, object] | None = project.models.get(name)
            if upstream is None or not (_contract_enforced(upstream) and _schema_columns(upstream)):
                return False
        elif kind == _SOURCE_REFERENCE:
            entry: dict[str, object] = (
                as_json_object((project.sources.get(name) or {}).get("source_entry")) or {}
            )
            if not entry.get("expression") and not (
                entry.get("contract") == _ENFORCED and records(entry.get("columns"))
            ):
                return False
        elif kind == _SEED_REFERENCE:
            if not _schema_columns(project.seeds.get(name) or {}):
                return False
        elif kind == _TABLE_FUNCTION_REFERENCE:
            if not records((project.functions.get(name) or {}).get("return_columns")):
                return False
    return True


def _longest_analysed_chain(project: _Project) -> int:
    """Return the most model-to-model hops along analysed models, ignoring reference cycles."""

    hops: dict[str, int] = dict.fromkeys(
        (name for name, model in project.models.items() if _analysed(model)), 0
    )
    for _ in range(len(hops)):
        hops = {name: _upstream_hops(project=project, name=name, hops=hops) for name in hops}
    return max(hops.values(), default=0)


def _upstream_hops(*, project: _Project, name: str, hops: dict[str, int]) -> int:
    """Return one more hop than the deepest analysed upstream model, capped by the model count."""

    upstream: list[int] = [
        hops[upstream_name]
        for upstream_name in _referenced(model=project.models[name], kind=_MODEL_REFERENCE)
        if upstream_name in hops
    ]
    return min(max(upstream, default=-1) + 1, len(hops))


def _shape_publication_kinds(project: _Project) -> set[str]:
    """Prove a contract's declared types and nullability reached a downstream model's shape."""

    kinds: set[str] = set()
    for model in project.models.values():
        if not _analysed(model):
            continue
        downstream: dict[str, dict[str, object]] = {
            str(column.get("name")): column for column in _columns(model)
        }
        for name in _referenced(model=model, kind=_MODEL_REFERENCE):
            upstream: dict[str, object] | None = project.models.get(name)
            if upstream is None or not _contract_enforced(upstream):
                continue
            inferred: dict[str, dict[str, object]] = {
                str(column.get("name")): column for column in _columns(upstream)
            }
            for declared in _schema_columns(upstream):
                column_name: str = str(declared.get("name"))
                published: dict[str, object] | None = downstream.get(column_name)
                if published is None:
                    continue
                size: re.Match[str] | None = _SIZED_TYPE.search(str(declared.get("type") or ""))
                published_size: re.Match[str] | None = _SIZED_TYPE.search(
                    str(published.get("type") or "")
                )
                if size and published_size and size.group(1) == published_size.group(1):
                    kinds.add("sized_contract_shape")
                if (
                    declared.get("nullable") is False
                    and _nullability(published) == _NON_NULL
                    and _nullability(inferred.get(column_name) or {}) != _NON_NULL
                ):
                    kinds.add("contract_nullability_shape")
    return kinds


def _input_resource_kinds(project: _Project) -> set[str]:
    kinds: set[str] = set()
    expression_shapes: object = (as_json_object(project.capture.get("binding_catalog")) or {}).get(
        "expression_shapes"
    )
    for model in project.models.values():
        if not _analysed(model):
            continue
        for kind, name in _references(model):
            if kind == _SOURCE_REFERENCE and has_content(expression_shapes):
                entry: dict[str, object] = (
                    as_json_object((project.sources.get(name) or {}).get("source_entry")) or {}
                )
                if entry.get("expression"):
                    kinds.add("source_expression_shape")
            elif kind == _SEED_REFERENCE and any(
                column.get("type") for column in _schema_columns(project.seeds.get(name) or {})
            ):
                kinds.add("seed_column_types")
            elif kind in (_UDF_REFERENCE, _TABLE_FUNCTION_REFERENCE):
                kinds.update(_function_kinds(function=project.functions.get(name), kind=kind))
    return kinds


def _function_kinds(*, function: dict[str, object] | None, kind: str) -> set[str]:
    if function is None:
        return set()
    arguments: list[dict[str, object]] = records(function.get("arguments"))
    kinds: set[str] = set()
    if arguments and all(argument.get("type") for argument in arguments):
        kinds.add("udf_argument_types")
    if kind == _TABLE_FUNCTION_REFERENCE and records(function.get("return_columns")):
        kinds.add("table_function")
    elif kind == _UDF_REFERENCE and function.get("returns"):
        kinds.add("scalar_udf")
    return kinds


def _configuration_kinds(project: _Project) -> set[str]:
    kinds: set[str] = set()
    settings: dict[str, object] = as_json_object(project.capture.get("settings")) or {}
    for model in project.models.values():
        values: dict[str, object] = _values(model)
        if (
            settings.get("require_sql_analysis") is True
            and values.get("sql_analysis") is False
            and model.get("inferred_columns") is None
            and model.get("rejected_sql_analysis_opt_out") is None
        ):
            kinds.add("sql_analysis_opt_out")
        for key in _HOOK_KEYS:
            hooks: list[dict[str, object]] = [
                hook
                for hook in records(values.get(key))
                if str(hook.get("__type__", "")).endswith(_SQL_HOOK_TYPE)
            ]
            kinds.update(
                "named_sql_hook" if hook.get("definition_sql") else "inline_sql_hook"
                for hook in hooks
            )
            if len(hooks) > 1:
                kinds.add("hook_list")
        if (
            settings.get("table_promotion_mode") == _STAGED
            and _contract_enforced(model)
            and values.get("materialized", _TABLE) == _TABLE
        ):
            kinds.add("explicit_promotion_mode")
    if project.capture.get("enforce_explicit_references") is True and has_content(
        project.capture.get("unmatched_literal_sql_relations")
    ):
        kinds.add("python_sql_literal_relation")
    destinations: list[dict[str, object]] = [
        as_json_object(resource.get("destination")) or {}
        for resource in (*project.models.values(), *project.seeds.values())
    ]
    if (
        str(project.capture.get("sql_analysis_dialect")) in ANALYSIS_EXPLICIT_WRITE_SCHEMA_DIALECTS
        and destinations
        and all(destination.get("schema") for destination in destinations)
    ):
        kinds.add("managed_write_schema")
    return kinds


def _metadata_kinds(project: _Project) -> set[str]:
    kinds: set[str] = set()
    for model in project.models.values():
        if not _analysed(model):
            continue
        entry: dict[str, object] = as_json_object(model.get("schema_entry")) or {}
        audits: list[dict[str, object]] = records(entry.get("audits"))
        for column in records(entry.get("columns")):
            audits.extend(records(column.get("audits")))
        kinds.update(
            _AUDIT_KINDS[name]
            for audit in audits
            if (name := str(audit.get("definition_name"))) in _AUDIT_KINDS
        )
        values: dict[str, object] = _values(model)
        output: set[str] = {str(column.get("name")).casefold() for column in _columns(model)}
        if any(
            (names := _column_names(values.get(key))) and names <= output
            for key in _METADATA_COLUMN_KEYS
        ):
            kinds.add("metadata_column_reference")
    return kinds


def _column_names(value: object) -> set[str]:
    """Return the case-folded column names a metadata key such as `unique_key` names."""

    if isinstance(value, str):
        return {value.casefold()}
    if isinstance(value, list):
        return {str(name).casefold() for name in value}
    return set()


def _attachment_kinds(project: _Project) -> set[str]:
    kinds: set[str] = set()
    for test in records(project.capture.get("sql_tests")):
        payload: dict[str, object] = as_json_object(test.get("payload")) or {}
        expected: list[str] = [
            str(cte.get("name", "")).removeprefix(_EXPECTED_CTE_PREFIX)
            for cte in records(payload.get("expected_ctes"))
        ]
        if any(_analysed(project.models.get(name) or {}) for name in expected):
            kinds.add("sql_test_expected_columns")
        mocks: list[str] = [
            str(mock) for mock in (as_json_object(payload.get("macro_mocks")) or {}).values()
        ]
        overrides: dict[str, object] = as_json_object(payload.get("model_query_overrides")) or {}
        if any(
            _mock_rendered(project=project, mocks=mocks, name=name, override=str(override))
            for name, override in overrides.items()
        ):
            kinds.add("sql_test_macro_mock")
    return kinds


def _mock_rendered(*, project: _Project, mocks: list[str], name: str, override: str) -> bool:
    """Whether a test's re-expanded query holds a mocked macro value the model's own SQL lacks."""

    compiled: str = str((project.models.get(name) or {}).get("query_sql", ""))
    return any(mock in override and mock not in compiled for mock in mocks)

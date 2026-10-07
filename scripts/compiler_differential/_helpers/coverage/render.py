"""Classify `CompileProjectInputs` captures into render kinds; only rendered evidence counts."""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Iterator
from pathlib import PurePosixPath

from scripts.compiler_differential._helpers.comparing.compare import as_json_object
from scripts.compiler_differential._helpers.coverage.capture_values import (
    capture_problems,
    enum_name,
    has_content,
    mapping_records,
    records,
)
from scripts.compiler_differential._helpers.coverage.macro_sources import (
    macro_function_source,
    takes_typed_reference,
)
from scripts.compiler_differential.constants import (
    RENDER_CALLABLE_CAPTURE_FIELDS,
    RENDER_DETAIL_KINDS,
    RENDER_HOOK_KEYS,
    RENDER_MACRO_SOURCE_READS,
    RENDER_NON_COLLECTION_FIELDS,
    RENDER_STAGE_CAPTURE_SUFFIX,
)
from sqlbuild.compiler.auditing.constants import BUILT_IN_AUDIT_NAMES
from sqlbuild.compiler.compile.models import CompileProjectInputs

_MACRO_CALL: re.Pattern[str] = re.compile(r"@([A-Za-z_]\w*)\(")
_REFERENCE_CALL: re.Pattern[str] = re.compile(r"__(ref|source|seed)\(\s*\"([^\"]+)\"\s*\)")
_PROJECT_VARIABLE: re.Pattern[str] = re.compile(r"(?<!@)@@(?!@)(?!ENV:|CTX:)[A-Za-z_]")
_ENVIRONMENT_VARIABLE: str = "@@ENV:"
_CONTEXT_VARIABLE: str = "@@CTX:"
_RUNTIME_PLACEHOLDER: re.Pattern[str] = re.compile(r"@@@([A-Za-z_]\w*)")
_CURSOR_INTRINSIC: str = "__cursor_start()"
_TEMPLATE_ARGUMENT: re.Pattern[str] = re.compile(r"(?<!@)@'?[A-Za-z_]\w*'?(?!\w|\()")
_PLACEHOLDERS_KEY: str = "placeholders"
_MATERIALIZED_KEY: str = "materialized"
_INCREMENTAL: str = "incremental"
_CURSOR_KEY: str = "cursor"
_IMPLICIT_AUDIT_ARGUMENT: str = "column"
_PYTHON_HOOK_TYPE: str = "PythonHookEntry"
_MACRO_DECLARATION: str = "macro"
_ENUM_DECLARATION: str = "enum"
_CONSTANT_DECLARATION: str = "constant"
_LIST_VALUE: str = "list"
_MODEL_RESOURCE: str = "model"
_CONSUMER_COLLECTIONS: dict[str, str] = {
    "test_inputs": "test",
    "scenario_inputs": "scenario",
    "audit_inputs": "audit",
    "sql_function_inputs": "function",
    "source_inputs": "source_expression",
}
_REFERENCE_COLLECTIONS: tuple[str, ...] = ("model_inputs", "sql_function_inputs", "audit_inputs")
_RELATION_REFERENCE_KINDS: frozenset[str] = frozenset({"ref", "source", "seed"})


def required_render_kinds() -> tuple[str, ...]:
    """Return every `CompileProjectInputs` collection field plus the finer required kinds."""

    return (*render_collection_kinds(), *RENDER_DETAIL_KINDS)


def render_collection_kinds() -> tuple[str, ...]:
    """Return the `CompileProjectInputs` fields that hold rendered inputs."""

    return tuple(
        field.name
        for field in dataclasses.fields(CompileProjectInputs)
        if field.name not in RENDER_NON_COLLECTION_FIELDS
    )


def project_render_kinds(captures: dict[str, dict[str, str]]) -> frozenset[str]:
    """Return the render kinds every `CompileProjectInputs` capture of one project proves."""

    kinds: set[str] = set()
    for files in captures.values():
        for name, text in files.items():
            if name.endswith(RENDER_STAGE_CAPTURE_SUFFIX):
                kinds.update(rendered_input_kinds(text))
    return frozenset(kinds)


def render_capture_problems(capture_text: str) -> tuple[str, ...]:
    """Return why a render capture is incomplete or not canonical; empty when it is sound."""

    return capture_problems(
        capture_text=capture_text,
        fields=tuple(field.name for field in dataclasses.fields(CompileProjectInputs)),
        callable_fields=RENDER_CALLABLE_CAPTURE_FIELDS,
    )


def rendered_input_kinds(capture_text: str) -> frozenset[str]:
    """Return the render input kinds one canonical `CompileProjectInputs` capture proves."""

    capture: dict[str, object] = as_json_object(json.loads(capture_text)) or {}
    kinds: set[str] = {kind for kind in render_collection_kinds() if has_content(capture.get(kind))}
    usages: list[tuple[str, dict[str, object]]] = list(_usages(capture))
    kinds.update(_macro_kinds(capture=capture, usages=usages))
    kinds.update(_declaration_kinds(capture=capture, usages=usages))
    kinds.update(_interpolation_kinds(capture))
    kinds.update(_hook_kinds(capture))
    kinds.update(_reference_kinds(capture))
    kinds.update(_attachment_kinds(capture))
    return frozenset(kinds)


def _usages(capture: dict[str, object]) -> Iterator[tuple[str, dict[str, object]]]:
    """Yield `(consumer collection label, usage)` for every recorded declaration usage."""

    for model in records(capture.get("model_inputs")):
        for field in ("macro_usages", "declaration_usages"):
            yield from ((_MODEL_RESOURCE, usage) for usage in records(model.get(field)))
    for collection, label in _CONSUMER_COLLECTIONS.items():
        for item in records(capture.get(collection)):
            yield from ((label, usage) for usage in records(item.get("declaration_usages")))


def _declaration_kind(usage: dict[str, object]) -> str | None:
    return enum_name((as_json_object(usage.get("declaration")) or {}).get("kind"))


def _macro_kinds(
    *, capture: dict[str, object], usages: list[tuple[str, dict[str, object]]]
) -> set[str]:
    kinds: set[str] = set()
    used_macros: set[str] = set()
    for consumer, usage in usages:
        if _declaration_kind(usage) != _MACRO_DECLARATION:
            continue
        used_macros.add(str((as_json_object(usage.get("declaration")) or {}).get("name")))
        kinds.add(f"macro_in_{consumer}")
    typed_macros: set[str] = set()
    for macro in mapping_records(capture.get("loaded_macros")):
        name: str = str(macro.get("name"))
        file_source: str = str(macro.get("raw_source", ""))
        if takes_typed_reference(file_source=file_source, name=name):
            typed_macros.add(name)
        if name not in used_macros:
            continue
        if records(macro.get("dependencies")):
            kinds.add("cross_file_macro_import")
        kinds.update(_macro_source_reads(macro_function_source(file_source=file_source, name=name)))
    for model in records(capture.get("model_inputs")):
        kinds.update(_model_macro_kinds(model=model, typed_macros=typed_macros))
    for test in records(capture.get("test_inputs")):
        if enum_name(test.get("mode")) == _MACRO_DECLARATION and any(
            _declaration_kind(usage) == _MACRO_DECLARATION
            for usage in records(test.get("declaration_usages"))
        ):
            kinds.add("tested_macro")
    return kinds


def _macro_source_reads(source: str) -> set[str]:
    kinds: set[str] = set()
    for kind, markers in RENDER_MACRO_SOURCE_READS.items():
        if any(marker in source for marker in markers):
            kinds.add(kind)
    return kinds


def _model_macro_kinds(*, model: dict[str, object], typed_macros: set[str]) -> set[str]:
    kinds: set[str] = set()
    authored: str = str(model.get("macro_source_sql", ""))
    rendered: str = str(model.get("query_sql", ""))
    calls: list[tuple[str, str]] = list(_macro_calls(authored))
    if not calls or _MACRO_CALL.search(rendered):
        return kinds
    if any(_MACRO_CALL.search(arguments) for _, arguments in calls):
        kinds.add("nested_macro_call")
    referenced: set[tuple[str, str]] = {
        (str(enum_name(reference.get("ref_kind"))), str(reference.get("ref_name")))
        for reference in records(model.get("references"))
    }
    passed: set[tuple[str, str]] = set()
    for name, arguments in calls:
        if name in typed_macros:
            passed.update(_REFERENCE_CALL.findall(arguments))
    if passed and passed <= referenced:
        kinds.add("typed_reference_argument")
    written: set[tuple[str, str]] = set(_REFERENCE_CALL.findall(authored))
    if {item for item in referenced if item[0] in _RELATION_REFERENCE_KINDS} - written:
        kinds.add("macro_generated_reference")
    return kinds


def _macro_calls(sql: str) -> Iterator[tuple[str, str]]:
    """Yield the name and argument text of every macro call, matching nested parentheses."""

    for match in _MACRO_CALL.finditer(sql):
        depth: int = 1
        index: int = match.end()
        while index < len(sql) and depth:
            depth += {"(": 1, ")": -1}.get(sql[index], 0)
            index += 1
        yield match.group(1), sql[match.end() : index - 1]


def _declaration_kinds(
    *, capture: dict[str, object], usages: list[tuple[str, dict[str, object]]]
) -> set[str]:
    kinds: set[str] = set()
    scopes: dict[str, str] = {
        json.dumps(record.get("identity"), sort_keys=True): str(enum_name(record.get("scope")))
        for record in records(
            (as_json_object(capture.get("scope_index")) or {}).get("declarations")
        )
    }
    list_constants: set[str] = {
        str(declaration.get("name"))
        for declaration in mapping_records(capture.get("public_constants"))
        if enum_name(
            (
                as_json_object((as_json_object(declaration.get("value")) or {}).get("logical_type"))
                or {}
            ).get("kind")
        )
        == _LIST_VALUE
    }
    for consumer, usage in usages:
        declaration: dict[str, object] = as_json_object(usage.get("declaration")) or {}
        kind: str | None = _declaration_kind(usage)
        if declaration.get("owner") is not None:
            kinds.add("scope_private_use")
        scope: str | None = scopes.get(json.dumps(declaration, sort_keys=True))
        if scope is not None:
            kinds.add(f"scope_{scope}_use")
        if kind == _ENUM_DECLARATION and usage.get("enum_member") is not None:
            kinds.add("enum_member")
        if kind == _CONSTANT_DECLARATION:
            kinds.add(
                "list_constant" if declaration.get("name") in list_constants else "scalar_constant"
            )
        if consumer != _MODEL_RESOURCE and usage.get("through") is not None:
            kinds.add("expected_model_grant")
    for model in records(capture.get("model_inputs")):
        if has_content(model.get("enum_columns")):
            kinds.add("enum_column_contract")
    return kinds


def _interpolation_kinds(capture: dict[str, object]) -> set[str]:
    kinds: set[str] = set()
    for model in records(capture.get("model_inputs")):
        model_file: dict[str, object] = as_json_object(model.get("model_file")) or {}
        authored: str = str(model_file.get("query_sql", ""))
        rendered: str = str(model.get("query_sql", ""))
        if _PROJECT_VARIABLE.search(authored) and not _PROJECT_VARIABLE.search(rendered):
            kinds.add("project_variable")
        if _ENVIRONMENT_VARIABLE in authored and _ENVIRONMENT_VARIABLE not in rendered:
            kinds.add("environment_variable")
        values: dict[str, object] = (
            as_json_object((as_json_object(model.get("config")) or {}).get("values")) or {}
        )
        placeholders: set[str] = set(_RUNTIME_PLACEHOLDER.findall(rendered))
        defaults: dict[str, object] = as_json_object(values.get(_PLACEHOLDERS_KEY)) or {}
        if placeholders and placeholders <= set(defaults):
            kinds.add("runtime_placeholder")
        if (
            _CURSOR_INTRINSIC in rendered
            and values.get(_MATERIALIZED_KEY) == _INCREMENTAL
            and values.get(_CURSOR_KEY) is not None
        ):
            kinds.add("cursor_intrinsic")
    discovered: dict[str, object] = as_json_object(capture.get("discovered_inputs")) or {}
    authored_expressions: dict[str, str] = {}
    for source_file in records(discovered.get("source_files")):
        for entry in records(source_file.get("source_entries")):
            authored_expressions[str(entry.get("name"))] = str(entry.get("expression"))
    for source in records(capture.get("source_inputs")):
        entry: dict[str, object] = as_json_object(source.get("source_entry")) or {}
        if authored_expressions.get(str(entry.get("name"))) not in (None, entry.get("expression")):
            kinds.add("source_expression_rendered")
    if _audit_arguments_rendered(capture):
        kinds.add("audit_arguments")
    return kinds


def _audit_arguments_rendered(capture: dict[str, object]) -> bool:
    """Whether an authored generic-audit argument's value is bound into its rendered SQL."""

    authored: dict[tuple[str, str | None, str], dict[str, object]] = _authored_audit_arguments(
        capture
    )
    for audit in records(capture.get("audit_inputs")):
        relative_path: dict[str, object] = (
            as_json_object((as_json_object(audit.get("audit_file")) or {}).get("relative_path"))
            or {}
        )
        definition: str = PurePosixPath(str(relative_path.get("__path__", ""))).stem
        key: tuple[str, str | None, str] = (
            str(audit.get("attached_target_name")),
            _optional_text(audit.get("attached_column_name")),
            definition,
        )
        template: str = str((as_json_object(audit.get("audit_block")) or {}).get("sql_body", ""))
        rendered: str = str(audit.get("sql_body", ""))
        for name, value in authored.get(key, {}).items():
            literal: re.Pattern[str] = re.compile(rf"(?<![\w.-]){re.escape(str(value))}(?![\w.])")
            if (
                re.search(rf"@'?{re.escape(name)}\b", template)
                and literal.search(rendered)
                and not literal.search(template)
            ):
                return True
    return False


def _authored_audit_arguments(
    capture: dict[str, object],
) -> dict[tuple[str, str | None, str], dict[str, object]]:
    """Map `(target, column, definition)` to authored arguments, except built-ins and `column`."""

    found: dict[tuple[str, str | None, str], dict[str, object]] = {}
    for model in records(capture.get("model_inputs")):
        entry: dict[str, object] = as_json_object(model.get("schema_entry")) or {}
        target: str = str(entry.get("name"))
        attachments: list[tuple[str | None, dict[str, object]]] = [
            (None, instance) for instance in records(entry.get("audits"))
        ]
        for column in records(entry.get("columns")):
            attachments.extend(
                (str(column.get("name")), instance) for instance in records(column.get("audits"))
            )
        for column_name, instance in attachments:
            definition: str = str(instance.get("definition_name"))
            if definition not in BUILT_IN_AUDIT_NAMES:
                found[(target, column_name, definition)] = _authored_arguments(instance)
    return found


def _authored_arguments(instance: dict[str, object]) -> dict[str, object]:
    arguments: dict[str, object] = as_json_object(instance.get("arguments")) or {}
    return {
        name: value
        for name, value in arguments.items()
        if name != _IMPLICIT_AUDIT_ARGUMENT and isinstance(value, (int, float, str))
    }


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _hook_kinds(capture: dict[str, object]) -> set[str]:
    kinds: set[str] = set()
    for model in records(capture.get("model_inputs")):
        header: dict[str, object] = (
            as_json_object((as_json_object(model.get("model_file")) or {}).get("header_values"))
            or {}
        )
        values: dict[str, object] = (
            as_json_object((as_json_object(model.get("config")) or {}).get("values")) or {}
        )
        for key in RENDER_HOOK_KEYS:
            authored_hooks: list[dict[str, object]] = records(header.get(key))
            rendered_hooks: list[dict[str, object]] = records(values.get(key))
            for authored, rendered in zip(authored_hooks, rendered_hooks, strict=False):
                kinds.update(_hook_entry_kinds(authored=authored, rendered=rendered))
    return kinds


def _hook_entry_kinds(*, authored: dict[str, object], rendered: dict[str, object]) -> set[str]:
    if str(rendered.get("__type__", "")).endswith(_PYTHON_HOOK_TYPE):
        return {"python_hook"}
    statement: str = str(rendered.get("statement", ""))
    authored_text: str = json.dumps(authored, ensure_ascii=False)
    kinds: set[str] = {"named_sql_hook" if rendered.get("definition_sql") else "inline_sql_hook"}
    if _CONTEXT_VARIABLE in authored_text and _CONTEXT_VARIABLE not in statement:
        kinds.add("hook_context_variable")
    if _MACRO_CALL.search(authored_text) and not _MACRO_CALL.search(statement):
        kinds.add("macro_in_hook")
    if (
        has_content(rendered.get("kwargs"))
        and _TEMPLATE_ARGUMENT.search(str(rendered.get("definition_sql", "")))
        and not _TEMPLATE_ARGUMENT.search(statement)
    ):
        kinds.add("named_hook_arguments")
    return kinds


def _reference_kinds(capture: dict[str, object]) -> set[str]:
    kinds: set[str] = set()
    for collection in _REFERENCE_COLLECTIONS:
        for item in records(capture.get(collection)):
            kinds.update(
                f"reference_{enum_name(reference.get('ref_kind'))}"
                for reference in records(item.get("references"))
            )
    return kinds


def _attachment_kinds(capture: dict[str, object]) -> set[str]:
    kinds: set[str] = set()
    for test in records(capture.get("test_inputs")):
        kinds.add(f"{enum_name(test.get('mode'))}_test")
        if test.get("case_name") is not None:
            kinds.add("parameterized_test_case")
    for audit in records(capture.get("audit_inputs")):
        target: str | None = enum_name(audit.get("attached_target_kind"))
        if target is None:
            kinds.add("singular_audit")
        elif audit.get("attached_column_name") is not None:
            kinds.add(f"{target}_column_audit")
        else:
            kinds.add(f"{target}_audit")
    for model in records(capture.get("model_inputs")):
        config: dict[str, object] = as_json_object(model.get("config")) or {}
        if config.get("matched_path_default") is not None:
            kinds.add("path_default")
    return kinds

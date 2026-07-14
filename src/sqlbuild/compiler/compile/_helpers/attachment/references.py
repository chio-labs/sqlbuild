"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.constants import TABLE_FUNCTION_RETURN_KEYS
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileSqlReference,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditFile,
    DiscoveredProjectInputs,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlModelFile,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver, SqlReferenceKind

_HOOK_TEMPLATE_PATTERN: re.Pattern[str] = re.compile(r"\$\{[^}]+\}")
_LEGACY_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hook", "post_hook"})
_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_HOOK_CONTEXT_PARAMETER_NAMES: frozenset[str] = frozenset(
    {"ctx", "context", "_ctx", "hook_context"}
)


def validate_model_references(
    *,
    references: tuple[CompileSqlReference, ...],
    model_file: DiscoveredSqlModelFile,
    known_model_names: set[str],
    known_seed_names: set[str],
    known_source_names: set[str],
    known_function_names: set[str],
    known_table_function_names: set[str],
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
) -> None:
    """Validate extracted model refs against discovered project inputs."""

    reference: CompileSqlReference
    for reference in references:
        if (
            reference.ref_kind == SqlReferenceKind.REF
            and reference.ref_name not in known_model_names
        ):
            if reference.ref_name in known_seed_names:
                raise CompileInputError(
                    f"Model file {model_file.relative_path} references seed '{reference.ref_name}' "
                    f"with {SqlReferenceKind.REF.placeholder_call('...')}. Use "
                    f"{SqlReferenceKind.SEED.example_call(reference.ref_name)} for seed "
                    f"references; {SqlReferenceKind.REF.function_name} only resolves models."
                )
            raise CompileInputError(
                f"Model file {model_file.relative_path} references unknown model "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.SEED
            and reference.ref_name not in known_seed_names
        ):
            if reference.ref_name in known_model_names:
                raise CompileInputError(
                    f"Model file {model_file.relative_path} references model "
                    f"'{reference.ref_name}' "
                    f"with {SqlReferenceKind.SEED.placeholder_call('...')}. Use "
                    f"{SqlReferenceKind.REF.example_call(reference.ref_name)} for model "
                    "references."
                )
            raise CompileInputError(
                f"Model file {model_file.relative_path} references unknown seed "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.SOURCE
            and reference.ref_name not in known_source_names
        ):
            raise CompileInputError(
                f"Model file {model_file.relative_path} references unknown source "
                f"'{reference.ref_name}'"
            )
        if reference.ref_kind == SqlReferenceKind.DBT_REF:
            if external_sql_reference_resolver is None:
                raise CompileInputError(
                    f"Model file {model_file.relative_path} uses "
                    f"{SqlReferenceKind.DBT_REF.example_call(reference.ref_name)} "
                    "but no dbt manifest was found",
                    code="C214",
                    help=(
                        "Run dbt compile or configure dbt target_path so SQLBuild can read "
                        "manifest.json."
                    ),
                )
            external_sql_reference_resolver.validate_reference(
                ref_kind=reference.ref_kind,
                ref_name=reference.ref_name,
                ref_package=reference.ref_package,
                owner_relative_sql_path=model_file.relative_path,
            )
        if (
            reference.ref_kind == SqlReferenceKind.UDF
            and reference.ref_name not in known_function_names
        ):
            raise CompileInputError(
                f"Model file {model_file.relative_path} references unknown SQL function "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.UDF
            and reference.ref_name in known_table_function_names
        ):
            raise CompileInputError(
                f"Model file {model_file.relative_path} references table function "
                f"'{reference.ref_name}' with {SqlReferenceKind.UDF.placeholder_call()}; "
                f"use {SqlReferenceKind.TABLE_FUNCTION.placeholder_call()} in SQL contexts "
                "that support table-valued functions"
            )
        if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION:
            raise CompileInputError(
                f"Model file {model_file.relative_path} references table function "
                f"'{reference.ref_name}', but table functions are terminal resources and cannot "
                "be model dependencies"
            )


def validate_function_references(
    *,
    references: tuple[CompileSqlReference, ...],
    function_file: DiscoveredSqlFunctionFile,
    known_model_names: set[str],
    known_seed_names: set[str],
    known_source_names: set[str],
    known_function_names: set[str],
    known_table_function_names: set[str],
) -> None:
    """Validate extracted SQL function refs against discovered project inputs."""

    reference: CompileSqlReference
    for reference in references:
        if (
            reference.ref_kind == SqlReferenceKind.REF
            and reference.ref_name not in known_model_names
        ):
            if reference.ref_name in known_seed_names:
                raise CompileInputError(
                    f"SQL function file {function_file.relative_path} references seed "
                    f"'{reference.ref_name}' with {SqlReferenceKind.REF.placeholder_call('...')}. "
                    f"Use {SqlReferenceKind.SEED.example_call(reference.ref_name)} "
                    f"for seed references; {SqlReferenceKind.REF.function_name} only "
                    "resolves models."
                )
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} references unknown model "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.SEED
            and reference.ref_name not in known_seed_names
        ):
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} references unknown seed "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.SOURCE
            and reference.ref_name not in known_source_names
        ):
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} references unknown source "
                f"'{reference.ref_name}'"
            )
        if reference.ref_kind == SqlReferenceKind.DBT_REF:
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} uses "
                f"{SqlReferenceKind.DBT_REF.example_call(reference.ref_name)} but dbt refs "
                "are not supported yet; "
                "support may be added in a future release"
            )
        if (
            reference.ref_kind in {SqlReferenceKind.UDF, SqlReferenceKind.TABLE_FUNCTION}
            and reference.ref_name not in known_function_names
        ):
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} references unknown SQL function "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.UDF
            and reference.ref_name in known_table_function_names
        ):
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} references table function "
                f"'{reference.ref_name}' with {SqlReferenceKind.UDF.placeholder_call()}; "
                f"use {SqlReferenceKind.TABLE_FUNCTION.placeholder_call()}"
            )
        if (
            reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION
            and reference.ref_name not in known_table_function_names
        ):
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} references scalar function "
                f"'{reference.ref_name}' with "
                f"{SqlReferenceKind.TABLE_FUNCTION.placeholder_call()}; "
                f"use {SqlReferenceKind.UDF.placeholder_call()} for scalar UDFs"
            )


def validate_audit_references(
    *,
    references: tuple[CompileSqlReference, ...],
    audit_file: DiscoveredAuditFile,
    known_model_names: set[str],
    known_seed_names: set[str],
    known_source_names: set[str],
) -> None:
    """Validate extracted audit refs against discovered project inputs."""

    reference: CompileSqlReference
    for reference in references:
        if reference.ref_kind == SqlReferenceKind.DBT_REF:
            raise CompileInputError(
                f"Audit file {audit_file.relative_path} may not use "
                f"{SqlReferenceKind.DBT_REF.example_call(reference.ref_name)}; audit dbt "
                "model checks belong in dbt"
            )
        if (
            reference.ref_kind == SqlReferenceKind.REF
            and reference.ref_name not in known_model_names
        ):
            if reference.ref_name in known_seed_names:
                raise CompileInputError(
                    f"Audit file {audit_file.relative_path} references seed '{reference.ref_name}' "
                    f"with {SqlReferenceKind.REF.placeholder_call('...')}. Use "
                    f"{SqlReferenceKind.SEED.example_call(reference.ref_name)} for seed "
                    f"references; {SqlReferenceKind.REF.function_name} only resolves models."
                )
            raise CompileInputError(
                f"Audit file {audit_file.relative_path} references unknown model "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.SEED
            and reference.ref_name not in known_seed_names
        ):
            raise CompileInputError(
                f"Audit file {audit_file.relative_path} references unknown seed "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.SOURCE
            and reference.ref_name not in known_source_names
        ):
            raise CompileInputError(
                f"Audit file {audit_file.relative_path} references unknown source "
                f"'{reference.ref_name}'"
            )


def build_known_ref_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of names valid as __ref() targets."""

    return {
        discovered_model_file.file_path.stem
        for discovered_model_file in discovered_inputs.model_files
    }


def build_known_seed_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of names valid as __seed() targets."""

    seed_names: set[str] = set()
    for schema_file in discovered_inputs.schema_files:
        for seed_entry in schema_file.seed_entries:
            seed_names.add(seed_entry.name)
    return seed_names


def build_known_source_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of names valid as __source() targets."""

    source_names: set[str] = set()
    for source_file in discovered_inputs.source_files:
        for source_entry in source_file.source_entries:
            source_names.add(source_entry.name)
    return source_names


def build_known_function_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of names valid as __udf() targets."""

    return {
        *(function_file.file_path.stem for function_file in discovered_inputs.sql_function_files),
        *(
            function_file.file_path.stem
            for function_file in discovered_inputs.python_function_files
        ),
    }


def build_known_table_function_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of discovered SQL functions declared as table functions."""

    return {
        function_file.file_path.stem
        for function_file in discovered_inputs.sql_function_files
        if _is_table_function_returns(function_file.header_values.get("returns"))
    }


def _is_table_function_returns(raw_returns: object) -> bool:
    return isinstance(raw_returns, dict) and set(raw_returns) == TABLE_FUNCTION_RETURN_KEYS

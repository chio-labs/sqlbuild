"""The Python classes and project inputs the native model loop builds models with."""

from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import cast

from sqlbuild.compiler.auditing.types import AuditSeverity
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompactLineageFacts,
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompiledObjectKey,
    CompiledRelationLocation,
    CompiledSqlExpansion,
    CompilerDiagnostic,
    CompileSqlReference,
    DeclarationScopeResolver,
    DynamicColumnContractProof,
    DynamicColumnFamilyProof,
    ExpansionSpan,
    FunctionArgument,
    FunctionReturnColumn,
    InferredColumn,
    ModelInputBuildContext,
    NativeModelConfigSession,
)
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind, FunctionLanguage
from sqlbuild.compiler.compiled_project._helpers.loop_inputs import (
    hook_signature,
    named_records,
    schema_enums,
    visibility_classes,
)
from sqlbuild.compiler.compiled_project.main._native_config_classes import native_config_classes
from sqlbuild.compiler.compiled_project.main.declaration_rows import declaration_rows
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditFactory,
    DiscoveredHookFunction,
    PythonHookEntry,
    SqlHookEntry,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.model_config.main._native_config_error import native_config_error
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver, SqlReferenceKind
from sqlbuild.compiler.scopes.exceptions import InvalidScopePathError
from sqlbuild.compiler.scopes.models import UsageRecord
from sqlbuild.compiler.scopes.types import UsageKind
from sqlbuild.spec.contracts.models import SchemaModelEntry, SourceLocation


def model_loop_classes(
    *,
    audit_factories: tuple[DiscoveredAuditFactory, ...],
    context: ModelInputBuildContext,
    external_resolver: ExternalSqlReferenceResolver | None,
    host_inputs: dict[str, object],
) -> dict[str, object]:
    """Return the classes, error factories and project declarations the model loop reads."""

    resolver: DeclarationScopeResolver | None = context.declaration_resolver
    hook_functions: tuple[DiscoveredHookFunction, ...] = cast(
        tuple[DiscoveredHookFunction, ...], host_inputs["hook_functions"]
    )
    provider_names: frozenset[str] = cast(frozenset[str], host_inputs["provider_names"])
    session: NativeModelConfigSession = cast(
        NativeModelConfigSession, host_inputs["config_session"]
    )
    return {
        "usage_record": UsageRecord,
        "compile_error": CompileInputError,
        "syntax_help": host_inputs["syntax_help"],
        "source_syntax_help": host_inputs["source_syntax_help"],
        "macros": host_inputs["macros"],
        "sql_hooks": host_inputs["sql_hooks"],
        "scope_path_error": InvalidScopePathError,
        "sql_hook_entry": SqlHookEntry,
        "config_error": native_config_error,
        "audit_factories": {factory.name: factory for factory in audit_factories},
        "generated_usage": UsageKind.GENERATED,
        "contract_enforced": ContractPolicy.ENFORCED,
        "model_schemas": context.public_model_schemas,
        "named_records": named_records(resolver),
        "schema_enums": schema_enums(resolver),
        "compiler_diagnostic": CompilerDiagnostic,
        "report_diagnostic": host_inputs["report_diagnostic"],
        "path_class": Path,
        "external_resolver": external_resolver,
        "reference_kind": SqlReferenceKind,
        "partial": partial,
        "config": native_config_classes(
            session=session, record_template_reads=host_inputs["record_template_reads"]
        ),
        "hooks": {
            "functions": {function.name: function for function in hook_functions},
            "provider_names": sorted(provider_names),
            "python_hook_entry": PythonHookEntry,
            "signature": hook_signature,
        },
        "visibility": visibility_classes(
            context=context, visible_declarations=host_inputs["visible_declarations"]
        ),
        "record": {"replace": replace, "declaration_rows": declaration_rows},
        "input_view": {
            "sql_reference": CompileSqlReference,
            "reference_kind": SqlReferenceKind,
            "schema_model_entry": SchemaModelEntry,
            "sql_expansion": CompiledSqlExpansion,
            "expansion_span": ExpansionSpan,
            "audits": {
                "audit_severity": AuditSeverity,
                "attached_target_kind": AttachedAuditTargetKind,
            },
            "functions": {
                "function_argument": FunctionArgument,
                "function_return_column": FunctionReturnColumn,
                "function_language": FunctionLanguage,
            },
            "compiled": {
                "object_key": CompiledObjectKey,
                "relation_location": CompiledRelationLocation,
                "inferred_column": InferredColumn,
                "nullability": InferredNullability,
                "compiler_diagnostic": CompilerDiagnostic,
                "source_location": SourceLocation,
                "compact_lineage_facts": CompactLineageFacts,
                "lineage_column_fact": CompiledLineageColumnFact,
                "lineage_source_fact": CompiledLineageSourceFact,
                "contract_proof": DynamicColumnContractProof,
                "family_proof": DynamicColumnFamilyProof,
            },
        },
    }

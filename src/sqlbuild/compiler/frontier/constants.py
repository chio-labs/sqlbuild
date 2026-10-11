"""Compiler engine switch, cache namespace, and stage capture constants."""

import re

from sqlbuild.compiler.frontier.types import CompilerEngine, NativeStage, NativeStageTier

COMPILER_ENGINE_ENV_VAR: str = "SQLBUILD_COMPILER_ENGINE"
COMPILER_ENGINE_OPTION: str = "--compiler-engine"
DEFAULT_COMPILER_ENGINE: CompilerEngine = CompilerEngine.NATIVE
COMPILER_ENGINE_VALUES: tuple[str, ...] = tuple(engine.value for engine in CompilerEngine)
NATIVE_CACHE_NAMESPACE_SUFFIX: str = "-native-v1"
NATIVE_PREVIEW_CACHE_NAMESPACE_SUFFIX: str = "-native-preview-v1"
REMOVED_PYTHON_ENGINE: str = "python"
ENGINE_CACHE_NAMESPACE_SUFFIXES: dict[CompilerEngine, str] = {
    CompilerEngine.NATIVE: NATIVE_CACHE_NAMESPACE_SUFFIX,
    CompilerEngine.NATIVE_PREVIEW: NATIVE_PREVIEW_CACHE_NAMESPACE_SUFFIX,
}
RETIRED_CACHE_NAMESPACE_SUFFIXES: tuple[str, ...] = ("", *ENGINE_CACHE_NAMESPACE_SUFFIXES.values())
NATIVE_STAGE_TIERS: dict[NativeStage, NativeStageTier] = {
    NativeStage.DISCOVERY: NativeStageTier.SHIPPED,
    NativeStage.DECLARATION_SCOPES: NativeStageTier.SHIPPED,
    NativeStage.MODEL_CONFIG: NativeStageTier.SHIPPED,
    NativeStage.REFERENCE_EXTRACTION: NativeStageTier.SHIPPED,
    NativeStage.DECLARATION_FILES: NativeStageTier.SHIPPED,
    NativeStage.MODEL_LOOP: NativeStageTier.SHIPPED,
    NativeStage.MACRO_CALLS: NativeStageTier.SHIPPED,
    NativeStage.MACRO_CALL_STORE: NativeStageTier.SHIPPED,
    NativeStage.ATTACHMENTS: NativeStageTier.SHIPPED,
    NativeStage.TYPE_SYSTEM: NativeStageTier.SHIPPED,
    NativeStage.MODEL_ANALYSIS: NativeStageTier.SHIPPED,
    NativeStage.SEMANTIC_CHECKS: NativeStageTier.SHIPPED,
    NativeStage.CONTRACTS: NativeStageTier.SHIPPED,
    NativeStage.LINEAGE_FACTS: NativeStageTier.SHIPPED,
    NativeStage.SQL_TEST_GLUE: NativeStageTier.SHIPPED,
    NativeStage.PROJECT_ASSEMBLY: NativeStageTier.SHIPPED,
    NativeStage.COMPILE_LINT_INPUTS: NativeStageTier.SHIPPED,
    NativeStage.RULES_REQUEST: NativeStageTier.SHIPPED,
    NativeStage.COMPILE_OUTPUTS: NativeStageTier.SHIPPED,
    NativeStage.REFACTORING: NativeStageTier.SHIPPED,
}
ENGINE_NATIVE_STAGE_TIERS: dict[CompilerEngine, frozenset[NativeStageTier]] = {
    CompilerEngine.NATIVE: frozenset({NativeStageTier.SHIPPED}),
    CompilerEngine.NATIVE_PREVIEW: frozenset({NativeStageTier.SHIPPED, NativeStageTier.PREVIEW}),
}
TARGET_DIRECTORY_NAME: str = "target"
CACHE_DIRECTORY_NAME: str = "cache"
COMPILER_CACHE_DIRECTORY_NAME: str = "compiler"
NATIVE_FALLBACK_RECORD_PREFIX: str = "native-fallbacks-"
NATIVE_FALLBACK_DEFAULT_KIND: str = "deferred"
NATIVE_ANSWER_SITE_SUFFIX: str = ".native"
STAGE_CAPTURE_DIR_ENV_VAR: str = "SQLBUILD_COMPILER_STAGE_CAPTURE_DIR"
COMPILE_REUSE_DISABLE_ENV_VAR: str = "SQLBUILD_DISABLE_COMPILE_REUSE"
STAGE_CAPTURE_SUFFIX: str = ".json"
STAGE_CAPTURE_SHARED_MARKER: str = "__shared__"
STAGE_CAPTURE_ROOT_KEY: str = "__capture__"
STAGE_CAPTURE_SHARED_NODES_KEY: str = "__shared_nodes__"
STAGE_CAPTURE_SHARED_MIN_BYTES: int = 1024
STAGE_CAPTURE_RESERVED_KEYS: frozenset[str] = frozenset(
    {STAGE_CAPTURE_SHARED_MARKER, STAGE_CAPTURE_ROOT_KEY, STAGE_CAPTURE_SHARED_NODES_KEY}
)
STAGE_CAPTURE_INVOCATION_ID_PATTERN: re.Pattern[str] = re.compile(r"\b\d{8}T\d{6}Z_[0-9a-f]{12}\b")
STAGE_CAPTURE_INVOCATION_ID_MASK: str = "<invocation-id>"
STAGE_CAPTURE_ENGINE_NAMESPACE_PATTERN: re.Pattern[str] = re.compile(r"-native(?:-preview)?-v\d+\b")
STAGE_CAPTURE_REFACTOR_STAGING_PATTERN: re.Pattern[str] = re.compile(r"\bsqb-refactor-[0-9a-z_]+")
STAGE_CAPTURE_REFACTOR_STAGING_MASK: str = "sqb-refactor-<staging>"
STAGE_CAPTURE_SKIPPED_SLOTS: frozenset[str] = frozenset({"__dict__", "__weakref__"})
STAGE_CAPTURE_UNORDERED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "sqlbuild.compiler.sql_analysis.classes.binding_catalog:BindingCatalog": frozenset(
        {"schemas", "analysis_shapes", "expression_shapes"}
    )
}
STAGE_CAPTURE_PROJECTED_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "sqlbuild._native:NativeAuditInput": (
        "audit_file",
        "audit_block",
        "sql_body",
        "evaluation_mode",
        "measurement_contract",
        "thresholds",
        "minimum_samples",
        "measure_sql",
        "evidence_sql",
        "evidence_limit",
        "references",
        "attached_target_kind",
        "attached_target_name",
        "attached_column_name",
        "severity",
        "run_scope",
        "always_run",
        "description",
        "declaration_usages",
        "name",
    ),
    "sqlbuild._native:NativeCompiledAudit": (
        "key",
        "scope_deps",
        "name",
        "definition_name",
        "audit_file",
        "audit_block",
        "sql_body",
        "evaluation_mode",
        "measurement_contract",
        "thresholds",
        "minimum_samples",
        "measure_sql",
        "evidence_sql",
        "evidence_limit",
        "references",
        "attached_target_kind",
        "attached_target_name",
        "attached_column_name",
        "severity",
        "run_scope",
        "always_run",
        "description",
    ),
    "sqlbuild._native:NativeFunctionInput": (
        "function_file",
        "name",
        "arguments",
        "returns",
        "body_sql",
        "return_columns",
        "references",
        "database",
        "schema",
        "logical_database",
        "logical_schema",
        "fingerprint_database",
        "fingerprint_schema",
        "fingerprint_logical_database",
        "fingerprint_logical_schema",
        "language",
        "runtime_version",
        "entry_point",
        "packages",
        "declaration_usages",
        "tags",
        "description",
    ),
    "sqlbuild._native:NativeCompiledFunction": (
        "key",
        "deps",
        "name",
        "relative_path",
        "arguments",
        "returns",
        "body_sql",
        "destination",
        "fingerprint_destination",
        "return_columns",
        "references",
        "language",
        "source_file_path",
        "runtime_version",
        "entry_point",
        "packages",
        "tags",
        "description",
    ),
    "sqlbuild._native:NativeSourceInput": (
        "source_entry",
        "source_file",
        "declaration_usages",
    ),
    "sqlbuild._native:NativeCompiledSource": (
        "key",
        "deps",
        "name",
        "source_entry",
        "source_file",
    ),
    "sqlbuild._native:NativeSeedInput": ("seed_file", "schema_entry", "schema_file"),
    "sqlbuild._native:NativeCompiledSeed": (
        "key",
        "deps",
        "name",
        "seed_file",
        "schema_entry",
        "schema_file",
        "destination",
        "external",
    ),
    "sqlbuild._native:NativeInputsView": (
        "project_config",
        "local_config",
        "discovered_inputs",
        "sql_lexical_syntax",
        "run_id",
        "effective_target_name",
        "effective_target",
        "compile_cache_dir",
        "effective_connection",
        "effective_settings",
        "no_sql_validation",
        "effective_vars",
        "macro_context",
        "loaded_macros",
        "public_enums",
        "public_constants",
        "model_inputs",
        "seed_inputs",
        "source_inputs",
        "sql_function_inputs",
        "test_inputs",
        "scenario_inputs",
        "audit_inputs",
        "diagnostics",
        "external_sql_reference_resolver",
        "scope_index",
        "declaration_scope",
    ),
    "sqlbuild._native:NativeProjectView": (
        "run_id",
        "effective_target_name",
        "effective_connection",
        "effective_vars",
        "binding_catalog",
        "effective_target_database",
        "effective_target_schema",
        "sql_analysis_dialect",
        "sql_lexical_syntax",
        "compile_cache_dir",
        "settings",
        "scenario",
        "models",
        "sources",
        "seeds",
        "functions",
        "audits",
        "sql_tests",
        "sql_scenarios",
        "loader_functions",
        "hook_functions",
        "enforce_explicit_references",
        "sql_hook_files",
        "materialization_files",
        "public_enums",
        "public_constants",
        "loaded_macros",
        "diagnostics",
        "unmatched_literal_sql_relations",
        "external_sql_reference_resolver",
        "scope_index",
        "sql_expansions",
    ),
    "sqlbuild._native:NativeCompiledModel": (
        "key",
        "deps",
        "name",
        "relative_path",
        "query_sql",
        "config",
        "destination",
        "references",
        "schema_entry",
        "inferred_columns",
        "fast_lineage_columns",
        "fast_lineage_has_star",
        "fast_lineage_star_resolved",
        "authored_sql",
        "authored_query_sql",
        "output_column_locations",
        "extract_implicit_alias_columns",
        "macro_deps",
        "enum_declarations",
        "constant_declarations",
        "enum_columns",
        "binding_diagnostics",
        "binding_validated",
        "dynamic_column_contract",
        "unchecked_output_columns",
        "rejected_sql_analysis_opt_out",
    ),
    "sqlbuild._native:NativeModelInput": (
        "model_file",
        "config",
        "query_sql",
        "macro_source_sql",
        "references",
        "schema_entry",
        "schema_file",
        "sql_validation_enabled",
        "rejected_sql_analysis_opt_out",
        "enum_declarations",
        "constant_declarations",
        "enum_columns",
        "macro_deps",
        "macro_usages",
        "declaration_usages",
        "sql_expansion",
        "lint_expansion",
    ),
}
STAGE_CAPTURE_OMITTED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "sqlbuild.compiler.scopes.models:ScopeLookup": frozenset({"native"}),
    "sqlbuild.compiler.sql_analysis.classes.binding_catalog:BindingCatalog": frozenset(
        {"shared_analyses"}
    ),
    "sqlbuild.compiler.discovery.models:DiscoveredProjectInputs": frozenset({"native_session"}),
    "sqlbuild.compiler.compile.models:DeclarationScopeResolver": frozenset({"native_contexts"}),
    "sqlbuild.compiler.compile.models:DeclarationScopeBuild": frozenset({"sql_test_scans"}),
    "sqlbuild.compiler.compile.models:CompileProjectInputs": frozenset({"native_project"}),
    "sqlbuild.compiler.compile.models:CompiledProject": frozenset(
        {"native_session", "native_project", "lineage_graph"}
    ),
}
STAGE_CAPTURE_CANONICAL_TYPES: dict[str, str] = {
    "sqlbuild._native:NativeInputsView": "sqlbuild.compiler.compile.models:CompileProjectInputs",
    "sqlbuild._native:NativeProjectView": "sqlbuild.compiler.compile.models:CompiledProject",
    "sqlbuild._native:NativeModelInput": "sqlbuild.compiler.compile.models:CompileModelInput",
    "sqlbuild._native:NativeCompiledModel": "sqlbuild.compiler.compile.models:CompiledModel",
    "sqlbuild._native:NativeCompiledSource": "sqlbuild.compiler.compile.models:CompiledSource",
    "sqlbuild._native:NativeCompiledSeed": "sqlbuild.compiler.compile.models:CompiledSeed",
    "sqlbuild._native:NativeCompiledFunction": "sqlbuild.compiler.compile.models:CompiledFunction",
    "sqlbuild._native:NativeCompiledAudit": "sqlbuild.compiler.compile.models:CompiledAudit",
}
STAGE_CAPTURE_DECODED_SEQUENCES: frozenset[str] = frozenset(
    {"sqlbuild.compiler.compile.models:CompactLineageFacts"}
)

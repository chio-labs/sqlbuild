"""Compiler engine switch, cache namespace, and stage capture constants."""

import re

from sqlbuild.compiler.frontier.types import CompilerEngine, NativeStage, NativeStageTier

COMPILER_ENGINE_ENV_VAR: str = "SQLBUILD_COMPILER_ENGINE"
COMPILER_ENGINE_OPTION: str = "--compiler-engine"
DEFAULT_COMPILER_ENGINE: CompilerEngine = CompilerEngine.NATIVE
COMPILER_ENGINE_VALUES: tuple[str, ...] = tuple(engine.value for engine in CompilerEngine)
NATIVE_CACHE_NAMESPACE_SUFFIX: str = "-native-v1"
NATIVE_PREVIEW_CACHE_NAMESPACE_SUFFIX: str = "-native-preview-v1"
ENGINE_CACHE_NAMESPACE_SUFFIXES: dict[CompilerEngine, str] = {
    CompilerEngine.PYTHON: "",
    CompilerEngine.NATIVE: NATIVE_CACHE_NAMESPACE_SUFFIX,
    CompilerEngine.NATIVE_PREVIEW: NATIVE_PREVIEW_CACHE_NAMESPACE_SUFFIX,
}
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
    NativeStage.TYPE_SYSTEM: NativeStageTier.PREVIEW,
    NativeStage.MODEL_ANALYSIS: NativeStageTier.PREVIEW,
    NativeStage.SEMANTIC_CHECKS: NativeStageTier.PREVIEW,
    NativeStage.CONTRACTS: NativeStageTier.PREVIEW,
    NativeStage.LINEAGE_FACTS: NativeStageTier.PREVIEW,
    NativeStage.RICH_LINEAGE: NativeStageTier.PREVIEW,
    NativeStage.RELATION_FINGERPRINT: NativeStageTier.PREVIEW,
    NativeStage.SQL_TEST_GLUE: NativeStageTier.PREVIEW,
    NativeStage.PROJECT_ASSEMBLY: NativeStageTier.PREVIEW,
}
ENGINE_NATIVE_STAGE_TIERS: dict[CompilerEngine, frozenset[NativeStageTier]] = {
    CompilerEngine.PYTHON: frozenset(),
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
STAGE_CAPTURE_SKIPPED_SLOTS: frozenset[str] = frozenset({"__dict__", "__weakref__"})
STAGE_CAPTURE_UNORDERED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "sqlbuild.compiler.sql_analysis.classes.binding_catalog:BindingCatalog": frozenset(
        {"schemas", "analysis_shapes", "expression_shapes"}
    )
}
STAGE_CAPTURE_OMITTED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "sqlbuild.compiler.sql_analysis.classes.binding_catalog:BindingCatalog": frozenset(
        {"shared_analyses"}
    ),
    "sqlbuild.compiler.discovery.models:DiscoveredProjectInputs": frozenset({"native_session"}),
    "sqlbuild.compiler.compile.models:DeclarationScopeResolver": frozenset({"native_contexts"}),
    "sqlbuild.compiler.compile.models:DeclarationScopeBuild": frozenset({"sql_test_scans"}),
    "sqlbuild.compiler.compile.models:CompiledProject": frozenset({"native_session"}),
}
STAGE_CAPTURE_DECODED_SEQUENCES: frozenset[str] = frozenset(
    {"sqlbuild.compiler.compile.models:CompactLineageFacts"}
)

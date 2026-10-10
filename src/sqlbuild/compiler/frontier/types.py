"""Compiler engine and frontier stage identities."""

from enum import StrEnum


class CompilerEngine(StrEnum):
    """Which compiler implementation produces the frontier objects."""

    PYTHON = "python"
    NATIVE = "native"
    NATIVE_PREVIEW = "native-preview"


class NativeStage(StrEnum):
    """A native implementation that replaces one Python compiler stage when its tier is active."""

    DISCOVERY = "discovery"
    DECLARATION_SCOPES = "declaration_scopes"
    MODEL_CONFIG = "model_config"
    REFERENCE_EXTRACTION = "reference_extraction"
    DECLARATION_FILES = "declaration_files"
    MODEL_LOOP = "model_loop"
    MACRO_CALLS = "macro_calls"
    MACRO_CALL_STORE = "macro_call_store"
    ATTACHMENTS = "attachments"
    TYPE_SYSTEM = "type_system"
    MODEL_ANALYSIS = "model_analysis"
    SEMANTIC_CHECKS = "semantic_checks"
    CONTRACTS = "contracts"
    LINEAGE_FACTS = "lineage_facts"
    SQL_TEST_GLUE = "sql_test_glue"
    PROJECT_ASSEMBLY = "project_assembly"
    COMPILE_LINT_INPUTS = "compile_lint_inputs"
    RULES_REQUEST = "rules_request"
    COMPILE_OUTPUTS = "compile_outputs"


class NativeStageTier(StrEnum):
    """Which engines run a native stage: shipped stages passed their flip gate."""

    SHIPPED = "shipped"
    PREVIEW = "preview"


class CompilerStage(StrEnum):
    """Frontier objects handed from one compiler stage to the next, in pipeline order."""

    DISCOVERED_PROJECT_INPUTS = "discovered_project_inputs"
    COMPILE_PROJECT_INPUTS = "compile_project_inputs"
    COMPILED_PROJECT = "compiled_project"


class NativeFallbackSite(StrEnum):
    """A place where a shipped native stage still hands its work to the Python implementation."""

    SCOPE_REBIND_LOOKUP = "declaration_scopes.rebind_lookup"
    LINT_EXPANSION = "model_loop.lint_expansion"
    COMPILE_JSON_REPORT = "compile_outputs.json_report"
    MACRO_CALL_SCAN = "macro_calls.scan"
    MACRO_CALL_RESOLUTION = "macro_calls.resolution"
    MACRO_UNBRIDGED_EXPANSION = "macro_calls.unbridged_expansion"
    MACRO_BRIDGE_UNAVAILABLE = "macro_calls.bridge_unavailable"
    MACRO_CALL_MOCKED = "macro_calls.mocked_evaluation"
    PROJECT_ASSEMBLY = "project_assembly.assembly"
    TYPE_NORMALIZATION = "type_system.normalization"
    SQL_TEST_ASSEMBLY = "sql_test_glue.assembly"

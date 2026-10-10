"""Compiler engine and frontier stage identities."""

from enum import StrEnum


class CompilerEngine(StrEnum):
    """Which compiler implementation produces the frontier objects."""

    NATIVE = "native"
    NATIVE_PREVIEW = "native-preview"


class NativeStage(StrEnum):
    """A native implementation behind the preview engine until its tier is shipped."""


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
    MACRO_CALL_SCAN = "macro_calls.scan"
    MACRO_CALL_RESOLUTION = "macro_calls.resolution"
    MACRO_UNBRIDGED_EXPANSION = "macro_calls.unbridged_expansion"
    MACRO_BRIDGE_UNAVAILABLE = "macro_calls.bridge_unavailable"
    MACRO_CALL_MOCKED = "macro_calls.mocked_evaluation"
    PROJECT_ASSEMBLY = "project_assembly.assembly"
    SQL_TEST_ASSEMBLY = "sql_test_glue.assembly"

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


class NativeStageTier(StrEnum):
    """Which engines run a native stage: shipped stages passed their flip gate."""

    SHIPPED = "shipped"
    PREVIEW = "preview"


class CompilerStage(StrEnum):
    """Frontier objects handed from one compiler stage to the next, in pipeline order."""

    DISCOVERED_PROJECT_INPUTS = "discovered_project_inputs"
    COMPILE_PROJECT_INPUTS = "compile_project_inputs"
    COMPILED_PROJECT = "compiled_project"

"""Compiler engine and frontier stage identities."""

from enum import StrEnum


class CompilerEngine(StrEnum):
    """Which compiler implementation produces the frontier objects."""

    PYTHON = "python"
    NATIVE = "native"


class CompilerStage(StrEnum):
    """Frontier objects handed from one compiler stage to the next, in pipeline order."""

    DISCOVERED_PROJECT_INPUTS = "discovered_project_inputs"
    COMPILE_PROJECT_INPUTS = "compile_project_inputs"
    COMPILED_PROJECT = "compiled_project"

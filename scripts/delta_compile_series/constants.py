"""Edits and markers of delta compile series."""

from __future__ import annotations

from scripts.delta_compile_series.models import DeltaCompileEdit
from scripts.delta_compile_series.types import EditTarget

DELTA_COMPILE_LINE: str = "against the previous compile"
DELTA_VERIFIED_LINE: str = "delta compile verified"
DELTA_FALLBACK_PATTERN: str = r"^delta compile fell back: (.*)$"
DELTA_MISMATCH_PATTERN: str = r"^delta compile mismatch: .*$"
COMPILE_REUSE_HIT_LINE: str = "Inputs unchanged; reused the previous compile"
MISMATCH_EXIT_CODE: int = 70
REVERT_PROBABILITY: float = 0.5
EDIT_ATTEMPTS: int = 50
DELTA_WEIGHT: int = 3
FALLBACK_WEIGHT: int = 1
STALE_PROBLEMS: str = "reports problems in files the edit leaves alone"
PROJECT_CONFIG: str = "sqlbuild_project.toml"
RANDOM_VALUE_LIMIT: int = 10**6

EDITS: tuple[DeltaCompileEdit, ...] = (
    DeltaCompileEdit("body_constant", r"COALESCE\(b\.amount, \d+\)", "COALESCE(b.amount, {value})"),
    DeltaCompileEdit("body_comment", r"\Z", "\n-- reviewed {value}\n"),
    DeltaCompileEdit(
        "description", r'MODEL \(description "[^"]*"', 'MODEL (description "Edited {value}."'
    ),
    DeltaCompileEdit(
        "column_description",
        r'description "Order quantity measure"',
        'description "Edited measure {value}"',
    ),
    DeltaCompileEdit("type_error", r"quantity_000 \(type DOUBLE", "quantity_000 (type VARCHAR"),
    DeltaCompileEdit("parse_error", r"projected AS \(SELECT", "projected AS (SELEC"),
    DeltaCompileEdit(
        "test_expectation",
        r"(__expected__\w+ AS \(SELECT CAST\()\d+",
        r"\g<1>{value}",
        target=EditTarget.TESTS,
    ),
    DeltaCompileEdit(
        "materialization",
        r"materialized table",
        "materialized view",
        fallback_reason="custom rules select models by their materialization",
    ),
    DeltaCompileEdit("contract", r"contract enforced, ", "", fallback_reason="a custom rule reads"),
    DeltaCompileEdit(
        "unknown_reference",
        r'__ref\("([^"]+)"\)',
        r'__ref("\1_missing")',
        fallback_reason="changed what it references",
    ),
    DeltaCompileEdit(
        "project_config",
        r"\Z",
        "\n# reviewed {value}\n",
        target=EditTarget.PROJECT_CONFIG,
        fallback_reason="sqlbuild_project.toml is not a model or SQL test file",
    ),
)
BODY_EDIT: DeltaCompileEdit = EDITS[0]
PRIVATE_PATH_MARKER: str = "/_"
SQL_GLOB: str = "*.sql"
FAILURE_TAIL_CHARACTERS: int = 2000
BODY_MODEL_INDEX: int = 11
BODY_SEED: int = 3
DOUBLE_COLUMN: str = "quantity_000 (type DOUBLE"
FLOAT_COLUMN: str = "quantity_000 (type FLOAT"
DOUBLE_CAST: str = "AS DOUBLE) AS quantity_000"
FLOAT_CAST: str = "AS FLOAT) AS quantity_000"

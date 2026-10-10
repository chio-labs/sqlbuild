"""Helpers for native compiled project integration tests."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.main import _build_compile_inputs as compile_inputs_module
from sqlbuild.compiler.compiled_project.main import compiled_project_facts as facts_module
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR

TYPE_PROOF_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRCONTRACT105"]\n\n'
        '[defaults]\ncontract = "enforced"\n'
    ),
    "models/stg_orders.sql": (
        "MODEL (description 'Staged orders.',\n"
        "  columns (order_id (type INTEGER), amount (type INTEGER)),\n"
        ");\n\n"
        "SELECT CAST(1 AS INTEGER) AS order_id, CAST(5 AS INTEGER) AS amount\n"
    ),
    "models/orders.sql": (
        "MODEL (description 'Typed orders.',\n"
        "  columns (order_id (type INTEGER), amount (type BIGINT)),\n"
        ");\n\n"
        'SELECT order_id, amount\nFROM __ref("stg_orders")\n'
    ),
}


def forbid_hand_built_projects(*, monkeypatch: pytest.MonkeyPatch, engine: str) -> None:
    """Fail if a consumer records a project from `CompiledProject` instead of the compile's."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine)

    def refuse(project: object) -> object:
        raise AssertionError(f"rules rebuilt project facts from {type(project).__name__}")

    monkeypatch.setattr(facts_module, "hand_built_project_impl", refuse)


def skip_model_retention(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Build compile inputs without retaining their models in the native project."""

    def skipped(*, project: object, model_inputs: object) -> None:
        del project, model_inputs

    monkeypatch.setattr(compile_inputs_module, "record_model_inputs", skipped)

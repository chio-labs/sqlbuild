"""Helpers for native compiled project integration tests."""

from __future__ import annotations

import shutil
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import sqlbuild._native as _native
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile import models as compile_models
from sqlbuild.compiler.compile._helpers.attachment import core as attachment_core
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompileAdapterContext, CompileProjectInputs
from sqlbuild.compiler.compiled_project.main import compiled_project_facts as facts_module
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.sql_values.types import CollectionRendering
from tests.integration.src.sqlbuild.compiler.graph.helpers import write_files

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
    """Run the native model loop into a throwaway project instead of the compile's own."""

    native_loop: Callable[..., object] = attachment_core._run_native_model_loop

    def discarded(**kwargs: Any) -> object:
        kwargs["native_project"] = _native.NativeCompiledProject()
        return native_loop(**kwargs)

    monkeypatch.setattr(attachment_core, "_run_native_model_loop", discarded)


LEGACY_PROJECT_TYPES: tuple[str, ...] = (
    "CompileProjectInputs",
    "CompileModelInput",
    "CompiledProject",
    "CompiledModel",
)


def count_legacy_constructions(*, monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """Count every construction of the Python project representation, `replace` included."""

    counts: Counter[str] = Counter()
    for name in LEGACY_PROJECT_TYPES:
        model_type: type = getattr(compile_models, name)
        monkeypatch.setattr(
            model_type, "__init__", _counted_init(counts=counts, name=name, model_type=model_type)
        )
    return counts


def _counted_init(*, counts: Counter[str], name: str, model_type: type) -> object:
    original: Callable[..., None] = model_type.__init__

    def counted(self: object, *args: object, **kwargs: object) -> None:
        counts[name] += 1
        original(self, *args, **kwargs)

    return counted


PARITY_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders"\nadapter = "duckdb"\n\n[vars]\nregion = "eu"\n\n'
        '[defaults]\nmaterialized = "table"\n\n[path_defaults.staging]\n'
        'materialized = "view"\ntags = ["staged"]\n'
    ),
    "seeds/payment_methods.csv": "method\ncard\n",
    "seeds/payment_methods.yml": (
        "seeds:\n  - name: payment_methods\n    description: Payment methods.\n"
        "    columns:\n      - name: method\n        type: VARCHAR\n"
    ),
    "models/staging/stg_orders.sql": (
        "MODEL (description 'Staged orders.', tags [daily]);\n"
        "SELECT 1 AS order_id, '@@region' AS region -- note\n"
    ),
    "models/staging/stg_payments.sql": (
        'MODEL (tags [payments]);\nSELECT method FROM __seed("payment_methods")\n'
    ),
    "models/marts/orders.sql": (
        "MODEL (description 'Orders.', materialized incremental, incremental_strategy append,"
        " cursor order_id, cursor_type integer);\n"
        'SELECT order_id FROM __ref("stg_orders")\n'
        "WHERE order_id >= __cursor_start()\n"
    ),
    "models/marts/opted_out.sql": ("MODEL (sql_analysis false);\nSELECT 1 AS order_id\n"),
    "models/marts/described_columns.sql": (
        "MODEL (\n  columns (order_id (type INTEGER, nullable false,"
        ' audits [not_null, unique]), note (description "Free text.")),\n'
        ");\n"
        "SELECT 1 AS order_id, 'x' AS note\n"
    ),
    "enums/status.sql": "ENUM (name order_status, members [PLACED, SHIPPED]);\n",
    "constants/limits.sql": (
        "CONSTANT (name order_cap, value 3);\nCONSTANT (name held_codes, value [30, 31]);\n"
    ),
    "models/marts/statuses.sql": (
        "MODEL (columns (status (type VARCHAR)));\n"
        'SELECT @enum("order_status").PLACED AS status, @const("order_cap") AS cap\n'
        'WHERE 30 NOT IN @const("held_codes")\n'
    ),
    "macros/money.py": 'def cents(value: str) -> str:\n    return f"{value} * 100"\n',
    "models/marts/priced.sql": (
        "MODEL (description 'Priced orders.');\n"
        "SELECT @cents('3') AS cents, order_id FROM __ref(\"stg_orders\")\n"
    ),
    "models/marts/hooked.sql": (
        "MODEL (\n  description 'Hooked orders.',\n"
        "  pre_hooks [inline_sql('SELECT @@region AS region')],\n"
        "  post_hooks [inline_sql('SELECT @cents(2) AS cents')],\n);\n"
        "SELECT 1 AS order_id\n"
    ),
    "models/marts/migrated.sql": (
        "MODEL (materialized incremental, incremental_strategy append,"
        " columns (order_id (migrate_from id)));\nSELECT 1 AS order_id\n"
    ),
}


HEADER_CONTRACT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": 'name = "orders"\nadapter = "duckdb"\n',
    "enums/status.sql": "ENUM (name order_status, members [PLACED, SHIPPED]);\n",
    "audits/generic/expression_is_true.sql": (
        'AUDIT ();\nSELECT * FROM __ref("@model") WHERE NOT (@expression)\n'
    ),
    "python/quality.py": (
        "from sqlbuild.audits import AuditCase, audit_factory\n\n\n"
        "@audit_factory\n"
        "def order_checks():\n"
        "    return [\n"
        '        AuditCase(name="positive_total", definition="expression_is_true",\n'
        '                  arguments={"expression": "total > 0"}),\n'
        "    ]\n"
    ),
    "models/order_amounts.sql": (
        "MODEL (columns (customer_id (type INTEGER)));\n"
        "SELECT 1 AS customer_id, 'books' AS category, 2 AS amount\n"
    ),
    "models/category_amounts.sql": (
        "MODEL (\n  columns (customer_id (type INTEGER)),\n"
        "  dynamic_columns (category_amounts (pivot_column category, value_column amount,"
        ' aggregate max, type INTEGER, name_pattern "^[a-z]+$")),\n);\n'
        'SELECT * FROM __ref("order_amounts")\n'
        "PIVOT(MAX(amount) FOR category IN (ANY ORDER BY category))\n"
    ),
    "models/order_statuses.sql": (
        "MODEL (\n  contract enforced,\n"
        "  columns (status (type order_status, audits [not_null]), total (type INTEGER)),\n"
        "  audit_factories [order_checks],\n);\n"
        'SELECT @enum("order_status").PLACED AS status, 3 AS total\n'
    ),
}


OPT_OUT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders"\nadapter = "duckdb"\n\n[settings]\nrequire_sql_analysis = true\n\n'
        "[path_defaults.legacy]\nsql_analysis = false\n"
    ),
    "models/header_opt_out.sql": "MODEL (\n  sql_analysis false\n);\nSELECT 1 AS order_id\n",
    "models/legacy/path_opt_out.sql": "MODEL ();\nSELECT 1 AS order_id\n",
    "models/unparsed.sql": "MODEL (sql_analysis false);\nSELECT FROM WHERE (\n",
    "models/invalid_call.sql": "MODEL ();\nSELECT * FROM __ref(order_name)\n",
}


def build_inputs_with_native_loop(
    *, project_dir: Path, native: bool, monkeypatch: pytest.MonkeyPatch
) -> tuple[CompileProjectInputs, list[int]]:
    """Build compile inputs; without `native`, the attachment builds every model itself."""

    finished: list[int] = []
    native_loop_type: type = _native.NativeModelLoop

    loops: dict[bool, Callable[..., object]] = {
        True: lambda *arguments: _CountingLoop(native_loop_type(*arguments), finished),
        False: lambda *_: _AttachmentLoop(finished),
    }

    with monkeypatch.context() as patch:
        patch.setattr(_native, "NativeModelLoop", loops[native])
        inputs: CompileProjectInputs = build_compile_inputs(
            discovered_inputs=discover_project_inputs(project_dir=project_dir),
            adapter_context=CompileAdapterContext(
                value_renderer=DuckDbAdapter(),
                collection_rendering=CollectionRendering.VALUE_LIST,
                python_functions_inherit_default_namespace=True,
                sql_lexical_syntax=DuckDbAdapter.sql_lexical_syntax,
            ),
            defer_model_sql_validation=True,
            no_cache=True,
        )
    return inputs, finished


@dataclass(frozen=True)
class _CountingLoop:
    native_loop: Any
    finished: list[int]

    def run(self, *arguments: object) -> tuple[list[object], int]:
        inputs, count = self.native_loop.run(*arguments)
        self.finished.append(count)
        return inputs, count


@dataclass(frozen=True)
class _AttachmentLoop:
    """The model loop as the attachment alone runs it, retaining facts from each model input."""

    finished: list[int]

    def run(
        self, project: _native.NativeCompiledProject, host: Any, models: list[object]
    ) -> tuple[list[object], int]:
        inputs: list[object] = []
        for index in range(len(models)):
            _ = host.config(index=index)
            model_input: object = host.fallback(index=index)
            project.record_model(host.model_row(model_input=model_input))
            inputs.append(model_input)
        self.finished.append(0)
        return inputs, 0


def expansions(inputs: CompileProjectInputs) -> list[tuple[object, object]]:
    """Each model's SQL expansion evidence, which model-input equality does not compare."""

    return [(item.sql_expansion, item.lint_expansion) for item in inputs.model_inputs]


WAFFLE_SHOP_NATIVE_MODELS: int = 13


def copy_project(*, fixtures: tuple[str, ...], files: dict[str, str], project_dir: Path) -> Path:
    """Copy each fixture into `project_dir`, then write `files` over them."""

    project_dir.mkdir(parents=True)
    for fixture in fixtures:
        _ = shutil.copytree(fixture, project_dir, dirs_exist_ok=True)
    write_files(project_dir=project_dir, files=files)
    return project_dir

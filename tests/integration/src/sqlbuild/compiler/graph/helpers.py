"""Helpers for native project graph integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

import sqlbuild._native as native_module

ORDERS_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": 'name = "orders"\nadapter = "duckdb"\n',
    "models/staging/stg_orders.sql": (
        "MODEL (description 'Staged orders.', tags [daily]);\nSELECT 1 AS order_id\n"
    ),
    "models/marts/orders.sql": (
        "MODEL (description 'Orders.');\nSELECT order_id FROM __ref(\"stg_orders\")\n"
    ),
    "models/marts/customers.sql": "MODEL (description 'Customers.');\nSELECT 1 AS customer_id\n",
}
MODEL_NAMES: frozenset[str] = frozenset({"stg_orders", "orders", "customers"})


def write_files(*, project_dir: Path, files: dict[str, str]) -> None:
    """Write project files under `project_dir`."""

    for relative_path, text in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def record_compile_owners(
    *, monkeypatch: pytest.MonkeyPatch
) -> list[native_module.NativeCompiledProject]:
    """Record every native compiled project the compile creates, to read its graph builds."""

    owners: list[native_module.NativeCompiledProject] = []
    owner_type: type[native_module.NativeCompiledProject] = native_module.NativeCompiledProject

    def recorded() -> native_module.NativeCompiledProject:
        owner: native_module.NativeCompiledProject = owner_type()
        owners.append(owner)
        return owner

    monkeypatch.setattr(native_module, "NativeCompiledProject", recorded)
    return owners


def compiled_models(*, stdout: str) -> dict[str, bool]:
    """Whether the compile report lists each project model."""

    return {name: f"── {name} " in stdout for name in sorted(MODEL_NAMES)}

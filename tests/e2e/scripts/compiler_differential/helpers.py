"""Harness invocations and a perturbation that makes one engine's output differ."""

from __future__ import annotations

from pathlib import Path

NATIVE_ONLY_STDERR_LINE: str = "native engine perturbation active"
WAFFLE_SHOP_FIXTURE: Path = Path(__file__).resolve().parents[2] / "fixtures" / "waffle_shop"
_SITECUSTOMIZE: str = f'''
import dataclasses
import sys

import sqlbuild.compiler.frontier.main._compile_frontier as frontier
from sqlbuild.compiler.frontier.types import CompilerStage

_original = frontier.native_frontier


def _perturbed(*, until, python_stage):
    result = _original(until=until, python_stage=python_stage)
    if until is not CompilerStage.COMPILED_PROJECT or not result.models:
        return result
    first = result.models[0]
    changed = dataclasses.replace(
        first, query_sql=f"SELECT * FROM ({{first.query_sql}}) AS perturbed_by_test"
    )
    return dataclasses.replace(result, models=(changed, *result.models[1:]))


frontier.native_frontier = _perturbed
print("{NATIVE_ONLY_STDERR_LINE}", file=sys.stderr)
'''

_BROKEN_REF_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "broken_orders"\nadapter = "duckdb"\n\n'
        '[connection]\ndatabase = "broken_orders.duckdb"\n'
    ),
    "models/order_totals.sql": (
        'MODEL (\n  description "Order totals",\n);\n\nSELECT * FROM __ref("nope")\n'
    ),
}


def write_broken_ref_project(directory: Path) -> Path:
    """Write a project whose only model references a model that does not exist."""

    for relative_path, contents in _BROKEN_REF_FILES.items():
        path: Path = directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8", newline="\n")
    return directory


def write_native_perturbation(directory: Path) -> Path:
    """Write a sitecustomize module that changes the first compiled model on the native path."""

    directory.mkdir(parents=True, exist_ok=True)
    _ = (directory / "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="utf-8")
    return directory


def harness_arguments(
    *, work_dir: Path, extra: tuple[str, ...], project: Path = WAFFLE_SHOP_FIXTURE
) -> list[str]:
    """Compare only one project (the waffle shop fixture by default), keeping run directories."""

    return [
        "--corpus",
        "--project",
        str(project),
        "--jobs",
        "1",
        "--work-dir",
        str(work_dir),
        *extra,
    ]


def perturbation_arguments(directory: Path) -> tuple[str, ...]:
    """Return the options that load the perturbation into native-engine processes only."""

    return (
        "--stage-captures",
        "--engine-env",
        f"native:PYTHONPATH={write_native_perturbation(directory)}",
    )

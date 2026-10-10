"""Harness invocations and a perturbation that makes one engine's output differ."""

from __future__ import annotations

from pathlib import Path

from scripts.compiler_differential.main.failure_cases import failure_cases

NATIVE_ONLY_STDERR_LINE: str = "native engine perturbation active"
WAFFLE_SHOP_FIXTURE: Path = Path(__file__).resolve().parents[2] / "fixtures" / "waffle_shop"
_SITECUSTOMIZE: str = f'''
import dataclasses
import sys

import sqlbuild.compiler.frontier.main._compile_frontier as frontier
from sqlbuild.compiler.frontier.types import CompilerStage

_original = frontier.native_frontier


def _perturbed(*, until, **stages):
    result = _original(until=until, **stages)
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

DISCOVERY_PERTURBATION: str = """
import dataclasses

import sqlbuild.compiler.frontier.main._compile_frontier as frontier
from sqlbuild.compiler.frontier.types import CompilerStage

_original = frontier.native_frontier


def _perturbed(*, until, **stages):
    result = _original(until=until, **stages)
    if until is not CompilerStage.DISCOVERED_PROJECT_INPUTS or len(result.model_files) < 2:
        return result
    return dataclasses.replace(result, model_files=tuple(reversed(result.model_files)))


frontier.native_frontier = _perturbed
"""

RENDER_PERTURBATION: str = """
import dataclasses

import sqlbuild.compiler.frontier.main._compile_frontier as frontier
from sqlbuild.compiler.frontier.types import CompilerStage

_original = frontier.native_frontier


def _perturbed(*, until, **stages):
    result = _original(until=until, **stages)
    if until is not CompilerStage.COMPILE_PROJECT_INPUTS or not result.model_inputs:
        return result
    first = result.model_inputs[0]
    changed = dataclasses.replace(first, macro_deps=(*first.macro_deps, "perturbed_by_test"))
    return dataclasses.replace(result, model_inputs=(changed, *result.model_inputs[1:]))


frontier.native_frontier = _perturbed
"""

CATALOG_PERTURBATION: str = """
import sqlbuild.compiler.analysis_session.classes.native_model_analysis as native_analysis

_original = native_analysis.NativeModelAnalysis._record_catalog_changes


def _perturbed(self, **changes):
    _original(self, **changes)
    self._catalog.schemas["perturbed_by_test"] = {"order_id": "INTEGER"}


native_analysis.NativeModelAnalysis._record_catalog_changes = _perturbed
"""

DEFERRAL_PERTURBATION: str = """
import json
import os
from pathlib import Path

_directory = os.environ.get("SQLBUILD_ANALYSIS_RECORD_DIR")
if _directory:
    Path(_directory).mkdir(parents=True, exist_ok=True)
    with open(Path(_directory) / f"analysis-deferrals-{os.getpid()}.jsonl", "a") as _record:
        _record.write(json.dumps({"kind": "legacy_fallback", "site": "orders.sql"}) + "\\n")
"""

MACRO_RESOLUTION_SABOTAGE: str = """
from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge

MacroBridge.call_class = lambda self, **_: None
"""

MODEL_ANALYSIS_SABOTAGE: str = """
import sqlbuild._native as native

native.start_model_analysis_session = lambda *_args: None
"""

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


def write_failure_case_project(directory: Path, *, name: str) -> Path:
    """Write one named failure-corpus project below a directory."""

    {case.name: case for case in failure_cases()}[name].write(directory)
    return directory


def write_native_perturbation(directory: Path, *, source: str = _SITECUSTOMIZE) -> Path:
    """Write a sitecustomize module that perturbs one frontier object on the native path.

    By default it changes the first compiled model.
    """

    directory.mkdir(parents=True, exist_ok=True)
    _ = (directory / "sitecustomize.py").write_text(source, encoding="utf-8")
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


def perturbation_arguments(directory: Path, *, source: str = _SITECUSTOMIZE) -> tuple[str, ...]:
    """Return the options that load the perturbation into native-engine processes only."""

    return (
        "--stage-captures",
        "--engine-env",
        f"native-preview:PYTHONPATH={write_native_perturbation(directory, source=source)}",
    )

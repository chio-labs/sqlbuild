import json
import os
import re
import shutil
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild.cli.commands._helpers.compile import output as output_module
from sqlbuild.cli.commands._helpers.compile import target_writer as target_writer_module
from sqlbuild.cli.commands.classes import native_artifact_batch as artifact_batch_module
from sqlbuild.cli.commands.classes import prepared_compile_artifacts
from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.cli.compile_reuse._helpers import project_files as project_files_module
from sqlbuild.cli.compile_reuse.constants import REUSE_DISABLE_ENV_VAR
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import NativeStage

STAGING_PREFIX: str = ".sqlbuild-staging-"
OUTPUT_MODEL_HEADER: str = (
    "MODEL (description 'Orders {name}.', materialized table, contract enforced, "
    "columns (order_id (type INTEGER)));\n"
)
OUTPUT_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL021"]\n'
    ),
    **{
        f"models/orders_{name}.sql": OUTPUT_MODEL_HEADER.format(name=name)
        + "SELECT CAST(1 AS INTEGER) AS order_id\n"
        for name in ("east", "north", "west")
    },
}
EDITED_MODEL: str = "models/orders_north.sql"
DELETED_MODEL: str = "models/orders_west.sql"
COMPILE_OUTPUTS_PREFIX: str = f"{NativeStage.COMPILE_OUTPUTS.value}:"
TOUCH_BACK_NS: int = 3_600_000_000_000
BLOCKED_ARTIFACT: str = "target/compiled/models/orders_north.sql"

type CompileOutcome = tuple[int, dict[str, Any], dict[str, bytes]]


def write_files(*, project_dir: Path, files: dict[str, str]) -> None:
    """Write project files at their project-relative paths."""

    for relative, contents in files.items():
        path: Path = project_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")


def record_output_work(
    *, monkeypatch: pytest.MonkeyPatch, engine: str, reuse_disabled: str
) -> Counter[str]:
    """Count native compile output work, staging small projects and settling file stamps."""

    counts: Counter[str] = Counter()
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine)
    monkeypatch.setenv(REUSE_DISABLE_ENV_VAR, reuse_disabled)
    monkeypatch.setattr(prepared_compile_artifacts, "_MIN_PREPARED_ARTIFACT_MODELS", 1)
    monkeypatch.setattr(project_files_module, "RACY_WINDOW_NS", 0)

    def counted(*, stage: NativeStage, kind: str, units: int = 1) -> None:
        counts[f"{stage.value}:{kind}"] += units

    for module in (
        output_module,
        target_writer_module,
        artifact_batch_module,
        project_files_module,
    ):
        monkeypatch.setattr(module, "report_native_answer", counted)
    return counts


def compile_outputs(
    *, project_dir: Path, args: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> CompileOutcome:
    """Compile through the CLI; return the exit code, timing-free JSON and compiled files."""

    exit_code: int = main(["--project-dir", str(project_dir), "compile", "--json", *args])
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    for key in ("compile_timings", "compiler_engine"):
        _ = payload.pop(key, None)
    return exit_code, payload, compile_files(project_dir=project_dir)


def compile_files(*, project_dir: Path) -> dict[str, bytes]:
    """Every file under target/compiled by its relative path."""

    compiled: Path = project_dir / "target" / "compiled"
    return {
        path.relative_to(compiled).as_posix(): path.read_bytes()
        for path in sorted(filter(Path.is_file, compiled.rglob("*")))
    }


def main_compile(*, project_dir: Path) -> int:
    """Run one uncached JSON compile through the CLI entry point."""

    return main(["--project-dir", str(project_dir), "compile", "--json", "--no-cache"])


def uncached_reference(
    *, project_dir: Path, reference_dir: Path, capsys: pytest.CaptureFixture[str]
) -> CompileOutcome:
    """Compile a fresh copy of the project with --no-cache."""

    shutil.rmtree(reference_dir, ignore_errors=True)
    _ = shutil.copytree(project_dir, reference_dir, ignore=shutil.ignore_patterns("target"))
    return compile_outputs(project_dir=reference_dir, args=("--no-cache",), capsys=capsys)


def comparable(outcome: CompileOutcome) -> tuple[int, dict[str, Any], dict[str, bytes]]:
    """The outcome with project paths made relative, so two copies compare equal."""

    exit_code, payload, files = outcome
    artifacts: dict[str, Any] = cast(dict[str, Any], payload.get("artifacts", {}))
    return exit_code, {**payload, "artifacts": sorted(artifacts)}, files


def work_delta(*, before: Counter[str], after: Counter[str]) -> dict[str, int]:
    """Native compile output work counted between two snapshots, by kind."""

    return {
        kind.removeprefix(COMPILE_OUTPUTS_PREFIX): units
        for kind, units in sorted((after - before).items())
    }


def staging_directories(target_dir: Path) -> list[str]:
    """Staging directories left beside the compiled directory."""

    return sorted(path.name for path in target_dir.glob(f"{STAGING_PREFIX}*"))


def block_artifact(*, project_dir: Path) -> Path:
    """Replace one published artifact with a non-empty directory and edit its model."""

    blocked: Path = project_dir / BLOCKED_ARTIFACT
    blocked.unlink()
    blocked.mkdir()
    _ = (blocked / "keep.txt").write_text("kept\n", encoding="utf-8")
    model: Path = project_dir / EDITED_MODEL
    _ = model.write_text(
        model.read_text(encoding="utf-8").replace("CAST(1 AS", "CAST(2 AS"), encoding="utf-8"
    )
    return blocked


def neutral_error(*, error: BaseException, project_dir: Path) -> str:
    """The error text with the project directory and staging name replaced."""

    text: str = str(error).replace(str(project_dir), "<project>")
    return re.sub(rf"{re.escape(STAGING_PREFIX)}[0-9a-f]+", f"{STAGING_PREFIX}<id>", text)


def edit_sequence_step(*, project_dir: Path, step: str) -> None:
    """Apply one step of the cached edit sequence."""

    _SEQUENCE_ACTIONS[step](project_dir=project_dir)


def _unchanged(*, project_dir: Path) -> None:
    del project_dir


def _touch_back(*, project_dir: Path) -> None:
    model: Path = project_dir / EDITED_MODEL
    touched_ns: int = model.stat().st_mtime_ns - TOUCH_BACK_NS
    os.utime(model, ns=(touched_ns, touched_ns))


def _edit(*, project_dir: Path) -> None:
    model: Path = project_dir / EDITED_MODEL
    _ = model.write_text(
        model.read_text(encoding="utf-8").replace("CAST(1 AS", "CAST(30 AS"), encoding="utf-8"
    )


def _delete(*, project_dir: Path) -> None:
    (project_dir / DELETED_MODEL).unlink()


_SEQUENCE_ACTIONS: dict[str, Callable[..., None]] = {
    "cold": _unchanged,
    "warm": _unchanged,
    "touch": _touch_back,
    "edit": _edit,
    "delete": _delete,
}


def published_files(counts: Counter[str]) -> int:
    """Staged artifacts published natively."""

    return counts[f"{COMPILE_OUTPUTS_PREFIX}published_files"]


def artifacts_except(*, files: dict[str, bytes], name: str) -> dict[str, bytes]:
    """Every artifact except one."""

    return {key: files[key] for key in sorted(files.keys() - {name})}

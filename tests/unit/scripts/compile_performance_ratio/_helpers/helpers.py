"""Builders for same-runner compile comparison test data."""

from pathlib import Path

from scripts.compile_performance_ratio.models import CompileComparison


def comparison(
    *, mode: str, wall: tuple[float, float], cpu: tuple[float, float]
) -> CompileComparison:
    """Build a dense 3000-model comparison from (base, head) wall and CPU medians."""

    return CompileComparison(
        kind="dense",
        models=3000,
        mode=mode,
        base_wall_seconds=wall[0],
        head_wall_seconds=wall[1],
        base_cpu_seconds=cpu[0],
        head_cpu_seconds=cpu[1],
        base_timings_ms={"total_ms": wall[0] * 1000},
        head_timings_ms={"total_ms": wall[1] * 1000},
    )


def write_model_files(*, project_dir: Path, model_files: dict[str, str]) -> None:
    """Write model files at project-relative paths."""

    for relative, contents in model_files.items():
        path: Path = project_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")


def read_model_files(*, project_dir: Path) -> dict[str, str]:
    """Read every model file keyed by its project-relative path."""

    return {
        path.relative_to(project_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((project_dir / "models").rglob("*.sql"))
    }

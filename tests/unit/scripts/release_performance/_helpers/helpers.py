"""Builders for release performance comparison test data."""

import subprocess
from pathlib import Path

from scripts.release_performance.models import CommandComparison, CommandSample

MIB: int = 1024 * 1024
MARKER_GENERATOR: str = """from pathlib import Path


def write_pristine_projects(*, root: Path, inspection_models: int, build_models: int) -> Path:
    for name, models in (("inspection", inspection_models), ("build", build_models)):
        (root / "pristine" / name).mkdir(parents=True)
        (root / "pristine" / name / "BASELINE_MARKER").write_text(str(models))
    return root / "pristine"
"""
FAILING_GENERATOR: str = """def write_pristine_projects(*, root, inspection_models, build_models):
    raise RuntimeError("baseline generator exploded")
"""


def comparison(
    *,
    name: str,
    baseline: tuple[tuple[float, float, int], ...],
    candidate: tuple[tuple[float, float, int], ...],
) -> CommandComparison:
    """Build a comparison from (wall seconds, CPU seconds, peak RSS MiB) samples."""

    return CommandComparison(
        name=name,
        baseline=tuple(_sample(values=values) for values in baseline),
        candidate=tuple(_sample(values=values) for values in candidate),
    )


def release_file(*, filename: str) -> dict[str, object]:
    """Build one PEP 691 file entry that is not yanked."""

    return {"filename": filename, "yanked": False, "url": filename}


def _sample(*, values: tuple[float, float, int]) -> CommandSample:
    wall, cpu, rss_mib = values
    return CommandSample(wall_seconds=wall, cpu_seconds=cpu, peak_rss_bytes=rss_mib * MIB)


def write_baseline_source(*, root: Path, generator: str) -> Path:
    """Write a source tree whose only content is a release benchmark generator."""

    helpers: Path = root / "scripts" / "release_performance" / "_helpers"
    helpers.mkdir(parents=True)
    for package in (root / "scripts", helpers.parent, helpers):
        _ = (package / "__init__.py").write_text("", encoding="utf-8")
    _ = (helpers / "benchmark.py").write_text(generator, encoding="utf-8")
    return root


def tagged_repository(*, root: Path, tag: str) -> Path:
    """Create a one-commit git repository with a tracked file and the given tag."""

    root.mkdir(parents=True)
    _ = (root / "release.txt").write_text(tag, encoding="utf-8")
    for command in (
        ("init", "--quiet"),
        ("add", "release.txt"),
        ("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "--quiet", "-m", "r"),
        ("tag", tag),
    ):
        _ = subprocess.run(["git", "-C", str(root), *command], check=True, capture_output=True)
    return root

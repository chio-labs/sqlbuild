"""Builders for release performance comparison test data."""

from scripts.release_performance.models import CommandComparison, CommandSample

MIB: int = 1024 * 1024


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

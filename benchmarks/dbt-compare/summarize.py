"""Summarize bench.sh output: median wall, user+sys CPU and peak RSS per variant and scenario.

Usage: python summarize.py OUTDIR
"""

import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SCENARIOS = ("cold", "warm", "edit1", "edit100")
TIME_RE = re.compile(r"^(?P<variant>\w+)\.(?P<scenario>\w+)\.r(?P<round>\d+)\.time$")
LOAD_RE = re.compile(r"^(\w+) (\w+) r\d+ load ([\d.]+) ([\d.]+)$")


def path_taken(variant: str, out: str, err: str) -> str:
    """What each tool reported doing: full work, a partial parse, a replay or a delta compile."""
    if variant.startswith("sqb"):
        if "Inputs unchanged; reused the previous compile" in err:
            return "reused"
        if "against the previous compile" in err:
            return "delta"
        return "full"
    if variant.startswith("core"):
        text = out + err
        if "Unable to do partial parsing" in text or "Starting full parse" in text:
            return "full parse"
        return "partial parse"
    return "-"


def main() -> None:
    out = Path(sys.argv[1])
    runs: dict[tuple[str, str], list[tuple[float, float, int, int, str]]] = defaultdict(list)
    for path in sorted(out.glob("*.time")):
        m = TIME_RE.match(path.name)
        if not m:
            continue
        stem = str(path)[: -len(".time")]
        wall, user, sys_, rss = path.read_text().strip().splitlines()[-1].split()
        rc = int(Path(stem + ".rc").read_text())
        taken = path_taken(
            m["variant"],
            Path(stem + ".out").read_text(errors="replace"),
            Path(stem + ".err").read_text(errors="replace"),
        )
        runs[(m["variant"], m["scenario"])].append(
            (float(wall), float(user) + float(sys_), int(rss), rc, taken)
        )
    loads: dict[tuple[str, str], list[float]] = defaultdict(list)
    for line in (out / "uptime.log").read_text().splitlines():
        m = LOAD_RE.match(line)
        if m:
            loads[(m[1], m[2])] += [float(m[3]), float(m[4])]

    print(
        "| variant | scenario | runs | wall s (median) | wall s (all) | user+sys s (median) "
        "| peak RSS MiB (median) | exit codes | path | 1-min load before/after |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    variants = sorted({variant for variant, _ in runs})
    for variant in variants:
        for scenario in SCENARIOS:
            cell = runs.get((variant, scenario))
            if not cell:
                continue
            walls = [r[0] for r in cell]
            load = loads.get((variant, scenario), [0.0])
            print(
                f"| {variant} | {scenario} | {len(cell)} | {statistics.median(walls):.2f} "
                f"| {', '.join(f'{w:.1f}' for w in walls)} "
                f"| {statistics.median(r[1] for r in cell):.1f} "
                f"| {statistics.median(r[2] for r in cell) / 1024:.0f} "
                f"| {','.join(sorted({str(r[3]) for r in cell}))} "
                f"| {','.join(sorted({r[4] for r in cell}))} "
                f"| {min(load):.2f}-{max(load):.2f} |"
            )


if __name__ == "__main__":
    main()

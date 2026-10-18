# ruff: noqa: E501, PLR0915
"""Summarize bench output: median wall, user+sys CPU and peak RSS per variant."""

import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

out = Path(sys.argv[1])
rows: dict[str, list[tuple[float, float, float, int]]] = defaultdict(list)
for path in sorted(out.glob("*.r*.time")):
    variant = path.name.rsplit(".r", 1)[0]
    last = path.read_text().strip().splitlines()[-1].split()
    wall, user, sys_, rss = float(last[0]), float(last[1]), float(last[2]), int(last[3])
    rows[variant].append((wall, user, sys_, rss))

loads: dict[str, list[float]] = defaultdict(list)
for line in (out / "uptime.log").read_text().splitlines():
    m = re.match(r"(\S+) r\d+ (before|after):.*load average: ([\d.]+),", line)
    if m:
        loads[m[1]].append(float(m[3]))

print(
    "| variant | runs | wall s (median) | wall s (all) | user+sys s (median) | peak RSS MiB (median) | 1-min load before/after (range) |"
)
print("|---|---|---|---|---|---|---|")
for variant, runs in rows.items():
    walls = [r[0] for r in runs]
    cpu = [r[1] + r[2] for r in runs]
    rss = [r[3] / 1024 for r in runs]
    load = loads.get(variant, [])
    print(
        f"| {variant} | {len(runs)} | {statistics.median(walls):.2f} | "
        f"{', '.join(f'{w:.1f}' for w in walls)} | {statistics.median(cpu):.1f} | "
        f"{statistics.median(rss):.0f} | {min(load):.2f}–{max(load):.2f} |"
    )

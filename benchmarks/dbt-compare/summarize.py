"""Summarize bench.sh output: median wall, user+sys CPU and peak RSS per variant and scenario.

Usage: python summarize.py OUTDIR
"""

import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SCENARIOS = ("cold", "warm", "edit1", "edit100")
VARIANT_ORDER = (
    "sqb_norules",
    "sqb_norules_full",
    "sqb_rules",
    "sqb_rules_full",
    "v2_compile_cached",
    "v2_compile_strict_cached",
    "v2_compile_dirty",
    "v2_compile_strict_dirty",
    "v2_compile",
    "v2_compile_strict",
    "v2_compile_strict_remote",
    "v2_parse",
    "core_parse",
    "core_compile",
)
SQB_DEFAULT = "SQLBuild (default: compile with column and type checks)"
SQB_RULES = "SQLBuild with every built-in rule and a custom Python rule"
FULL = ", full compile with per-model caches"
LABELS = {
    "sqb_norules": SQB_DEFAULT,
    "sqb_norules_full": SQB_DEFAULT + FULL,
    "sqb_rules": SQB_RULES,
    "sqb_rules_full": SQB_RULES + FULL,
    "v2_compile_cached": "dbt v2 with parse cache (opt-in; compiles the whole project)",
    "v2_compile_strict_cached": "dbt v2 with parse cache, strict",
    "v2_compile_dirty": "dbt v2 --dirty (changed models and descendants only)",
    "v2_compile_strict_dirty": "dbt v2 --dirty, strict",
    "v2_compile": "dbt v2 default",
    "v2_compile_strict": "dbt v2 default, strict",
    "v2_compile_strict_remote": "dbt v2 default, strict, source columns read from the warehouse",
    "v2_parse": "dbt v2 parse",
    "core_parse": "dbt Core parse",
    "core_compile": "dbt Core compile",
}
# SQLBuild's default warm run replays the stored result of the previous compile.
REPLAY_VARIANTS = ("sqb_norules", "sqb_rules")
PROCESSED_RE = re.compile(r"Processed: (\d+) models?")
SKIPPED_ANALYSIS_RE = re.compile(r"Skipping analysis for '([^']+)'")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
TIME_RE = re.compile(r"^(?P<variant>\w+)\.(?P<scenario>\w+)\.r(?P<round>\d+)\.time$")
LOAD_RE = re.compile(r"^(\w+) (\w+) r\d+ load ([\d.]+) ([\d.]+)$")


def path_taken(variant: str, out: str, err: str) -> str:
    """What each tool reported doing.

    SQLBuild: a full compile, a replay of the stored result or a delta compile.
    dbt Core: a full or partial parse.
    dbt v2: how many models it processed, how many it skipped static analysis for, whether its
    parse cache fell back to a full parse, or that `--dirty` found nothing to do.
    """
    if variant.startswith("sqb"):
        if "Inputs unchanged; reused the previous compile" in err:
            return "replay"
        if "against the previous compile" in err:
            return "delta"
        return "full"
    if variant.startswith("core"):
        text = out + err
        if "Unable to do partial parsing" in text or "Starting full parse" in text:
            return "full parse"
        return "partial parse"
    if variant.startswith("v2"):
        text = ANSI_RE.sub("", out + err)
        processed = PROCESSED_RE.search(text)
        if processed:
            skipped = len(set(SKIPPED_ANALYSIS_RE.findall(text)))
            note = f", analysis skipped for {skipped}" if skipped else ""
            if "falling back to full parse" in text:
                note += ", full parse"
            return f"{processed[1]} models{note}"
        if "NoNodesSelected" in text:
            return "nothing to do"
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
    uptime = out / "uptime.log"
    for line in uptime.read_text().splitlines() if uptime.exists() else []:
        m = LOAD_RE.match(line)
        if m:
            loads[(m[1], m[2])] += [float(m[3]), float(m[4])]

    print(
        "| tool | variant | scenario | runs | wall s (median) | wall s (all) | user+sys s (median) "
        "| peak RSS MiB (median) | exit codes | what the tool did | 1-min load before/after |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    found = {variant for variant, _ in runs}
    variants = [v for v in VARIANT_ORDER if v in found] + sorted(found - set(VARIANT_ORDER))
    for variant in variants:
        for scenario in SCENARIOS:
            cell = runs.get((variant, scenario))
            if not cell:
                continue
            walls = [r[0] for r in cell]
            scenario_label = scenario
            if scenario == "warm" and variant in REPLAY_VARIANTS:
                scenario_label = "warm (replay)"
            load = loads.get((variant, scenario), [0.0])
            print(
                f"| {LABELS.get(variant, variant)} | {variant} | {scenario_label} | {len(cell)} "
                f"| {statistics.median(walls):.2f} "
                f"| {', '.join(f'{w:.1f}' for w in walls)} "
                f"| {statistics.median(r[1] for r in cell):.1f} "
                f"| {statistics.median(r[2] for r in cell) / 1024:.0f} "
                f"| {','.join(sorted({str(r[3]) for r in cell}))} "
                f"| {','.join(sorted({r[4] for r in cell}))} "
                f"| {min(load):.2f}-{max(load):.2f} |"
            )


if __name__ == "__main__":
    main()

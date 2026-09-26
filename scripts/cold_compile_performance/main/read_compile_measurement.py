"""Report completed or interrupted benchmark measurements before guard assertions."""

import json
from pathlib import Path

from scripts.cold_compile_performance.constants import COMPILE_MEASUREMENT_FIELD_COUNT


def read_compile_measurement(
    *, label: str, measurement_path: Path, output_path: Path, elapsed_seconds: float
) -> tuple[object, list[str]]:
    """Read one timed CLI result and report unavailable measurements explicitly."""
    measurement: list[str] = []
    if measurement_path.exists():
        lines: list[str] = measurement_path.read_text(encoding="utf-8").splitlines()
        if lines:
            measurement = lines[-1].split()
    payload: object = None
    if output_path.exists():
        try:
            payload = json.loads(output_path.read_bytes())
        except json.JSONDecodeError:
            payload = None
    report: dict[str, object] = {
        "label": label,
        "wall_seconds": elapsed_seconds,
        "cpu_seconds": None,
        "cpu_utilization": None,
        "peak_rss_bytes": None,
        "major_page_faults": None,
        "minor_page_faults": None,
        "compile_timings": payload.get("compile_timings") if isinstance(payload, dict) else None,
    }
    if len(measurement) == COMPILE_MEASUREMENT_FIELD_COUNT:
        wall, rss, user, system, major, minor = measurement
        try:
            report.update(
                wall_seconds=float(wall),
                cpu_seconds=float(user) + float(system),
                cpu_utilization=(float(user) + float(system)) / float(wall)
                if float(wall)
                else None,
                peak_rss_bytes=int(rss) * 1024,
                major_page_faults=int(major),
                minor_page_faults=int(minor),
            )
        except ValueError:
            measurement = []
    print("compile measurement " + json.dumps(report, sort_keys=True), flush=True)
    return payload, measurement

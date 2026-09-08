"""Shared rendering for effective policy test thresholds."""

from sqlbuild.policy_engine.constants import POLICY_THRESHOLD_DEFAULTS
from sqlbuild.policy_engine.models import PolicyConfig


def format_threshold_lines(*, config: PolicyConfig) -> tuple[str, ...]:
    """Render global and path-scoped thresholds in deterministic authored order."""

    thresholds: dict[str, int] = {**POLICY_THRESHOLD_DEFAULTS, **config.thresholds}
    lines: list[str] = [f"- `{name}` = `{value}`" for name, value in sorted(thresholds.items())]
    for index, entry in enumerate(config.threshold_overrides, start=1):
        lines.append(
            f"- Override {index} at `{','.join(entry.paths)}`: "
            f"`{dict(sorted(entry.thresholds.items()))}` ({entry.reason})"
        )
    if config.threshold_overrides:
        lines.append("- Matching overrides apply in authored order; the last match wins.")
    return tuple(lines)

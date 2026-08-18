"""Public phase-completion line rendering entry."""

from __future__ import annotations

from sqlbuild.presentation._helpers.structure import format_phase_line as _format_phase_line
from sqlbuild.presentation.classes.cli_style import CliStyle


def format_phase_line(*, style: CliStyle, ok: bool, label: str, summary: str | None = None) -> str:
    """Render a concise phase-completion line: state glyph, label, dim summary."""

    return _format_phase_line(style=style, ok=ok, label=label, summary=summary)

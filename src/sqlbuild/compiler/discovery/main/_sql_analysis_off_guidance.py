"""Entry for the note and help shown when SQL analysis is turned off by a config file."""

from __future__ import annotations

from sqlbuild.compiler.discovery._helpers.settings.guidance import (
    effective_sql_analysis,
    sql_analysis_off_note_and_help,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs


def sql_analysis_off_guidance(
    *, discovered_inputs: DiscoveredProjectInputs, purpose: str
) -> tuple[str, str] | None:
    """Return `(note, help)` naming the file that turns SQL analysis off, or None when it is on."""

    if effective_sql_analysis(discovered_inputs):
        return None
    return sql_analysis_off_note_and_help(discovered_inputs=discovered_inputs, purpose=purpose)

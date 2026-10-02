"""Current values of project settings and the exact TOML that changes them."""

from __future__ import annotations

from sqlbuild.compiler.discovery.constants import (
    ENFORCE_EXPLICIT_REFERENCES_KEY,
    LOCAL_CONFIG_FILENAME,
    MICROBATCH_CONCURRENCY_SETTING_KEY,
    PROJECT_CONFIG_FILENAME,
    REFERENCES_SECTION,
    SETTINGS_SECTION,
    SQL_ANALYSIS_CONFIG_KEY,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.errors.setting_help.main.setting_help import setting_help
from sqlbuild.errors.setting_help.main.setting_note import setting_note


def effective_sql_analysis(discovered_inputs: DiscoveredProjectInputs) -> bool:
    """Return the project SQL analysis setting after local overrides."""

    if SQL_ANALYSIS_CONFIG_KEY in discovered_inputs.local_config.setting_overrides:
        return discovered_inputs.local_config.settings.sql_analysis
    return discovered_inputs.project_config.settings.sql_analysis


def sql_analysis_off_note_and_help(
    *, discovered_inputs: DiscoveredProjectInputs, purpose: str
) -> tuple[str, str]:
    """Return a note naming the file that turns SQL analysis off and help to turn it on."""

    file_name: str = (
        LOCAL_CONFIG_FILENAME
        if SQL_ANALYSIS_CONFIG_KEY in discovered_inputs.local_config.setting_overrides
        else PROJECT_CONFIG_FILENAME
    )
    return (
        setting_note(
            file_name=file_name, section=SETTINGS_SECTION, key=SQL_ANALYSIS_CONFIG_KEY, value=False
        ),
        setting_help(
            purpose=purpose,
            file_name=file_name,
            section=SETTINGS_SECTION,
            key=SQL_ANALYSIS_CONFIG_KEY,
            value=True,
        ),
    )


def microbatch_concurrency_note() -> str:
    """State that concurrent microbatches are off in the project file."""

    return setting_note(
        file_name=PROJECT_CONFIG_FILENAME,
        section=SETTINGS_SECTION,
        key=MICROBATCH_CONCURRENCY_SETTING_KEY,
        value=False,
        explicit=None,
    )


def microbatch_concurrency_help() -> str:
    """Show the exact setting that allows `batch_concurrency` above one."""

    return setting_help(
        purpose="to run microbatches concurrently",
        file_name=PROJECT_CONFIG_FILENAME,
        section=SETTINGS_SECTION,
        key=MICROBATCH_CONCURRENCY_SETTING_KEY,
        value=True,
    )


def explicit_references_help(*, allowed: str) -> str:
    """Show the exact migration setting that relaxes explicit references, with its value."""

    note: str = setting_note(
        file_name=PROJECT_CONFIG_FILENAME,
        section=REFERENCES_SECTION,
        key=ENFORCE_EXPLICIT_REFERENCES_KEY,
        value=True,
        explicit=None,
    )
    return f"{note}; " + setting_help(
        purpose=f"while migrating a project, to allow {allowed}",
        file_name=PROJECT_CONFIG_FILENAME,
        section=REFERENCES_SECTION,
        key=ENFORCE_EXPLICIT_REFERENCES_KEY,
        value=False,
    )

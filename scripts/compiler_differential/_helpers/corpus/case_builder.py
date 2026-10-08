"""Build failure cases as small edits of the shared base project."""

from scripts.compiler_differential.constants import (
    FAILURE_BASE_CONFIG,
    FAILURE_BASE_FILES,
    FAILURE_CONFIG_PATH,
    FAILURE_MART_PATH,
    FAILURE_STAGING_PATH,
)
from scripts.compiler_differential.models import FailureCase

_MART_HEADER: str = 'MODEL (\n  description "Order totals per customer",\n);\n\n'


def failure_case(
    *,
    name: str,
    expected_code: str,
    files: dict[str, str],
    expected_warning_code: str | None = None,
    expected_message: str | None = None,
    expected_help: str | None = None,
    expected_notes: tuple[str, ...] = (),
    expected_location: tuple[int, int] | None = None,
    expected_codes: tuple[str, ...] | None = None,
) -> FailureCase:
    """Return the base project with `files` added or replaced; notes are whole note lines."""

    return FailureCase(
        files={**FAILURE_BASE_FILES, **files},
        name=name,
        expected_code=expected_code,
        expected_warning_code=expected_warning_code,
        expected_message=expected_message,
        expected_help=expected_help,
        expected_notes=expected_notes,
        expected_location=expected_location,
        expected_codes=expected_codes,
    )


def staging_files(sql: str) -> dict[str, str]:
    """Replace the staging model."""

    return {FAILURE_STAGING_PATH: sql}


def mart_body_files(body: str) -> dict[str, str]:
    """Replace the mart model's query, keeping its header."""

    return {FAILURE_MART_PATH: _MART_HEADER + body}


def config_files(extra: str) -> dict[str, str]:
    """Append `extra` to the base project configuration."""

    return {FAILURE_CONFIG_PATH: FAILURE_BASE_CONFIG + extra}

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.authored_values.main._optional_bool import optional_bool
from sqlbuild.compiler.authored_values.main._optional_mapping import optional_mapping
from sqlbuild.compiler.authored_values.main._optional_named_bool import optional_named_bool
from sqlbuild.compiler.authored_values.main._optional_named_string import (
    optional_named_string,
)
from sqlbuild.compiler.authored_values.main._optional_non_empty_string import (
    optional_non_empty_string,
)
from sqlbuild.compiler.authored_values.main._optional_string_tuple import (
    optional_string_tuple,
)
from sqlbuild.compiler.authored_values.main._require_non_empty_string import (
    require_non_empty_string,
)

AUTHORED_VALUES_FILE_PATH: Path = Path("models/orders.yml")
AUTHORED_VALUES_LABEL: str = "model 'orders'"


class AuthoredValueTestError(Exception):
    """Error class injected into authored value parsers under test."""


def _entry(raw_value: object | None) -> dict[str, object]:
    return {"setting": raw_value}


def parse_required_string(raw_value: object | None) -> object:
    return require_non_empty_string(
        entry=_entry(raw_value),
        key="setting",
        file_path=AUTHORED_VALUES_FILE_PATH,
        label=AUTHORED_VALUES_LABEL,
        error_class=AuthoredValueTestError,
    )


def parse_optional_string(raw_value: object | None) -> object:
    return optional_non_empty_string(
        entry=_entry(raw_value),
        key="setting",
        file_path=AUTHORED_VALUES_FILE_PATH,
        label=AUTHORED_VALUES_LABEL,
        error_class=AuthoredValueTestError,
    )


def parse_named_string(raw_value: object | None) -> object:
    return optional_named_string(
        raw_value=raw_value,
        file_path=AUTHORED_VALUES_FILE_PATH,
        label=AUTHORED_VALUES_LABEL,
        key="setting",
        error_class=AuthoredValueTestError,
    )


def parse_optional_bool(raw_value: object | None) -> object:
    return optional_bool(
        entry=_entry(raw_value),
        key="setting",
        file_path=AUTHORED_VALUES_FILE_PATH,
        label=AUTHORED_VALUES_LABEL,
        error_class=AuthoredValueTestError,
    )


def parse_named_bool_default_false(raw_value: object | None) -> object:
    return optional_named_bool(
        raw_value=raw_value,
        file_path=AUTHORED_VALUES_FILE_PATH,
        label=AUTHORED_VALUES_LABEL,
        key="setting",
        error_class=AuthoredValueTestError,
        default=False,
    )


def parse_named_bool_default_none(raw_value: object | None) -> object:
    return optional_named_bool(
        raw_value=raw_value,
        file_path=AUTHORED_VALUES_FILE_PATH,
        label=AUTHORED_VALUES_LABEL,
        key="setting",
        error_class=AuthoredValueTestError,
        default=None,
    )


def parse_optional_mapping(raw_value: object | None) -> object:
    return optional_mapping(
        entry=_entry(raw_value),
        key="setting",
        file_path=AUTHORED_VALUES_FILE_PATH,
        label=AUTHORED_VALUES_LABEL,
        error_class=AuthoredValueTestError,
    )


def parse_optional_string_tuple(raw_value: object | None) -> object:
    return optional_string_tuple(
        entry=_entry(raw_value),
        key="setting",
        file_path=AUTHORED_VALUES_FILE_PATH,
        label=AUTHORED_VALUES_LABEL,
        error_class=AuthoredValueTestError,
    )

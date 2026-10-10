"""Raise a native config stage's exact error as the Python stage raises it."""

from __future__ import annotations

from collections.abc import Mapping

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.discovery.exceptions import DiscoveryConflictError
from sqlbuild.compiler.model_config.constants import (
    CONFIG_VALUE_TYPE_ERROR,
    DISCOVERY_CONFLICT_ERROR,
    EXPECTED_STRING,
    RESOURCE_IDENTITY_ERROR,
)
from sqlbuild.compiler.resource_names.exceptions import ResourceIdentityError
from sqlbuild.spec.contracts.exceptions import ConfigValueTypeError


def native_config_error(
    *,
    error: _native.NativeConfigError,
    values: Mapping[str, object] | None = None,
) -> Exception:
    """Return the exception class `error` names, with its message, code and help."""

    if error.class_name == CONFIG_VALUE_TYPE_ERROR and error.key is not None and values is not None:
        return ConfigValueTypeError(
            key=error.key, expected=EXPECTED_STRING, actual_type=type(values[error.key])
        )
    if error.class_name == RESOURCE_IDENTITY_ERROR:
        return ResourceIdentityError(error.message, help=error.help)
    if error.class_name == DISCOVERY_CONFLICT_ERROR:
        return DiscoveryConflictError(error.message, help=error.help)
    return CompileInputError(error.message, code=error.code, help=error.help)

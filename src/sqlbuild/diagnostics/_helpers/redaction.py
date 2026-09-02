"""Secret-safe diagnostic record rendering."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Final

from sqlbuild.diagnostics.constants import FORMATTER_RECORD_FIELDS, SQL_TEXT_FIELD

_REDACTED: Final[str] = "[REDACTED]"
_SECRET_FIELD_PARTS: Final[tuple[str, ...]] = (
    "access_key",
    "api_key",
    "authorization",
    "client_secret",
    "credential",
    "dsn",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
)
_SECRET_VALUE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(api[-_]?key|access[-_]?key|private[-_]?key|authorization|"
    r"client[-_]?secret|refresh[-_]?token|"
    r"password|passwd|pwd|secret|token|dsn|connection_string)"
    r"(\s*[=:]\s*)(\"[^\"\r\n]{0,512}\"|'[^'\r\n]{0,512}'|[^\s,;]{1,512})"
)
_AUTHORIZATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(authorization)(\s*[=:]\s*)(?:basic|bearer)\s+"
    r"(\"[^\"\r\n]{1,512}\"|'[^'\r\n]{1,512}'|[^\s,;]{1,512})"
)
_BEARER_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{1,512}")
_URI_CREDENTIAL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@]+)(@)"
)
_STANDARD_RECORD_FIELDS: Final[frozenset[str]] = frozenset(logging.makeLogRecord({}).__dict__)


def redact_text(value: str) -> str:
    """Redact obvious named secrets and URI passwords from diagnostic text."""

    authorization_redacted: str = _AUTHORIZATION_PATTERN.sub(rf"\1\2{_REDACTED}", value)
    bearer_redacted: str = _BEARER_PATTERN.sub(f"Bearer {_REDACTED}", authorization_redacted)
    named_redacted: str = _SECRET_VALUE_PATTERN.sub(rf"\1\2{_REDACTED}", bearer_redacted)
    return _URI_CREDENTIAL_PATTERN.sub(rf"\1{_REDACTED}\3", named_redacted)


def redact_value(*, name: str, value: object) -> object:
    """Return a persistence-safe value for one structured logging field."""

    lowered_name: str = name.lower().replace("-", "_")
    if any(part in lowered_name for part in _SECRET_FIELD_PARTS):
        return _REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): redact_value(name=str(key), value=item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(name=name, value=item) for item in value]
    try:
        return redact_text(str(value))
    except Exception:
        return f"<{type(value).__name__}>"


def safe_extra_fields(record: logging.LogRecord) -> dict[str, object]:
    """Collect redacted non-standard fields without evaluating arbitrary formatters."""

    return {
        key: redact_value(name=key, value=value)
        for key, value in record.__dict__.items()
        if key not in _STANDARD_RECORD_FIELDS
        and key not in FORMATTER_RECORD_FIELDS
        and key != SQL_TEXT_FIELD
    }

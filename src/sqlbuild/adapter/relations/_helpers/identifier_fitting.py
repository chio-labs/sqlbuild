"""Fit generated relation names within identifier limits measured in UTF-8 bytes."""

from __future__ import annotations

import hashlib

from sqlbuild.adapter.relations.constants import SHORTENED_LOGICAL_NAME_HASH_LENGTH
from sqlbuild.errors.contracts.exceptions import SharedInputError


def fit_artifact_logical_name_impl(
    *, logical_name: str, fixed_prefix: str, identifier_limit: int, artifact_label: str
) -> str:
    """Fit a readable logical component with a deterministic hash suffix."""

    max_logical_length: int = identifier_limit - _byte_length(fixed_prefix)
    if max_logical_length < 1:
        raise SharedInputError(
            f"{artifact_label} prefix '{fixed_prefix}' does not fit within identifier "
            f"limit {identifier_limit}"
        )
    if _byte_length(logical_name) <= max_logical_length:
        return logical_name

    suffix_length: int = SHORTENED_LOGICAL_NAME_HASH_LENGTH + 1
    if max_logical_length <= suffix_length:
        raise SharedInputError(
            f"{artifact_label} name for '{logical_name}' cannot fit within identifier "
            f"limit {identifier_limit}"
        )
    logical_hash: str = hashlib.sha256(logical_name.encode("utf-8")).hexdigest()[
        :SHORTENED_LOGICAL_NAME_HASH_LENGTH
    ]
    prefix_length: int = max_logical_length - suffix_length
    return f"{_truncate_bytes(value=logical_name, max_bytes=prefix_length)}_{logical_hash}"


def fit_auxiliary_relation_name_impl(*, base_name: str, suffix: str, identifier_limit: int) -> str:
    """Append a suffix, shortening the base with a stable hash when the whole name is too long."""

    if _byte_length(base_name) + _byte_length(suffix) <= identifier_limit:
        return f"{base_name}{suffix}"
    hash_part: str = (
        "_"
        + hashlib.sha256(base_name.encode("utf-8")).hexdigest()[:SHORTENED_LOGICAL_NAME_HASH_LENGTH]
    )
    kept_length: int = identifier_limit - _byte_length(suffix) - len(hash_part)
    if kept_length < 1:
        raise SharedInputError(
            f"auxiliary relation suffix '{suffix}' for '{base_name}' cannot fit within "
            f"identifier limit {identifier_limit}"
        )
    return f"{_truncate_bytes(value=base_name, max_bytes=kept_length)}{hash_part}{suffix}"


def _byte_length(value: str) -> int:
    return len(value.encode("utf-8"))


def _truncate_bytes(*, value: str, max_bytes: int) -> str:
    """Keep the longest prefix whose UTF-8 encoding fits, never splitting a character."""

    return value.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")

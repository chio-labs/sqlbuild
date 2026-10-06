"""Identifier-limit fitting implementations for generated relation names."""

from __future__ import annotations

import hashlib

from sqlbuild.adapter.relations.constants import SHORTENED_LOGICAL_NAME_HASH_LENGTH
from sqlbuild.errors.contracts.exceptions import SharedInputError


def fit_artifact_logical_name_impl(
    *, logical_name: str, fixed_prefix: str, identifier_limit: int, artifact_label: str
) -> str:
    """Fit a readable logical component with a deterministic hash suffix."""

    max_logical_length: int = identifier_limit - len(fixed_prefix)
    if max_logical_length < 1:
        raise SharedInputError(
            f"{artifact_label} prefix '{fixed_prefix}' does not fit within identifier "
            f"limit {identifier_limit}"
        )
    if len(logical_name) <= max_logical_length:
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
    return f"{logical_name[:prefix_length]}_{logical_hash}"


def fit_auxiliary_relation_name_impl(*, base_name: str, suffix: str, identifier_limit: int) -> str:
    """Append a suffix, shortening the base with a stable hash when the whole name is too long."""

    if len(base_name) + len(suffix) <= identifier_limit:
        return f"{base_name}{suffix}"
    hash_part: str = (
        "_"
        + hashlib.sha256(base_name.encode("utf-8")).hexdigest()[:SHORTENED_LOGICAL_NAME_HASH_LENGTH]
    )
    kept_length: int = identifier_limit - len(suffix) - len(hash_part)
    if kept_length < 1:
        raise SharedInputError(
            f"auxiliary relation suffix '{suffix}' for '{base_name}' cannot fit within "
            f"identifier limit {identifier_limit}"
        )
    return f"{base_name[:kept_length]}{hash_part}{suffix}"

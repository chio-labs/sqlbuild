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

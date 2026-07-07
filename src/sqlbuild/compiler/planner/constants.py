"""Planner domain constants."""

from __future__ import annotations

from sqlbuild.shared.constants import (
    SCENARIO_HASH_PREFIX_LENGTH as SHARED_SCENARIO_HASH_PREFIX_LENGTH,
)
from sqlbuild.shared.constants import (
    SCENARIO_SHORTENED_LOGICAL_HASH_LENGTH as SHARED_SCENARIO_SHORTENED_LOGICAL_HASH_LENGTH,
)

PATH_SELECTOR_EXPLICIT_ROOT_ERROR: str = (
    "path selectors require an explicit root: use 'models/', 'tasks/', 'assets/', "
    "'checks/', or 'loaders/'"
)
MICROBATCH_START_SENTINEL: str = "__SQB_CURSOR_START__"
MICROBATCH_END_SENTINEL: str = "__SQB_CURSOR_END__"
METADATA_NAME_FILTER_LIMIT: int = 250
SCENARIO_HASH_PREFIX_LENGTH: int = SHARED_SCENARIO_HASH_PREFIX_LENGTH
SCENARIO_SHORTENED_LOGICAL_HASH_LENGTH: int = SHARED_SCENARIO_SHORTENED_LOGICAL_HASH_LENGTH
SCENARIO_DEFAULT_IDENTIFIER_LIMIT: int = 63

"""Planner domain constants."""

from __future__ import annotations

from sqlbuild.cursor_algebra.main.sentinel_to_token import sentinel_to_token
from sqlbuild.cursor_algebra.types import BoundSentinel

PATH_SELECTOR_EXPLICIT_ROOT_ERROR: str = (
    "path selectors require an explicit root: use 'models/', 'tasks/', 'assets/', "
    "'checks/', or 'loaders/'"
)
EMPTY_FINGERPRINT_METADATA_JSON: str = "{}"
MODEL_SELECTOR_ROOT: str = "models"
MODEL_SELECTOR_ROOT_PREFIX: str = "models/"
SELECTOR_MISSING_NAME_ERROR_FRAGMENT: str = "no name"
PATH_SELECTOR_SEPARATOR: str = "~"
SELECTOR_KIND_SEPARATOR: str = ":"
SELECTOR_PATH_SEPARATOR: str = "/"
EMPTY_SELECTOR_PATH: str = ""
POLYGLOT_CUSTOM_DATA_TYPE_NAME: str = "CUSTOM"
SQL_FUNCTION_CALL_OPEN_PAREN: str = "("
SQL_ALIAS_BOUNDARY_CHARACTERS: frozenset[str] = frozenset("),;")
SQL_ALIAS_KEYWORD: str = "AS"
SQL_IDENTIFIER_LEADING_CHARACTERS: frozenset[str] = frozenset("[_")
SOURCE_ALIAS_BOUNDARY_CHARACTERS: frozenset[str] = frozenset(",);")
SQL_BRACKETED_IDENTIFIER_START: str = "["
SQL_QUOTED_IDENTIFIER_DELIMITERS: frozenset[str] = frozenset({'"', "`"})
POLYGLOT_ALIAS_VALUE_KEY: str = "this"
SOURCE_DEFERRAL_CONTEXT_FIELDS: frozenset[str] = frozenset({"schema", "database"})
UNIFIED_DIFF_ADDITION_PREFIX: str = "+"
UNIFIED_DIFF_ADDITION_HEADER_PREFIX: str = "+++"
UNIFIED_DIFF_REMOVAL_PREFIX: str = "-"
UNIFIED_DIFF_REMOVAL_HEADER_PREFIX: str = "---"
SELECTOR_EXPANSION_MARKER: str = "+"
MODEL_CUSTOM_CONFIG_KEY: str = "config"
MODEL_PLACEHOLDERS_CONFIG_KEY: str = "placeholders"
MODEL_PRE_HOOKS_CONFIG_KEY: str = "pre_hooks"
MODEL_POST_HOOKS_CONFIG_KEY: str = "post_hooks"
MODEL_CONTRACT_CONFIG_KEY: str = "contract"
MICROBATCH_START_SENTINEL: str = sentinel_to_token(sentinel=BoundSentinel.START)
MICROBATCH_END_SENTINEL: str = sentinel_to_token(sentinel=BoundSentinel.END)
METADATA_NAME_FILTER_LIMIT: int = 250
SCENARIO_ARTIFACT_PREFIX: str = "__sqb_"
SCENARIO_HASH_PREFIX_LENGTH: int = 12
SCENARIO_SHORTENED_LOGICAL_HASH_LENGTH: int = 8
SCENARIO_ARTIFACT_KINDS: tuple[str, ...] = ("source", "ref", "seed", "dbt_ref", "model")
SCENARIO_DEFAULT_IDENTIFIER_LIMIT: int = 63
SCENARIO_PLAN_INVALID_HASH_PREFIX: str = "S501"
SCENARIO_PLAN_HASH_COLLISION: str = "S502"
SCENARIO_PLAN_RELATION_COLLISION: str = "S503"
SCENARIO_PLAN_GRAPH_VALIDATION: str = "S504"
SCENARIO_PLAN_SQLGLOT_UNAVAILABLE: str = "S505"
SCENARIO_PLAN_SQLGLOT_PARSE: str = "S506"
SCENARIO_PLAN_UNKNOWN_SEED: str = "S507"
SCENARIO_PLAN_MISSING_FIXTURE_SQL: str = "S508"
SCENARIO_PLAN_MISSING_RELATION_TARGET: str = "S509"
SCENARIO_PLAN_INTERNAL: str = "S599"

WHOLE_DAY_CURSOR_GRAINS: frozenset[str] = frozenset({"day", "month", "year"})

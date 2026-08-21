"""Kata engine constants."""

KATA_SKILL_PATHS: tuple[str, ...] = (
    ".agents/skills/sqlbuild-kata/SKILL.md",
    ".claude/skills/sqlbuild-kata/SKILL.md",
    ".opencode/skills/sqlbuild-kata/SKILL.md",
)

KATA_SKILLS_COMMAND: str = "skills"

AST_COLUMN_KIND: str = "column"
AST_ALIAS_KIND: str = "alias"
AST_LITERAL_KIND: str = "literal"
AST_SELECT_KIND: str = "select"
AST_STAR_KIND: str = "star"
AST_FUNCTION_KIND: str = "function"
AST_TABLE_KIND: str = "table"
DEPENDENCY_FUNCTIONS: frozenset[str] = frozenset({"__ref", "__source"})
CROSS_JOIN_KIND: str = "CROSS"
CONTRACT_ENFORCED: str = "enforced"
MATERIALIZED_VIEW: str = "view"
REFERENCE_KIND_REF: str = "ref"
LAYER_INT_CLEAN: str = "int_clean"
LAYER_INT_ENRICHED: str = "int_enriched"
LAYER_INT_VIEW: str = "int_v"

BOOLEAN_TYPE: str = "BOOLEAN"
DATE_TYPE: str = "DATE"
TIMESTAMP_TYPE: str = "TIMESTAMP"

CANONICAL_NUMERIC_LITERALS: frozenset[str] = frozenset({"-1", "0", "1"})
FINAL_CTE_NAMES: frozenset[str] = frozenset({"final", "final_cte"})
SET_OPERATION_BY_NAME: str = " BY NAME"

MODEL_NAME_PART_COUNT: int = 3
NAMED_CTE_TUPLE_SIZE: int = 2
MAX_ENTITY_PARTS: int = 2
DECLARATION_DOMAIN_PART_COUNT: int = 3
TARGET_DIRECTORY_NAME: str = "target"
SQL_LINE_COMMENT: str = "--"
SQL_BLOCK_COMMENT: str = "/*"
EVALUATE_RULE_CALL: str = "evaluate_rule"
CANONICAL_ONE: str = "1"
KATA_DECORATOR_TOKEN: str = "@kata"
KATA_DIRECTORY_NAME: str = "kata"
PARENT_DIRECTORY_TOKEN: str = ".."
RULE_CHECK_PARAMETER_NAMES: tuple[str, str] = ("model", "ctx")

MIN_AUDITS_PER_MODEL: str = "min_audits_per_model"
MIN_TESTS_PER_MODEL: str = "min_tests_per_model"
MIN_CUSTOM_RULE_TEST_CASES: str = "min_custom_rule_test_cases"
CUSTOM_RULE_COVERAGE_CODE: str = "KTX201"
KATA_THRESHOLD_DEFAULTS: dict[str, int] = {
    MIN_AUDITS_PER_MODEL: 1,
    MIN_TESTS_PER_MODEL: 1,
    MIN_CUSTOM_RULE_TEST_CASES: 1,
}

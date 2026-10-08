pub(crate) const DATETIME_TYPE: &str = "DATETIME";
pub(crate) const DBT_REF_REFERENCE_KIND: &str = "dbt_ref";
pub(crate) const DIRECT_DEPENDENCY_PATH_LENGTH: usize = 2;
pub(crate) const MACRO_TEST_MODE: &str = "macro";
pub(crate) const QUOTED_IDENTIFIER_DELIMITER_BYTES: usize = 2;
/// Keywords after which a trailing projection token is an operand, not an implicit alias.
pub(crate) const OPERAND_KEYWORDS: &[&str] = &[
    "AND", "OR", "NOT", "IS", "IN", "LIKE", "ILIKE", "SIMILAR", "BETWEEN", "CASE", "WHEN", "THEN",
    "ELSE", "DISTINCT", "ALL", "ANY", "SOME", "EXISTS", "COLLATE", "ESCAPE", "INTERVAL", "ZONE",
    "OVER", "AS",
];
/// Keywords that end an expression, so a trailing one is part of it rather than an implicit alias.
pub(crate) const VALUE_KEYWORDS: &[&str] = &["NULL", "TRUE", "FALSE", "UNKNOWN", "END"];
/// Characters after which a trailing projection token is an operand, not an implicit alias.
pub(crate) const OPERATOR_CHARACTERS: &str = "+-*/%=<>|&^~!:.,";
/// A projection that selects every column.
pub(crate) const SELECT_STAR_PROJECTION: &str = "*";
pub(crate) const SQL_TEST_ACTUAL_CTE: &str = "__actual";
pub(crate) const SQL_TEST_EXPECTED_CTE: &str = "__expected";
pub(crate) const SQL_TEST_ACTUAL_CTE_PREFIX: &str = "__actual__";
pub(crate) const TABLE_FUNCTION_TEST_MODE: &str = "table_fn";
pub(crate) const UDF_TEST_MODE: &str = "udf";
pub(crate) const UNKNOWN_SQL_TYPE: &str = "UNKNOWN";
pub(crate) const VARCHAR_SQL_TYPE: &str = "VARCHAR";
pub(crate) const WITH_KEYWORD: &str = "with";
/// Clause keywords that end a WITH list at their parenthesis depth.
pub(crate) const WITH_LIST_ENDING_CLAUSES: &[&str] = &[
    "select",
    "from",
    "where",
    "group",
    "having",
    "qualify",
    "order",
    "limit",
    "window",
    "union",
    "except",
    "intersect",
    "minus",
    "values",
    "insert",
    "update",
    "delete",
    "merge",
];

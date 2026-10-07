//! Reference call prefixes and the contexts Python names in reference errors.

use crate::sql_references::types::ReferencePrefix;

/// Call prefixes with their kinds and error names, in Python's matching order.
pub(crate) const REFERENCE_PREFIXES: [ReferencePrefix; 6] = [
    (b"__dbt_ref(", "dbt_ref", "__dbt_ref"),
    (b"__table_fn(", "table_fn", "__table_fn"),
    (b"__source(", "source", "__source"),
    (b"__seed(", "seed", "__seed"),
    (b"__udf(", "udf", "__udf"),
    (b"__ref(", "ref", "__ref"),
];
pub(crate) const DBT_REFERENCE_KIND: &str = "dbt_ref";
pub(crate) const TABLE_FUNCTION_REFERENCE_KIND: &str = "table_fn";
pub(crate) const REFERENCE_CONTEXT: &str = "SQL reference";
pub(crate) const TABLE_FUNCTION_CALL_CONTEXT: &str = "SQL table function call";
/// Line comment prefixes Python's reference and parenthesis scans both stop at.
pub(crate) const SUPPORTED_LINE_COMMENT_PREFIXES: [&str; 3] = ["--", "//", "#"];
/// Characters that may start a comment or quoted text under a supported syntax.
pub(crate) const NON_CODE_START_BYTES: &[u8] = b"-/#'\"`$";
/// Non-code openers whose text an argument keeps; comments become one space.
pub(crate) const QUOTE_BYTES: &[u8] = b"'\"`$";
/// Shortest quoted reference name: the opening and closing quote.
pub(crate) const PAIRED_QUOTE_LENGTH: usize = 2;
/// Quotes that delimit a reference name.
pub(crate) const NAME_QUOTE_BYTES: &[u8] = b"'\"";
/// Python `str.isspace()` for ASCII characters.
pub(crate) const PYTHON_ASCII_WHITESPACE: &[u8] = b" \t\n\x0b\x0c\r\x1c\x1d\x1e\x1f";

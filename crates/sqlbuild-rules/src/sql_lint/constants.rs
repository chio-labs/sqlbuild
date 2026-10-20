pub(crate) const CAST_TYPE_SEPARATOR_KEYWORD: &str = "AS";
pub(crate) const CLOSE_PARENTHESIS: &str = ")";
pub(crate) const LINT_API_VERSION: u32 = 1;
pub(crate) const OPEN_PARENTHESIS: &str = "(";
pub(crate) const POSITION_ARGUMENT_SEPARATOR: &str = ",";
pub(crate) const CTE_MACRO_PLACEHOLDER_LITERAL: &str = "1";
pub(crate) const POSTFIX_CAST_PREFIX_TOKEN_COUNT: usize = 2;
pub(crate) const RELATION_MODIFIER_KEYWORDS: [&str; 43] = [
    "ANTI",
    "APPLY",
    "ASOF",
    "AT",
    "BEFORE",
    "CHANGES",
    "CONNECT",
    "CROSS",
    "EXCEPT",
    "FETCH",
    "FINAL",
    "FOR",
    "FULL",
    "GROUP",
    "HAVING",
    "INNER",
    "INTERSECT",
    "JOIN",
    "LATERAL",
    "LEFT",
    "LIMIT",
    "MATCH_RECOGNIZE",
    "MINUS",
    "NATURAL",
    "OFFSET",
    "ON",
    "ORDER",
    "OUTER",
    "PASTE",
    "PIVOT",
    "POSITIONAL",
    "QUALIFY",
    "RETURNING",
    "RIGHT",
    "SAMPLE",
    "SEMI",
    "START",
    "TABLESAMPLE",
    "UNION",
    "UNPIVOT",
    "USING",
    "WHERE",
    "WINDOW",
];
/// The parts of a `SQBRSQL038` message that names its joined relation and CTE.
pub(crate) const CROSS_JOIN_PREFIX: &str = "CROSS JOIN with `";
pub(crate) const CROSS_JOIN_CTE_MARKER: &str = "` in CTE `";
pub(crate) const CROSS_JOIN_SUFFIX: &str = "` creates an explicit cartesian product";
/// The `SQBRSQL038` message for a join whose relation cannot be named.
pub(crate) const CROSS_JOIN_UNNAMED_MESSAGE: &str = "CROSS JOIN creates an explicit cartesian product with an unnamed relation; only a file-wide exception (rule and path) can cover it";
/// Stands for the finding's project-relative path until the caller that knows it fills it in.
pub(crate) const CROSS_JOIN_PATH_PLACEHOLDER: &str = "<path of this file>";
pub(crate) const CROSS_JOIN_REASON_PLACEHOLDER: &str = "<why this deviation is intentional>";

//! Keyword classes that decide which authored tokens may change letter case.

/// Keywords that stay keywords wherever they appear outside qualified names and aliases.
pub(crate) const ALWAYS_KEYWORDS: [&str; 38] = [
    "SELECT",
    "FROM",
    "WHERE",
    "JOIN",
    "ON",
    "BY",
    "AS",
    "AND",
    "OR",
    "NOT",
    "IN",
    "IS",
    "LIKE",
    "ILIKE",
    "BETWEEN",
    "EXISTS",
    "CASE",
    "WHEN",
    "THEN",
    "ELSE",
    "END",
    "NULL",
    "TRUE",
    "FALSE",
    "ALL",
    "DISTINCT",
    "ASC",
    "DESC",
    "DEFAULT",
    "PRECEDING",
    "FOLLOWING",
    "UNBOUNDED",
    "CURRENT_DATE",
    "CURRENT_TIME",
    "CURRENT_TIMESTAMP",
    "BOTH",
    "LEADING",
    "TRAILING",
];
/// Keywords that continue a keyword phrase after `AS` rather than naming an alias.
pub(crate) const AFTER_AS_KEYWORDS: [&str; 8] = [
    "SELECT",
    "WITH",
    "VALUES",
    "OF",
    "STRUCT",
    "VALUE",
    "MATERIALIZED",
    "NOT",
];
/// Keywords after which a keyword-typed word starts a new operand rather than a phrase.
pub(crate) const OPERAND_INTRODUCERS: [&str; 33] = [
    "SELECT",
    "FROM",
    "JOIN",
    "WHERE",
    "AND",
    "OR",
    "ON",
    "BY",
    "WHEN",
    "THEN",
    "ELSE",
    "AS",
    "IN",
    "NOT",
    "IS",
    "HAVING",
    "QUALIFY",
    "SET",
    "RETURNING",
    "DISTINCT",
    "ALL",
    "USING",
    "WITH",
    "LIMIT",
    "OFFSET",
    "VALUES",
    "CASE",
    "BETWEEN",
    "LIKE",
    "ILIKE",
    "EXISTS",
    "TOP",
    "RECURSIVE",
];
/// Keywords after which a keyword-typed word names a relation.
pub(crate) const RELATION_INTRODUCERS: [&str; 5] = ["FROM", "JOIN", "INTO", "UPDATE", "TABLE"];
/// Keywords that may directly follow `FROM` or `JOIN` without naming a relation.
pub(crate) const RELATION_POSITION_KEYWORDS: [&str; 6] =
    ["LATERAL", "UNNEST", "VALUES", "ONLY", "TABLE", "SELECT"];
/// Tokens that end an expression, so a keyword-typed word before them is an operand.
pub(crate) const OPERAND_FOLLOWERS: [&str; 31] = [
    ",", ")", "]", ";", "=", "<", ">", "<=", ">=", "<>", "!=", "+", "-", "*", "/", "%", "||", "::",
    ":=", "=>", "->", "->>", "AS", "FROM", "WHERE", "THEN", "ELSE", "WHEN", "ASC", "DESC", "IN",
];
pub(crate) const OPERAND_FOLLOWER_KEYWORDS: [&str; 7] =
    ["END", "AND", "OR", "IS", "NOT", "LIKE", "ILIKE"];
/// `BETWEEN` follows an operand only where an operand may start; elsewhere it is a frame bound.
pub(crate) const RANGE_PREDICATE: &str = "BETWEEN";

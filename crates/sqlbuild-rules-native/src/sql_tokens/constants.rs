//! Token positions that decide which authored words may change letter case.

use polyglot_sql::tokens::TokenType;

/// Column aliases after `AS` may be any keyword in DuckDB and PostgreSQL.
pub(crate) const ALIAS_KEYWORD: &str = "AS";
/// The token that turns a preceding name into a function call.
pub(crate) const CALL_OPENER: &str = "(";
/// Field names after `.`, path keys after `:`, and parameter names after `@` or `$`.
pub(crate) const NAME_PREFIXES: [&str; 4] = [".", ":", "@", "$"];
/// Built-in calls with keyword syntax inside their parentheses, which catalogues do not list.
pub(crate) const CALL_SYNTAX_FUNCTIONS: [&str; 6] = [
    "CAST",
    "TRY_CAST",
    "SAFE_CAST",
    "EXTRACT",
    "CONVERT",
    "TRY_CONVERT",
];

pub(crate) const PROJECTION_ENDS: [TokenType; 13] = [
    TokenType::From,
    TokenType::Where,
    TokenType::Group,
    TokenType::GroupBy,
    TokenType::Having,
    TokenType::Qualify,
    TokenType::Order,
    TokenType::OrderBy,
    TokenType::Limit,
    TokenType::Window,
    TokenType::Union,
    TokenType::Except,
    TokenType::Intersect,
];

//! TOML values as SQLBuild writes them into configuration text.

/// A boolean, integer, string or array literal.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TomlLiteral {
    Bool(bool),
    /// An integer, as its decimal text.
    Integer(String),
    Text(String),
    Array(Vec<TomlLiteral>),
}

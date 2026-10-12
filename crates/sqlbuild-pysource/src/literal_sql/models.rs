//! A function source to read literal SQL from, and the literal SQL calls found in it.

/// A dedented function source, its first line in the file, and the interpreter it runs on.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FunctionSource<'a> {
    pub text: &'a str,
    pub start_line: usize,
    /// The prefix of the numbered stand-ins for interpolated f-string values.
    pub placeholder: &'a str,
    pub python_version: (u8, u8),
}

/// One context SQL call with literal SQL: the method, the SQL text and its line in the file.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LiteralSql {
    pub method: String,
    pub sql: String,
    pub line: usize,
}

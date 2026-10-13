//! Header spans, header rule violations and the parser the rules read header values with.

/// One located DSL header; offsets are character positions.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HeaderSpan {
    pub kind: String,
    pub start: usize,
    pub end: usize,
}

/// Whether a header violation blocks formatting.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HeaderSeverity {
    Fault,
    Warning,
}

/// One header rule violation at a one-based line and column.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HeaderViolation {
    pub line: usize,
    pub column: usize,
    pub code: &'static str,
    pub message: String,
    pub severity: HeaderSeverity,
    pub remediation: String,
}

/// The line width and description length the header rules enforce.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct HeaderRulesConfig {
    pub line_width: i64,
    pub max_description_lines: usize,
}

/// Why a header failed to parse: the error's text and help.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParseFailure {
    pub message: String,
    pub help: Option<String>,
}

/// One header parse: values, a header syntax error, or another error the caller raised.
pub enum ParseOutcome<V, E> {
    Parsed(V),
    Rejected(ParseFailure),
    Raised(E, ParseFailure),
}

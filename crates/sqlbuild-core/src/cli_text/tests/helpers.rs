use crate::cli_text::models::{DiagnosticText, LocationText};

/// A location in `models/a.sql`, whose text has a CRLF line, a non-ASCII name and a vertical tab.
pub(super) fn location(line: i64, column: i64, end: (Option<i64>, Option<i64>)) -> LocationText {
    LocationText {
        path: "models/a.sql".to_owned(),
        line,
        column,
        end_line: end.0,
        end_column: end.1,
        source: Some("SELECT 1\r\nFROM orders\u{e9} x\u{0b}third".to_owned()),
    }
}

/// A diagnostic with only its severity, code and message set.
pub(super) fn diagnostic(severity: &str, code: &str, message: &str) -> DiagnosticText {
    DiagnosticText {
        severity: severity.to_owned(),
        code: code.to_owned(),
        message: message.to_owned(),
        resource_type: None,
        resource_name: None,
        location: None,
        path: None,
        related: Vec::new(),
        notes: Vec::new(),
        affected_rules: Vec::new(),
        help: None,
        occurrences: 1,
    }
}

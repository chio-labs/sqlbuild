use crate::semantic_validation::models::DiagnosticRow;

pub(super) const MODEL: &str =
    "MODEL (\n  description \"Orders\"\n);\n\nSELECT o.amount, o.missing\nFROM orders AS o";
pub(super) const QUERY: &str = "SELECT o.amount, o.missing\nFROM orders AS o";

fn row(
    code: &str,
    message: &str,
    position: (Option<usize>, Option<usize>),
    span: (Option<usize>, Option<usize>),
    severity: &str,
) -> DiagnosticRow {
    DiagnosticRow {
        code: code.to_owned(),
        message: message.to_owned(),
        line: position.0,
        column: position.1,
        start: span.0,
        end: span.1,
        severity: severity.to_owned(),
    }
}

fn missing_column() -> DiagnosticRow {
    row(
        "E201",
        "Unknown column 'missing'",
        (Some(1), Some(17)),
        (Some(17), Some(24)),
        "error",
    )
}

pub(super) fn one_missing_column() -> Vec<DiagnosticRow> {
    vec![missing_column()]
}

pub(super) fn repeated_rows() -> Vec<DiagnosticRow> {
    let warning: DiagnosticRow = row("W1", "warn", (Some(1), Some(1)), (None, None), "warning");
    vec![
        row("B000", "x", (Some(1), Some(1)), (Some(0), Some(1)), "error"),
        missing_column(),
        missing_column(),
        warning.clone(),
        warning,
    ]
}

pub(super) fn unmapped_row() -> Vec<DiagnosticRow> {
    vec![row(
        "E1",
        "no position",
        (Some(2), Some(3)),
        (None, None),
        "error",
    )]
}

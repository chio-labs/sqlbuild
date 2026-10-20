use crate::semantic_validation::models::DiagnosticRow;

/// `(code, line, column, (line, column, end line, end column))` of one reported diagnostic.
pub(super) type LocatedCase = (
    &'static str,
    Option<usize>,
    Option<usize>,
    Option<(usize, usize, Option<usize>, Option<usize>)>,
);

/// A model's texts, its raw binding rows, and the diagnostics compile reports for them.
pub(super) struct LocateBindingDiagnosticsTestCase {
    pub(super) description: &'static str,
    pub(super) authored: &'static str,
    pub(super) query: &'static str,
    pub(super) rows: fn() -> Vec<DiagnosticRow>,
    pub(super) expected_located: &'static [LocatedCase],
}

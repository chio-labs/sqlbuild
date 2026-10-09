use crate::semantic_checks::models::SemanticDeferral;

/// One located `(code, message, help, notes, location)` diagnostic of a completed project.
pub(crate) type DescribedDiagnostic = (
    String,
    String,
    Option<String>,
    Vec<String>,
    Option<(i64, i64, Option<i64>, Option<i64>)>,
);

pub(crate) struct ProjectionSpanTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) dialect: Option<&'static str>,
    pub(crate) expected_spans: Result<&'static [(usize, usize)], SemanticDeferral>,
}

pub(crate) struct ParsedFactsTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_aliases: &'static [(&'static str, &'static str)],
    pub(crate) expected_unaliased: &'static [&'static str],
}

pub(crate) struct ClosestColumnTestCase {
    pub(crate) description: &'static str,
    pub(crate) name: &'static str,
    pub(crate) columns: &'static [(&'static str, &'static str)],
    pub(crate) expected_closest: Result<Option<&'static str>, SemanticDeferral>,
    pub(crate) expected_order: Result<&'static [&'static str], SemanticDeferral>,
}

pub(crate) struct SentenceMessageTestCase {
    pub(crate) description: &'static str,
    pub(crate) message: &'static str,
    pub(crate) expected_sentence: Result<&'static str, SemanticDeferral>,
    pub(crate) expected_missing:
        Result<Option<(&'static str, Option<&'static str>)>, SemanticDeferral>,
}

pub(crate) struct ComparisonHelpTestCase {
    pub(crate) description: &'static str,
    pub(crate) types: &'static [&'static str],
    pub(crate) dialect: Option<&'static str>,
    pub(crate) expected_help: &'static str,
}

pub(crate) struct TypeRecoveryTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: Option<&'static str>,
    pub(crate) errors: bool,
    pub(crate) revised: &'static [(&'static str, Option<i64>, Option<i64>)],
    pub(crate) expected_status: &'static str,
    pub(crate) expected_poisoned: &'static [(&'static str, &'static str)],
    pub(crate) expected_revalidated: &'static [usize],
    pub(crate) expected_kept: &'static [(usize, Option<&'static str>)],
    pub(crate) expected_bindings: &'static [&'static [usize]],
}

pub(crate) struct CompletionTestCase {
    pub(crate) description: &'static str,
    pub(crate) non_ascii_comment: bool,
    pub(crate) without_diagnostics: bool,
    pub(crate) expected_deferral: Option<&'static str>,
    pub(crate) expected_diagnostics: Vec<DescribedDiagnostic>,
    pub(crate) expected_bindings: Option<Vec<Vec<usize>>>,
}

pub(crate) struct OperandTypeTestCase {
    pub(crate) description: &'static str,
    pub(crate) joined: &'static str,
    pub(crate) shapes: &'static [(&'static str, &'static [(&'static str, &'static str)])],
    pub(crate) expected_diagnostics: Vec<DescribedDiagnostic>,
}

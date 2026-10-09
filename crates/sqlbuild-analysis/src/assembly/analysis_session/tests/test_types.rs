use crate::assembly::analysis_session::models::PivotOutcome;

/// A model as `(name, sql, source names, model refs)`.
pub(crate) type ModelSpec = (
    &'static str,
    &'static str,
    &'static [&'static str],
    &'static [&'static str],
);

pub(crate) struct SessionTestCase {
    pub(crate) description: &'static str,
    pub(crate) models: &'static [ModelSpec],
    /// `step_lines` of each step, in order.
    pub(crate) expected_steps: &'static [&'static [&'static str]],
    /// `described` of each model's outcome, in request order.
    pub(crate) expected_outcomes: &'static [&'static [&'static str]],
}

pub(crate) struct SessionFactsTestCase {
    pub(crate) description: &'static str,
    pub(crate) models: &'static [ModelSpec],
    /// `fact_lines` of each model, in request order.
    pub(crate) expected_facts: &'static [&'static str],
}

pub(crate) struct UnscheduledTestCase {
    pub(crate) description: &'static str,
    pub(crate) models: &'static [ModelSpec],
    pub(crate) expected_started: bool,
}

pub(crate) struct ExpressionShapeTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: &'static str,
    pub(crate) case_sensitive_shapes: bool,
    pub(crate) expression: &'static str,
    pub(crate) expected_shape: &'static str,
}

pub(crate) struct DictTestCase {
    pub(crate) description: &'static str,
    pub(crate) pairs: &'static [(&'static str, &'static str)],
    pub(crate) expected_dict: &'static [(&'static str, &'static str)],
}

pub(crate) struct WavesTestCase {
    pub(crate) description: &'static str,
    pub(crate) producers: &'static [&'static [usize]],
    pub(crate) expected_waves: Option<&'static [&'static [usize]]>,
}

pub(crate) struct PivotTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: &'static str,
    pub(crate) sql: &'static str,
    /// `(pivot column, value column, aggregate)` of one `amounts` family, or none declared.
    pub(crate) family: Option<(&'static str, &'static str, &'static str)>,
    pub(crate) expected_outcome: PivotOutcome,
}

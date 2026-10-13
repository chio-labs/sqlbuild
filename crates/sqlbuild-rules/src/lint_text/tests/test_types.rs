use crate::lint_text::models::{Neutralized, RetainedViolation};

pub(crate) struct NeutralizeTestCase {
    pub(crate) description: &'static str,
    pub(crate) body: &'static str,
    pub(crate) formatting: bool,
    pub(crate) expected_text: &'static str,
    pub(crate) expected_sites: Vec<(&'static str, usize, usize)>,
}

pub(crate) struct ParameterTestCase {
    pub(crate) description: &'static str,
    pub(crate) body: &'static str,
    pub(crate) neutralize: fn(&str) -> Neutralized,
    pub(crate) expected_text: &'static str,
}

pub(crate) struct RestoreTestCase {
    pub(crate) description: &'static str,
    pub(crate) body: &'static str,
    pub(crate) fixed: &'static str,
    pub(crate) expected_restored: Result<String, String>,
}

pub(crate) struct TokenAtTestCase {
    pub(crate) description: &'static str,
    pub(crate) body: &'static str,
    pub(crate) start: usize,
    pub(crate) expected_token: Option<&'static str>,
}

pub(crate) struct SuppressionTestCase {
    pub(crate) description: &'static str,
    pub(crate) contents: &'static str,
    pub(crate) violations: Vec<(usize, &'static str)>,
    pub(crate) allow: bool,
    pub(crate) expected_retained: Vec<RetainedViolation>,
}

pub(crate) struct FormatBodiesTestCase {
    pub(crate) description: &'static str,
    pub(crate) relative_parts: Option<Vec<String>>,
    pub(crate) contents: &'static str,
    pub(crate) expected_formatted: Vec<(usize, String)>,
    pub(crate) expected_fault_lines: Vec<usize>,
}

pub(crate) struct LintBodiesTestCase {
    pub(crate) description: &'static str,
    pub(crate) contents: &'static str,
    pub(crate) body: crate::lint_text::models::LintSqlBody,
    pub(crate) expected_findings: Vec<Finding<'static>>,
}

/// One mapped finding: code, line, column and optional end position.
pub(crate) type Finding<'a> = (&'a str, i64, i64, Option<(i64, i64)>);

pub(super) struct FormatSettingsTestCase {
    pub(super) description: &'static str,
    pub(super) project_toml: &'static str,
    pub(super) local_toml: &'static str,
    pub(super) expected_settings: crate::lint_text::models::FormatSettings,
}

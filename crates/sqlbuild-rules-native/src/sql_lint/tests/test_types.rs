pub(crate) struct LintTestCase {
    pub description: &'static str,
    pub sql: &'static str,
    pub expected_codes: &'static [&'static str],
    pub expected_anchors: &'static [(&'static str, &'static str)],
}

pub(crate) struct EmptyFixtureLintTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) allows_empty_fixture_star: bool,
    pub(crate) expected_diagnostic_count: usize,
}

pub(crate) struct BatchLintTestCase {
    pub(crate) description: &'static str,
    pub(crate) queries: &'static [&'static str],
    pub(crate) expected_responses: usize,
}

pub(crate) struct LintMetadataTestCase {
    pub description: &'static str,
    pub sql: &'static str,
    pub expected_code: &'static str,
    pub expected_message: &'static str,
    pub expected_remediation: &'static str,
}

pub(crate) struct LintFixTestCase {
    pub description: &'static str,
    pub sql: &'static str,
    pub expected_code: &'static str,
    pub expected_replacement: Option<&'static str>,
}

pub(crate) struct AdditionalLintRuleTestCase {
    pub description: &'static str,
    pub sql: &'static str,
    pub rule: &'static str,
    pub expected_anchor: Option<&'static str>,
    pub expected_replacement: Option<&'static str>,
}

pub(crate) struct CeremonialCteLintTestCase {
    pub description: &'static str,
    pub sql: &'static str,
    pub expected_count: usize,
    pub expected_start: Option<u64>,
}

pub(crate) struct PlainSqlLintTestCase {
    pub description: &'static str,
    pub sql: &'static str,
    pub rule: &'static str,
    pub expected_count: usize,
}

pub(crate) struct DynamicOutputStarLintTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_count: usize,
    pub(crate) expected_prefix: &'static str,
}

pub(crate) struct DependencyImportLintTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) dependency_identifiers: &'static [&'static str],
    pub(crate) expected_count: usize,
}

pub(crate) struct DialectLintRuleTestCase {
    pub description: &'static str,
    pub sql: &'static str,
    pub dialect: &'static str,
    pub rule: &'static str,
    pub expected_count: usize,
    pub expected_fix: bool,
    pub expected_reason: &'static str,
}

pub(crate) struct FormatTestCase {
    pub description: &'static str,
    pub sql: &'static str,
    pub expected_sql: &'static str,
    pub expected_changed: bool,
}

pub(crate) struct InvalidRuleTestCase {
    pub description: &'static str,
    pub rule: &'static str,
    pub expected_message: &'static str,
}

pub(crate) struct FunctionDepthTestCase {
    pub description: &'static str,
    pub depth: usize,
    pub expected_diagnostic_count: usize,
}

pub(crate) struct FunctionDepthFailureTestCase {
    pub description: &'static str,
    pub depth: usize,
    pub expected_code: &'static str,
    pub expected_limit: &'static str,
}

pub(crate) struct AuthoredTokenTestCase {
    pub description: &'static str,
    pub authored: &'static str,
    pub generated: &'static str,
    /// `None` when the formatter must refuse the change.
    pub expected_sql: Option<&'static str>,
}

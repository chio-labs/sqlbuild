use crate::audits::_helpers::parameters::RenderStop;
use crate::audits::models::{AuditAttachment, AuditRendering, ParameterRenderStop};

pub(super) struct ParameterizedSqlTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_sql: Result<&'static str, RenderStop>,
}

pub(super) struct UnusedArgumentsTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    /// Argument names, each passed as the text `<name>-value`.
    pub(super) arguments: &'static [&'static str],
    pub(super) expected_sql: Result<&'static str, ParameterRenderStop>,
}

pub(super) struct AttachedAuditTestCase {
    pub(super) description: &'static str,
    pub(super) attachment: AuditAttachment,
    pub(super) expected_rendering: AuditRendering,
}

pub(super) struct SingularResourcesTestCase {
    pub(super) description: &'static str,
    pub(super) references: Vec<(&'static str, &'static str)>,
    pub(super) expected_resources: Vec<(&'static str, &'static str)>,
    pub(super) expected_problem: Option<&'static str>,
}

pub(super) struct AuditPoliciesTestCase {
    pub(super) description: &'static str,
    pub(super) severity: (Option<&'static str>, Option<&'static str>),
    pub(super) run_scope: (Option<&'static str>, Option<&'static str>),
    pub(super) expected_policies: Result<(&'static str, &'static str), &'static str>,
}

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

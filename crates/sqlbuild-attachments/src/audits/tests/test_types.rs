use crate::audits::_helpers::parameters::RenderStop;
use crate::audits::models::{AuditAttachment, AuditRendering};

pub(super) struct ParameterizedSqlTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) reject_unused: bool,
    pub(super) expected_sql: Result<&'static str, RenderStop>,
}

pub(super) struct AttachedAuditTestCase {
    pub(super) description: &'static str,
    pub(super) attachment: AuditAttachment,
    /// None where Python must decide.
    pub(super) expected_rendering: Option<AuditRendering>,
}

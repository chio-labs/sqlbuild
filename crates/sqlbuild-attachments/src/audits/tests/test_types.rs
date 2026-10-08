use crate::audits::models::AuditAttachment;

pub(super) struct ParameterizedSqlTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) reject_unused: bool,
    pub(super) expected_sql: Option<&'static str>,
}

pub(super) struct AttachedAuditTestCase {
    pub(super) description: &'static str,
    pub(super) attachment: AuditAttachment,
    /// `(sql body, evidence, severity, run scope source)` spelled as text, or None to defer.
    pub(super) expected_rendering: Option<&'static str>,
}

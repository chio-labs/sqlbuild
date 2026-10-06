use crate::models::{DeclarationIdentity, Diagnostic, SqlValue};

pub(super) struct IdentityTextTestCase {
    pub(super) description: &'static str,
    pub(super) identity: DeclarationIdentity,
    pub(super) expected_text: &'static str,
}

pub(super) struct IdentityOrderTestCase {
    pub(super) description: &'static str,
    pub(super) identities: Vec<DeclarationIdentity>,
    pub(super) expected_texts: Vec<&'static str>,
}

pub(super) struct DiagnosticOrderTestCase {
    pub(super) description: &'static str,
    pub(super) diagnostics: Vec<Diagnostic>,
    pub(super) expected_codes: Vec<&'static str>,
    pub(super) expected_errors: Vec<bool>,
}

pub(super) struct SqlTypeNameTestCase {
    pub(super) description: &'static str,
    pub(super) value: SqlValue,
    pub(super) expected_name: &'static str,
}

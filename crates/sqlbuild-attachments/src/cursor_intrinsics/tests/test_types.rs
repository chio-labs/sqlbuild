use crate::cursor_intrinsics::models::IntrinsicCheck;

pub(super) struct IntrinsicCheckTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_check: IntrinsicCheck,
}

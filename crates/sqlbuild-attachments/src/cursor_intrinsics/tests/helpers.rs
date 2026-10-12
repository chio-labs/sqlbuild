use crate::cursor_intrinsics::models::IntrinsicCheck;

pub(super) fn rejected(message: &str) -> IntrinsicCheck {
    IntrinsicCheck::Rejected(message.to_owned())
}

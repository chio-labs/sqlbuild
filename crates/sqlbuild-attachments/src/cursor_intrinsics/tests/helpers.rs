use sqlbuild_core::text::main::python_text::python_text;
use sqlbuild_core::text::models::PythonText;

use crate::cursor_intrinsics::models::IntrinsicCheck;

pub(super) fn rejected(message: &str) -> IntrinsicCheck {
    IntrinsicCheck::Rejected(message.to_owned())
}

pub(super) fn python() -> PythonText {
    python_text((3, 12), "15.0.0").expect("Python 3.12 is supported")
}

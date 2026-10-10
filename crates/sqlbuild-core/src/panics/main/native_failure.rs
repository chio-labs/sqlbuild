use crate::constants::NATIVE_FAILURE_PREFIX;

/// An internal native failure the boundary raises as `NativeCompilerError`; a caught panic keeps
/// its own message.
pub fn native_failure(context: &str, reason: &str) -> String {
    if reason.starts_with(NATIVE_FAILURE_PREFIX) {
        format!("{reason} ({context})")
    } else {
        format!("{NATIVE_FAILURE_PREFIX}{context}: {reason}")
    }
}

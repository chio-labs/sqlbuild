use crate::constants::NATIVE_FAILURE_PREFIX;

/// Whether `message` is a caught panic or another native internal failure.
pub fn is_compiler_panic(message: &str) -> bool {
    message.starts_with(NATIVE_FAILURE_PREFIX)
}

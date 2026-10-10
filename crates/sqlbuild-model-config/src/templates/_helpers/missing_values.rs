//! The template errors Python's `coalesce` treats as a missing value.

const MISSING_VALUE_PARTS: [&str; 3] = [
    "references missing ENV variable",
    "references unknown variable",
    "references unknown CTX key",
];
const UNAVAILABLE_CONTEXT_PART: &str = "references CTX key";
const NO_VALUE_PART: &str = "no value is available";

/// Whether Python's `coalesce` treats this error message as a missing value and skips it.
pub(crate) fn is_missing_value_message(message: &str) -> bool {
    MISSING_VALUE_PARTS
        .iter()
        .any(|part| message.contains(part))
        || (message.contains(UNAVAILABLE_CONTEXT_PART) && message.contains(NO_VALUE_PART))
}

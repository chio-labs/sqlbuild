//! Authored SQL-test mode identifiers.

pub(crate) const MODEL_TEST_MODE: &str = "model";
/// The rule codes whose fixes `sqb format --fix` may apply after compiler verification.
pub(crate) const SAFE_RULE_FIX_CODES: [&str; 8] = [
    "SQBRSQL002",
    "SQBRSQL003",
    "SQBRSQL005",
    "SQBRSQL006",
    "SQBRSQL008",
    "SQBRSQL017",
    "SQBRSQL025",
    "SQBRSQL042",
];
/// The note attached to a rule finding that has an available fix.
pub(crate) const RULE_FIX_AVAILABLE_NOTE: &str =
    "Fix available: `sqb format --fix` applies it after compiler verification";
pub(crate) const RULES_NATIVE_API_VERSION: i64 = 1;

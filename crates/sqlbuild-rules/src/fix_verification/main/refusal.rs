use crate::fix_verification::models::FixEligibility;

/// Refuse edits whose model ownership or dialect lacks a semantic proof.
pub fn refusal(facts: &FixEligibility) -> Option<&'static str> {
    if !facts.model_body {
        Some("Compiler-verified Rule fixes currently require a model SQL body")
    } else if facts.has_fix && !facts.safe_code {
        Some("This proposed rewrite is not proven meaning-preserving in this dialect")
    } else if facts.conditionless_join && !facts.snowflake {
        Some("Conditionless JOIN equivalence is only established for Snowflake")
    } else {
        None
    }
}

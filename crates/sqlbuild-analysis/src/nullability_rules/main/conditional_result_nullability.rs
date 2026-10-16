//! The nullability of an IF/IFF-style conditional from its two result arguments.

use crate::assembly::analysis_session::constants::{
    NON_NULL_NULLABILITY, NULLABLE_NULLABILITY, UNKNOWN_NULLABILITY,
};

/// Non-null when both results are, nullable when either is, otherwise unknown.
pub fn conditional_result_nullability(arguments: &[&str]) -> &'static str {
    let [_, when_true, when_false, ..] = arguments else {
        return UNKNOWN_NULLABILITY;
    };
    if *when_true == NON_NULL_NULLABILITY && *when_false == NON_NULL_NULLABILITY {
        return NON_NULL_NULLABILITY;
    }
    if *when_true == NULLABLE_NULLABILITY || *when_false == NULLABLE_NULLABILITY {
        return NULLABLE_NULLABILITY;
    }
    UNKNOWN_NULLABILITY
}

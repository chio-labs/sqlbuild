//! The plan warning for sources whose freshness could not be observed.

use crate::planner_warehouse::constants::{
    FRESHNESS_ERROR, FRESHNESS_ERROR_EXPLANATION, FRESHNESS_NAME_LIMIT, FRESHNESS_UNAVAILABLE,
    FRESHNESS_UNAVAILABLE_EXPLANATION, SOURCE_FRESHNESS_UNKNOWN_WARNING_TITLE,
};

/// The warning for one explained reason, or `None` for reasons that need no warning.
pub fn freshness_unknown_message(reason: &str, names: &[String]) -> Option<String> {
    let explanation = if reason == FRESHNESS_UNAVAILABLE {
        FRESHNESS_UNAVAILABLE_EXPLANATION
    } else if reason == FRESHNESS_ERROR {
        FRESHNESS_ERROR_EXPLANATION
    } else {
        return None;
    };
    let mut ordered: Vec<&String> = names.iter().collect();
    ordered.sort();
    let mut shown = ordered
        .iter()
        .take(FRESHNESS_NAME_LIMIT)
        .map(|name| name.as_str())
        .collect::<Vec<_>>()
        .join(", ");
    if ordered.len() > FRESHNESS_NAME_LIMIT {
        shown = format!("{shown} and {} more", ordered.len() - FRESHNESS_NAME_LIMIT);
    }
    Some(format!(
        "{SOURCE_FRESHNESS_UNKNOWN_WARNING_TITLE} ({reason}) for {shown}: {explanation}; run sqb freshness for each source's details"
    ))
}

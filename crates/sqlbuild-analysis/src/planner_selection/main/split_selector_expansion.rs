//! Split `+selector+` marker syntax from the selector core without resolving the core.

use crate::planner_selection::constants::EXPANSION_MARKER;
use crate::planner_selection::models::SelectorExpansion;

/// The core and expansion flags, or the input error message.
pub fn split_selector_expansion(raw: &str) -> Result<SelectorExpansion, String> {
    let stripped: &str = raw.trim_matches(char::is_whitespace);
    if stripped.is_empty() {
        return Err("empty selector".to_owned());
    }
    let core: &str = stripped
        .trim_start_matches(EXPANSION_MARKER)
        .trim_end_matches(EXPANSION_MARKER);
    if core.is_empty() {
        return Err(format!(
            "selector '{stripped}' has no name after removing '+' markers"
        ));
    }
    if core.contains(EXPANSION_MARKER) {
        return Err(format!(
            "selector '{stripped}' contains '+' in an unsupported position"
        ));
    }
    Ok(SelectorExpansion {
        core: core.to_owned(),
        upstream: stripped.starts_with(EXPANSION_MARKER),
        downstream: stripped.ends_with(EXPANSION_MARKER),
    })
}

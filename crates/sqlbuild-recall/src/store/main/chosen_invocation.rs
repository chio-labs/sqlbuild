//! `chosen_invocation`: the one invocation a selector names among the IDs it matched.

use crate::store::constants::{LAST_INVOCATION_SELECTOR as LAST, LISTED_INVOCATION_CANDIDATES};
use crate::store::errors::{StoreError, StoreErrorKind};

/// The invocation `selector` names among `candidates`, the IDs it prefixes (at most [`LISTED_INVOCATION_CANDIDATES`] and one more, in ID order): an exact match, else the only candidate; none or several fail, several listing the candidates.
pub fn chosen_invocation(selector: &str, candidates: &[String]) -> Result<String, StoreError> {
    if let Some(exact) = candidates.iter().find(|candidate| *candidate == selector) {
        return Ok(exact.clone());
    }
    match candidates {
        [] => Err(StoreError::new(
            StoreErrorKind::NotFound,
            if selector == LAST {
                "no invocations are recorded yet".to_owned()
            } else {
                format!("no recorded invocation matches '{selector}'")
            },
        )),
        [only] => Ok(only.clone()),
        several => {
            let listed: &[String] = &several[..several.len().min(LISTED_INVOCATION_CANDIDATES)];
            Err(StoreError::new(
                StoreErrorKind::Ambiguous,
                format!(
                    "'{selector}' matches several invocations; use a longer prefix: {}{}",
                    listed.join(", "),
                    if several.len() > listed.len() {
                        ", and more"
                    } else {
                        ""
                    }
                ),
            ))
        }
    }
}

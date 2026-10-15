//! The strict reserved query-diff artifact name format.

use crate::janitor_planning::_helpers::name_parts::{
    after_marker, leading_number, strip_prefix_folded,
};
use crate::janitor_planning::constants::{
    ARTIFACT_RUN_HEX_DIGITS, DATE_DIGITS, QUERY_DIFF_ARTIFACT_PREFIX, QUERY_DIFF_SIDES,
    TIME_DIGITS, YEAR_DIGITS,
};

/// The artifact's run id and folded side, or `None` when the name is not a query-diff artifact.
#[must_use]
pub fn query_diff_artifact_parts(name: &str) -> Option<(String, String)> {
    let run_and_side: &str = strip_prefix_folded(name, QUERY_DIFF_ARTIFACT_PREFIX)?;
    let (_, rest) = leading_number(run_and_side, YEAR_DIGITS + 2 * DATE_DIGITS)?;
    let rest: &str = after_marker(rest, 'T')?;
    let (_, rest) = leading_number(rest, 3 * TIME_DIGITS)?;
    let rest: &str = after_marker(rest, 'Z')?;
    let rest: &str = rest.strip_prefix('_')?;
    let hex: &str = rest.get(..ARTIFACT_RUN_HEX_DIGITS)?;
    if !hex.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return None;
    }
    let side: &str = rest.get(ARTIFACT_RUN_HEX_DIGITS..)?.strip_prefix('_')?;
    let folded: String = side.to_ascii_lowercase();
    if !QUERY_DIFF_SIDES.contains(&folded.as_str()) {
        return None;
    }
    let run_id: &str = run_and_side.get(..run_and_side.len() - side.len() - 1)?;
    Some((run_id.to_owned(), folded))
}

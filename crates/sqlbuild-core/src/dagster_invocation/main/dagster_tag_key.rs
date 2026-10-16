//! The default Dagster translator's tag key for one SQLBuild tag.

use crate::dagster_invocation::_helpers::names::replace_runs;
use crate::dagster_invocation::constants::{NAME_SEPARATOR, TAG_KEY_PUNCTUATION};

/// `re.sub(r"[^A-Za-z0-9_.\-/]+", "_", value).strip("_")`.
#[must_use]
pub fn dagster_tag_key(value: &str) -> String {
    replace_runs(value, |character| {
        character.is_ascii_alphanumeric()
            || character == NAME_SEPARATOR
            || TAG_KEY_PUNCTUATION.contains(&character)
    })
    .trim_matches(NAME_SEPARATOR)
    .to_owned()
}

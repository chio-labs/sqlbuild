//! Token positions where some dialect accepts even a reserved word as an unquoted name.

use crate::sql_tokens::constants::{ALIAS_KEYWORD, NAME_PREFIXES};

/// Return, for every upper-cased token, whether it follows `.`, `:`, `@`, `$` or `AS`.
pub(crate) fn name_positions(uppers: &[String]) -> Vec<bool> {
    let mut positions = Vec::with_capacity(uppers.len());
    let mut previous: Option<&str> = None;
    for upper in uppers {
        positions.push(
            previous.is_some_and(|word| word == ALIAS_KEYWORD || NAME_PREFIXES.contains(&word)),
        );
        previous = Some(upper.as_str());
    }
    positions
}

//! The model a test's progress rows are grouped under.

use crate::test_command::constants::UNKNOWN_GROUP;

/// The first model with expected rows, else the first model, else `(unknown)`.
#[must_use]
pub fn test_group_name(chain: &[(String, bool)]) -> String {
    chain
        .iter()
        .find(|(_, expected)| *expected)
        .or_else(|| chain.first())
        .map_or_else(|| UNKNOWN_GROUP.to_owned(), |(model, _)| model.clone())
}

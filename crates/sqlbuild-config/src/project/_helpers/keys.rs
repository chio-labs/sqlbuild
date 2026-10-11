//! Rejection of unknown and removed keys in configuration mappings.

use crate::models::ConfigValue;
use crate::project::constants::{LISTED_SUPPORTED_KEYS_LIMIT, SUGGESTION_CUTOFF};
use crate::project::errors::ConfigFailure;
use crate::project::models::ConfigFile;
use crate::project::types::{Entries, Loaded};
use sqlbuild_core::text::main::close_matches::close_matches;

/// Where a mapping lives: its file and the label messages name it by.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Place<'a> {
    pub(crate) file: ConfigFile,
    pub(crate) label: &'a str,
}

fn sorted_unique<'a>(keys: impl IntoIterator<Item = &'a str>) -> Vec<&'a str> {
    let mut sorted: Vec<&str> = keys.into_iter().collect();
    sorted.sort_unstable();
    sorted.dedup();
    sorted
}

fn key_text(key: &ConfigValue) -> &str {
    match key {
        ConfigValue::String(text) => text,
        _ => "",
    }
}

fn has_key(mapping: &Entries, key: &str) -> bool {
    mapping
        .iter()
        .any(|(candidate, _)| key_text(candidate) == key)
}

fn unknown_keys<'a>(mapping: &'a Entries, allowed: &[&str]) -> Vec<&'a str> {
    sorted_unique(
        mapping
            .iter()
            .map(|(key, _)| key_text(key))
            .filter(|key| !allowed.contains(key)),
    )
}

/// `unsupported_keys_help`: the nearest supported key for each unsupported key.
pub(crate) fn unsupported_keys_help(keys: &[&str], supported: &[&str]) -> String {
    let candidates = sorted_unique(supported.iter().copied());
    let suggestions: Vec<String> = keys
        .iter()
        .filter_map(|key| {
            let nearest = close_matches(key, &candidates, 1, SUGGESTION_CUTOFF)
                .into_iter()
                .next()?;
            Some(if keys.len() == 1 {
                format!("'{nearest}'")
            } else {
                format!("'{nearest}' for '{key}'")
            })
        })
        .collect();
    if !suggestions.is_empty() {
        return format!("did you mean {}?", suggestions.join(", "));
    }
    if candidates.len() <= LISTED_SUPPORTED_KEYS_LIMIT {
        return format!("supported keys: {}", candidates.join(", "));
    }
    "remove the key; see the reference for supported keys".to_owned()
}

/// `_validate_allowed_keys`: reject keys outside `allowed`, listing the allowed keys.
pub(crate) fn validate_allowed_keys(
    mapping: &Entries,
    allowed: &[&str],
    place: Place<'_>,
) -> Result<(), ConfigFailure> {
    let unknown = unknown_keys(mapping, allowed);
    if unknown.is_empty() {
        return Ok(());
    }
    let listed = sorted_unique(allowed.iter().copied()).join(", ");
    Err(ConfigFailure::at(
        place.file,
        format!(
            "{} contains unknown key(s): {}. Allowed keys: {listed}",
            place.label,
            unknown.join(", ")
        ),
    )
    .with_help(unsupported_keys_help(&unknown, allowed)))
}

/// `reject_unknown_mapping_keys`: the same check with the shared YAML-section wording.
pub(crate) fn reject_unknown_mapping_keys(
    mapping: &Entries,
    allowed: &[&str],
    place: Place<'_>,
) -> Loaded<()> {
    let unknown = unknown_keys(mapping, allowed);
    if unknown.is_empty() {
        return Ok(());
    }
    let listed = sorted_unique(allowed.iter().copied()).join(", ");
    Err(ConfigFailure::at(
        place.file,
        format!(
            "{} has unknown keys: {}; allowed keys: {listed}",
            place.label,
            unknown.join(", ")
        ),
    )
    .with_help(unsupported_keys_help(&unknown, allowed)))
}

/// `_reject_removed_virtual_keys`: options removed with virtual environments.
pub(crate) fn reject_removed_virtual_keys(
    mapping: &Entries,
    removed: &[&str],
    place: Place<'_>,
) -> Loaded<()> {
    let present = sorted_unique(removed.iter().copied().filter(|key| has_key(mapping, key)));
    if present.is_empty() {
        return Ok(());
    }
    Err(ConfigFailure::at(
        place.file,
        format!(
            "[{}] option(s) {} were removed with virtual environments; projects run in direct mode",
            place.label,
            present.join(", ")
        ),
    ))
}

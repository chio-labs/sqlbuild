//! Optional enrichment removed from the parts of a record.

use crate::integration_results::constants::{
    MICROBATCH_KEYS, OPTIONAL_ASSET_ENRICHMENT, OPTIONAL_CHECK_ENRICHMENT,
    OPTIONAL_MICROBATCH_ENUMS,
};
use crate::json::models::JsonValue;

type Entries = Vec<(String, JsonValue)>;

fn without(entries: Entries, dropped: &[&str]) -> Entries {
    entries
        .into_iter()
        .filter(|(key, _)| !dropped.contains(&key.as_str()))
        .collect()
}

/// Whether a microbatch key survives: known, and not an optional enumeration.
fn core_microbatch_key(key: &str) -> bool {
    MICROBATCH_KEYS.contains(&key) && !OPTIONAL_MICROBATCH_ENUMS.contains(&key)
}

fn stripped_microbatch(microbatch: Entries) -> Entries {
    microbatch
        .into_iter()
        .filter(|(key, _)| core_microbatch_key(key))
        .collect()
}

fn stripped_asset_field((name, item): (String, JsonValue)) -> (String, JsonValue) {
    match (name.as_str(), item) {
        ("microbatch", JsonValue::Object(microbatch)) => {
            (name, JsonValue::Object(stripped_microbatch(microbatch)))
        }
        (_, item) => (name, item),
    }
}

fn stripped_asset(asset: Entries) -> Entries {
    without(asset, &OPTIONAL_ASSET_ENRICHMENT)
        .into_iter()
        .map(stripped_asset_field)
        .collect()
}

fn stripped_check(check: JsonValue) -> JsonValue {
    match check {
        JsonValue::Object(check) => JsonValue::Object(without(check, &OPTIONAL_CHECK_ENRICHMENT)),
        other => other,
    }
}

pub(crate) fn stripped_field((key, value): (String, JsonValue)) -> (String, JsonValue) {
    match (key.as_str(), value) {
        ("asset", JsonValue::Object(asset)) => (key, JsonValue::Object(stripped_asset(asset))),
        ("checks", JsonValue::Array(checks)) => (
            key,
            JsonValue::Array(checks.into_iter().map(stripped_check).collect()),
        ),
        (_, value) => (key, value),
    }
}

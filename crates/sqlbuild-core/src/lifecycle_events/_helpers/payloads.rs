//! Event-family payload rules: statements, operations, microbatches, skips, retries and runs.

use std::collections::BTreeSet;

use crate::lifecycle_events::_helpers::fields::field_problem;
use crate::lifecycle_events::_helpers::fields::{catalogued, get, integer};
use crate::lifecycle_events::constants::{
    AUDIT_RUN_COUNT_FIELDS, CONFIGURED_CONCURRENCY_FIELD, FORBIDDEN_STATEMENT_PAYLOAD_FIELDS,
    HOOK_NAME_MAX_TAIL, HOOK_PHASES, HOOK_TYPES, METADATA_FIELD, MICROBATCH_EVENT_PREFIX,
    MICROBATCH_KINDS, MICROBATCH_RUN_TYPES, MICROBATCH_STRATEGIES, OPERATION_ADAPTERS,
    OPERATION_EVENT_PREFIX, OPERATION_KINDS, OPERATION_METADATA_FIELDS, OPERATION_NAMES,
    OPERATION_PHASES, OPERATION_SCOPES, OPERATION_STRATEGIES, OPERATION_TARGET_KINDS,
    RESOURCE_ATTEMPT_SKIPPED_EVENT, RESOURCE_SKIP_CODES, RESOURCE_SKIP_MODES,
    RETRY_SCHEDULED_EVENT, RUN_STARTED_EVENT, RUN_TERMINALS, STATEMENT_EVENT_PREFIX,
};
use crate::lifecycle_events::models::{KnownEventFacts, PayloadValue};
use crate::lifecycle_events::types::PayloadCheck;

type Payload = [(String, PayloadValue)];

/// Every forbidden SQL or parameter key anywhere in a statement payload.
pub(crate) fn forbidden_statement_fields(value: &PayloadValue) -> BTreeSet<String> {
    let mut found: BTreeSet<String> = BTreeSet::new();
    match value {
        PayloadValue::Object(entries) => {
            for (key, item) in entries {
                if FORBIDDEN_STATEMENT_PAYLOAD_FIELDS.contains(&key.as_str()) {
                    found.insert(key.clone());
                }
                found.extend(forbidden_statement_fields(item));
            }
        }
        PayloadValue::Array(items) => {
            for item in items {
                found.extend(forbidden_statement_fields(item));
            }
        }
        _ => {}
    }
    found
}

pub(crate) fn safe_hook_name(name: &str) -> bool {
    let mut characters = name.chars();
    let Some(first) = characters.next() else {
        return false;
    };
    (first.is_ascii_alphabetic() || first == '_')
        && name.len() <= HOOK_NAME_MAX_TAIL + 1
        && characters.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

fn uncatalogued(payload: &Payload, name: &str, allowed: &[&str]) -> bool {
    get(payload, name).is_some_and(|value| !catalogued(Some(value), allowed))
}

/// Catalogued operation dimensions, hook identity and allowlisted metadata counts.
pub(crate) fn operation_problem(payload: &Payload) -> Option<String> {
    if uncatalogued(payload, "operation_kind", &OPERATION_KINDS) {
        return Some("operation_kind must be a catalogued value".to_owned());
    }
    if uncatalogued(payload, "operation_name", &OPERATION_NAMES) {
        return Some("operation_name must be a catalogued value".to_owned());
    }
    let dimensions: [(&str, &[&str]); 5] = [
        ("phase", &OPERATION_PHASES),
        ("strategy", &OPERATION_STRATEGIES),
        ("target_kind", &OPERATION_TARGET_KINDS),
        ("adapter", &OPERATION_ADAPTERS),
        ("scope", &OPERATION_SCOPES),
    ];
    for (name, allowed) in dimensions {
        if uncatalogued(payload, name, allowed) {
            return Some(format!("{name} must be a catalogued value"));
        }
    }
    let hook_fields = ["hook_phase", "hook_type", "hook_index", "hook_name"];
    if hook_fields.iter().any(|name| get(payload, name).is_some()) {
        if !catalogued(get(payload, "hook_phase"), &HOOK_PHASES) {
            return Some("hook_phase must be a catalogued value".to_owned());
        }
        if !catalogued(get(payload, "hook_type"), &HOOK_TYPES) {
            return Some("hook_type must be a catalogued value".to_owned());
        }
        if !integer(get(payload, "hook_index")).is_some_and(|index| index >= 0) {
            return Some("hook_index must be a nonnegative integer".to_owned());
        }
        let unsafe_name: bool = match get(payload, "hook_name") {
            None => false,
            Some(PayloadValue::Text(name)) => !safe_hook_name(name),
            Some(_) => true,
        };
        if unsafe_name {
            return Some("hook_name must be a non-empty safe token".to_owned());
        }
    }
    let entries: &Vec<(String, PayloadValue)> = match get(payload, METADATA_FIELD)? {
        PayloadValue::Object(entries) => entries,
        _ => return Some("operation metadata must be a JSON object".to_owned()),
    };
    if entries
        .iter()
        .any(|(key, _)| !OPERATION_METADATA_FIELDS.contains(&key.as_str()))
    {
        return Some("operation metadata contains a non-allowlisted field".to_owned());
    }
    entries
        .iter()
        .any(|(_, value)| !integer(Some(value)).is_some_and(|count| count >= 0))
        .then(|| "operation metadata values must be nonnegative integers excluding bool".to_owned())
}

/// Positive, ordered batch positions and catalogued microbatch dimensions.
pub(crate) fn microbatch_problem(payload: &Payload) -> Option<String> {
    let Some(index) = integer(get(payload, "batch_index")).filter(|index| *index >= 1) else {
        return Some("batch_index must be a positive integer".to_owned());
    };
    let Some(count) = integer(get(payload, "batch_count")).filter(|count| *count >= 1) else {
        return Some("batch_count must be a positive integer".to_owned());
    };
    if index > count {
        return Some("batch_index must not exceed batch_count".to_owned());
    }
    let dimensions: [(&str, &[&str]); 3] = [
        ("microbatch_strategy", &MICROBATCH_STRATEGIES),
        ("microbatch_run_type", &MICROBATCH_RUN_TYPES),
        ("batch_kind", &MICROBATCH_KINDS),
    ];
    dimensions
        .into_iter()
        .find(|(name, allowed)| !catalogued(get(payload, name), allowed))
        .map(|(name, _)| format!("{name} must be a catalogued value"))
}

/// A catalogued skip code and, when present, skip mode.
pub(crate) fn skip_problem(payload: &Payload) -> Option<String> {
    if !catalogued(get(payload, "skip_code"), &RESOURCE_SKIP_CODES) {
        return Some("skip_code must be a catalogued value".to_owned());
    }
    uncatalogued(payload, "skip_mode", &RESOURCE_SKIP_MODES)
        .then(|| "skip_mode must be a catalogued value".to_owned())
}

/// A positive failed attempt followed by the next attempt number.
pub(crate) fn retry_problem(payload: &Payload) -> Option<String> {
    let Some(failed) = integer(get(payload, "failed_attempt_number")).filter(|number| *number > 0)
    else {
        return Some("failed_attempt_number must be a positive integer".to_owned());
    };
    (integer(get(payload, "next_attempt_number")) != Some(failed + 1))
        .then(|| "next_attempt_number must equal failed_attempt_number + 1".to_owned())
}

fn run_count(payload: &Payload, name: &str) -> Result<i128, String> {
    integer(get(payload, name))
        .filter(|count| *count >= 0)
        .ok_or_else(|| format!("{name} must be a nonnegative integer excluding bool"))
}

/// Worker counts of a started run and audit totals of a finished run.
pub(crate) fn run_problem(event_type: &str, payload: &Payload) -> Option<String> {
    let present = |name: &str| payload.iter().any(|(key, _)| key == name);
    if event_type == RUN_STARTED_EVENT && present(CONFIGURED_CONCURRENCY_FIELD) {
        let Some(configured) =
            integer(get(payload, CONFIGURED_CONCURRENCY_FIELD)).filter(|count| *count >= 1)
        else {
            return Some(
                "configured_concurrency must be a positive integer excluding bool".to_owned(),
            );
        };
        let Some(selected) = integer(get(payload, "selected_count")).filter(|count| *count >= 0)
        else {
            return Some("selected_count must be a nonnegative integer excluding bool".to_owned());
        };
        let Some(workers) = integer(get(payload, "worker_count")) else {
            return Some("worker_count must be an integer excluding bool".to_owned());
        };
        if workers != configured.min(selected) {
            return Some(
                "worker_count must equal min(configured_concurrency, selected_count)".to_owned(),
            );
        }
    }
    if !RUN_TERMINALS.contains(&event_type)
        || !AUDIT_RUN_COUNT_FIELDS.iter().any(|name| present(name))
    {
        return None;
    }
    if !AUDIT_RUN_COUNT_FIELDS.iter().all(|name| present(name)) {
        return Some(
            "audit run terminals must include pass_count, warn_count, and fail_count together"
                .to_owned(),
        );
    }
    let counts = || -> Result<Option<String>, String> {
        let pass: i128 = run_count(payload, "pass_count")?;
        let warn: i128 = run_count(payload, "warn_count")?;
        let fail: i128 = run_count(payload, "fail_count")?;
        let succeeded: i128 = run_count(payload, "succeeded_count")?;
        let failed: i128 = run_count(payload, "failed_count")?;
        if succeeded != pass + warn {
            return Ok(Some(
                "succeeded_count must equal pass_count + warn_count".to_owned(),
            ));
        }
        Ok((failed != fail).then(|| "failed_count must equal fail_count".to_owned()))
    };
    counts().unwrap_or_else(Some)
}

/// The first statement, operation, microbatch, skip, retry, field or run violation.
pub(crate) fn family_problem(event: &KnownEventFacts) -> Option<String> {
    let event_type: &str = &event.event_type;
    if event_type.starts_with(STATEMENT_EVENT_PREFIX) {
        let forbidden: BTreeSet<String> =
            forbidden_statement_fields(&PayloadValue::Object(event.payload.clone()));
        if !forbidden.is_empty() {
            let names: Vec<String> = forbidden.into_iter().collect();
            return Some(format!(
                "statement lifecycle payload must not contain SQL or parameter values; \
forbidden field(s): {}",
                names.join(", ")
            ));
        }
    }
    let checks: [(bool, PayloadCheck); 4] = [
        (
            event_type.starts_with(OPERATION_EVENT_PREFIX),
            operation_problem,
        ),
        (
            event_type.starts_with(MICROBATCH_EVENT_PREFIX),
            microbatch_problem,
        ),
        (event_type == RESOURCE_ATTEMPT_SKIPPED_EVENT, skip_problem),
        (event_type == RETRY_SCHEDULED_EVENT, retry_problem),
    ];
    for (applies, check) in checks {
        if let Some(problem) = applies.then(|| check(&event.payload)).flatten() {
            return Some(problem);
        }
    }
    event
        .payload
        .iter()
        .find_map(|(name, value)| field_problem(name, value))
        .or_else(|| run_problem(event_type, &event.payload))
}

//! The asset, check and envelope parts of one record, completed and checked against the contract.

use crate::integration_results::_helpers::bounded::{
    allowlisted_mapping, encode, has_exactly, maximum_start_safety,
};
use crate::integration_results::_helpers::timestamps::aware_timestamp;
use crate::integration_results::_helpers::values::{
    field, finite_float, non_negative_integer, null_or_one_of, one_of, optional_identifier,
    require_identifier, text, text_length,
};
use crate::integration_results::constants::{
    ASSET_FIELDS, ASSET_KINDS, ASSET_MAPPING_FIELDS, ASSET_OUTPUT, ASSET_STATUSES, AUDIT_KIND,
    AUDIT_SEVERITIES, BOUND_OPERATORS, CHECK_ATTACHMENT_KINDS, CHECK_FIELDS, CHECK_KINDS,
    CHECK_NON_FAIL_STATUSES, CHECK_OUTPUT, CHECK_RUN_SCOPE_PHASES, CHECK_STATUSES, CLONE_ACTIONS,
    ENVELOPE_FIELDS, EVALUATION_MODES, EXTRA_RESOURCE_KINDS, FAILED_PHASES, FAILED_STATUS,
    FUTURE_CURSOR_KEYS, LOADER_KIND, MICROBATCH_COUNT_KEYS, MICROBATCH_KEYS,
    MICROBATCH_LIMIT_ACTIONS, MICROBATCH_PARTITION_POLICIES, MICROBATCH_REPLAY_STATES,
    MICROBATCH_RUN_TYPES, MIN_DURATION_MS, MODEL_RESOURCE_KINDS, NON_IDENTIFIER_IDENTITY_KEYS,
    RANGE_OPERATOR, RESOURCE_FAILED_EVENT, RESOURCE_SKIP_CODES, RESOURCE_SKIPPED_EVENT,
    RESOURCE_TERMINALS, SKIP_MODES, SKIPPED_STATUS, THRESHOLD_LEVELS,
};
use crate::integration_results::errors::IntegrationRecordError;
use crate::json::models::JsonValue;

/// A constructor received an unknown or missing field.
pub(crate) fn invalid_envelope() -> IntegrationRecordError {
    IntegrationRecordError::new("invalid integration result envelope")
}

fn reject(message: impl Into<String>) -> Result<(), IntegrationRecordError> {
    Err(IntegrationRecordError::new(message))
}

fn is_field(fields: &[(&str, bool)], key: &str) -> bool {
    fields.iter().any(|(name, _)| *name == key)
}

/// The object's fields in declaration order, defaults filled in; unknown or missing fields are invalid.
pub(crate) fn completed(
    object: Vec<(String, JsonValue)>,
    fields: &[(&str, bool)],
    mappings: &[&str],
) -> Result<Vec<(String, JsonValue)>, IntegrationRecordError> {
    if object.iter().any(|(key, _)| !is_field(fields, key)) {
        return Err(invalid_envelope());
    }
    let mut ordered: Vec<(String, JsonValue)> = Vec::with_capacity(fields.len());
    for (name, required) in fields {
        let value: Option<JsonValue> = object
            .iter()
            .find(|(key, _)| key == name)
            .map(|(_, value)| value.clone());
        let value: JsonValue = match value {
            Some(value) => value,
            None if *required => return Err(invalid_envelope()),
            None if mappings.contains(name) => JsonValue::Object(Vec::new()),
            None => JsonValue::Null,
        };
        ordered.push(((*name).to_owned(), value));
    }
    Ok(ordered)
}

fn microbatch(value: &JsonValue) -> Result<(), IntegrationRecordError> {
    allowlisted_mapping(value, "microbatch", &MICROBATCH_KEYS)?;
    let JsonValue::Object(entries) = value else {
        return Ok(());
    };
    for key in MICROBATCH_COUNT_KEYS {
        let count: &JsonValue = field(entries, key);
        if !matches!(count, JsonValue::Null) && !non_negative_integer(count) {
            return reject(format!(
                "integration microbatch {key} must be non-negative integer"
            ));
        }
    }
    for (key, allowed) in [
        ("run_type", &MICROBATCH_RUN_TYPES[..]),
        ("action", &MICROBATCH_LIMIT_ACTIONS[..]),
        (
            "unaccounted_partition_policy",
            &MICROBATCH_PARTITION_POLICIES[..],
        ),
        ("replay_requirement_state", &MICROBATCH_REPLAY_STATES[..]),
    ] {
        if !null_or_one_of(field(entries, key), allowed) {
            return reject(format!("integration microbatch {key} is unsupported"));
        }
    }
    if !matches!(
        field(entries, "concurrent_enabled"),
        JsonValue::Null | JsonValue::Bool(_)
    ) {
        return reject("integration microbatch concurrent_enabled must be boolean");
    }
    Ok(())
}

/// `IntegrationAssetResult(**asset)`: the completed asset, or the contract it breaks.
pub(crate) fn asset(
    object: Vec<(String, JsonValue)>,
) -> Result<Vec<(String, JsonValue)>, IntegrationRecordError> {
    let asset: Vec<(String, JsonValue)> = completed(object, &ASSET_FIELDS, &ASSET_MAPPING_FIELDS)?;
    let value = |key: &str| field(&asset, key);
    require_identifier(value("kind"), "asset kind")?;
    require_identifier(value("name"), "asset name")?;
    if !one_of(value("kind"), &ASSET_KINDS) {
        reject("integration asset kind is unsupported")?;
    }
    if !one_of(value("status"), &ASSET_STATUSES) {
        reject("integration asset status is unsupported")?;
    }
    if !null_or_one_of(value("action"), &CLONE_ACTIONS) {
        reject("integration asset action is unsupported")?;
    }
    if !null_or_one_of(value("failed_phase"), &FAILED_PHASES) {
        reject("integration asset failed_phase is unsupported")?;
    }
    for name in [
        "target",
        "origin_relation",
        "staging_relation",
        "failed_phase",
        "loader",
    ] {
        optional_identifier(value(name), name)?;
    }
    let rows_loaded: &JsonValue = value("rows_loaded");
    if !matches!(rows_loaded, JsonValue::Null) && !non_negative_integer(rows_loaded) {
        reject("integration rows_loaded must be non-negative")?;
    }
    if !matches!(value("materialized"), JsonValue::Null | JsonValue::Bool(_)) {
        reject("integration materialized must be boolean")?;
    }
    allowlisted_mapping(
        value("future_cursor_safety"),
        "future_cursor_safety",
        &FUTURE_CURSOR_KEYS,
    )?;
    allowlisted_mapping(value("microbatch"), "microbatch", &MICROBATCH_KEYS)?;
    maximum_start_safety(value("maximum_start_safety"))?;
    microbatch(value("microbatch"))?;
    Ok(asset)
}

fn thresholds(value: &JsonValue) -> Result<(), IntegrationRecordError> {
    let JsonValue::Object(entries) = value else {
        return reject("integration check thresholds are invalid");
    };
    if entries.is_empty()
        || entries
            .iter()
            .any(|(key, _)| !THRESHOLD_LEVELS.contains(&key.as_str()))
    {
        return reject("integration check thresholds are invalid");
    }
    for (_, bound) in entries {
        let JsonValue::Object(bound) = bound else {
            return reject("integration check threshold must be an object");
        };
        let operator: &JsonValue = field(bound, "operator");
        let expected: &[&str] = if one_of(operator, &BOUND_OPERATORS) {
            &["operator", "limit"]
        } else if one_of(operator, &[RANGE_OPERATOR]) {
            &["operator", "lower", "upper"]
        } else {
            return reject("integration check threshold operator is unsupported");
        };
        if !has_exactly(bound, expected)
            || expected[1..]
                .iter()
                .any(|key| !finite_float(field(bound, key)))
        {
            return reject("integration check threshold bound is invalid");
        }
    }
    encode(value, false).map(|_| ())
}

/// `IntegrationCheckResult(**check)`: the completed check, or the contract it breaks.
pub(crate) fn check(
    object: Vec<(String, JsonValue)>,
) -> Result<Vec<(String, JsonValue)>, IntegrationRecordError> {
    let check: Vec<(String, JsonValue)> = completed(object, &CHECK_FIELDS, &[])?;
    let value = |key: &str| field(&check, key);
    require_identifier(value("kind"), "check kind")?;
    require_identifier(value("name"), "check name")?;
    require_identifier(value("check_id"), "check id")?;
    optional_identifier(value("dag_check_id"), "dag_check_id")?;
    if !one_of(value("kind"), &CHECK_KINDS) {
        reject("integration check kind is unsupported")?;
    }
    if text(value("kind")) == Some(AUDIT_KIND)
        && matches!(value("audit_definition_name"), JsonValue::Null)
    {
        reject("integration audit check requires audit_definition_name")?;
    }
    if !one_of(value("status"), &CHECK_STATUSES) {
        reject("integration check status is unsupported")?;
    }
    let JsonValue::Bool(passed) = value("passed") else {
        return Err(IntegrationRecordError::new(
            "integration check passed must be boolean",
        ));
    };
    if *passed != one_of(value("status"), &CHECK_NON_FAIL_STATUSES) {
        reject("integration check status and passed are incoherent")?;
    }
    if !null_or_one_of(value("severity"), &AUDIT_SEVERITIES) {
        reject("integration check severity is unsupported")?;
    }
    if !null_or_one_of(value("attachment_kind"), &CHECK_ATTACHMENT_KINDS) {
        reject("integration check attachment_kind is unsupported")?;
    }
    if !null_or_one_of(value("run_scope_phase"), &CHECK_RUN_SCOPE_PHASES) {
        reject("integration check run_scope_phase is unsupported")?;
    }
    for name in [
        "asset_name",
        "attachment_kind",
        "attached_column_name",
        "attached_target_name",
        "run_scope_phase",
        "audit_definition_name",
    ] {
        optional_identifier(value(name), name)?;
    }
    let row_count: &JsonValue = value("row_count");
    if !matches!(row_count, JsonValue::Null) && !non_negative_integer(row_count) {
        reject("integration check row_count must be non-negative")?;
    }
    if !matches!(value("reused"), JsonValue::Null | JsonValue::Bool(_)) {
        reject("integration check reused must be boolean")?;
    }
    if !null_or_one_of(value("evaluation_mode"), &EVALUATION_MODES) {
        reject("integration check evaluation_mode is unsupported")?;
    }
    let measured: &JsonValue = value("measured_value");
    if !matches!(measured, JsonValue::Null) && !finite_float(measured) {
        reject("integration check measured_value must be finite")?;
    }
    for name in ["sample_count", "minimum_samples", "evidence_count"] {
        let count: &JsonValue = value(name);
        if !matches!(count, JsonValue::Null) && !non_negative_integer(count) {
            reject(format!("integration check {name} must be non-negative"))?;
        }
    }
    optional_identifier(value("sample_unit"), "sample_unit")?;
    if !matches!(
        value("evidence_truncated"),
        JsonValue::Null | JsonValue::Bool(_)
    ) {
        reject("integration check evidence_truncated must be boolean")?;
    }
    let description: &JsonValue = value("audit_description");
    if !matches!(description, JsonValue::Null)
        && !match description {
            JsonValue::String(text) => !text.trim().is_empty(),
            JsonValue::Utf16(_) => true,
            _ => false,
        }
    {
        reject("integration check audit_description must be a non-empty string")?;
    }
    if !matches!(value("thresholds"), JsonValue::Null) {
        thresholds(value("thresholds"))?;
    }
    Ok(check)
}

/// `integration_resource_id`: the canonical resource identifier of a result.
pub(crate) fn resource_id(
    kind: &str,
    name: &str,
    check_id: Option<&str>,
    loader: Option<&str>,
) -> String {
    if CHECK_KINDS.contains(&kind) {
        return check_id.unwrap_or_default().to_owned();
    }
    if MODEL_RESOURCE_KINDS.contains(&kind) {
        return format!("model:{name}");
    }
    if kind == LOADER_KIND && loader.is_some() {
        return format!("source:{name}");
    }
    format!("{kind}:{name}")
}

fn result_identity(record: &[(String, JsonValue)]) -> Result<(), IntegrationRecordError> {
    let value = |key: &str| field(record, key);
    let checks: &[JsonValue] = match value("checks") {
        JsonValue::Array(checks) => checks,
        _ => &[],
    };
    let output_kind: Option<&str> = text(value("output_kind"));
    if output_kind == Some(ASSET_OUTPUT) {
        let JsonValue::Object(asset) = value("asset") else {
            return reject("asset output must contain exactly one asset");
        };
        if !checks.is_empty() {
            return reject("asset output must contain exactly one asset");
        }
        if field(asset, "kind") != value("resource_kind")
            || field(asset, "name") != value("resource_name")
        {
            return reject("integration asset identity does not match terminal");
        }
        let expected: String = resource_id(
            text(value("resource_kind")).unwrap_or_default(),
            text(value("resource_name")).unwrap_or_default(),
            None,
            text(field(asset, "loader")),
        );
        if text(value("resource_id")) != Some(expected.as_str()) {
            return reject("integration asset resource_id is incoherent");
        }
        return Ok(());
    }
    if output_kind == Some(CHECK_OUTPUT) {
        if !matches!(value("asset"), JsonValue::Null) || checks.len() != 1 {
            return reject("check output must contain exactly one check");
        }
        let JsonValue::Object(check) = &checks[0] else {
            return reject("check output must contain exactly one check");
        };
        if field(check, "check_id") != value("resource_id") {
            return reject("integration check identity does not match terminal");
        }
        return Ok(());
    }
    reject("integration result output_kind is unsupported")
}

fn asset_status(record: &[(String, JsonValue)]) -> Option<&JsonValue> {
    match field(record, "asset") {
        JsonValue::Object(asset) => Some(field(asset, "status")),
        _ => None,
    }
}

fn terminal_facts(record: &[(String, JsonValue)]) -> Result<(), IntegrationRecordError> {
    let value = |key: &str| field(record, key);
    let set = |key: &str| !matches!(value(key), JsonValue::Null);
    let event_type: Option<&str> = text(value("event_type"));
    if event_type == Some(RESOURCE_FAILED_EVENT) {
        if !set("error_type") || set("skip_code") || set("skip_mode") {
            return reject("failed integration terminal facts are invalid");
        }
        if asset_status(record).is_some_and(|status| text(status) != Some(FAILED_STATUS)) {
            return reject("failed terminal asset status is incoherent");
        }
        return Ok(());
    }
    if event_type == Some(RESOURCE_SKIPPED_EVENT) {
        if !one_of(value("skip_code"), &RESOURCE_SKIP_CODES)
            || set("error_code")
            || set("error_type")
            || !null_or_one_of(value("skip_mode"), &SKIP_MODES)
        {
            return reject("skipped integration terminal facts are invalid");
        }
        if asset_status(record).is_some_and(|status| text(status) != Some(SKIPPED_STATUS)) {
            return reject("skipped terminal asset status is incoherent");
        }
        return Ok(());
    }
    if ["error_code", "error_type", "skip_code", "skip_mode"]
        .iter()
        .any(|key| set(key))
    {
        return reject("completed integration terminal has failure facts");
    }
    Ok(())
}

/// The `IntegrationResultEnvelope` checks of a completed record.
pub(crate) fn envelope(record: &[(String, JsonValue)]) -> Result<(), IntegrationRecordError> {
    let value = |key: &str| field(record, key);
    if !one_of(value("event_type"), &RESOURCE_TERMINALS) {
        return reject("integration result event_type is not a resource terminal");
    }
    let identity: [&str; 10] = [
        "event_id",
        "event_type",
        "occurred_at",
        "invocation_id",
        "run_id",
        "resource_id",
        "resource_attempt_id",
        "resource_kind",
        "resource_name",
        "command",
    ];
    if identity
        .iter()
        .any(|key| text_length(value(key)).is_none_or(|length| length == 0))
    {
        return reject("integration result identity fields must be non-empty");
    }
    for key in identity {
        if !NON_IDENTIFIER_IDENTITY_KEYS.contains(&key) {
            require_identifier(value(key), key)?;
        }
    }
    if !one_of(
        value("resource_kind"),
        &crate::integration_results::constants::ASSET_KINDS,
    ) && !one_of(value("resource_kind"), &EXTRA_RESOURCE_KINDS)
    {
        return reject("integration resource_kind is unsupported");
    }
    optional_identifier(value("operation_id"), "operation_id")?;
    optional_identifier(value("statement_id"), "statement_id")?;
    match text(value("occurred_at")).and_then(aware_timestamp) {
        Some(true) => {}
        Some(false) => return reject("integration result occurred_at must include a timezone"),
        None => return reject("integration result occurred_at must be an ISO-8601 timestamp"),
    }
    if !non_negative_integer(value("event_sequence")) {
        return reject("integration result event_sequence must be non-negative");
    }
    let attempt_positive: bool = match value("attempt_number") {
        JsonValue::Integer(number) => number.to_i128().is_none_or(|number| number >= 1),
        _ => false,
    };
    if !attempt_positive {
        return reject("integration result attempt_number must be positive");
    }
    let no_checks: bool = matches!(value("checks"), JsonValue::Array(checks) if checks.is_empty());
    if matches!(value("asset"), JsonValue::Null) && no_checks {
        return reject("integration result must contain asset or check enrichment");
    }
    let duration_valid: bool = match value("duration_ms") {
        JsonValue::Null => true,
        JsonValue::Integer(number) => !number.as_str().starts_with('-'),
        JsonValue::Float(number) => number.is_finite() && *number >= MIN_DURATION_MS,
        _ => false,
    };
    if !duration_valid {
        return reject("integration result duration_ms must be non-negative");
    }
    for key in ["error_code", "error_type", "skip_code", "skip_mode"] {
        optional_identifier(value(key), key)?;
    }
    if !matches!(value("projection_degraded"), JsonValue::Bool(_)) {
        return reject("integration result projection_degraded must be boolean");
    }
    result_identity(record)?;
    terminal_facts(record)
}

/// The envelope fields followed by `projection_degraded`, the asset and the checks.
pub(crate) fn envelope_fields() -> Vec<(&'static str, bool)> {
    let mut fields: Vec<(&'static str, bool)> = ENVELOPE_FIELDS.to_vec();
    fields.push(("projection_degraded", false));
    fields
}

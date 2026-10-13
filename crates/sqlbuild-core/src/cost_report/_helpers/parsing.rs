//! A persisted cost run artifact read with the coercions `CostRunRecord` loading applied.

use crate::cost_report::_helpers::decimal_text::is_decimal;
use crate::cost_report::_helpers::instants::parse;
use crate::cost_report::constants::{
    ARTIFACT_VERSION, COST_STATUSES, RUN_ID_SEPARATORS, UNSAFE_RUN_IDS,
};
use crate::cost_report::errors::CostArtifactError;
use crate::cost_report::models::{CostResource, CostRun, CostSummary};
use crate::json::main::python_float_repr::python_float_repr;
use crate::json::models::{JsonInteger, JsonValue};

type Entries = [(String, JsonValue)];

fn invalid(message: impl Into<String>) -> CostArtifactError {
    CostArtifactError::new(message)
}

fn get<'a>(entries: &'a Entries, key: &str) -> Option<&'a JsonValue> {
    entries
        .iter()
        .find(|(name, _)| name == key)
        .map(|(_, value)| value)
}

/// `payload[key]`: the value, or the failure of a missing key.
fn required<'a>(entries: &'a Entries, key: &str) -> Result<&'a JsonValue, CostArtifactError> {
    get(entries, key).ok_or_else(|| invalid(format!("cost run artifact is missing '{key}'")))
}

/// `str(value)` of a JSON scalar.
fn text(value: &JsonValue) -> Result<String, CostArtifactError> {
    match value {
        JsonValue::String(text) => Ok(text.clone()),
        JsonValue::Integer(number) => Ok(number.as_str().to_owned()),
        JsonValue::Float(number) => Ok(python_float_repr(*number)),
        JsonValue::Bool(flag) => Ok(if *flag { "True" } else { "False" }.to_owned()),
        JsonValue::Null => Ok("None".to_owned()),
        _ => Err(invalid("cost run artifact value must be a scalar")),
    }
}

/// `None` for an absent or `null` value, else `str(value)`.
fn optional_text(value: Option<&JsonValue>) -> Result<Option<String>, CostArtifactError> {
    match value {
        None | Some(JsonValue::Null) => Ok(None),
        Some(value) => text(value).map(Some),
    }
}

fn whole_number(text: &str) -> Option<i64> {
    let Ok(number) = text.trim().parse::<i64>() else {
        return None;
    };
    Some(number)
}

fn json_integer(number: &JsonInteger) -> Option<i64> {
    let Ok(number) = i64::try_from(number.to_i128()?) else {
        return None;
    };
    Some(number)
}

/// `int(value)` of an integer, boolean or integral string.
fn integer(value: &JsonValue) -> Result<i64, CostArtifactError> {
    let parsed: Option<i64> = match value {
        JsonValue::Integer(number) => json_integer(number),
        JsonValue::Bool(flag) => Some(i64::from(*flag)),
        JsonValue::String(text) => whole_number(text),
        _ => None,
    };
    parsed.ok_or_else(|| invalid("cost run artifact count must be an integer"))
}

fn integer_or_zero(value: Option<&JsonValue>) -> Result<i64, CostArtifactError> {
    value.map_or(Ok(0), integer)
}

/// `str(value)` when `Decimal(str(value))` accepts it.
fn decimal(value: &JsonValue) -> Result<String, CostArtifactError> {
    let text: String = text(value)?;
    if !is_decimal(&text) {
        return Err(invalid("cost run artifact amount must be a decimal"));
    }
    Ok(text.trim().to_owned())
}

fn decimal_or_zero(value: Option<&JsonValue>) -> Result<String, CostArtifactError> {
    value.map_or(Ok("0".to_owned()), decimal)
}

fn object<'a>(value: &'a JsonValue, message: &str) -> Result<&'a Entries, CostArtifactError> {
    match value {
        JsonValue::Object(entries) => Ok(entries),
        _ => Err(invalid(message)),
    }
}

/// `_validate_run_id`: a run ID is exactly one safe path component.
pub(crate) fn check_run_id(run_id: &str) -> Result<(), CostArtifactError> {
    if run_id.is_empty() || UNSAFE_RUN_IDS.contains(&run_id) || run_id.contains(RUN_ID_SEPARATORS) {
        return Err(invalid("cost run ID must be one path component"));
    }
    Ok(())
}

fn resource(entries: &Entries) -> Result<CostResource, CostArtifactError> {
    Ok(CostResource {
        resource_type: text(required(entries, "resource_type")?)?,
        resource_name: text(required(entries, "resource_name")?)?,
        warehouse_name: text(required(entries, "warehouse_name")?)?,
        warehouse_size: text(required(entries, "warehouse_size")?)?,
        warehouse_type: optional_text(get(entries, "warehouse_type"))?,
        cluster_number: match get(entries, "cluster_number") {
            None | Some(JsonValue::Null) => None,
            Some(value) => Some(integer(value)?),
        },
        query_count: integer(required(entries, "query_count")?)?,
        attributed_seconds: decimal(required(entries, "attributed_seconds")?)?,
        bytes_scanned: integer(required(entries, "bytes_scanned")?)?,
        estimated_compute_credits: decimal(required(entries, "estimated_compute_credits")?)?,
        estimated_usd: decimal(required(entries, "estimated_usd")?)?,
    })
}

fn resources(cost: &Entries) -> Result<Vec<CostResource>, CostArtifactError> {
    let items: &[JsonValue] = match get(cost, "resources") {
        None => &[],
        Some(JsonValue::Array(items)) => items,
        Some(_) => return Err(invalid("cost run artifact 'resources' must be a list")),
    };
    let mut objects: Vec<&Entries> = Vec::with_capacity(items.len());
    for item in items {
        objects.push(object(item, "cost run artifact resources must be objects")?);
    }
    objects.into_iter().map(resource).collect()
}

fn limitations(cost: &Entries) -> Result<Vec<String>, CostArtifactError> {
    match get(cost, "limitations") {
        None => Ok(Vec::new()),
        Some(JsonValue::Array(items)) => items.iter().map(text).collect(),
        Some(_) => Err(invalid("cost run artifact 'limitations' must be a list")),
    }
}

fn summary(cost: &Entries, resources: Vec<CostResource>) -> Result<CostSummary, CostArtifactError> {
    let status: String = text(required(cost, "status")?)?;
    if !COST_STATUSES.contains(&status.as_str()) {
        return Err(invalid(format!("unsupported cost status: {status}")));
    }
    Ok(CostSummary {
        status,
        usd_per_credit: decimal(required(cost, "usd_per_credit")?)?,
        rate_source: text(required(cost, "rate_source")?)?,
        resources,
        query_count: integer_or_zero(get(cost, "query_count"))?,
        attributed_seconds: decimal_or_zero(get(cost, "attributed_seconds"))?,
        bytes_scanned: integer_or_zero(get(cost, "bytes_scanned"))?,
        estimated_compute_credits: decimal_or_zero(get(cost, "estimated_compute_credits"))?,
        estimated_usd: decimal_or_zero(get(cost, "estimated_usd"))?,
        expected_statement_count: integer_or_zero(get(cost, "expected_statement_count"))?,
        observed_statement_count: integer_or_zero(get(cost, "observed_statement_count"))?,
        missing_statement_count: integer_or_zero(get(cost, "missing_statement_count"))?,
        skipped_statement_count: integer_or_zero(get(cost, "skipped_statement_count"))?,
        source: optional_text(get(cost, "source"))?.unwrap_or_default(),
        method: optional_text(get(cost, "method"))?.unwrap_or_default(),
        limitations: limitations(cost)?,
        message: optional_text(get(cost, "message"))?,
    })
}

/// `_aware_datetime`: the timestamp text, which must carry a UTC offset.
fn aware(value: &JsonValue, field: &str) -> Result<String, CostArtifactError> {
    let text: String = text(value)?;
    let Some(timestamp) = parse(&text) else {
        return Err(invalid(format!(
            "cost run artifact '{field}' must be an ISO timestamp"
        )));
    };
    if timestamp.offset_seconds.is_none() {
        return Err(invalid(format!(
            "cost run artifact '{field}' must include a timezone"
        )));
    }
    Ok(text)
}

fn executable_work(payload: &Entries) -> Result<Option<bool>, CostArtifactError> {
    match get(payload, "had_executable_work") {
        None | Some(JsonValue::Null) => Ok(None),
        Some(JsonValue::Bool(flag)) => Ok(Some(*flag)),
        Some(_) => Err(invalid(
            "cost run artifact 'had_executable_work' must be a boolean",
        )),
    }
}

/// `_record_from_payload`: the run an artifact payload describes.
pub(crate) fn cost_run(payload: &JsonValue) -> Result<CostRun, CostArtifactError> {
    let payload: &Entries = object(payload, "cost run artifact must be an object")?;
    let version: i64 = integer(required(payload, "version")?)?;
    if version != ARTIFACT_VERSION {
        return Err(invalid(format!(
            "unsupported cost run artifact version: {version}"
        )));
    }
    let run_id: String = text(required(payload, "run_id")?)?;
    check_run_id(&run_id)?;
    let cost: &Entries = object(
        required(payload, "cost")?,
        "cost run artifact 'cost' must be an object",
    )?;
    let resources: Vec<CostResource> = resources(cost)?;
    let started_at: String = aware(required(payload, "started_at")?, "started_at")?;
    let completed_at: String = aware(required(payload, "completed_at")?, "completed_at")?;
    let had_executable_work: Option<bool> = executable_work(payload)?;
    let cost: CostSummary = summary(cost, resources)?;
    Ok(CostRun {
        version,
        run_id,
        adapter_name: text(required(payload, "adapter_name")?)?,
        target_name: optional_text(get(payload, "target_name"))?,
        build_status: text(required(payload, "build_status")?)?,
        started_at,
        completed_at,
        cost,
        had_executable_work,
    })
}

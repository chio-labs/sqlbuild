//! SQL rule result cache keys, stored-entry lookup and the cache file.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};

use serde_json::{Value, json};
use sqlbuild_rules::rule_cache::main::file_rule_key::file_rule_key;

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::rules::findings::FindingClasses;
use sqlbuild_rules::rule_cache::main::lint_key::lint_key;
use sqlbuild_rules::rule_cache::main::lookup_rule_cache::lookup_rule_cache;
use sqlbuild_rules::rule_cache::main::model_rule_keys::model_rule_keys as parallel_model_rule_keys;
use sqlbuild_rules::rule_cache::main::parse_rule_cache::parse_rule_cache;
use sqlbuild_rules::rule_cache::main::rule_cache_text::rule_cache_text;
use sqlbuild_rules::rule_cache::models::{CacheLookup, CachedEntry, LintKeyInput, ModelKeyInput};
use sqlbuild_rules::rule_cache::types::CachedEntries;
use sqlbuild_rules::rule_results::models::RuleFinding;

use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::rules::lint_pipeline::LintSettings;

/// Stored entries as `{path: (key, findings JSON)}`.
pub(crate) type StoredEntries = BTreeMap<String, (String, String)>;

fn invalid(error: serde_json::Error) -> PyErr {
    PyValueError::new_err(error.to_string())
}

/// The lint settings part of every SQL rule cache key.
pub(crate) fn settings_lint_key(settings: &LintSettings) -> String {
    lint_key(&LintKeyInput {
        dialect: settings.sql.dialect.clone(),
        max_literal_length: settings.sql.max_literal_length,
        max_ranking_order_by: settings.sql.max_ranking_order_by,
        relation_keys: settings.relation_keys.clone(),
        allow_suppressions: settings.allow_suppressions,
    })
}

/// The lint settings part of every SQL rule cache key.
#[pyfunction]
#[pyo3(signature = (*, config))]
fn sql_rule_lint_key(config: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(settings_lint_key(&LintSettings::from_record(config)?))
}

/// Each model path's SQL rule cache key from `(path, authored_sql, query_sql, contract)`.
#[pyfunction]
#[pyo3(signature = (*, lint_key, codes, models))]
fn sql_model_rule_keys(
    py: Python<'_>,
    lint_key: &str,
    codes: Vec<String>,
    models: Vec<(String, String, String, Option<String>)>,
) -> BTreeMap<String, String> {
    model_rule_keys(py, lint_key, &codes, &models)
}

/// Each model path's SQL rule cache key, hashed in parallel with the GIL released.
pub(crate) fn model_rule_keys(
    py: Python<'_>,
    lint_key: &str,
    codes: &[String],
    models: &[(String, String, String, Option<String>)],
) -> BTreeMap<String, String> {
    let inputs: Vec<ModelKeyInput<'_>> = models
        .iter()
        .map(|(_, authored_sql, query_sql, contract)| ModelKeyInput {
            authored_sql,
            query_sql,
            contract: contract.as_deref(),
        })
        .collect();
    let keys: Vec<String> = py.detach(|| parallel_model_rule_keys(lint_key, codes, &inputs));
    models
        .iter()
        .map(|(path, ..)| path.clone())
        .zip(keys)
        .collect()
}

/// One non-model SQL file's cache key, or `None` when its findings depend on expansion.
#[pyfunction]
#[pyo3(signature = (**request))]
fn sql_file_rule_key(request: Option<&Bound<'_, PyDict>>) -> PyResult<Option<String>> {
    let request = Request::new("sql_file_rule_key", request)?;
    let lint_key: String = request.get("lint_key")?.extract()?;
    let codes: Vec<String> = request.get("codes")?.extract()?;
    let relative_path: String = request.get("relative_path")?.extract()?;
    let contents: String = request.get("contents")?.extract()?;
    let expanded: bool = request.get("expanded")?.extract()?;
    Ok(file_rule_key(
        &lint_key,
        &codes,
        (&relative_path, &contents),
        expanded,
    ))
}

/// The usable stored entries of the cache file at `path`; unreadable files read as empty.
#[pyfunction]
#[pyo3(signature = (*, path))]
fn load_sql_rule_cache(path: PathBuf) -> PyResult<StoredEntries> {
    stored_entries(&path)
}

/// The usable stored entries of the cache file at `path`; unreadable files read as empty.
pub(crate) fn stored_entries(path: &Path) -> PyResult<StoredEntries> {
    let Ok(text) = std::fs::read_to_string(path) else {
        return Ok(StoredEntries::new());
    };
    parse_rule_cache(&text)
        .into_iter()
        .map(|(key, entry)| {
            let findings: String = serde_json::to_string(&entry.findings).map_err(invalid)?;
            Ok((key, (entry.identity, findings)))
        })
        .collect()
}

fn cached_entries(entries: &StoredEntries) -> PyResult<CachedEntries> {
    entries
        .iter()
        .map(|(path, (identity, findings))| {
            let findings: Vec<Value> = serde_json::from_str(findings).map_err(invalid)?;
            let entry = CachedEntry {
                identity: identity.clone(),
                findings,
            };
            Ok((path.clone(), entry))
        })
        .collect()
}

/// The stored findings of each path whose key matches, as rows; undecodable stored findings miss.
pub(crate) fn cached_rule_findings(
    entries: &StoredEntries,
    keys: &[(String, String)],
) -> PyResult<BTreeMap<String, Vec<RuleFinding>>> {
    let lookup: CacheLookup = lookup_rule_cache(&cached_entries(entries)?, keys);
    let mut hits: BTreeMap<String, Vec<RuleFinding>> = BTreeMap::new();
    for (path, findings) in lookup.hits {
        let decoded: Option<Vec<RuleFinding>> = findings.iter().map(payload_finding).collect();
        if let Some(decoded) = decoded {
            hits.insert(path, decoded);
        }
    }
    Ok(hits)
}

/// One finding of a stored payload, or `None` when the payload is malformed.
fn payload_finding(value: &Value) -> Option<RuleFinding> {
    let payload = value.as_object()?;
    let text = |key: &str| payload.get(key).and_then(Value::as_str).map(str::to_owned);
    let number = |key: &str| {
        payload
            .get(key)
            .filter(|value| value.is_u64())
            .and_then(Value::as_i64)
    };
    let flag = |key: &str| payload.get(key).and_then(Value::as_bool) == Some(true);
    Some(RuleFinding {
        code: text("code")?,
        path: text("path")?,
        line: number("line")?,
        column: number("column")?,
        message: text("message")?,
        remediation: text("remediation")?,
        unevaluated: flag("unevaluated"),
        affected_rules: Vec::new(),
        fixable: flag("fixable"),
    })
}

/// The stored payload of one finding row.
pub(crate) fn finding_json(finding: &RuleFinding) -> Value {
    json!({
        "unevaluated": finding.unevaluated,
        "code": finding.code,
        "path": finding.path,
        "line": finding.line,
        "column": finding.column,
        "message": finding.message,
        "remediation": finding.remediation,
        "fixable": finding.fixable,
    })
}

/// The stored JSON of one path's finding rows.
pub(crate) fn encoded_findings(findings: &[&RuleFinding]) -> PyResult<String> {
    let payloads: Vec<Value> = findings
        .iter()
        .map(|finding| finding_json(finding))
        .collect();
    serde_json::to_string(&payloads).map_err(invalid)
}

/// The stored findings of each path whose key matches; undecodable stored findings miss.
#[pyfunction]
#[pyo3(signature = (*, entries, keys))]
fn lookup_sql_rule_cache<'py>(
    py: Python<'py>,
    entries: StoredEntries,
    keys: Vec<(String, String)>,
) -> PyResult<BTreeMap<String, Vec<Bound<'py, PyAny>>>> {
    let lookup: CacheLookup = lookup_rule_cache(&cached_entries(&entries)?, &keys);
    let classes = FindingClasses::new(py)?;
    let mut hits: BTreeMap<String, Vec<Bound<'py, PyAny>>> = BTreeMap::new();
    for (path, findings) in lookup.hits {
        let decoded: Option<Vec<Bound<'py, PyAny>>> = findings
            .iter()
            .map(|finding| classes.finding_of_payload(finding))
            .collect::<PyResult<_>>()?;
        if let Some(decoded) = decoded {
            hits.insert(path, decoded);
        }
    }
    Ok(hits)
}

fn finding_payload(finding: &Bound<'_, PyAny>) -> PyResult<Value> {
    let path: String = native_field(finding, "path")?
        .call_method0("as_posix")?
        .extract()?;
    Ok(json!({
        "unevaluated": native_field(finding, "unevaluated")?.extract::<bool>()?,
        "code": native_field(finding, "code")?.extract::<String>()?,
        "path": path,
        "line": native_field(finding, "line")?.extract::<Option<i64>>()?,
        "column": native_field(finding, "column")?.extract::<Option<i64>>()?,
        "message": native_field(finding, "message")?.extract::<String>()?,
        "remediation": native_field(finding, "remediation")?.extract::<Option<String>>()?,
        "fixable": native_field(finding, "fixable")?.extract::<bool>()?,
    }))
}

/// The stored JSON of one path's findings.
#[pyfunction]
#[pyo3(signature = (*, findings))]
fn encode_sql_rule_findings(findings: Vec<Bound<'_, PyAny>>) -> PyResult<String> {
    let payloads: Vec<Value> = findings
        .iter()
        .map(finding_payload)
        .collect::<PyResult<_>>()?;
    serde_json::to_string(&payloads).map_err(invalid)
}

/// Replace the cache file at `path` atomically with `entries`.
#[pyfunction]
#[pyo3(signature = (*, path, entries))]
fn write_sql_rule_cache(path: PathBuf, entries: &Bound<'_, PyDict>) -> PyResult<()> {
    let mut stored = StoredEntries::new();
    for (key, value) in entries.iter() {
        stored.insert(key.extract()?, value.extract()?);
    }
    write_rule_cache(&path, &stored)
}

/// Replace the cache file at `path` atomically with `entries`.
pub(crate) fn write_rule_cache(path: &Path, stored: &StoredEntries) -> PyResult<()> {
    let text: String = rule_cache_text(&cached_entries(stored)?);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let temporary: PathBuf = path.with_extension(format!("tmp-{}", std::process::id()));
    std::fs::write(&temporary, text)?;
    std::fs::rename(&temporary, path)?;
    Ok(())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(sql_rule_lint_key, module)?)?;
    module.add_function(wrap_pyfunction!(sql_model_rule_keys, module)?)?;
    module.add_function(wrap_pyfunction!(sql_file_rule_key, module)?)?;
    module.add_function(wrap_pyfunction!(load_sql_rule_cache, module)?)?;
    module.add_function(wrap_pyfunction!(lookup_sql_rule_cache, module)?)?;
    module.add_function(wrap_pyfunction!(encode_sql_rule_findings, module)?)?;
    module.add_function(wrap_pyfunction!(write_sql_rule_cache, module)?)?;
    Ok(())
}

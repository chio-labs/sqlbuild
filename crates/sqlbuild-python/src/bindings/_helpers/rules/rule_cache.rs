//! SQL rule result cache keys, stored-entry lookup and the cache file.

use std::collections::BTreeMap;
use std::path::PathBuf;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};

use serde_json::{Value, json};
use sqlbuild_rules::rule_cache::main::file_rule_key::file_rule_key;

use crate::bindings::_helpers::boundary::keyword_request::Request;
use sqlbuild_rules::rule_cache::main::lint_key::lint_key;
use sqlbuild_rules::rule_cache::main::lookup_rule_cache::lookup_rule_cache;
use sqlbuild_rules::rule_cache::main::model_rule_key::model_rule_key;
use sqlbuild_rules::rule_cache::main::parse_rule_cache::parse_rule_cache;
use sqlbuild_rules::rule_cache::main::rule_cache_text::rule_cache_text;
use sqlbuild_rules::rule_cache::models::{CacheLookup, CachedEntry, LintKeyInput, ModelKeyInput};
use sqlbuild_rules::rule_cache::types::CachedEntries;

/// Stored entries as `{path: (key, findings JSON)}`.
type StoredEntries = BTreeMap<String, (String, String)>;

fn invalid(error: serde_json::Error) -> PyErr {
    PyValueError::new_err(error.to_string())
}

/// The lint settings part of every SQL rule cache key.
#[pyfunction]
#[pyo3(signature = (*, config))]
fn sql_rule_lint_key(config: &Bound<'_, PyAny>) -> PyResult<String> {
    let mut relation_keys: Vec<(String, Vec<Vec<String>>)> = Vec::new();
    for item in config
        .getattr("relation_keys")?
        .call_method0("items")?
        .try_iter()?
    {
        relation_keys.push(item?.extract()?);
    }
    Ok(lint_key(&LintKeyInput {
        dialect: config.getattr("dialect")?.extract()?,
        max_literal_length: config.getattr("max_literal_length")?.extract()?,
        max_ranking_order_by: config.getattr("max_ranking_order_by")?.extract()?,
        relation_keys,
        allow_suppressions: config.getattr("allow_suppressions")?.extract()?,
    }))
}

/// Each model path's SQL rule cache key from `(path, authored_sql, query_sql, contract)`.
#[pyfunction]
#[pyo3(signature = (*, lint_key, codes, models))]
fn sql_model_rule_keys(
    lint_key: &str,
    codes: Vec<String>,
    models: Vec<(String, String, String, Option<String>)>,
) -> BTreeMap<String, String> {
    models
        .iter()
        .map(|(path, authored_sql, query_sql, contract)| {
            let model = ModelKeyInput {
                authored_sql,
                query_sql,
                contract: contract.as_deref(),
            };
            (path.clone(), model_rule_key(lint_key, &codes, &model))
        })
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
    let Ok(text) = std::fs::read_to_string(&path) else {
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

/// `(hits, misses)`: stored findings JSON of paths whose key matches, and every other path.
#[pyfunction]
#[pyo3(signature = (*, entries, keys))]
fn lookup_sql_rule_cache(
    entries: StoredEntries,
    keys: Vec<(String, String)>,
) -> PyResult<(BTreeMap<String, String>, Vec<String>)> {
    let lookup: CacheLookup = lookup_rule_cache(&cached_entries(&entries)?, &keys);
    let hits: BTreeMap<String, String> = lookup
        .hits
        .into_iter()
        .map(|(path, findings)| Ok((path, serde_json::to_string(&findings).map_err(invalid)?)))
        .collect::<PyResult<_>>()?;
    Ok((hits, lookup.misses))
}

fn finding_payload(finding: &Bound<'_, PyAny>) -> PyResult<Value> {
    let path: String = finding
        .getattr("path")?
        .call_method0("as_posix")?
        .extract()?;
    Ok(json!({
        "unevaluated": finding.getattr("unevaluated")?.extract::<bool>()?,
        "code": finding.getattr("code")?.extract::<String>()?,
        "path": path,
        "line": finding.getattr("line")?.extract::<Option<i64>>()?,
        "column": finding.getattr("column")?.extract::<Option<i64>>()?,
        "message": finding.getattr("message")?.extract::<String>()?,
        "remediation": finding.getattr("remediation")?.extract::<Option<String>>()?,
        "fixable": finding.getattr("fixable")?.extract::<bool>()?,
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
    let text: String = rule_cache_text(&cached_entries(&stored)?);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let temporary: PathBuf = path.with_extension(format!("tmp-{}", std::process::id()));
    std::fs::write(&temporary, text)?;
    std::fs::rename(&temporary, &path)?;
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

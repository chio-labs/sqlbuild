//! Run the planned SQL rules through native lint, reusing cached and early-lint results.

use std::collections::{BTreeSet, HashMap};
use std::time::Instant;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{
    PyDict, PyDictMethods, PyFrozenSet, PyList, PyListMethods, PySet, PySetMethods, PyString,
    PyTuple,
};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::records::ids::{ErrorId, NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::rules::constants::SAFE_RULE_FIX_CODES;
use crate::bindings::_helpers::rules::early_sql_lint::{sql_lint_config, sql_rule_cache_path};

const DATACLASSES_MODULE: &str = "dataclasses";
const JSON_MODULE: &str = "json";
const BUILTINS_MODULE: &str = "builtins";
const SQL_RULE_PREFIX: &str = "SQBRSQL";
const SQL_RULE_SUPPRESSION_CODE: &str = "SQBRSQL000";
const DEFAULT_REMEDIATION: &str = "Update the authored SQL to satisfy this rule.";

/// `native.name`, looked up at call time.
fn native<'py>(py: Python<'py>, name: NativeAttr) -> PyResult<Bound<'py, PyAny>> {
    registry::native(py, name)
}

/// The SQL rule codes among `rules`, in order.
fn sql_rule_codes(rules: &[Bound<'_, PyAny>]) -> PyResult<Vec<String>> {
    let mut codes: Vec<String> = Vec::new();
    for rule in rules {
        let code: String = rule.getattr("code")?.extract()?;
        if code.starts_with(SQL_RULE_PREFIX) {
            codes.push(code);
        }
    }
    Ok(codes)
}

/// The settings, project and inputs one SQL rules evaluation reads.
struct SqlRun<'a, 'py> {
    codes: &'a [String],
    project_dir: Bound<'py, PyAny>,
    discovered_inputs: Bound<'py, PyAny>,
    project: Bound<'py, PyAny>,
    lint_config: Bound<'py, PyAny>,
    selected_model_paths: Bound<'py, PyAny>,
    cache_enabled: bool,
    prepared_sql: Bound<'py, PyAny>,
    expansion_reuse: Bound<'py, PyAny>,
}

/// Run the planned SQL rules on the caller while built-in rules evaluate natively.
#[pyfunction]
#[pyo3(signature = (**options))]
fn run_planned_sql_rules<'py>(options: Option<&Bound<'py, PyDict>>) -> PyResult<Bound<'py, PyAny>> {
    let options = Request::new("run_planned_sql_rules", options)?;
    let py: Python<'py> = options.py();
    let plan: Bound<'py, PyAny> = options.get("plan")?;
    let graph: Bound<'py, PyAny> = options.get("graph")?;
    let effective_config: Bound<'py, PyAny> = plan.getattr("effective_config")?;
    let mut native_rules: Vec<Bound<'py, PyAny>> = Vec::new();
    for rule in plan.getattr("selected")?.try_iter()? {
        let rule: Bound<'py, PyAny> = rule?;
        if !rule.getattr("custom")?.is_truthy()? {
            native_rules.push(rule);
        }
    }
    let codes: Vec<String> = sql_rule_codes(&native_rules)?;
    let lint_config: Bound<'py, PyAny> = sql_lint_config(
        &options.get("dialect")?,
        &codes,
        &effective_config.getattr("thresholds")?,
        (
            native(py, NativeAttr::CompiledRelationKeys)?.call1((graph.getattr("project")?,))?,
            effective_config.getattr("allow_exceptions")?,
        ),
    )?;
    let run = SqlRun {
        codes: &codes,
        project_dir: plan.getattr("project_dir")?,
        discovered_inputs: options.get("discovered_inputs")?,
        project: plan.getattr("project")?,
        lint_config,
        selected_model_paths: plan.getattr("model_paths")?,
        cache_enabled: effective_config
            .getattr("cache")?
            .getattr("enabled")?
            .is_truthy()?,
        prepared_sql: options.get("prepared_sql")?,
        expansion_reuse: options.get("expansion_reuse")?,
    };
    let lint_key: String = lint_key(&run.lint_config)?;
    let identities: Vec<(String, String)> = model_rule_identities(&run, &lint_key)?;
    let project_files: Option<Bound<'py, PyAny>> = if !identities.is_empty()
        && run.prepared_sql.is_none()
        && run.selected_model_paths.is_none()
    {
        Some(collected_project_files(&run.project_dir)?)
    } else {
        None
    };
    let started: Instant = Instant::now();
    let (findings, hits, misses) =
        evaluated_sql_rules(&run, (&lint_key, identities), project_files)?;
    let sql_ms: i64 = (started.elapsed().as_secs_f64() * 1000.0).round_ties_even() as i64;
    call_with(
        &registry::class(py, RecordId::SqlRulesEvaluation)?,
        &[
            ("findings", findings),
            ("cache_hits", hits.into_bound_py_any(py)?),
            ("cache_misses", misses.into_bound_py_any(py)?),
            ("sql_ms", sql_ms.into_bound_py_any(py)?),
        ],
    )
}

fn lint_key(lint_config: &Bound<'_, PyAny>) -> PyResult<String> {
    call_with(
        &native(lint_config.py(), NativeAttr::SqlRuleLintKey)?,
        &[("config", lint_config.clone())],
    )?
    .extract()
}

fn collected_project_files<'py>(project_dir: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    call_with(
        &native(py, NativeAttr::CollectLintProjectFiles)?,
        &[
            ("project_dir", project_dir.clone()),
            ("selected_paths", py.None().into_bound(py)),
        ],
    )
}

/// The project's models SQL rules analyse, keyed by relative path in project order.
fn sql_rule_models<'py>(project: &Bound<'py, PyAny>) -> PyResult<Vec<(String, Bound<'py, PyAny>)>> {
    let mut models: Vec<(String, Bound<'py, PyAny>)> = Vec::new();
    if !project
        .getattr("settings")?
        .getattr("sql_analysis")?
        .is_truthy()?
    {
        return Ok(models);
    }
    let excluded: Bound<'py, PyAny> = false.into_bound_py_any(project.py())?;
    for model in project.getattr("models")?.try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        let analysis: Bound<'py, PyAny> = model
            .getattr("config")?
            .getattr("values")?
            .call_method1("get", ("sql_analysis",))?;
        if analysis.is(&excluded) {
            continue;
        }
        let path: String = model
            .getattr("relative_path")?
            .call_method0("as_posix")?
            .extract()?;
        if let Some(index) = models.iter().position(|(known, _)| *known == path) {
            models[index].1 = model;
        } else {
            models.push((path, model));
        }
    }
    Ok(models)
}

/// Each analysed model's SQL rule cache key, in project order.
fn model_rule_identities(run: &SqlRun<'_, '_>, lint_key: &str) -> PyResult<Vec<(String, String)>> {
    let py: Python<'_> = run.project.py();
    if run.codes.is_empty() {
        return Ok(Vec::new());
    }
    let mut models: Vec<Bound<'_, PyTuple>> = Vec::new();
    let mut paths: Vec<String> = Vec::new();
    for (path, model) in sql_rule_models(&run.project)? {
        models.push(PyTuple::new(
            py,
            [
                PyString::new(py, &path).into_any(),
                model.getattr("authored_sql")?,
                model.getattr("query_sql")?,
                contract_text(&model)?,
            ],
        )?);
        paths.push(path);
    }
    let keys: Bound<'_, PyAny> = call_with(
        &native(py, NativeAttr::SqlModelRuleKeys)?,
        &[
            ("lint_key", PyString::new(py, lint_key).into_any()),
            ("codes", PyList::new(py, run.codes)?.into_any()),
            ("models", PyList::new(py, models)?.into_any()),
        ],
    )?;
    paths
        .into_iter()
        .map(|path| {
            let key: String = keys.get_item(&path)?.extract()?;
            Ok((path, key))
        })
        .collect()
}

/// Canonical text of the dynamic column contract that SQL rule findings depend on.
fn contract_text<'py>(model: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = model.py();
    let contract: Bound<'py, PyAny> = model.getattr("dynamic_column_contract")?;
    if contract.is_none() {
        return Ok(contract);
    }
    imported(py, JSON_MODULE, "dumps")?.call(
        (imported(py, DATACLASSES_MODULE, "asdict")?.call1((contract,))?,),
        Some(&keywords(
            py,
            &[
                ("sort_keys", true.into_bound_py_any(py)?),
                ("separators", (",", ":").into_bound_py_any(py)?),
                ("default", imported(py, BUILTINS_MODULE, "str")?),
            ],
        )?),
    )
}

/// The stored findings of every path whose key still matches; undecodable ones miss.
fn cached_findings<'py>(
    bucket: &Bound<'py, PyAny>,
    keys: Vec<(String, String)>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = bucket.py();
    Ok(call_with(
        &native(py, NativeAttr::LookupSqlRuleCache)?,
        &[
            ("entries", bucket.clone()),
            ("keys", keys.into_bound_py_any(py)?),
        ],
    )?
    .downcast_into()?)
}

/// The early SQL lint's full-project file read, when it ran for this project and these codes.
fn prepared_project_files<'py>(run: &SqlRun<'_, 'py>) -> PyResult<Option<Bound<'py, PyAny>>> {
    let py: Python<'py> = run.project_dir.py();
    let prepared: &Bound<'py, PyAny> = &run.prepared_sql;
    if prepared.is_none()
        || prepared.getattr("project_dir")?.ne(&run.project_dir)?
        || !same_codes(&prepared.getattr("codes")?, run.codes)?
        || !prepared
            .getattr("future")?
            .call_method0("exception")?
            .is_none()
    {
        return Ok(None);
    }
    let texts: Bound<'py, PyAny> = prepared
        .getattr("future")?
        .call_method0("result")?
        .getattr("result")?
        .getattr("source_texts")?;
    Ok(Some(
        imported(py, BUILTINS_MODULE, "dict")?.call1((texts,))?,
    ))
}

fn same_codes(codes: &Bound<'_, PyAny>, expected: &[String]) -> PyResult<bool> {
    let mut known: BTreeSet<String> = BTreeSet::new();
    if !codes.is_none() {
        for code in codes.try_iter()? {
            known.insert(code?.extract()?);
        }
    }
    Ok(known == expected.iter().cloned().collect())
}

/// Each analysed model's findings, cached or linted, then cache accounting.
fn evaluated_sql_rules<'py>(
    run: &SqlRun<'_, 'py>,
    (lint_key, identities): (&str, Vec<(String, String)>),
    prepared_files: Option<Bound<'py, PyAny>>,
) -> PyResult<(Bound<'py, PyAny>, usize, usize)> {
    let py: Python<'py> = run.project_dir.py();
    if run.codes.is_empty() {
        return Ok((PyTuple::empty(py).into_any(), 0, 0));
    }
    let project_dir: &Bound<'py, PyAny> = &run.project_dir;
    let models: Vec<(String, Bound<'py, PyAny>)> = sql_rule_models(&run.project)?;
    let cache_path: Bound<'py, PyAny> = sql_rule_cache_path(project_dir)?;
    let bucket: Bound<'py, PyAny> = if run.cache_enabled {
        call_with(
            &native(py, NativeAttr::LoadSqlRuleCache)?,
            &[("path", cache_path.clone())],
        )?
    } else {
        PyDict::new(py).into_any()
    };
    let findings: Bound<'py, PyList> = PyList::empty(py);
    let model_hits: Bound<'py, PyDict> = cached_findings(&bucket, identities.clone())?;
    let mut misses: Vec<(String, String)> = Vec::new();
    for (path, identity) in &identities {
        match model_hits.get_item(path)? {
            Some(hit) => {
                for finding in hit.try_iter()? {
                    findings.append(finding?)?;
                }
            }
            None => misses.push((path.clone(), identity.clone())),
        }
    }
    let selected_paths: Bound<'py, PySet> = PySet::empty(py)?;
    for (path, _) in &misses {
        selected_paths.add(project_dir.div(path)?)?;
    }
    let mut file_identities: Vec<(String, String)> = Vec::new();
    let mut project_files: Bound<'py, PyAny> = py.None().into_bound(py);
    if run.selected_model_paths.is_none() {
        let model_paths: Bound<'py, PySet> = PySet::empty(py)?;
        for model in run.project.getattr("models")?.try_iter()? {
            model_paths.add(project_dir.div(model?.getattr("relative_path")?)?)?;
        }
        project_files = match prepared_project_files(run)? {
            Some(files) => files,
            None => match prepared_files {
                Some(files) => files,
                None => collected_project_files(project_dir)?,
            },
        };
        let expansions: Bound<'py, PyAny> = run.project.getattr("sql_expansions")?;
        let mut file_keys: Vec<(Bound<'py, PyAny>, String, Option<String>)> = Vec::new();
        for item in project_files.downcast::<PyDict>()?.iter() {
            let (file_path, contents) = item;
            if model_paths.contains(&file_path)? {
                continue;
            }
            let relative_path: String = file_path
                .call_method1("relative_to", (project_dir,))?
                .call_method0("as_posix")?
                .extract()?;
            let key: Option<String> = call_with(
                &native(py, NativeAttr::SqlFileRuleKey)?,
                &[
                    ("lint_key", PyString::new(py, lint_key).into_any()),
                    ("codes", PyList::new(py, run.codes)?.into_any()),
                    (
                        "relative_path",
                        PyString::new(py, &relative_path).into_any(),
                    ),
                    ("contents", contents),
                    (
                        "expanded",
                        expansions.contains(&file_path)?.into_bound_py_any(py)?,
                    ),
                ],
            )?
            .extract()?;
            file_keys.push((file_path, relative_path, key));
        }
        let mut keyed: Vec<(String, String)> = Vec::new();
        for (_, path, key) in &file_keys {
            if let Some(key) = key {
                keyed.push((path.clone(), key.clone()));
            }
        }
        let file_hits: Bound<'py, PyDict> = cached_findings(&bucket, keyed)?;
        for (file_path, relative_path, identity) in file_keys {
            match file_hits.get_item(&relative_path)? {
                Some(hit) => {
                    for finding in hit.try_iter()? {
                        findings.append(finding?)?;
                    }
                }
                None => {
                    selected_paths.add(file_path)?;
                    if let Some(identity) = identity {
                        file_identities.push((relative_path, identity));
                    }
                }
            }
        }
    }
    let violations: Vec<Bound<'py, PyAny>> = if selected_paths.is_empty() {
        Vec::new()
    } else {
        let mut dynamic: Vec<Bound<'py, PyAny>> = Vec::new();
        for (_, model) in &models {
            let contract: Bound<'py, PyAny> = model.getattr("dynamic_column_contract")?;
            if !contract.is_none() && contract.getattr("output_proven")?.is_truthy()? {
                dynamic.push(
                    project_dir
                        .div(model.getattr("relative_path")?)?
                        .call_method0("resolve")?,
                );
            }
        }
        prepared_lint_violations(
            run,
            &PyFrozenSet::new(py, selected_paths.iter())?,
            &PyFrozenSet::new(py, dynamic)?,
            &project_files,
        )?
    };
    let model_paths: BTreeSet<String> = models.into_iter().map(|(path, _)| path).collect();
    let evaluated: Vec<Bound<'py, PyAny>> = violation_findings(run, &violations, &model_paths)?;
    for finding in &evaluated {
        findings.append(finding)?;
    }
    let mut written: Vec<(String, String)> = misses.clone();
    written.extend(file_identities);
    if run.cache_enabled && !written.is_empty() {
        write_cache(&bucket, (&cache_path, written), &evaluated)?;
    }
    let hinted: Bound<'py, PyAny> = call_with(
        &native(py, NativeAttr::WithDuplicateLiteralHints)?,
        &[
            ("findings", PyTuple::new(py, findings.iter())?.into_any()),
            ("project_dir", project_dir.clone()),
        ],
    )?;
    Ok((hinted, identities.len() - misses.len(), misses.len()))
}

/// Store each rewritten path's evaluated findings in `bucket` and replace the cache file.
fn write_cache<'py>(
    bucket: &Bound<'py, PyAny>,
    (cache_path, written): (&Bound<'py, PyAny>, Vec<(String, String)>),
    evaluated: &[Bound<'py, PyAny>],
) -> PyResult<()> {
    let py: Python<'py> = bucket.py();
    let encode: Bound<'py, PyAny> = native(py, NativeAttr::EncodeSqlRuleFindings)?;
    let mut by_path: HashMap<String, Vec<Bound<'py, PyAny>>> = HashMap::new();
    for finding in evaluated {
        let path: String = finding
            .getattr("path")?
            .call_method0("as_posix")?
            .extract()?;
        by_path.entry(path).or_default().push(finding.clone());
    }
    for (path, identity) in written {
        let own: &[Bound<'py, PyAny>] = by_path.get(&path).map(Vec::as_slice).unwrap_or_default();
        let encoded: Bound<'py, PyAny> =
            call_with(&encode, &[("findings", PyList::new(py, own)?.into_any())])?;
        bucket.set_item(path, (identity, encoded))?;
    }
    let _ = call_with(
        &native(py, NativeAttr::WriteSqlRuleCache)?,
        &[("path", cache_path.clone()), ("entries", bucket.clone())],
    )?;
    Ok(())
}

/// Lint violations of `selected_paths`, reusing a matching early SQL lint.
fn prepared_lint_violations<'py>(
    run: &SqlRun<'_, 'py>,
    selected_paths: &Bound<'py, PyFrozenSet>,
    dynamic_output_paths: &Bound<'py, PyFrozenSet>,
    source_files: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = run.project_dir.py();
    let run_lint: Bound<'py, PyAny> = native(py, NativeAttr::RunLint)?;
    let compiled_expansions: Bound<'py, PyAny> = run.project.getattr("sql_expansions")?;
    let enabled_codes: Bound<'py, PyAny> = run.lint_config.getattr("enabled_native_rules")?;
    let enabled: Vec<String> = if enabled_codes.is_none() {
        Vec::new()
    } else {
        enabled_codes.extract()?
    };
    if run.prepared_sql.is_none() || !same_codes(&run.prepared_sql.getattr("codes")?, &enabled)? {
        let expansion_context: Bound<'py, PyAny> =
            if run.lint_config.getattr("native_enabled")?.is_truthy()? {
                lint_expansion_context(run)?
            } else {
                py.None().into_bound(py)
            };
        return call_with(
            &run_lint,
            &[
                ("project_dir", run.project_dir.clone()),
                ("config", run.lint_config.clone()),
                ("selected_paths", selected_paths.clone().into_any()),
                ("discovered_inputs", run.discovered_inputs.clone()),
                ("compiled_expansions", compiled_expansions),
                (
                    "dynamic_output_paths",
                    dynamic_output_paths.clone().into_any(),
                ),
                ("expansion_context", expansion_context),
                ("source_files", source_files.clone()),
            ],
        )?
        .getattr("violations")?
        .try_iter()?
        .collect();
    }
    let completed: Bound<'py, PyAny> =
        run.prepared_sql.getattr("future")?.call_method0("result")?;
    let prepared: Bound<'py, PyAny> = completed.getattr("result")?;
    let proof_paths: Bound<'py, PyAny> =
        selected_paths.call_method1("__and__", (dynamic_output_paths,))?;
    let mut violations: Vec<Bound<'py, PyAny>> = Vec::new();
    for violation in prepared.getattr("violations")?.try_iter()? {
        let violation: Bound<'py, PyAny> = violation?;
        let path: Bound<'py, PyAny> = violation.getattr("file_path")?;
        if selected_paths.contains(&path)? && !proof_paths.contains(&path)? {
            violations.push(violation);
        }
    }
    if proof_paths.is_truthy()? {
        let proven: Bound<'py, PyAny> = call_with(
            &run_lint,
            &[
                ("project_dir", run.project_dir.clone()),
                ("config", run.lint_config.clone()),
                ("selected_paths", proof_paths.clone()),
                ("discovered_inputs", run.discovered_inputs.clone()),
                ("compiled_expansions", compiled_expansions),
                ("dynamic_output_paths", proof_paths),
                ("expansion_context", completed.getattr("context")?),
                (
                    "source_files",
                    imported(py, BUILTINS_MODULE, "dict")?
                        .call1((prepared.getattr("source_texts")?,))?,
                ),
            ],
        )?;
        for violation in proven.getattr("violations")?.try_iter()? {
            violations.push(violation?);
        }
    }
    Ok(violations)
}

/// Build lint expansion, reusing the compiler's scope only for the same discovery.
fn lint_expansion_context<'py>(run: &SqlRun<'_, 'py>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = run.project_dir.py();
    let reuse: &Bound<'py, PyAny> = &run.expansion_reuse;
    let declaration_scope: Bound<'py, PyAny> = if !reuse.is_none()
        && reuse
            .getattr("discovered_inputs")?
            .is(&run.discovered_inputs)
    {
        reuse.getattr("declaration_scope")?
    } else {
        py.None().into_bound(py)
    };
    call_with(
        &native(py, NativeAttr::BuildLintExpansionContext)?,
        &[
            ("project_dir", run.project_dir.clone()),
            ("discovered_inputs", run.discovered_inputs.clone()),
            ("declaration_scope", declaration_scope),
        ],
    )
}

/// The findings of the selected SQL rules' violations; an engine failure leaves each unevaluated.
fn violation_findings<'py>(
    run: &SqlRun<'_, 'py>,
    violations: &[Bound<'py, PyAny>],
    model_paths: &BTreeSet<String>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = run.project_dir.py();
    let engine_error: String = registry::error(py, ErrorId::NativeLint)?
        .getattr("code")?
        .extract()?;
    let safe_fixes: Bound<'py, PyAny> = PyFrozenSet::new(py, SAFE_RULE_FIX_CODES)?.into_any();
    let resolved: Bound<'py, PyAny> = run.project_dir.call_method0("resolve")?;
    let replace: Bound<'py, PyAny> = imported(py, DATACLASSES_MODULE, "replace")?;
    let no_paths: BTreeSet<String> = BTreeSet::new();
    let mut evaluated: Vec<Bound<'py, PyAny>> = Vec::new();
    for violation in violations {
        let code: String = violation.getattr("code")?.extract()?;
        if code == SQL_RULE_SUPPRESSION_CODE || run.codes.contains(&code) {
            evaluated.push(lint_finding(
                violation,
                (&resolved, &safe_fixes),
                model_paths,
            )?);
        } else if code == engine_error {
            let finding: Bound<'py, PyAny> =
                lint_finding(violation, (&resolved, &safe_fixes), &no_paths)?;
            let message: String = violation.getattr("message")?.extract()?;
            for rule_code in run.codes {
                evaluated.push(
                    replace.call(
                        (&finding,),
                        Some(&keywords(
                            py,
                            &[
                                ("code", PyString::new(py, rule_code).into_any()),
                                (
                                    "message",
                                    PyString::new(
                                        py,
                                        &format!(
                                            "Rule {rule_code} could not be evaluated: {message}"
                                        ),
                                    )
                                    .into_any(),
                                ),
                                ("unevaluated", true.into_bound_py_any(py)?),
                            ],
                        )?),
                    )?,
                );
            }
        }
    }
    Ok(evaluated)
}

/// One lint violation as a finding; fixable when `format --fix` would attempt its edit.
fn lint_finding<'py>(
    violation: &Bound<'py, PyAny>,
    (resolved_dir, safe_fixes): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    fixable_paths: &BTreeSet<String>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = violation.py();
    let mut path: Bound<'py, PyAny> = violation.getattr("file_path")?;
    if path.call_method0("is_absolute")?.is_truthy()?
        && path
            .call_method1("is_relative_to", (resolved_dir,))?
            .is_truthy()?
    {
        path = path.call_method1("relative_to", (resolved_dir,))?;
    }
    let code: Bound<'py, PyAny> = violation.getattr("code")?;
    let remediation: Bound<'py, PyAny> = violation.getattr("remediation")?;
    let fixable: bool = !violation.getattr("fix")?.is_none()
        && safe_fixes.contains(&code)?
        && fixable_paths.contains(&path.call_method0("as_posix")?.extract::<String>()?);
    call_with(
        &registry::class(py, RecordId::Finding)?,
        &[
            ("code", code),
            ("path", path),
            ("line", violation.getattr("line")?),
            ("column", violation.getattr("column")?),
            ("message", violation.getattr("message")?),
            (
                "remediation",
                if remediation.is_truthy()? {
                    remediation
                } else {
                    PyString::new(py, DEFAULT_REMEDIATION).into_any()
                },
            ),
            ("fixable", fixable.into_bound_py_any(py)?),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_planned_sql_rules, module)?)?;
    Ok(())
}

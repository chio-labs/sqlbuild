//! Run the planned SQL rules through native lint, reusing cached and early-lint results.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::time::Instant;

use pyo3::exceptions::PyException;
use pyo3::prelude::{
    Bound, IntoPyObject, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyRef, PyResult,
    Python,
};
use pyo3::types::{PyBytes, PyDict, PyString, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_core::text::main::python_splitlines::python_splitlines;
use sqlbuild_rules::rule_cache::main::file_rule_key::file_rule_key;
use sqlbuild_rules::rule_results::main::duplicate_literal_hints::duplicate_literal_hints;
use sqlbuild_rules::rule_results::models::RuleFinding;

use crate::bindings::_helpers::analysis::model_reads::output_proven;
use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::rules::constants::SAFE_RULE_FIX_CODES;
use crate::bindings::_helpers::rules::early_sql_lint::{
    EarlyLintResult, EarlySqlLint, PreparedSqlLint, sql_lint_settings, sql_rule_cache_path,
};
use crate::bindings::_helpers::rules::lint_expansion::{
    LintExpansionSources, lint_expansion_inputs,
};
use crate::bindings::_helpers::rules::lint_inputs::project_sql_expansions;
use crate::bindings::_helpers::rules::lint_pipeline::{
    CompiledSource, LintFile, LintOutcome, LintRequest, LintSettings, LintViolationRow, lint,
    lint_sources, outside_project, resolved,
};
use crate::bindings::_helpers::rules::relation_keys::project_relation_keys;
use crate::bindings::_helpers::rules::rule_cache::{
    StoredEntries, cached_rule_findings, encoded_findings, model_rule_keys, settings_lint_key,
    stored_entries, write_rule_cache,
};

const DATACLASSES_MODULE: &str = "dataclasses";
const JSON_MODULE: &str = "json";
const BUILTINS_MODULE: &str = "builtins";
const PATHLIB_MODULE: &str = "pathlib";
const SQL_RULE_PREFIX: &str = "SQBRSQL";
const SQL_RULE_SUPPRESSION_CODE: &str = "SQBRSQL000";
const DEFAULT_REMEDIATION: &str = "Update the authored SQL to satisfy this rule.";
const UTF8: &str = "utf-8";

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
    project_dir: PathBuf,
    discovered_inputs: Bound<'py, PyAny>,
    project: Bound<'py, PyAny>,
    settings: LintSettings,
    /// Whether the plan selected model paths, rather than the whole project.
    model_selection: bool,
    cache_enabled: bool,
    early_lint: Option<PyRef<'py, EarlySqlLint>>,
}

impl<'py> SqlRun<'_, 'py> {
    /// The early SQL lint that started for this compile, if any.
    fn prepared(&self) -> Option<&PreparedSqlLint> {
        self.early_lint
            .as_ref()
            .and_then(|early| early.preparation())
            .map(|preparation| preparation.get())
    }
}

/// `path` with forward slashes, as `PurePath.as_posix` writes it.
fn posix(path: &Path) -> String {
    path.to_string_lossy()
        .replace(std::path::MAIN_SEPARATOR, "/")
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
    let thresholds: Bound<'py, PyAny> = effective_config.getattr("thresholds")?;
    let dialect: String = options.get("dialect")?.extract()?;
    let settings: LintSettings = sql_lint_settings(
        &dialect,
        &codes,
        |key| thresholds.call_method1("get", (key,))?.extract(),
        (
            project_relation_keys(&graph.getattr("project")?)?,
            effective_config.getattr("allow_exceptions")?.is_truthy()?,
        ),
    )?;
    let early_lint: Bound<'py, PyAny> = options.get("early_lint")?;
    let run = SqlRun {
        codes: &codes,
        project_dir: plan.getattr("project_dir")?.extract()?,
        discovered_inputs: options.get("discovered_inputs")?,
        project: plan.getattr("project")?,
        settings,
        model_selection: !plan.getattr("model_paths")?.is_none(),
        cache_enabled: effective_config
            .getattr("cache")?
            .getattr("enabled")?
            .is_truthy()?,
        early_lint: if early_lint.is_none() {
            None
        } else {
            Some(early_lint.downcast::<EarlySqlLint>()?.borrow())
        },
    };
    let lint_key: String = settings_lint_key(&run.settings);
    let identities: Vec<(String, String)> = model_rule_identities(&run, &lint_key)?;
    let project_files: Option<Vec<LintFile>> =
        if !identities.is_empty() && run.prepared().is_none() && !run.model_selection {
            Some(lint_sources(&run.project_dir, None, None)?)
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
            ("findings", finding_objects(py, findings)?.into_any()),
            ("cache_hits", hits.into_bound_py_any(py)?),
            ("cache_misses", misses.into_bound_py_any(py)?),
            ("sql_ms", sql_ms.into_bound_py_any(py)?),
        ],
    )
}

/// Finding rows as `Finding` records.
fn finding_objects(py: Python<'_>, findings: Vec<RuleFinding>) -> PyResult<Bound<'_, PyTuple>> {
    let class: Bound<'_, PyAny> = registry::class(py, RecordId::Finding)?;
    let path_class: Bound<'_, PyAny> = imported(py, PATHLIB_MODULE, "Path")?;
    let objects: Vec<Bound<'_, PyAny>> = findings
        .into_iter()
        .map(|finding| {
            call_with(
                &class,
                &[
                    ("code", PyString::new(py, &finding.code).into_any()),
                    ("path", path_class.call1((finding.path,))?),
                    ("line", finding.line.into_pyobject(py)?.into_any()),
                    ("column", finding.column.into_pyobject(py)?.into_any()),
                    ("message", PyString::new(py, &finding.message).into_any()),
                    (
                        "remediation",
                        PyString::new(py, &finding.remediation).into_any(),
                    ),
                    ("unevaluated", finding.unevaluated.into_bound_py_any(py)?),
                    ("fixable", finding.fixable.into_bound_py_any(py)?),
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    PyTuple::new(py, objects)
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
    if run.codes.is_empty() {
        return Ok(Vec::new());
    }
    let mut models: Vec<(String, String, String, Option<String>)> = Vec::new();
    for (path, model) in sql_rule_models(&run.project)? {
        models.push((
            path,
            model.getattr("authored_sql")?.extract()?,
            model.getattr("query_sql")?.extract()?,
            contract_text(&model)?,
        ));
    }
    let keys: BTreeMap<String, String> = model_rule_keys(lint_key, run.codes, &models);
    Ok(models
        .into_iter()
        .map(|(path, ..)| {
            let key: String = keys[&path].clone();
            (path, key)
        })
        .collect())
}

/// Canonical text of the dynamic column contract that SQL rule findings depend on.
fn contract_text(model: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    let py: Python<'_> = model.py();
    let contract: Bound<'_, PyAny> = model.getattr("dynamic_column_contract")?;
    if contract.is_none() {
        return Ok(None);
    }
    imported(py, JSON_MODULE, "dumps")?
        .call(
            (imported(py, DATACLASSES_MODULE, "asdict")?.call1((contract,))?,),
            Some(&keywords(
                py,
                &[
                    ("sort_keys", true.into_bound_py_any(py)?),
                    ("separators", (",", ":").into_bound_py_any(py)?),
                    ("default", imported(py, BUILTINS_MODULE, "str")?),
                ],
            )?),
        )?
        .extract()
        .map(Some)
}

/// The early SQL lint's result, when it ran for this project and these codes.
fn prepared_result<'a>(
    run: &'a SqlRun<'_, '_>,
    py: Python<'_>,
) -> Option<&'a Result<EarlyLintResult, PyErr>> {
    let prepared: &PreparedSqlLint = run.prepared()?;
    if !prepared.matches(&run.project_dir, run.codes) {
        return None;
    }
    Some(prepared.result(py))
}

/// Each analysed model's findings, cached or linted, then cache accounting.
fn evaluated_sql_rules(
    run: &SqlRun<'_, '_>,
    (lint_key, identities): (&str, Vec<(String, String)>),
    prepared_files: Option<Vec<LintFile>>,
) -> PyResult<(Vec<RuleFinding>, usize, usize)> {
    let py: Python<'_> = run.project.py();
    if run.codes.is_empty() {
        return Ok((Vec::new(), 0, 0));
    }
    let project_dir: &Path = &run.project_dir;
    let models: Vec<(String, Bound<'_, PyAny>)> = sql_rule_models(&run.project)?;
    let cache_path: PathBuf = sql_rule_cache_path(project_dir);
    let mut bucket: StoredEntries = if run.cache_enabled {
        stored_entries(&cache_path)?
    } else {
        StoredEntries::new()
    };
    let mut findings: Vec<RuleFinding> = Vec::new();
    let mut model_hits: BTreeMap<String, Vec<RuleFinding>> =
        cached_rule_findings(&bucket, &identities)?;
    let mut misses: Vec<(String, String)> = Vec::new();
    for (path, identity) in &identities {
        match model_hits.remove(path) {
            Some(hit) => findings.extend(hit),
            None => misses.push((path.clone(), identity.clone())),
        }
    }
    let mut selected_paths: BTreeSet<PathBuf> = misses
        .iter()
        .map(|(path, _)| project_dir.join(path))
        .collect();
    let mut file_identities: Vec<(String, String)> = Vec::new();
    let mut project_files: Option<Vec<LintFile>> = None;
    let compiled: HashMap<PathBuf, CompiledSource> = project_sql_expansions(&run.project)?;
    if !run.model_selection {
        let mut model_paths: HashSet<PathBuf> = HashSet::new();
        for model in run.project.getattr("models")?.try_iter()? {
            model_paths
                .insert(project_dir.join(model?.getattr("relative_path")?.extract::<PathBuf>()?));
        }
        let files: Vec<LintFile> = match prepared_result(run, py) {
            Some(Ok(result)) => result.outcome.files.clone(),
            Some(Err(error)) if !error.is_instance_of::<PyException>(py) => {
                return Err(error.clone_ref(py));
            }
            Some(Err(_)) | None => match prepared_files {
                Some(files) => files,
                None => lint_sources(project_dir, None, None)?,
            },
        };
        let mut file_keys: Vec<(PathBuf, String, Option<String>)> = Vec::new();
        for file in &files {
            if model_paths.contains(&file.path) {
                continue;
            }
            let Ok(relative) = file.path.strip_prefix(project_dir) else {
                return Err(outside_project(&file.path, project_dir));
            };
            let relative_path: String = posix(relative);
            let key: Option<String> = file_rule_key(
                lint_key,
                run.codes,
                (&relative_path, &file.contents),
                compiled.contains_key(&file.path),
            );
            file_keys.push((file.path.clone(), relative_path, key));
        }
        let mut keyed: Vec<(String, String)> = Vec::new();
        for (_, path, key) in &file_keys {
            if let Some(key) = key {
                keyed.push((path.clone(), key.clone()));
            }
        }
        let mut file_hits: BTreeMap<String, Vec<RuleFinding>> =
            cached_rule_findings(&bucket, &keyed)?;
        for (file_path, relative_path, identity) in file_keys {
            match file_hits.remove(&relative_path) {
                Some(hit) => findings.extend(hit),
                None => {
                    selected_paths.insert(file_path);
                    if let Some(identity) = identity {
                        file_identities.push((relative_path, identity));
                    }
                }
            }
        }
        project_files = Some(files);
    }
    let violations: Vec<(PathBuf, LintViolationRow)> = if selected_paths.is_empty() {
        Vec::new()
    } else {
        let mut dynamic: HashSet<PathBuf> = HashSet::new();
        for (_, model) in &models {
            if output_proven(model)? {
                dynamic.insert(resolved(
                    &project_dir.join(model.getattr("relative_path")?.extract::<PathBuf>()?),
                ));
            }
        }
        prepared_lint_violations(run, (&selected_paths, &dynamic), &compiled, project_files)?
    };
    let model_paths: BTreeSet<String> = models.into_iter().map(|(path, _)| path).collect();
    let evaluated: Vec<RuleFinding> = violation_findings(run, &violations, &model_paths)?;
    findings.extend(evaluated.iter().cloned());
    let mut written: Vec<(String, String)> = misses.clone();
    written.extend(file_identities);
    if run.cache_enabled && !written.is_empty() {
        let mut by_path: HashMap<&str, Vec<&RuleFinding>> = HashMap::new();
        for finding in &evaluated {
            by_path
                .entry(finding.path.as_str())
                .or_default()
                .push(finding);
        }
        for (path, identity) in written {
            let own: &[&RuleFinding] = by_path.get(path.as_str()).map_or(&[], Vec::as_slice);
            let encoded: String = encoded_findings(own)?;
            bucket.insert(path, (identity, encoded));
        }
        write_rule_cache(&cache_path, &bucket)?;
    }
    let hints: Vec<Option<String>> =
        duplicate_literal_hints::<PyErr>(&findings, |path| file_lines(py, project_dir, path))?;
    for (finding, hint) in findings.iter_mut().zip(hints) {
        if let Some(remediation) = hint {
            finding.remediation = remediation;
        }
    }
    Ok((findings, identities.len() - misses.len(), misses.len()))
}

/// The authored lines of one finding's file; an unreadable file has none.
fn file_lines(py: Python<'_>, project_dir: &Path, path: &str) -> PyResult<Vec<String>> {
    let bytes: Vec<u8> = match std::fs::read(project_dir.join(path)) {
        Ok(bytes) => bytes,
        Err(_) => return Ok(Vec::new()),
    };
    let text: String = match String::from_utf8(bytes) {
        Ok(text) => text,
        Err(error) => {
            return PyBytes::new(py, error.as_bytes())
                .call_method1("decode", (UTF8,))?
                .extract();
        }
    };
    Ok(python_splitlines(&text)
        .into_iter()
        .map(str::to_owned)
        .collect())
}

/// Lint violations of `selected_paths` by file path, reusing a matching early SQL lint.
fn prepared_lint_violations(
    run: &SqlRun<'_, '_>,
    (selected_paths, dynamic_output_paths): (&BTreeSet<PathBuf>, &HashSet<PathBuf>),
    compiled: &HashMap<PathBuf, CompiledSource>,
    source_files: Option<Vec<LintFile>>,
) -> PyResult<Vec<(PathBuf, LintViolationRow)>> {
    let py: Python<'_> = run.project.py();
    let enabled: &[String] = run
        .settings
        .sql
        .enabled_rules
        .as_deref()
        .unwrap_or_default();
    let prepared: Option<&PreparedSqlLint> = run
        .prepared()
        .filter(|prepared| prepared.has_codes(enabled));
    let Some(prepared) = prepared else {
        let context = if run.settings.native_enabled {
            Some(lint_expansion_context(run)?)
        } else {
            None
        };
        let files: Vec<LintFile> =
            lint_sources(&run.project_dir, Some(selected_paths), source_files)?;
        let outcome: LintOutcome = lint(
            py,
            &LintRequest {
                project_dir: &run.project_dir,
                settings: &run.settings,
                dynamic_output_paths,
                compiled_expansions: compiled,
                context: context.as_ref(),
                skip_unexpandable: false,
                stop: None,
            },
            files,
        )?;
        return Ok(path_rows(outcome));
    };
    let result: &EarlyLintResult = match prepared.result(py) {
        Ok(result) => result,
        Err(error) => return Err(error.clone_ref(py)),
    };
    let proof_paths: BTreeSet<PathBuf> = selected_paths
        .iter()
        .filter(|path| dynamic_output_paths.contains(*path))
        .cloned()
        .collect();
    let early: &LintOutcome = &result.outcome;
    let mut violations: Vec<(PathBuf, LintViolationRow)> = early
        .violations
        .iter()
        .filter_map(|row| {
            let path: &PathBuf = &early.files[row.file].path;
            (selected_paths.contains(path) && !proof_paths.contains(path))
                .then(|| (path.clone(), row.clone()))
        })
        .collect();
    if !proof_paths.is_empty() {
        let proof_set: HashSet<PathBuf> = proof_paths.iter().cloned().collect();
        let files: Vec<LintFile> = lint_sources(
            &run.project_dir,
            Some(&proof_paths),
            Some(early.files.clone()),
        )?;
        let proven: LintOutcome = lint(
            py,
            &LintRequest {
                project_dir: &run.project_dir,
                settings: &run.settings,
                dynamic_output_paths: &proof_set,
                compiled_expansions: compiled,
                context: Some(&result.context),
                skip_unexpandable: false,
                stop: None,
            },
            files,
        )?;
        violations.extend(path_rows(proven));
    }
    Ok(violations)
}

/// An outcome's violations with their file paths.
fn path_rows(outcome: LintOutcome) -> Vec<(PathBuf, LintViolationRow)> {
    let files: Vec<LintFile> = outcome.files;
    outcome
        .violations
        .into_iter()
        .map(|row| (files[row.file].path.clone(), row))
        .collect()
}

/// Build lint expansion, reusing the compiler's scope only for the same discovery.
fn lint_expansion_context(
    run: &SqlRun<'_, '_>,
) -> PyResult<
    crate::bindings::_helpers::compile_attachment::sql_expansion_context::SqlExpansionInputs,
> {
    let py: Python<'_> = run.project.py();
    let declaration_scope: Option<Bound<'_, PyAny>> = run
        .early_lint
        .as_ref()
        .and_then(|early| early.expansion_reuse())
        .filter(|reuse| reuse.discovered_inputs.bind(py).is(&run.discovered_inputs))
        .map(|reuse| reuse.declaration_scope.bind(py).clone());
    lint_expansion_inputs(LintExpansionSources {
        project_dir: run.project_dir.clone().into_pyobject(py)?.into_any(),
        value_renderer: None,
        discovered_inputs: (!run.discovered_inputs.is_none())
            .then(|| run.discovered_inputs.clone()),
        declaration_scope,
        static_declaration_scope: None,
    })
}

/// The findings of the selected SQL rules' violations; an engine failure leaves each unevaluated.
fn violation_findings(
    run: &SqlRun<'_, '_>,
    violations: &[(PathBuf, LintViolationRow)],
    model_paths: &BTreeSet<String>,
) -> PyResult<Vec<RuleFinding>> {
    let py: Python<'_> = run.project.py();
    let engine_error: String = registry::error(py, ErrorId::NativeLint)?
        .getattr("code")?
        .extract()?;
    let resolved_dir: PathBuf = resolved(&run.project_dir);
    let no_paths: BTreeSet<String> = BTreeSet::new();
    let mut evaluated: Vec<RuleFinding> = Vec::new();
    for (path, violation) in violations {
        let code: &str = &violation.code;
        if code == SQL_RULE_SUPPRESSION_CODE || run.codes.iter().any(|known| known == code) {
            evaluated.push(lint_finding((path, violation), &resolved_dir, model_paths));
        } else if code == engine_error {
            let finding: RuleFinding = lint_finding((path, violation), &resolved_dir, &no_paths);
            for rule_code in run.codes {
                evaluated.push(RuleFinding {
                    code: rule_code.clone(),
                    message: format!(
                        "Rule {rule_code} could not be evaluated: {}",
                        violation.message
                    ),
                    unevaluated: true,
                    ..finding.clone()
                });
            }
        }
    }
    Ok(evaluated)
}

/// One lint violation as a finding; fixable when `format --fix` would attempt its edit.
fn lint_finding(
    (path, violation): (&Path, &LintViolationRow),
    resolved_dir: &Path,
    fixable_paths: &BTreeSet<String>,
) -> RuleFinding {
    let path: &Path = if path.is_absolute() {
        path.strip_prefix(resolved_dir).unwrap_or(path)
    } else {
        path
    };
    let path: String = posix(path);
    let fixable: bool = violation.fix.is_some()
        && SAFE_RULE_FIX_CODES.contains(&violation.code.as_str())
        && fixable_paths.contains(&path);
    RuleFinding {
        code: violation.code.clone(),
        path,
        line: violation.line,
        column: violation.column,
        message: violation.message.clone(),
        remediation: violation
            .remediation
            .clone()
            .filter(|remediation| !remediation.is_empty())
            .unwrap_or_else(|| DEFAULT_REMEDIATION.to_owned()),
        unevaluated: false,
        affected_rules: Vec::new(),
        fixable,
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_planned_sql_rules, module)?)?;
    Ok(())
}

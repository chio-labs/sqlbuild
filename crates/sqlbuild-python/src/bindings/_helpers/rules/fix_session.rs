//! Compiler-verified fixed-point repair planning, entirely in memory.

use std::collections::BTreeSet;
use std::path::PathBuf;

use pyo3::exceptions::PyException;
use pyo3::prelude::{Bound, IntoPyObject, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyList, PyListMethods, PyTuple};
use sqlbuild_rules::fix_verification::main::refusal::refusal;
use sqlbuild_rules::fix_verification::main::with_edits::with_edits;
use sqlbuild_rules::fix_verification::models::{FixEdit, FixEligibility};

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::rules::constants::SAFE_RULE_FIX_CODES;
use crate::bindings::_helpers::rules::fix_facts::compile_facts;
use crate::bindings::_helpers::rules::fix_verdict::fix_verdict;

const NATIVE: &str = "sqlbuild._native";
const MODELS: &str = "sqlbuild.lint.models";
const ADAPTER: &str = "sqlbuild.adapter.contract.classes.base_adapter";
const COMPILE_ERRORS: &str = "sqlbuild.compiler.compile.exceptions";
const LINT_ERRORS: &str = "sqlbuild.lint.exceptions";
const VERIFICATION_FAILURE: &str =
    "Compilation could not prove unchanged output columns, types, dependencies and lineage";
const APPLIED_REASON: &str = "Meaning-preserving rewrite; compiler invariants verified";
const MAX_PASSES: usize = 128;

struct FixSession<'py> {
    project_dir: Bound<'py, PyAny>,
    original: Bound<'py, PyDict>,
    config: Bound<'py, PyAny>,
    adapter: Bound<'py, PyAny>,
    inputs: Bound<'py, PyAny>,
    reports: Vec<Bound<'py, PyAny>>,
    blocked: Bound<'py, PyDict>,
    skipped: Bound<'py, PyDict>,
    baseline: Option<Bound<'py, PyAny>>,
    baseline_facts: Option<Bound<'py, PyAny>>,
}

type PlannedPass<'py> = (
    Bound<'py, PyDict>,
    Vec<Bound<'py, PyAny>>,
    Vec<Bound<'py, PyAny>>,
);
type FixState = (Vec<(PathBuf, String)>, Vec<PathBuf>);

/// Plan fixes without exposing any unverified intermediate source on disk.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn plan_rule_fixes<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "plan_rule_fixes",
        options,
        (
            &[
                "project_dir",
                "files",
                "config",
                "adapter",
                "discovered_inputs",
                "enabled",
            ],
            &[],
        ),
    )?;
    let files = args.value("files")?.cast_into::<PyDict>()?;
    if !args.flag("enabled")? {
        return result(&files, &[], &[]);
    }
    let adapter = args.value("adapter")?;
    let inputs = args.value("discovered_inputs")?;
    if !adapter.is_instance(&imported(py, ADAPTER, "BaseAdapter")?)? || inputs.is_none() {
        return Err(PyErr::from_value(
            imported(py, LINT_ERRORS, "ProjectCompileError")?
                .call1(("format --fix requires discovered compiler inputs and an adapter",))?,
        ));
    }
    FixSession {
        project_dir: args.value("project_dir")?,
        original: files,
        config: args.value("config")?,
        adapter,
        inputs,
        reports: Vec::new(),
        blocked: PyDict::new(py),
        skipped: PyDict::new(py),
        baseline: None,
        baseline_facts: None,
    }
    .run()
}

impl<'py> FixSession<'py> {
    fn run(&mut self) -> PyResult<Bound<'py, PyAny>> {
        let py = self.original.py();
        let mut current = self.original.copy()?;
        let paths: Vec<Bound<'py, PyAny>> = self
            .inputs
            .getattr("model_files")?
            .try_iter()?
            .map(|model| model?.getattr("file_path"))
            .collect::<PyResult<_>>()?;
        let model_paths = PyFrozenSet::new(py, paths)?;
        let mut seen: BTreeSet<FixState> = BTreeSet::new();
        for _ in 0..MAX_PASSES {
            let mut files: Vec<(PathBuf, String)> = current
                .iter()
                .map(|(path, contents)| Ok((path.extract()?, contents.extract()?)))
                .collect::<PyResult<_>>()?;
            files.sort();
            let mut blocked: Vec<PathBuf> = self.blocked.keys().extract()?;
            blocked.sort();
            if !seen.insert((files, blocked)) {
                return self.decline("Rule fixes did not converge");
            }
            let (edits, pending, remaining) = self.plan_pass(&current, model_paths.as_any())?;
            if edits.is_empty() {
                let mut reports = self.reports.clone();
                reports.extend(not_yet_reported(py, &self.reports, &remaining)?);
                let mut faults = self.blocked_faults()?;
                faults.extend(self.skipped_warnings()?);
                return result(&current, &reports, &faults);
            }
            let Some(verified) = self.verify_pass(&current, &edits, &pending)? else {
                self.reports.extend(pending);
                return self.decline(VERIFICATION_FAILURE);
            };
            current = verified;
        }
        self.decline("Rule fix pass limit exceeded")
    }

    fn plan_pass(
        &mut self,
        files: &Bound<'py, PyDict>,
        model_paths: &Bound<'py, PyAny>,
    ) -> PyResult<PlannedPass<'py>> {
        let py = files.py();
        let relation_keys = self.relation_keys()?;
        let config = replace(
            &self.config,
            &[
                (
                    "enabled_native_rules",
                    PyTuple::new(py, ["SQBRSQL"])?.into_any(),
                ),
                ("relation_keys", relation_keys),
            ],
        )?;
        let lint = call_with(
            &imported(py, NATIVE, "run_lint")?,
            &[
                ("project_dir", self.project_dir.clone()),
                ("config", config),
                ("value_renderer", self.adapter.clone()),
                ("discovered_inputs", updated_inputs(&self.inputs, files)?),
                ("source_files", files.clone().into_any()),
                (
                    "selected_paths",
                    PyFrozenSet::new(py, files.keys())?.into_any(),
                ),
                (
                    "skip_unexpandable",
                    true.into_pyobject(py)?.to_owned().into_any(),
                ),
            ],
        )?;
        self.skipped
            .call_method1("update", (lint.getattr("unexpandable")?,))?;
        let edits = PyDict::new(py);
        let mut pending: Vec<Bound<'py, PyAny>> = Vec::new();
        let mut remaining: Vec<Bound<'py, PyAny>> = Vec::new();
        for violation in lint.getattr("violations")?.try_iter()? {
            let violation = violation?;
            if !violation
                .getattr("code")?
                .extract::<String>()?
                .starts_with("SQBRSQL")
            {
                continue;
            }
            let reason = self.refusal(&violation, model_paths)?;
            let edit = violation.getattr("fix")?;
            if reason.is_some() || edit.is_none() {
                remaining.push(report(
                    &violation,
                    if reason.is_some() {
                        "refused"
                    } else {
                        "unavailable"
                    },
                    reason
                        .as_deref()
                        .unwrap_or("No meaning-preserving automatic fix is available"),
                )?);
                continue;
            }
            let path = edit.getattr("file_path")?;
            let chosen = if let Some(chosen) = edits.get_item(&path)? {
                chosen.cast_into::<PyList>()?
            } else {
                let chosen = PyList::empty(py);
                edits.set_item(&path, &chosen)?;
                chosen
            };
            let start: usize = edit.getattr("start")?.extract()?;
            let end: usize = edit.getattr("end")?.extract()?;
            let mut overlaps = false;
            for other in chosen.iter() {
                if start < other.getattr("end")?.extract::<usize>()?
                    && other.getattr("start")?.extract::<usize>()? < end
                {
                    overlaps = true;
                    break;
                }
            }
            if !overlaps {
                chosen.append(edit)?;
                pending.push(report(&violation, "applied", APPLIED_REASON)?);
            }
        }
        Ok((edits, pending, remaining))
    }

    fn refusal(
        &self,
        violation: &Bound<'py, PyAny>,
        model_paths: &Bound<'py, PyAny>,
    ) -> PyResult<Option<String>> {
        let code = violation.getattr("code")?;
        let path = violation.getattr("file_path")?;
        let has_fix = !violation.getattr("fix")?.is_none();
        let facts = FixEligibility {
            model_body: model_paths.contains(&path)?,
            has_fix,
            safe_code: SAFE_RULE_FIX_CODES.contains(&code.extract::<String>()?.as_str()),
            conditionless_join: code.eq("SQBRSQL003")?,
            snowflake: self.config.getattr("dialect")?.eq("snowflake")?,
        };
        if let Some(reason) = refusal(&facts) {
            return Ok(Some(reason.to_owned()));
        }
        let unavailable = violation.getattr("fix_unavailable_reason")?;
        if !unavailable.is_none() || !has_fix {
            return unavailable.extract();
        }
        self.blocked
            .get_item(path)?
            .map_or(Ok(None), |reason| reason.extract().map(Some))
    }

    fn verify_pass(
        &mut self,
        current: &Bound<'py, PyDict>,
        edits: &Bound<'py, PyDict>,
        pending: &[Bound<'py, PyAny>],
    ) -> PyResult<Option<Bound<'py, PyDict>>> {
        let mut accepted = edits.copy()?;
        let mut confirmed = false;
        while !accepted.is_empty() {
            let verdict = self.verdict(&edited_files(&self.unblocked(current)?, &accepted)?)?;
            if let Some(verdict) = &verdict
                && verdict.getattr("verified")?.is_truthy()?
            {
                confirmed = true;
                break;
            }
            let hits = failing_edits(verdict.as_ref(), &accepted)?;
            if hits.is_empty() {
                accepted = self.isolate(current, &accepted)?;
                break;
            }
            for (path, reason) in hits.iter() {
                self.blocked.set_item(&path, reason)?;
                accepted.del_item(path)?;
            }
        }
        let candidate = edited_files(&self.unblocked(current)?, &accepted)?;
        if !accepted.is_empty() && !confirmed {
            let verdict = self.verdict(&candidate)?;
            if !verdict
                .as_ref()
                .map_or(Ok(false), |value| value.getattr("verified")?.is_truthy())?
            {
                return Ok(None);
            }
        }
        let mut reports: Vec<Bound<'py, PyAny>> = Vec::new();
        for report in self.reports.iter().chain(pending) {
            reports.push(
                if let Some(reason) = self.blocked.get_item(report.getattr("file_path")?)? {
                    refused(report, &reason.extract::<String>()?)?
                } else {
                    report.clone()
                },
            );
        }
        self.reports = reports;
        Ok(Some(candidate))
    }

    fn isolate(
        &mut self,
        current: &Bound<'py, PyDict>,
        edits: &Bound<'py, PyDict>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let base = self.unblocked(current)?;
        let accepted = PyDict::new(current.py());
        for (path, path_edits) in edits.iter() {
            let single = PyDict::new(current.py());
            single.set_item(&path, &path_edits)?;
            let verdict = self.verdict(&edited_files(&base, &single)?)?;
            if let Some(verdict) = &verdict
                && verdict.getattr("verified")?.is_truthy()?
            {
                accepted.set_item(path, path_edits)?;
            } else {
                let hits = failing_edits(verdict.as_ref(), &single)?;
                self.blocked.set_item(
                    &path,
                    hits.get_item(&path)?
                        .unwrap_or(VERIFICATION_FAILURE.into_pyobject(current.py())?.into_any()),
                )?;
            }
        }
        Ok(accepted)
    }

    fn unblocked(&self, files: &Bound<'py, PyDict>) -> PyResult<Bound<'py, PyDict>> {
        let result = files.copy()?;
        for (path, _) in self.blocked.iter() {
            if result.contains(&path)? {
                result.set_item(&path, self.original.get_item(&path)?)?;
            }
        }
        Ok(result)
    }

    fn baseline(&mut self) -> PyResult<Bound<'py, PyAny>> {
        if let Some(baseline) = &self.baseline {
            return Ok(baseline.clone());
        }
        let baseline = call_with(
            &imported(self.inputs.py(), NATIVE, "build_compiled_project")?,
            &[
                ("discovered_inputs", self.inputs.clone()),
                ("adapter", self.adapter.clone()),
            ],
        )?;
        self.baseline = Some(baseline.clone());
        Ok(baseline)
    }

    fn relation_keys(&mut self) -> PyResult<Bound<'py, PyAny>> {
        let py = self.inputs.py();
        let baseline = match self.baseline() {
            Ok(value) => value,
            Err(error)
                if error.value(py).is_instance(&imported(
                    py,
                    COMPILE_ERRORS,
                    "CompileInputError",
                )?)? =>
            {
                return Ok(PyDict::new(py).into_any());
            }
            Err(error) => return Err(error),
        };
        imported(py, NATIVE, "compiled_relation_keys")?.call1((baseline,))
    }

    fn verdict(&mut self, files: &Bound<'py, PyDict>) -> PyResult<Option<Bound<'py, PyAny>>> {
        let py = files.py();
        match self.compile_verdict(files) {
            Ok(verdict) => Ok(Some(verdict)),
            Err(error) if error.is_instance_of::<PyException>(py) => Ok(None),
            Err(error) => Err(error),
        }
    }

    fn compile_verdict(&mut self, files: &Bound<'py, PyDict>) -> PyResult<Bound<'py, PyAny>> {
        let py = files.py();
        let baseline = self.baseline()?;
        if self.baseline_facts.is_none() {
            self.baseline_facts = Some(compile_facts(py, &baseline, &self.project_dir)?);
        }
        let compiled = call_with(
            &imported(py, NATIVE, "build_compiled_project")?,
            &[
                ("discovered_inputs", updated_inputs(&self.inputs, files)?),
                ("adapter", self.adapter.clone()),
            ],
        )?;
        let mut edited: Vec<Bound<'py, PyAny>> = Vec::new();
        for (path, text) in files.iter() {
            if !text.eq(self.original.get_item(&path)?)? {
                edited.push(path.call_method0("resolve")?);
            }
        }
        let before = self
            .baseline_facts
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("missing compile facts"))?;
        fix_verdict(
            py,
            before,
            &compile_facts(py, &compiled, &self.project_dir)?,
            PyFrozenSet::new(py, edited)?.as_any(),
        )
    }

    fn blocked_faults(&self) -> PyResult<Vec<Bound<'py, PyAny>>> {
        sorted_items(&self.blocked)?
            .into_iter()
            .map(|(path, reason)| verification_fault(&path, &reason.extract::<String>()?))
            .collect()
    }

    fn skipped_warnings(&self) -> PyResult<Vec<Bound<'py, PyAny>>> {
        sorted_items(&self.skipped)?
            .into_iter()
            .map(|(path, reason)| {
                violation(
                    &path,
                    (
                        "format-fix-skipped",
                        &format!("Rule fixes skipped this file: {}", reason.str()?),
                        "warning",
                        "Fix the reported problem, then rerun `sqb format --fix`.",
                    ),
                )
            })
            .collect()
    }

    fn decline(&self, reason: &str) -> PyResult<Bound<'py, PyAny>> {
        let py = self.original.py();
        let affected = self.blocked.copy()?;
        let mut reports: Vec<Bound<'py, PyAny>> = Vec::new();
        for report in &self.reports {
            if report.getattr("status")?.eq("applied")? {
                affected.set_item(report.getattr("file_path")?, py.None())?;
            }
            reports.push(refused(report, reason)?);
        }
        let mut faults: Vec<Bound<'py, PyAny>> = sorted_items(&affected)?
            .into_iter()
            .map(|(path, _)| verification_fault(&path, reason))
            .collect::<PyResult<_>>()?;
        faults.extend(self.skipped_warnings()?);
        result(&self.original, &reports, &faults)
    }
}

fn replace<'py>(
    object: &Bound<'py, PyAny>,
    changes: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let kwargs =
        crate::bindings::_helpers::compile_driver::python_calls::keywords(object.py(), changes)?;
    object
        .py()
        .import("dataclasses")?
        .getattr("replace")?
        .call((object,), Some(&kwargs))
}

fn updated_inputs<'py>(
    inputs: &Bound<'py, PyAny>,
    files: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = inputs.py();
    let mut models: Vec<Bound<'py, PyAny>> = Vec::new();
    for model in inputs.getattr("model_files")?.try_iter()? {
        let model = model?;
        let current = model.getattr("contents")?;
        if let Some(text) = files.get_item(model.getattr("file_path")?)?
            && !text.eq(&current)?
        {
            let start = current.call_method1("index", (model.getattr("query_sql")?,))?;
            let query = text
                .get_item(pyo3::types::PySlice::new(
                    py,
                    start.extract()?,
                    isize::MAX,
                    1,
                ))?
                .call_method0("strip")?;
            models.push(model.call_method1("with_text", (text, query))?);
        } else {
            models.push(model);
        }
    }
    replace(
        inputs,
        &[
            ("model_files", PyTuple::new(py, models)?.into_any()),
            ("native_session", py.None().into_bound(py)),
        ],
    )
}

fn edited_files<'py>(
    files: &Bound<'py, PyDict>,
    edits: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let candidate = files.copy()?;
    for (path, path_edits) in edits.iter() {
        let edits: Vec<FixEdit> = path_edits
            .try_iter()?
            .map(|edit| {
                let edit = edit?;
                Ok(FixEdit {
                    start: edit.getattr("start")?.extract()?,
                    end: edit.getattr("end")?.extract()?,
                    replacement: edit.getattr("replacement")?.extract()?,
                })
            })
            .collect::<PyResult<_>>()?;
        let text: String = candidate
            .get_item(&path)?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("edit path"))?
            .extract()?;
        candidate.set_item(path, with_edits(&text, edits))?;
    }
    Ok(candidate)
}

fn failing_edits<'py>(
    verdict: Option<&Bound<'py, PyAny>>,
    edits: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let result = PyDict::new(edits.py());
    let Some(verdict) = verdict else {
        return Ok(result);
    };
    let resolved = PyDict::new(edits.py());
    for (path, _) in edits.iter() {
        resolved.set_item(path.call_method0("resolve")?, path)?;
    }
    for (path, reason) in verdict.getattr("failing")?.cast_into::<PyDict>()?.iter() {
        if let Some(original) = resolved.get_item(path)? {
            result.set_item(original, reason)?;
        }
    }
    Ok(result)
}

fn not_yet_reported<'py>(
    py: Python<'py>,
    reports: &[Bound<'py, PyAny>],
    remaining: &[Bound<'py, PyAny>],
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let recorded = PyDict::new(py);
    for report in reports {
        let count = recorded
            .get_item(report)?
            .map_or(Ok(0), |count| count.extract::<usize>())?;
        recorded.set_item(report, count + 1)?;
    }
    let mut fresh: Vec<Bound<'py, PyAny>> = Vec::new();
    for report in remaining {
        let count = recorded
            .get_item(report)?
            .map_or(Ok(0), |count| count.extract::<usize>())?;
        if count > 0 {
            recorded.set_item(report, count - 1)?;
        } else {
            fresh.push(report.clone());
        }
    }
    Ok(fresh)
}

fn report<'py>(
    source: &Bound<'py, PyAny>,
    status: &str,
    reason: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let py = source.py();
    call_with(
        &imported(py, MODELS, "RuleFixResult")?,
        &[
            ("file_path", source.getattr("file_path")?),
            ("code", source.getattr("code")?),
            ("line", source.getattr("line")?),
            ("status", status.into_pyobject(py)?.into_any()),
            ("reason", reason.into_pyobject(py)?.into_any()),
        ],
    )
}

fn refused<'py>(report: &Bound<'py, PyAny>, reason: &str) -> PyResult<Bound<'py, PyAny>> {
    if !report.getattr("status")?.eq("applied")? {
        return Ok(report.clone());
    }
    replace(
        report,
        &[
            ("status", "refused".into_pyobject(report.py())?.into_any()),
            ("reason", reason.into_pyobject(report.py())?.into_any()),
        ],
    )
}

fn violation<'py>(
    path: &Bound<'py, PyAny>,
    details: (&str, &str, &str, &str),
) -> PyResult<Bound<'py, PyAny>> {
    let py = path.py();
    call_with(
        &imported(py, MODELS, "LintViolation")?,
        &[
            ("file_path", path.clone()),
            ("line", 1_i64.into_pyobject(py)?.into_any()),
            ("column", 1_i64.into_pyobject(py)?.into_any()),
            ("code", details.0.into_pyobject(py)?.into_any()),
            ("message", details.1.into_pyobject(py)?.into_any()),
            ("severity", details.2.into_pyobject(py)?.into_any()),
            ("engine", "native".into_pyobject(py)?.into_any()),
            ("remediation", details.3.into_pyobject(py)?.into_any()),
        ],
    )
}

fn verification_fault<'py>(path: &Bound<'py, PyAny>, reason: &str) -> PyResult<Bound<'py, PyAny>> {
    violation(
        path,
        (
            "format-fix-verification-failed",
            reason,
            "fault",
            "Restructure the SQL manually and recompile; the original file was retained.",
        ),
    )
}

fn sorted_items<'py>(
    items: &Bound<'py, PyDict>,
) -> PyResult<Vec<(Bound<'py, PyAny>, Bound<'py, PyAny>)>> {
    let sorted = items
        .py()
        .import("builtins")?
        .getattr("sorted")?
        .call1((items.items(),))?;
    sorted.extract()
}

fn result<'py>(
    files: &Bound<'py, PyDict>,
    reports: &[Bound<'py, PyAny>],
    faults: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyTuple::new(
        files.py(),
        [
            files.clone().into_any(),
            PyTuple::new(files.py(), reports)?.into_any(),
            PyList::new(files.py(), faults)?.into_any(),
        ],
    )?
    .into_any())
}

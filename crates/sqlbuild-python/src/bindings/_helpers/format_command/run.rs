//! Format every authored SQL file and collect the violations that remain.

use std::collections::BTreeSet;
use std::path::PathBuf;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyList, PyListMethods};
use sqlbuild_core::format_command::main::collect_lint_files::collect_lint_files;

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::compile_driver::python_calls::keywords;
use crate::bindings::_helpers::compile_driver::stage_work::{
    FORMAT_LINT_BATCHES, FORMAT_LINT_FILES, count_stage,
};
use crate::bindings::_helpers::discovery::description_inputs::externally_described_models;
use crate::bindings::_helpers::format_command::files::{
    FormatChange, file_dictionary, overlaid, persist_changes, sorted_items,
};
use crate::bindings::_helpers::records::construct::error_class;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::ErrorId;
use crate::bindings::_helpers::rules::dsl_headers::format_native_headers;
use crate::bindings::_helpers::rules::dsl_headers::reject_unparseable_header_rewrites;
use crate::bindings::_helpers::rules::dsl_headers::safe_format_files;
use crate::bindings::_helpers::rules::dsl_headers::{header_violations, rules_config};
use crate::bindings::_helpers::rules::fixture_formatting::format_redundant_fixture_nulls;
use crate::bindings::_helpers::rules::lint_pipeline::{LintViolationRow, ViolationClasses};
use crate::bindings::_helpers::rules::lint_text::apply_lint_suppressions;
use crate::bindings::_helpers::rules::lint_text::format_lint_sql_bodies;
use sqlbuild_rules::dsl_headers::main::scan_headers::scan_headers;
use sqlbuild_rules::dsl_headers::models::{HeaderRulesConfig, HeaderViolation};

const DESCRIPTION_PRESENT: &str = "description-present";

/// What one format run formats and how.
pub(crate) struct FormatRequest<'a, 'py> {
    pub(crate) project_dir: &'a Bound<'py, PyAny>,
    pub(crate) config: &'a Bound<'py, PyAny>,
    pub(crate) adapter: Option<&'a Bound<'py, PyAny>>,
    pub(crate) selected: Option<&'a BTreeSet<PathBuf>>,
    pub(crate) discovered: Option<&'a Bound<'py, PyAny>>,
    pub(crate) fixtures_only: bool,
    pub(crate) write: bool,
    pub(crate) fix: bool,
}

/// The outcome of one format run, with Python violations and Rule fix reports.
pub(crate) struct FormatOutcome<'py> {
    pub(crate) files_checked: usize,
    pub(crate) violations: Vec<Bound<'py, PyAny>>,
    pub(crate) changes: Vec<FormatChange<'py>>,
    pub(crate) rule_fixes: Vec<Bound<'py, PyAny>>,
    /// Paths whose formatting was declined, so their applied fixes were not kept.
    pub(crate) declined: BTreeSet<PathBuf>,
    pub(crate) final_contents: Bound<'py, PyDict>,
}

/// Fixture-null rewrites proven safe by the contracts, when fixture inputs are known.
fn fixture_autofix<'py>(
    request: &FormatRequest<'_, 'py>,
    fixture_inputs: Option<&(Bound<'py, PyAny>, Bound<'py, PyAny>)>,
    files: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = files.py();
    let Some((discovered, syntax)) = fixture_inputs else {
        return Ok(PyDict::new(py));
    };
    Ok(format_redundant_fixture_nulls(
        &files.clone().into_any().cast_into::<PyDict>()?,
        &request.project_dir.clone(),
        &discovered.clone(),
        &syntax.clone(),
    )
    .and_then(|value| pyo3::IntoPyObjectExt::into_bound_py_any(value, py))?
    .downcast_into::<PyDict>()?)
}

/// SQL bodies of `files` formatted natively: changed texts and declined-body faults.
fn format_bodies<'py>(
    request: &FormatRequest<'_, 'py>,
    files: &Bound<'py, PyDict>,
) -> PyResult<(Bound<'py, PyDict>, Bound<'py, PyAny>)> {
    let py: Python<'py> = files.py();
    let items: Vec<(Bound<'py, PyAny>, String)> = sorted_items(files)?
        .into_iter()
        .map(|(path, contents)| Ok((path, contents.extract::<String>()?)))
        .collect::<PyResult<_>>()?;
    count_stage(py, FORMAT_LINT_BATCHES, 1)?;
    count_stage(py, FORMAT_LINT_FILES, items.len() as u64)?;
    let result: Bound<'py, PyAny> = format_lint_sql_bodies(
        py,
        items,
        request.project_dir.extract::<std::path::PathBuf>()?,
        request.config,
    )
    .and_then(|value| pyo3::IntoPyObjectExt::into_bound_py_any(value, py))?;
    Ok((
        result.get_item(0)?.downcast_into::<PyDict>()?,
        result.get_item(1)?,
    ))
}

/// Contents after header, SQL body and fixture fixes, and the faults of declined rewrites.
fn apply_fixes<'py>(
    request: &FormatRequest<'_, 'py>,
    files: &Bound<'py, PyDict>,
    fixture_inputs: Option<&(Bound<'py, PyAny>, Bound<'py, PyAny>)>,
) -> PyResult<(Bound<'py, PyDict>, Bound<'py, PyList>)> {
    let py: Python<'py> = files.py();
    let updated: Bound<'py, PyDict> = fixture_autofix(request, fixture_inputs, files)?;
    let faults: Bound<'py, PyList> = PyList::empty(py);
    if request.fixtures_only {
        return Ok((updated, faults));
    }
    let current: Bound<'py, PyDict> = overlaid(files, &updated)?;
    for (path, contents) in sorted_items(&current)? {
        let result: Bound<'py, PyAny> =
            format_native_headers(&contents.clone(), &path.clone(), &request.config.clone())
                .and_then(|value| pyo3::IntoPyObjectExt::into_bound_py_any(value, py))?;
        for fault in result.get_item(1)?.try_iter()? {
            faults.append(fault?)?;
        }
        let formatted: Bound<'py, PyAny> = result.get_item(0)?;
        if !formatted.eq(&contents)? {
            updated.set_item(path, formatted)?;
        }
    }
    let (native_formatted, native_faults) = format_bodies(request, &overlaid(files, &updated)?)?;
    for fault in native_faults.try_iter()? {
        faults.append(fault?)?;
    }
    updated.update(native_formatted.as_mapping())?;
    let fixture_formatted: Bound<'py, PyDict> =
        fixture_autofix(request, fixture_inputs, &overlaid(files, &updated)?)?;
    if !fixture_formatted.is_empty() {
        let (final_native, final_faults) = format_bodies(request, &fixture_formatted)?;
        for fault in final_faults.try_iter()? {
            faults.append(fault?)?;
        }
        updated.update(fixture_formatted.as_mapping())?;
        updated.update(final_native.as_mapping())?;
    }
    let result: Bound<'py, PyAny> = reject_unparseable_header_rewrites(
        &updated.into_any().cast_into::<PyDict>()?,
        &request.config.clone(),
        &faults.into_any().cast_into::<PyList>()?,
    )
    .and_then(|value| pyo3::IntoPyObjectExt::into_bound_py_any(value, py))?;
    Ok((
        result.get_item(0)?.downcast_into::<PyDict>()?,
        result.get_item(1)?.downcast_into::<PyList>()?,
    ))
}

/// Formatter-owned header diagnostics of the final contents, without configured Rules.
fn lint_final_contents<'py>(
    request: &FormatRequest<'_, 'py>,
    files: &Bound<'py, PyDict>,
    updated: &Bound<'py, PyDict>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = files.py();
    let mut violations: Vec<Bound<'py, PyAny>> = Vec::new();
    let header_rules: HeaderRulesConfig = rules_config(request.config)?;
    let classes: ViolationClasses<'py> = ViolationClasses::new(py)?;
    for (path, contents) in sorted_items(files)? {
        let final_contents: String = updated.get_item(&path)?.unwrap_or(contents).extract()?;
        let text: Vec<char> = final_contents.chars().collect();
        let found: Vec<HeaderViolation> =
            header_violations(&text, &scan_headers(&text, false), header_rules)
                .map_err(value_error)?;
        for violation in found {
            violations.push(classes.violation(&path, &LintViolationRow::header(0, violation))?);
        }
    }
    Ok(violations)
}

fn code_is(violation: &Bound<'_, PyAny>, code: &str) -> PyResult<bool> {
    Ok(native_field(violation, "code")?.extract::<String>()? == code)
}

/// Drop `description-present` faults for models described outside their header.
fn drop_resolved_description_faults<'py>(
    project_dir: &Bound<'py, PyAny>,
    violations: Vec<Bound<'py, PyAny>>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut has_description_fault: bool = false;
    for violation in &violations {
        has_description_fault |= code_is(violation, DESCRIPTION_PRESENT)?;
    }
    if !has_description_fault {
        return Ok(violations);
    }
    let described: BTreeSet<PathBuf> = externally_described_models(project_dir)?
        .try_iter()?
        .map(|path| path?.call_method0("resolve")?.extract())
        .collect::<PyResult<_>>()?;
    let mut kept: Vec<Bound<'py, PyAny>> = Vec::new();
    for violation in violations {
        let resolved: PathBuf = native_field(&violation, "file_path")?
            .call_method0("resolve")?
            .extract()?;
        if !code_is(&violation, DESCRIPTION_PRESENT)? || !described.contains(&resolved) {
            kept.push(violation);
        }
    }
    Ok(kept)
}

/// Rule fixes planned in memory and verified by compilation, when `--fix` is set.
fn plan_rule_fixes<'py>(
    request: &FormatRequest<'_, 'py>,
    files: &Bound<'py, PyDict>,
) -> PyResult<(Bound<'py, PyDict>, Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py: Python<'py> = files.py();
    let result: Bound<'py, PyAny> = crate::bindings::_helpers::rules::fix_session::plan_rule_fixes(
        py,
        Some(keywords(
            py,
            &[
                ("project_dir", request.project_dir.clone()),
                ("files", files.clone().into_any()),
                ("config", request.config.clone()),
                (
                    "adapter",
                    request
                        .adapter
                        .map_or_else(|| py.None().into_bound(py), Clone::clone),
                ),
                (
                    "discovered_inputs",
                    request
                        .discovered
                        .map_or_else(|| py.None().into_bound(py), Clone::clone),
                ),
                (
                    "enabled",
                    PyBool::new(py, request.fix).to_owned().into_any(),
                ),
            ],
        )?),
    )?;
    Ok((
        result.get_item(0)?.downcast_into::<PyDict>()?,
        result.get_item(1)?,
        result.get_item(2)?,
    ))
}

/// Format the project's authored SQL files and report what remains.
pub(crate) fn run_format<'py>(request: &FormatRequest<'_, 'py>) -> PyResult<FormatOutcome<'py>> {
    let py: Python<'py> = request.project_dir.py();
    let fixture_inputs: Option<(Bound<'py, PyAny>, Bound<'py, PyAny>)> =
        match (request.discovered, request.adapter) {
            (Some(discovered), Some(adapter)) => Some((
                discovered.clone(),
                native_field(adapter, "sql_lexical_syntax")?,
            )),
            (Some(_), None) => {
                return Err(error_class(py, ErrorId::Lint)?
                    .call1(("fixture-null formatting requires the project adapter",))
                    .map(pyo3::PyErr::from_value)?);
            }
            _ => None,
        };
    let directory: PathBuf = request.project_dir.extract()?;
    let collected: Vec<(PathBuf, String)> = collect_lint_files(&directory, request.selected)
        .map_err(|error| pyo3::exceptions::PyOSError::new_err(error.to_string()))?;
    let files_checked: usize = collected.len();
    let files: Bound<'py, PyDict> = file_dictionary(py, collected)?;
    let safe: Bound<'py, PyAny> = safe_format_files(
        &files.clone().into_any().cast_into::<PyDict>()?,
        &request.config.clone(),
    )
    .and_then(|value| pyo3::IntoPyObjectExt::into_bound_py_any(value, py))?;
    let newlines: Bound<'py, PyDict> = safe.get_item(1)?.downcast_into::<PyDict>()?;
    let (safe_files, rule_fixes, rule_faults) =
        plan_rule_fixes(request, &safe.get_item(0)?.downcast_into::<PyDict>()?)?;
    let (fixed, format_faults) = apply_fixes(request, &safe_files, fixture_inputs.as_ref())?;
    for fault in rule_faults.try_iter()? {
        format_faults.append(fault?)?;
    }
    let merged: Bound<'py, PyDict> = safe_files.copy()?;
    merged.update(fixed.as_mapping())?;
    let declined: BTreeSet<PathBuf> = format_faults
        .iter()
        .map(|fault| native_field(&fault, "file_path")?.extract())
        .collect::<PyResult<_>>()?;
    let updated: Bound<'py, PyDict> = PyDict::new(py);
    for (path, contents) in merged.iter() {
        if !declined.contains(&path.extract::<PathBuf>()?) {
            updated.set_item(path, contents)?;
        }
    }
    let changes: Vec<FormatChange<'py>> =
        persist_changes((&files, &updated), &newlines, request.write)?;
    let mut violations: Vec<Bound<'py, PyAny>> = if request.fixtures_only {
        Vec::new()
    } else {
        lint_final_contents(request, &files, &updated)?
    };
    violations.extend(format_faults.iter());
    let violations: Vec<Bound<'py, PyAny>> =
        drop_resolved_description_faults(request.project_dir, violations)?;
    let final_contents: Bound<'py, PyDict> = overlaid(&files, &updated)?;
    let allow_suppressions: bool = native_field(request.config, "allow_suppressions")?.extract()?;
    let violations: Vec<Bound<'py, PyAny>> =
        apply_lint_suppressions(py, violations, final_contents.clone(), allow_suppressions)?;
    Ok(FormatOutcome {
        files_checked,
        violations,
        changes,
        rule_fixes: rule_fixes.try_iter()?.collect::<PyResult<_>>()?,
        declined,
        final_contents,
    })
}

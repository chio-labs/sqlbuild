//! Format every authored SQL file and collect the violations that remain.

use std::collections::BTreeSet;
use std::path::PathBuf;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyList, PyListMethods, PyTuple};
use sqlbuild_core::format_command::main::collect_lint_files::collect_lint_files;

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::discovery::description_inputs::externally_described_models;
use crate::bindings::_helpers::format_command::files::{
    FormatChange, file_dictionary, overlaid, persist_changes, sorted_items,
};
use crate::bindings::_helpers::records::ids::{ErrorId, NativeAttr};
use crate::bindings::_helpers::records::registry;

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

fn native<'py>(py: Python<'py>, name: NativeAttr) -> PyResult<Bound<'py, PyAny>> {
    registry::native(py, name)
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
    Ok(call_with(
        &registry::native(py, NativeAttr::FormatRedundantFixtureNulls)?,
        &[
            ("files", files.clone().into_any()),
            ("project_dir", request.project_dir.clone()),
            ("discovered_inputs", discovered.clone()),
            ("sql_lexical_syntax", syntax.clone()),
        ],
    )?
    .downcast_into::<PyDict>()?)
}

/// SQL bodies of `files` formatted natively: changed texts and declined-body faults.
fn format_bodies<'py>(
    request: &FormatRequest<'_, 'py>,
    files: &Bound<'py, PyDict>,
) -> PyResult<(Bound<'py, PyDict>, Bound<'py, PyAny>)> {
    let py: Python<'py> = files.py();
    let items: Vec<Bound<'py, PyAny>> = sorted_items(files)?
        .into_iter()
        .map(|(path, contents)| Ok(PyTuple::new(py, [path, contents])?.into_any()))
        .collect::<PyResult<_>>()?;
    let result: Bound<'py, PyAny> = native(py, NativeAttr::FormatLintSqlBodies)?.call1((
        PyList::new(py, items)?,
        request.project_dir,
        request.config,
    ))?;
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
    call_with(
        &native(py, NativeAttr::PrepareNativeHeaderCache)?,
        &[("files", current.clone().into_any())],
    )?;
    for (path, contents) in sorted_items(&current)? {
        let result: Bound<'py, PyAny> = call_with(
            &native(py, NativeAttr::FormatNativeHeaders)?,
            &[
                ("contents", contents.clone()),
                ("file_path", path.clone()),
                ("config", request.config.clone()),
            ],
        )?;
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
    let result: Bound<'py, PyAny> = call_with(
        &native(py, NativeAttr::RejectUnparseableHeaderRewrites)?,
        &[
            ("updated", updated.into_any()),
            ("config", request.config.clone()),
            ("faults", faults.into_any()),
        ],
    )?;
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
    for (path, contents) in sorted_items(files)? {
        let final_contents: Bound<'py, PyAny> = updated.get_item(&path)?.unwrap_or(contents);
        let headers: Bound<'py, PyAny> = call_with(
            &native(py, NativeAttr::ScanHeaders)?,
            &[("contents", final_contents.clone())],
        )?;
        let found: Bound<'py, PyAny> = call_with(
            &native(py, NativeAttr::LintNativeHeaders)?,
            &[
                ("contents", final_contents),
                ("file_path", path),
                ("headers", headers),
                ("config", request.config.clone()),
            ],
        )?;
        for violation in found.try_iter()? {
            violations.push(violation?);
        }
    }
    Ok(violations)
}

fn code_is(violation: &Bound<'_, PyAny>, code: &str) -> PyResult<bool> {
    Ok(violation.getattr("code")?.extract::<String>()? == code)
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
        let resolved: PathBuf = violation
            .getattr("file_path")?
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
    let result: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::PlanRuleFixes)?,
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
            (Some(discovered), Some(adapter)) => {
                Some((discovered.clone(), adapter.getattr("sql_lexical_syntax")?))
            }
            (Some(_), None) => {
                return Err(registry::error(py, ErrorId::Lint)?
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
    let safe: Bound<'py, PyAny> = call_with(
        &native(py, NativeAttr::SafeFormatFiles)?,
        &[
            ("files", files.clone().into_any()),
            ("config", request.config.clone()),
        ],
    )?;
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
        .map(|fault| fault.getattr("file_path")?.extract())
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
    let allow_suppressions: Bound<'py, PyAny> = request.config.getattr("allow_suppressions")?;
    let violations: Vec<Bound<'py, PyAny>> = native(py, NativeAttr::ApplyLintSuppressions)?
        .call1((violations, &final_contents, allow_suppressions))?
        .extract()?;
    Ok(FormatOutcome {
        files_checked,
        violations,
        changes,
        rule_fixes: rule_fixes.try_iter()?.collect::<PyResult<_>>()?,
        declined,
        final_contents,
    })
}

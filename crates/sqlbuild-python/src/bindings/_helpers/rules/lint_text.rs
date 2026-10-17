//! Interpolation sentinels, suppressions and fixture-null candidates over Python lint models.

use std::collections::BTreeSet;
use std::path::PathBuf;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyString};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_rules::lint_text::errors::LintTextError;
use sqlbuild_rules::lint_text::main::apply_suppressions::apply_suppressions;
use sqlbuild_rules::lint_text::main::format_sql_bodies::format_sql_bodies;
use sqlbuild_rules::lint_text::main::interpolation_text_at::interpolation_text_at;
use sqlbuild_rules::lint_text::main::named_declaration_role_kind::named_declaration_role_kind as role_kind;
use sqlbuild_rules::lint_text::main::neutralize_audit_parameters::neutralize_audit_parameters;
use sqlbuild_rules::lint_text::main::neutralize_context_interpolation::neutralize_context_interpolation;
use sqlbuild_rules::lint_text::main::neutralize_interpolation::neutralize_interpolation;
use sqlbuild_rules::lint_text::main::restore_interpolation::restore_interpolation;
use sqlbuild_rules::lint_text::main::scan_fixture_null_candidates::scan_fixture_null_candidates;
use sqlbuild_rules::lint_text::models::{
    FormatFile, FormattedBodies, InterpolationSite, Neutralized, RetainedViolation,
    SuppressibleViolation,
};

use crate::bindings::_helpers::boundary::panics::{compiler_guard, value_error};
use crate::bindings::_helpers::records::construct::{
    enum_from_value, enum_member, new_record_with,
};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::rules::lint_pipeline::{
    LintViolationRow, NATIVE_ENGINE, ViolationClasses,
};
use crate::bindings::types::CompilerDetach;

const FORMAT_UNSAFE_CODE: &str = "format-unsafe";
const FORMAT_UNSAFE_REMEDIATION: &str = "Rewrite the unsupported SQL shape or report a minimal formatter reproduction. No header, SQL body, or fixture changes were written to this file.";

/// One interpolation site as `InterpolationSite` fields.
type SiteTuple = (String, usize, usize, usize, usize, String);

fn site_tuples(neutralized: Neutralized) -> (String, Vec<SiteTuple>) {
    let sites: Vec<SiteTuple> = neutralized
        .sites
        .into_iter()
        .map(|site| {
            (
                site.sentinel,
                site.neutralized_start,
                site.neutralized_end,
                site.original_start,
                site.original_end,
                site.original_text,
            )
        })
        .collect();
    (neutralized.text, sites)
}

#[pyfunction]
#[pyo3(signature = (body, dialect, for_formatting = false))]
fn neutralize_lint_interpolation(
    body: &str,
    dialect: &str,
    for_formatting: bool,
) -> PyResult<(String, Vec<SiteTuple>)> {
    compiler_guard(|| {
        neutralize_interpolation(body, dialect, for_formatting)
            .map(site_tuples)
            .map_err(value_error)
    })
}

#[pyfunction]
fn neutralize_lint_context_interpolation(body: &str) -> PyResult<(String, Vec<SiteTuple>)> {
    compiler_guard(|| Ok(site_tuples(neutralize_context_interpolation(body))))
}

#[pyfunction]
fn neutralize_lint_audit_parameters(body: &str) -> PyResult<(String, Vec<SiteTuple>)> {
    compiler_guard(|| Ok(site_tuples(neutralize_audit_parameters(body))))
}

/// Restored text, or `(False, reason)` when a sentinel is missing or repeated.
#[pyfunction]
fn restore_lint_interpolation(fixed: &str, sites: Vec<SiteTuple>) -> PyResult<(bool, String)> {
    let sites: Vec<InterpolationSite> = sites
        .into_iter()
        .map(|site| InterpolationSite {
            sentinel: site.0,
            neutralized_start: site.1,
            neutralized_end: site.2,
            original_start: site.3,
            original_end: site.4,
            original_text: site.5,
        })
        .collect();
    match compiler_guard(|| Ok(restore_interpolation(fixed, &sites)))? {
        Ok(restored) => Ok((true, restored)),
        Err(LintTextError::Restoration(message)) => Ok((false, message)),
        Err(error) => Err(value_error(error)),
    }
}

#[pyfunction]
fn lint_interpolation_text_at(body: &str, start: usize, dialect: &str) -> PyResult<Option<String>> {
    compiler_guard(|| Ok(interpolation_text_at(body, start, dialect)))
}

#[pyfunction]
#[pyo3(signature = (project_dir, selected_paths = None))]
fn scan_fixture_typed_null_candidates<'py>(
    py: Python<'py>,
    project_dir: PathBuf,
    selected_paths: Option<BTreeSet<PathBuf>>,
) -> PyResult<(Bound<'py, PyFrozenSet>, Bound<'py, PyFrozenSet>)> {
    let candidates = compiler_guard(|| {
        scan_fixture_null_candidates(&project_dir, selected_paths.as_ref()).map_err(value_error)
    })?;
    let paths: Vec<PathBuf> = candidates.paths.into_iter().map(PathBuf::from).collect();
    Ok((
        PyFrozenSet::new(py, paths)?,
        PyFrozenSet::new(py, candidates.model_names)?,
    ))
}

/// The named declaration kind of a project-relative path, as `DeclarationKind`.
#[pyfunction]
#[pyo3(signature = (*, relative_path))]
fn named_declaration_role_kind<'py>(
    relative_path: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let parts: Vec<String> = native_field(relative_path, "parts")?.extract()?;
    match role_kind(&parts) {
        Some(kind) => Ok(Some(enum_from_value(
            relative_path.py(),
            RecordId::DeclarationKind,
            kind,
        )?)),
        None => Ok(None),
    }
}

/// Remove violations matched by suppressions and add the suppression findings, as lint models.
#[pyfunction]
pub(crate) fn apply_lint_suppressions<'py>(
    py: Python<'py>,
    violations: Vec<Bound<'py, PyAny>>,
    contents_by_path: Bound<'py, PyDict>,
    allow_suppressions: bool,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let index_by_path: Bound<'py, PyDict> = PyDict::new(py);
    let mut paths: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut contents: Vec<String> = Vec::new();
    for (path, text) in contents_by_path.iter() {
        index_by_path.set_item(&path, paths.len())?;
        paths.push(path);
        contents.push(text.extract()?);
    }
    let keys: Vec<SuppressibleViolation> = violations
        .iter()
        .map(|violation| suppressible(violation, &index_by_path))
        .collect::<PyResult<_>>()?;
    let texts: Vec<&str> = contents.iter().map(String::as_str).collect();
    let retained: Vec<RetainedViolation> = compiler_guard(|| {
        apply_suppressions(&texts, &keys, allow_suppressions).map_err(value_error)
    })?;
    let classes: ViolationClasses<'py> = ViolationClasses::new(py)?;
    retained
        .into_iter()
        .map(|item| match item {
            RetainedViolation::Existing(index) => Ok(violations[index].clone()),
            RetainedViolation::Added(finding) => {
                let row: LintViolationRow = LintViolationRow::suppression(finding);
                classes.violation(&paths[row.file], &row)
            }
        })
        .collect()
}

/// The suppression identity of one Python lint violation.
fn suppressible(
    violation: &Bound<'_, PyAny>,
    index_by_path: &Bound<'_, PyDict>,
) -> PyResult<SuppressibleViolation> {
    let file: Option<usize> = match index_by_path.get_item(native_field(violation, "file_path")?)? {
        Some(index) => Some(index.extract()?),
        None => None,
    };
    Ok(SuppressibleViolation {
        file: file.unwrap_or(usize::MAX),
        line: native_field(violation, "line")?.extract()?,
        code: native_field(violation, "code")?.extract()?,
        native: native_field(violation, "engine")?.extract::<String>()? == NATIVE_ENGINE,
    })
}

/// The parts of `path` below `project_dir`, or `None` outside the project.
fn relative_parts(path: &std::path::Path, project_dir: &std::path::Path) -> Option<Vec<String>> {
    match path.strip_prefix(project_dir) {
        Ok(relative) => Some(
            relative
                .components()
                .map(|part| part.as_os_str().to_string_lossy().into_owned())
                .collect(),
        ),
        Err(_) => None,
    }
}

/// Format the SQL bodies of `files`; return changed texts by path and declined-body faults.
#[pyfunction]
pub(crate) fn format_lint_sql_bodies<'py>(
    py: Python<'py>,
    files: Vec<(Bound<'py, PyAny>, String)>,
    project_dir: PathBuf,
    config: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyDict>, Vec<Bound<'py, PyAny>>)> {
    let inputs: Vec<FormatFile> = files
        .iter()
        .map(|(path, contents)| {
            Ok(FormatFile {
                relative_parts: relative_parts(&path.extract::<PathBuf>()?, &project_dir),
                contents: contents.clone(),
            })
        })
        .collect::<PyResult<_>>()?;
    let dialect: String = native_field(config, "dialect")?.extract()?;
    let line_width: usize = native_field(config, "line_width")?.extract()?;
    let result: FormattedBodies = py
        .compiler_detach(|| {
            format_sql_bodies(&inputs, &dialect, line_width).map_err(|error| error.to_string())
        })
        .map_err(value_error)?;
    let formatted: Bound<'py, PyDict> = PyDict::new(py);
    for (index, text) in result.formatted {
        formatted.set_item(&files[index].0, text)?;
    }
    let fault: Bound<'py, PyAny> = enum_member(py, RecordId::LintSeverity, "FAULT")?;
    let faults: Vec<Bound<'py, PyAny>> = result
        .faults
        .into_iter()
        .map(|item| {
            new_record_with(py, RecordId::LintViolation, &[
                    ("file_path", files[item.file].0.clone()),
                    ("line", item.line.into_pyobject(py)?.into_any()),
                    ("column", 1_usize.into_pyobject(py)?.into_any()),
                    ("code", PyString::new(py, FORMAT_UNSAFE_CODE).into_any()),
                    (
                        "message",
                        PyString::new(
                            py,
                            &format!(
                                "File left unchanged because its SQL body could not be formatted: {}",
                                item.reason
                            ),
                        )
                        .into_any(),
                    ),
                    ("severity", fault.clone()),
                    ("engine", PyString::new(py, NATIVE_ENGINE).into_any()),
                    (
                        "remediation",
                        PyString::new(py, FORMAT_UNSAFE_REMEDIATION).into_any(),
                    ),
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    Ok((formatted, faults))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(neutralize_lint_interpolation, module)?)?;
    module.add_function(wrap_pyfunction!(
        neutralize_lint_context_interpolation,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(neutralize_lint_audit_parameters, module)?)?;
    module.add_function(wrap_pyfunction!(restore_lint_interpolation, module)?)?;
    module.add_function(wrap_pyfunction!(lint_interpolation_text_at, module)?)?;
    module.add_function(wrap_pyfunction!(
        scan_fixture_typed_null_candidates,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(format_lint_sql_bodies, module)?)?;
    module.add_function(wrap_pyfunction!(named_declaration_role_kind, module)?)?;
    module.add_function(wrap_pyfunction!(apply_lint_suppressions, module)?)
}

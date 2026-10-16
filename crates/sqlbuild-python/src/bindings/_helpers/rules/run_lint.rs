//! Lint authored SQL files: header rules, then expanded bodies through the native SQL engine.

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use pyo3::exceptions::{PyException, PyOSError};
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyFrozenSet, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_core::format_command::main::collect_lint_files::collect_lint_files;
use sqlbuild_rules::lint_text::main::first_header_only::first_header_only;

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, keywords,
};
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::rules::lint_expansion::build_lint_expansion_context;
use crate::bindings::_helpers::rules::lint_stop::check_stop;

fn resolved(path: &Path) -> PathBuf {
    fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf())
}

fn selected_set(selected_paths: &Bound<'_, PyAny>) -> PyResult<Option<BTreeSet<PathBuf>>> {
    if selected_paths.is_none() {
        return Ok(None);
    }
    selected_paths
        .try_iter()?
        .map(|path| path?.extract())
        .collect::<PyResult<_>>()
        .map(Some)
}

/// Authored SQL files keyed by path: `source_files` filtered to the selection, or read from disk.
fn project_files<'py>(
    project_dir: &Bound<'py, PyAny>,
    selected_paths: &Bound<'py, PyAny>,
    source_files: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = project_dir.py();
    let selected: Option<BTreeSet<PathBuf>> = selected_set(selected_paths)?;
    let files: Bound<'py, PyDict> = PyDict::new(py);
    if !source_files.is_none() {
        for (path, contents) in source_files.downcast::<PyDict>()?.iter() {
            let keep: bool = match &selected {
                None => true,
                Some(paths) => paths.contains(&resolved(&path.extract::<PathBuf>()?)),
            };
            if keep {
                files.set_item(path, contents)?;
            }
        }
        return Ok(files);
    }
    let directory: PathBuf = project_dir.extract()?;
    let collected: Vec<(PathBuf, String)> = collect_lint_files(&directory, selected.as_ref())
        .map_err(|error| PyOSError::new_err(error.to_string()))?;
    for (path, contents) in collected {
        files.set_item(path, contents)?;
    }
    Ok(files)
}

/// Collect supported SQL-analysis inputs of a project.
#[pyfunction]
#[pyo3(signature = (*, project_dir, selected_paths = None))]
fn collect_lint_project_files<'py>(
    project_dir: &Bound<'py, PyAny>,
    selected_paths: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = project_dir.py();
    let none: Bound<'py, PyAny> = py.None().into_bound(py);
    project_files(
        project_dir,
        &selected_paths.unwrap_or_else(|| none.clone()),
        &none,
    )
}

/// The keyword arguments of one lint run.
struct LintRun<'py> {
    project_dir: Bound<'py, PyAny>,
    config: Bound<'py, PyAny>,
    dynamic_output_paths: Bound<'py, PyAny>,
    compiled_expansions: Bound<'py, PyAny>,
    skip_unexpandable: bool,
}

/// One file's header violations and, when expanding, its expanded bodies.
fn scan_file<'py>(
    run: &LintRun<'py>,
    (file_path, contents): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    context: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Option<Bound<'py, PyAny>>)> {
    let py: Python<'py> = file_path.py();
    let relative_path: Bound<'py, PyAny> =
        file_path.call_method1("relative_to", (&run.project_dir,))?;
    let relative_parts: Vec<String> = relative_path.getattr("parts")?.extract()?;
    let headers: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::ScanHeaders)?,
        &[
            ("contents", contents.clone()),
            (
                "first_only",
                PyBool::new(py, first_header_only(&relative_parts))
                    .to_owned()
                    .into_any(),
            ),
        ],
    )?;
    let header_violations: Bound<'py, PyAny> =
        if run.config.getattr("header_rules_enabled")?.is_truthy()? {
            call_with(
                &registry::native(py, NativeAttr::LintNativeHeaders)?,
                &[
                    ("contents", contents.clone()),
                    ("file_path", file_path.clone()),
                    ("headers", headers.clone()),
                    ("config", run.config.clone()),
                ],
            )?
        } else {
            PyTuple::empty(py).into_any()
        };
    if context.is_none() {
        return Ok((header_violations, None));
    }
    let expanded: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::ExpandFileBodies)?,
        &[
            ("file_path", file_path.clone()),
            ("contents", contents.clone()),
            ("headers", headers),
            ("context", context.clone()),
            ("dialect", run.config.getattr("dialect")?),
            ("project_dir", run.project_dir.clone()),
            ("relative_path", relative_path),
            ("dynamic_output_paths", run.dynamic_output_paths.clone()),
            ("compiled_expansions", run.compiled_expansions.clone()),
        ],
    )?;
    Ok((header_violations, Some(expanded)))
}

/// The expansion context: the caller's, or one built when native lint is enabled.
fn expansion_context<'py>(
    run: &LintRun<'py>,
    arguments: &KeywordArguments<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = run.config.py();
    let given: Bound<'py, PyAny> = arguments.value("expansion_context")?;
    if given.is_truthy()? {
        return Ok(given);
    }
    if !run.config.getattr("native_enabled")?.is_truthy()? {
        return Ok(py.None().into_bound(py));
    }
    build_lint_expansion_context(
        py,
        Some(keywords(
            py,
            &[
                ("project_dir", run.project_dir.clone()),
                ("value_renderer", arguments.value("value_renderer")?),
                ("discovered_inputs", arguments.value("discovered_inputs")?),
            ],
        )?),
    )
}

/// Violations sorted by file path text, then line and column.
fn sorted_violations<'py>(violations: Vec<Bound<'py, PyAny>>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut keyed: Vec<((String, i64, i64), Bound<'py, PyAny>)> = violations
        .into_iter()
        .map(|violation| {
            let key: (String, i64, i64) = (
                violation.getattr("file_path")?.str()?.extract()?,
                violation.getattr("line")?.extract()?,
                violation.getattr("column")?.extract()?,
            );
            Ok((key, violation))
        })
        .collect::<PyResult<_>>()?;
    keyed.sort_by(|left, right| left.0.cmp(&right.0));
    Ok(keyed.into_iter().map(|(_, violation)| violation).collect())
}

/// Header and expanded-body violations of every file, and the files expansion skipped.
fn lint_files<'py>(
    run: &LintRun<'py>,
    files: &Bound<'py, PyDict>,
    context: &Bound<'py, PyAny>,
) -> PyResult<(Vec<Bound<'py, PyAny>>, Bound<'py, PyAny>)> {
    let py: Python<'py> = files.py();
    let mut items: Vec<(PathBuf, Bound<'py, PyAny>, Bound<'py, PyAny>)> = files
        .iter()
        .map(|(path, contents)| Ok((path.extract::<PathBuf>()?, path, contents)))
        .collect::<PyResult<_>>()?;
    items.sort_by(|left, right| left.0.cmp(&right.0));
    let mut violations: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut expanded_files: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut failure: Option<PyErr> = None;
    for (_, file_path, contents) in &items {
        let (header_violations, expanded) = match scan_file(run, (file_path, contents), context) {
            Ok(scanned) => scanned,
            Err(error) if error.is_instance_of::<PyException>(py) => {
                failure = Some(error);
                break;
            }
            Err(error) => return Err(error),
        };
        for violation in header_violations.try_iter()? {
            violations.push(violation?);
        }
        let Some(expanded) = expanded else {
            continue;
        };
        let failed: bool = !expanded.getattr("failure")?.is_none();
        expanded_files.push(expanded);
        if failed && !run.skip_unexpandable {
            break;
        }
    }
    let skip: Bound<'py, PyAny> = PyBool::new(py, run.skip_unexpandable).to_owned().into_any();
    let prepared: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::PrepareExpandedFiles)?,
        &[
            (
                "expanded_files",
                PyTuple::new(py, expanded_files)?.into_any(),
            ),
            ("dialect", run.config.getattr("dialect")?),
            ("skip_unexpandable", skip),
        ],
    )?;
    if let Some(error) = failure {
        return Err(error);
    }
    let bodies: Bound<'py, PyAny> = prepared.getattr("bodies")?;
    if bodies.is_truthy()? && run.config.getattr("native_enabled")?.is_truthy()? {
        check_stop(py)?;
        let body_list: Vec<Bound<'py, PyAny>> = bodies.extract()?;
        let found: Bound<'py, PyAny> = registry::native(py, NativeAttr::LintNativeSqlBodies)?
            .call1((body_list, files, &run.config))?;
        for violation in found.try_iter()? {
            violations.push(violation?);
        }
        check_stop(py)?;
    }
    Ok((violations, prepared.getattr("unexpandable")?))
}

/// Lint all DSL files without modifying anything; optionally skip unexpandable SQL.
#[pyfunction]
#[pyo3(signature = (**options))]
fn run_lint<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "run_lint",
        options,
        (
            &["project_dir", "config"],
            &[
                "value_renderer",
                "selected_paths",
                "discovered_inputs",
                "dynamic_output_paths",
                "compiled_expansions",
                "expansion_context",
                "source_files",
                "skip_unexpandable",
            ],
        ),
    )?;
    let project_dir: Bound<'py, PyAny> = arguments.value("project_dir")?;
    let dynamic_output_paths: Bound<'py, PyAny> = if arguments.passed("dynamic_output_paths")? {
        arguments.value("dynamic_output_paths")?
    } else {
        PyFrozenSet::empty(py)?.into_any()
    };
    let run: LintRun<'py> = LintRun {
        project_dir,
        config: arguments.value("config")?,
        dynamic_output_paths,
        compiled_expansions: arguments.value("compiled_expansions")?,
        skip_unexpandable: arguments.flag("skip_unexpandable")?,
    };
    let files: Bound<'py, PyDict> = project_files(
        &run.project_dir,
        &arguments.value("selected_paths")?,
        &arguments.value("source_files")?,
    )?;
    let context: Bound<'py, PyAny> = expansion_context(&run, &arguments)?;
    let (violations, unexpandable) = lint_files(&run, &files, &context)?;
    let allow_suppressions: Bound<'py, PyAny> = run.config.getattr("allow_suppressions")?;
    let retained: Vec<Bound<'py, PyAny>> = registry::native(py, NativeAttr::ApplyLintSuppressions)?
        .call1((violations, &files, allow_suppressions))?
        .extract()?;
    call_with(
        &registry::class(py, RecordId::LintRunResult)?,
        &[
            ("files_checked", files.len().into_pyobject(py)?.into_any()),
            (
                "violations",
                PyTuple::new(py, sorted_violations(retained)?)?.into_any(),
            ),
            ("formatted_files", PyTuple::empty(py).into_any()),
            ("source_texts", files.into_any()),
            ("unexpandable", unexpandable),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_lint, module)?)?;
    module.add_function(wrap_pyfunction!(collect_lint_project_files, module)?)?;
    Ok(())
}

//! Native lint expansion orchestration around the existing user-macro boundary.

use pyo3::prelude::{Bound, IntoPyObject, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyDict, PyDictMethods, PyList, PyTuple};
use sqlbuild_rules::lint_text::main::dependency_sites::dependency_sites;
use sqlbuild_rules::lint_text::models::InterpolationSite;

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, keywords,
};
use crate::bindings::_helpers::rules::lint_headers::{lint_body_ranges, lint_file_role};

const NATIVE: &str = "sqlbuild._native";
const MODELS: &str = "sqlbuild.lint.models";
const EXPANSION_MODELS: &str = "sqlbuild.compiler.compile.models";
const COMPILE_ERRORS: &str = "sqlbuild.compiler.compile.exceptions";
const LINT_ERRORS: &str = "sqlbuild.lint.exceptions";
const STOP: &str = "sqlbuild.lint.classes.stop_context";

/// Expand a single body and finish its native SQL preparation.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn prepare_lint_body<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let pending = expand_lint_body(py, options)?;
    let prepared =
        imported(py, NATIVE, "prepare_lint_sql")?.call1((pending.getattr("request")?,))?;
    finish_body(&pending, &prepared)
}

/// Expand authored SQL while retaining source offsets and pre-expansion substitutions.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn expand_lint_body<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "expand_lint_body",
        options,
        (
            &[
                "role",
                "file_path",
                "contents",
                "body_range",
                "context",
                "dialect",
            ],
            &[
                "external_identifiers",
                "allows_ceremonial_select",
                "allows_dynamic_output_star",
                "compiled_expansion",
            ],
        ),
    )?;
    let (mut start, mut end): (usize, usize) = args.value("body_range")?.extract()?;
    let body = args.value("contents")?.get_item(pyo3::types::PySlice::new(
        py,
        start as isize,
        end as isize,
        1,
    ))?;
    let mut input = body.clone();
    let mut sites = PyTuple::empty(py).into_any();
    let role = args.value("role")?;
    let kind = role.getattr("declaration_kind")?;
    let in_project = role.getattr("in_project")?.is_truthy()?;
    let neutralizer = if in_project && kind.eq("audit")? {
        Some("neutralize_lint_audit_parameters")
    } else if role.getattr("in_hook_directory")?.is_truthy()?
        || (in_project && kind.eq("sql_hook")?)
    {
        Some("neutralize_lint_context_interpolation")
    } else {
        None
    };
    if let Some(neutralizer) = neutralizer {
        let neutralized = imported(py, NATIVE, neutralizer)?.call1((&body,))?;
        input = neutralized.get_item(0)?;
        sites = site_objects(&neutralized.get_item(1)?)?;
    }
    let compiled = args.value("compiled_expansion")?;
    let expanded;
    let passes;
    if !compiled.is_none()
        && body
            .call_method0("strip")?
            .eq(compiled.getattr("authored_sql")?)?
    {
        start += body.len()? - body.call_method0("lstrip")?.len()?;
        input = compiled.getattr("authored_sql")?;
        end = start + input.len()?;
        expanded = compiled.getattr("expanded_sql")?;
        passes = compiled.getattr("passes")?;
    } else if !input.extract::<String>()?.contains('@')
        && !input.extract::<String>()?.contains("${")
    {
        expanded = input.clone();
        passes = PyTuple::empty(py).into_any();
    } else {
        let value = call_with(
            &imported(py, NATIVE, "expand_sql_with_spans")?,
            &[
                ("sql", input.clone()),
                ("file_path", args.value("file_path")?),
                ("context", args.value("context")?),
            ],
        )
        .map_err(|error| expansion_error(py, &args, error))?;
        expanded = value.get_item(0)?;
        passes = value.get_item(1)?;
    }
    let mut prior_sites: Vec<Bound<'py, PyAny>> = Vec::new();
    for site in sites.try_iter()? {
        prior_sites.push(site?.getattr("neutralized_start")?);
    }
    let request = keywords(
        py,
        &[
            ("expanded", expanded.clone()),
            ("before_expansion", input.clone()),
            ("prior_sites", PyList::new(py, prior_sites)?.into_any()),
            ("dialect", args.value("dialect")?),
        ],
    )?;
    let external = if args.passed("external_identifiers")? {
        args.value("external_identifiers")?
    } else {
        PyTuple::empty(py).into_any()
    };
    call_with(
        &imported(py, MODELS, "PendingLintBody")?,
        &[
            ("file_path", args.value("file_path")?),
            ("body_start", start.into_pyobject(py)?.into_any()),
            ("body_end", end.into_pyobject(py)?.into_any()),
            ("expansion_input", input),
            ("expanded", expanded),
            ("expansion_passes", passes),
            ("pre_expansion_sites", sites),
            ("external_identifiers", external),
            (
                "allows_ceremonial_select",
                args.value_or_false("allows_ceremonial_select")?,
            ),
            (
                "allows_dynamic_output_star",
                args.value_or_false("allows_dynamic_output_star")?,
            ),
            (
                "allows_empty_fixture_star",
                false.into_pyobject(py)?.to_owned().into_any(),
            ),
            ("request", request.into_any()),
        ],
    )
}

fn expansion_error(py: Python<'_>, args: &KeywordArguments<'_>, error: PyErr) -> PyErr {
    let wrapped = (|| -> PyResult<Option<PyErr>> {
        if !error
            .value(py)
            .is_instance(&imported(py, COMPILE_ERRORS, "CompileInputError")?)?
        {
            return Ok(None);
        }
        let message = format!(
            "{} could not be expanded, so its SQL cannot be linted: {}",
            args.value("file_path")?.str()?,
            error.value(py).str()?
        );
        Ok(Some(PyErr::from_value(
            imported(py, LINT_ERRORS, "ProjectCompileError")?.call1((message,))?,
        )))
    })();
    match wrapped {
        Ok(Some(wrapped)) => {
            wrapped.set_cause(py, Some(error));
            wrapped
        }
        Ok(None) => error,
        Err(wrapping_error) => wrapping_error,
    }
}

fn site_objects<'py>(sites: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let class = imported(sites.py(), MODELS, "InterpolationSite")?;
    let values: Vec<Bound<'py, PyAny>> = sites
        .try_iter()?
        .map(|site| class.call1(site?.cast_into::<PyTuple>()?))
        .collect::<PyResult<_>>()?;
    Ok(PyTuple::new(sites.py(), values)?.into_any())
}

fn sentinel_spans<'py>(sites: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py = sites.py();
    let mut spans: Vec<Bound<'py, PyAny>> = Vec::new();
    for site in sites.try_iter()? {
        let site = site?;
        spans.push(call_with(
            &imported(py, EXPANSION_MODELS, "ExpansionSpan")?,
            &[
                ("source_start", site.getattr("original_start")?),
                ("source_end", site.getattr("original_end")?),
                ("output_start", site.getattr("neutralized_start")?),
                ("output_end", site.getattr("neutralized_end")?),
            ],
        )?);
    }
    Ok(PyTuple::new(py, spans)?.into_any())
}

fn finish_body<'py>(
    pending: &Bound<'py, PyAny>,
    prepared: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = pending.py();
    if prepared.is_none() {
        return Err(PyErr::from_value(
            imported(py, LINT_ERRORS, "NativeLintError")?.call1((format!(
                "{} could not be prepared for native SQL lint",
                pending.getattr("file_path")?.str()?
            ),))?,
        ));
    }
    let sites = site_objects(&prepared.get_item(1)?)?;
    let native_sites: Vec<InterpolationSite> = sites
        .try_iter()?
        .map(|site| {
            let site = site?;
            Ok(InterpolationSite {
                sentinel: site.getattr("sentinel")?.extract()?,
                original_text: site.getattr("original_text")?.extract()?,
                original_start: site.getattr("original_start")?.extract()?,
                original_end: site.getattr("original_end")?.extract()?,
                neutralized_start: site.getattr("neutralized_start")?.extract()?,
                neutralized_end: site.getattr("neutralized_end")?.extract()?,
            })
        })
        .collect::<PyResult<_>>()?;
    let dependencies = dependency_sites(&native_sites)
        .map_err(crate::bindings::_helpers::boundary::panics::value_error)?;
    let mut passes: Vec<Bound<'py, PyAny>> =
        vec![sentinel_spans(&pending.getattr("pre_expansion_sites")?)?];
    passes.extend(
        pending
            .getattr("expansion_passes")?
            .try_iter()?
            .collect::<PyResult<Vec<_>>>()?,
    );
    passes.push(sentinel_spans(&sites)?);
    let values = keywords(
        py,
        &[
            ("lint_text", prepared.get_item(0)?),
            ("passes", PyTuple::new(py, passes)?.into_any()),
            (
                "dependency_identifiers",
                PyTuple::new(py, dependencies.identifiers)?.into_any(),
            ),
            (
                "externally_referenced_ctes",
                PyTuple::new(py, prepared.get_item(2)?.extract::<Vec<String>>()?)?.into_any(),
            ),
            (
                "dependency_relations",
                PyTuple::new(py, dependencies.relations)?.into_any(),
            ),
        ],
    )?;
    for name in [
        "file_path",
        "body_start",
        "body_end",
        "external_identifiers",
        "allows_ceremonial_select",
        "allows_dynamic_output_star",
        "allows_empty_fixture_star",
    ] {
        values.set_item(name, pending.getattr(name)?)?;
    }
    imported(py, MODELS, "LintBody")?.call((), Some(&values))
}

fn prepare_batch<'py>(
    py: Python<'py>,
    pending: &[Bound<'py, PyAny>],
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    if pending.is_empty() {
        return Ok(Vec::new());
    }
    let requests: Vec<Bound<'py, PyAny>> = pending
        .iter()
        .map(|body| body.getattr("request"))
        .collect::<PyResult<_>>()?;
    let results =
        imported(py, NATIVE, "prepare_lint_sql_batch")?.call1((PyList::new(py, requests)?,))?;
    let mut prepared: Vec<Bound<'py, PyAny>> = Vec::new();
    for (body, result) in pending.iter().zip(results.try_iter()?) {
        let result = result?;
        prepared.push(if result.get_item(0)?.is_truthy()? {
            result.get_item(1)?
        } else {
            imported(py, NATIVE, "prepare_lint_sql")?.call1((body.getattr("request")?,))?
        });
    }
    if prepared.len() != pending.len() || results.len()? != pending.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "native preparation batch length mismatch",
        ));
    }
    Ok(prepared)
}

/// Expand each file body in order, preserving the first expansion failure with its partial work.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn expand_file_bodies<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "expand_file_bodies",
        options,
        (
            &[
                "file_path",
                "contents",
                "headers",
                "context",
                "dialect",
                "project_dir",
                "relative_path",
                "dynamic_output_paths",
                "compiled_expansions",
            ],
            &[],
        ),
    )?;
    imported(py, STOP, "LintStopContext")?.call_method0("check")?;
    let path = args.value("file_path")?;
    let role = lint_file_role(
        &path,
        &args.value("project_dir")?,
        Some(args.value("relative_path")?),
    )?;
    let dynamic = args.value("dynamic_output_paths")?;
    let dynamic_star = dynamic.is_truthy()? && dynamic.contains(path.call_method0("resolve")?)?;
    let expansions = args.value("compiled_expansions")?;
    let compiled = if expansions.is_truthy()? {
        expansions.call_method1("get", (&path,))?
    } else {
        py.None().into_bound(py)
    };
    let external = call_with(
        &imported(py, NATIVE, "external_identifiers_for_headers")?,
        &[
            ("contents", args.value("contents")?),
            ("headers", args.value("headers")?),
        ],
    )?;
    let mut ceremonial = false;
    for header in args.value("headers")?.try_iter()? {
        let kind = header?.getattr("kind")?;
        if kind.eq("TEST")? || kind.eq("SCENARIO")? {
            ceremonial = true;
            break;
        }
    }
    let mut bodies: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut failure = py.None().into_bound(py);
    let expansion = (|| -> PyResult<()> {
        let ranges = lint_body_ranges(
            py,
            Some(keywords(
                py,
                &[
                    ("contents", args.value("contents")?),
                    ("headers", args.value("headers")?),
                    ("file_path", path.clone()),
                    ("project_dir", args.value("project_dir")?),
                    ("role", role.clone()),
                ],
            )?),
        )?;
        for range in ranges.try_iter()? {
            let pending = expand_lint_body(
                py,
                Some(keywords(
                    py,
                    &[
                        ("role", role.clone()),
                        ("file_path", path.clone()),
                        ("contents", args.value("contents")?),
                        ("body_range", range?),
                        ("context", args.value("context")?),
                        ("dialect", args.value("dialect")?),
                        ("external_identifiers", external.clone()),
                        (
                            "allows_ceremonial_select",
                            ceremonial.into_pyobject(py)?.to_owned().into_any(),
                        ),
                        (
                            "allows_dynamic_output_star",
                            dynamic_star.into_pyobject(py)?.to_owned().into_any(),
                        ),
                        ("compiled_expansion", compiled.clone()),
                    ],
                )?),
            )?;
            let changes = keywords(
                py,
                &[(
                    "allows_empty_fixture_star",
                    ceremonial.into_pyobject(py)?.to_owned().into_any(),
                )],
            )?;
            bodies.push(
                py.import("dataclasses")?
                    .getattr("replace")?
                    .call((pending,), Some(&changes))?,
            );
        }
        Ok(())
    })();
    if let Err(error) = expansion {
        if !error
            .value(py)
            .is_instance(&imported(py, LINT_ERRORS, "ProjectCompileError")?)?
        {
            return Err(error);
        }
        failure = error.value(py).clone().into_any();
    }
    call_with(
        &imported(py, MODELS, "ExpandedLintFile")?,
        &[
            ("file_path", path),
            ("bodies", PyTuple::new(py, bodies)?.into_any()),
            ("failure", failure),
        ],
    )
}

/// Batch SQL preparation, then publish bodies or failures in the original file order.
#[pyfunction]
#[pyo3(signature = (*, expanded_files, dialect, skip_unexpandable))]
pub(crate) fn prepare_expanded_files<'py>(
    expanded_files: &Bound<'py, PyAny>,
    dialect: &str,
    skip_unexpandable: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let _ = dialect;
    let py = expanded_files.py();
    imported(py, STOP, "LintStopContext")?.call_method0("check")?;
    let files: Vec<Bound<'py, PyAny>> = expanded_files.try_iter()?.collect::<PyResult<_>>()?;
    let mut pending: Vec<Bound<'py, PyAny>> = Vec::new();
    for file in &files {
        pending.extend(
            file.getattr("bodies")?
                .try_iter()?
                .collect::<PyResult<Vec<_>>>()?,
        );
    }
    let prepared = prepare_batch(py, &pending)?;
    let mut bodies: Vec<Bound<'py, PyAny>> = Vec::new();
    let unexpandable = PyDict::new(py);
    let mut position = 0;
    for file in files {
        let mut file_bodies: Vec<Bound<'py, PyAny>> = Vec::new();
        for body in file.getattr("bodies")?.try_iter()? {
            file_bodies.push(finish_body(&body?, &prepared[position])?);
            position += 1;
        }
        let failure = file.getattr("failure")?;
        if failure.is_none() {
            bodies.extend(file_bodies);
        } else if skip_unexpandable {
            let path = file.getattr("file_path")?;
            let message: String = failure.str()?.extract()?;
            let prefix = format!("{} ", path.str()?);
            unexpandable.set_item(path, message.strip_prefix(&prefix).unwrap_or(&message))?;
        } else {
            return Err(PyErr::from_value(failure));
        }
    }
    call_with(
        &imported(py, MODELS, "PreparedLintFiles")?,
        &[
            ("bodies", PyTuple::new(py, bodies)?.into_any()),
            ("unexpandable", unexpandable.into_any()),
        ],
    )
}

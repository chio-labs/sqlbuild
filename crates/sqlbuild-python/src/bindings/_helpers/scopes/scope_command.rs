//! `sqb scope`: load offline compiler facts, run one scope query and present its result.

use std::collections::BTreeSet;

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_scopes::scope_report::models::ScopeResult;
use sqlbuild_scopes::scope_text::main::render_scope_text::render_scope_text;
use sqlbuild_scopes::scope_text::main::scope_result_failed::scope_result_failed;
use sqlbuild_scopes::scope_text::models::ScopeTextRequest;

use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;
use crate::bindings::_helpers::scopes::scope_lookup::build_scope_lookup;
use crate::bindings::_helpers::scopes::scope_objects::ScopeClasses;
use crate::bindings::_helpers::scopes::scope_report_objects::read_result;
use crate::bindings::_helpers::scopes::scope_reports::{
    scope_browse, scope_explain, scope_list, scope_move_preview, scope_report,
    serialize_scope_report,
};

const NATIVE_MODULE: &str = "sqlbuild._native";
const MODELS_MODULE: &str = "sqlbuild.compiler.scopes.models";
const TYPES_MODULE: &str = "sqlbuild.compiler.scopes.types";
const ERRORS_MODULE: &str = "sqlbuild._native";
const TARGET_ERROR_CODE: &str = "C960";
const BARE_USAGE: &str = "bare names work for models, sources, seeds and functions; write macros, \
enums, constants, tests and audits with their prefix, for example macro:<name>";
/// Resource kinds a bare target name may refer to.
const BARE_KINDS: [&str; 4] = ["model", "source", "seed", "function"];
const PATH_MARKERS: [char; 3] = ['/', '\\', '.'];

fn keywords<'py>(
    py: Python<'py>,
    items: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyDict>> {
    let dict: Bound<'py, PyDict> = PyDict::new(py);
    for (name, value) in items {
        dict.set_item(*name, value)?;
    }
    Ok(dict)
}

fn user_error(py: Python<'_>, message: String) -> PyResult<PyErr> {
    let options: Bound<'_, PyDict> = PyDict::new(py);
    options.set_item("code", TARGET_ERROR_CODE)?;
    options.set_item("help", BARE_USAGE)?;
    let error: Bound<'_, PyAny> = py
        .import(ERRORS_MODULE)?
        .getattr("CliUserError")?
        .call((message,), Some(&options))?;
    Ok(PyErr::from_value(error))
}

fn or_list(values: &[String]) -> String {
    match values.split_last() {
        Some((last, rest)) if !rest.is_empty() => format!("{} or {last}", rest.join(", ")),
        _ => values.join(""),
    }
}

/// The kinds of resources named `target`, and the prefixed names of other matches.
fn target_matches(
    lookup: &Bound<'_, PyAny>,
    target: &str,
) -> PyResult<(BTreeSet<String>, Vec<String>)> {
    let mut bare: BTreeSet<String> = BTreeSet::new();
    let mut prefixed: BTreeSet<String> = BTreeSet::new();
    for identity in lookup.getattr("resources")?.try_iter()? {
        let identity: Bound<'_, PyAny> = identity?;
        if identity.getattr("name")?.extract::<String>()? != target {
            continue;
        }
        let kind: String = identity.getattr("kind")?.str()?.extract()?;
        if BARE_KINDS.contains(&kind.as_str()) {
            bare.insert(kind);
        } else {
            prefixed.insert(format!("{kind}:{target}"));
        }
    }
    for identity in lookup.getattr("declarations")?.try_iter()? {
        let identity: Bound<'_, PyAny> = identity?;
        if identity.getattr("owner")?.is_none()
            && identity.getattr("name")?.extract::<String>()? == target
        {
            let kind: String = identity.getattr("kind")?.str()?.extract()?;
            prefixed.insert(format!("{kind}:{target}"));
        }
    }
    Ok((bare, prefixed.into_iter().collect()))
}

/// `target` with its kind prefix when it is a bare model, source, seed or function.
fn qualify_target(
    py: Python<'_>,
    lookup: &Bound<'_, PyAny>,
    target: Option<String>,
) -> PyResult<Option<String>> {
    let Some(target) = target else {
        return Ok(None);
    };
    if target.contains(':') || target.contains(PATH_MARKERS) {
        return Ok(Some(target));
    }
    let (bare, prefixed) = target_matches(lookup, &target)?;
    if bare.is_empty() {
        let message: String = if prefixed.is_empty() {
            format!("unknown scope target '{target}'")
        } else {
            format!(
                "scope target '{target}' needs its prefix: {}",
                or_list(&prefixed)
            )
        };
        return Err(user_error(py, message)?);
    }
    let candidates: Vec<String> = bare
        .iter()
        .map(|kind| format!("{kind}:{target}"))
        .chain(prefixed)
        .collect();
    if candidates.len() > 1 {
        return Err(user_error(
            py,
            format!(
                "scope target '{target}' matches more than one resource or declaration; write {}",
                or_list(&candidates)
            ),
        )?);
    }
    Ok(candidates.into_iter().next())
}

fn text_request(request: &Bound<'_, PyAny>, target: Option<String>) -> PyResult<ScopeTextRequest> {
    let mut kinds: Vec<String> = Vec::new();
    for kind in request.getattr("kinds")?.try_iter()? {
        kinds.push(kind?.extract()?);
    }
    Ok(ScopeTextRequest {
        target,
        at: request.getattr("at")?.extract()?,
        as_path: request.getattr("as_path")?.extract()?,
        defined_under: request.getattr("defined_under")?.extract()?,
        kinds,
        glob: request.getattr("match")?.extract()?,
        used_only: request.getattr("used_only")?.extract()?,
        include_nearby: request.getattr("include_nearby")?.extract()?,
        nearby_depth: request.getattr("nearby_depth")?.extract()?,
        dependency_depth: request.getattr("dependency_depth")?.extract()?,
        explain: request.getattr("explain")?.extract()?,
        globals: request.getattr("globals")?.extract()?,
        page_size: request.getattr("page_size")?.extract()?,
        paths: request.getattr("paths")?.extract()?,
        verbose: request.getattr("verbose")?.extract()?,
        no_cache: request.getattr("no_cache")?.extract()?,
    })
}

fn report_filters<'py>(
    py: Python<'py>,
    request: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let kind_class: Bound<'_, PyAny> = py.import(TYPES_MODULE)?.getattr("DeclarationKind")?;
    let mut kinds: Vec<Bound<'_, PyAny>> = Vec::new();
    for kind in request.getattr("kinds")?.try_iter()? {
        kinds.push(kind_class.call1((kind?,))?);
    }
    let options: Bound<'_, PyDict> = keywords(
        py,
        &[
            ("include_nearby", request.getattr("include_nearby")?),
            ("defined_under", request.getattr("defined_under")?),
            ("kinds", PyTuple::new(py, kinds)?.into_any()),
            ("glob", request.getattr("match")?),
            ("used_only", request.getattr("used_only")?),
            ("dependency_depth", request.getattr("dependency_depth")?),
            ("cursor", request.getattr("after")?),
            ("page_size", request.getattr("page_size")?),
            ("nearby_depth", request.getattr("nearby_depth")?),
            ("globals", request.getattr("globals")?),
        ],
    )?;
    py.import(MODELS_MODULE)?
        .getattr("ScopeReportFilters")?
        .call((), Some(&options))
}

/// `dataclasses.replace(report, **changes)`.
fn replaced<'py>(
    report: &Bound<'py, PyAny>,
    changes: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    report
        .py()
        .import("dataclasses")?
        .getattr("replace")?
        .call((report,), Some(changes))
}

/// The report with extra diagnostics and a part of the result merged in.
fn merged<'py>(
    report: &Bound<'py, PyAny>,
    (name, value): (&str, Bound<'py, PyAny>),
    (diagnostics, complete): (Bound<'py, PyAny>, bool),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = report.py();
    let combined: Bound<'py, PyAny> = report.getattr("diagnostics")?.add(diagnostics)?;
    let complete: bool = report.getattr("complete")?.extract::<bool>()? && complete;
    let changes: Bound<'py, PyDict> = keywords(
        py,
        &[
            (name, value),
            ("diagnostics", combined),
            (
                "complete",
                pyo3::types::PyBool::new(py, complete).to_owned().into_any(),
            ),
        ],
    )?;
    replaced(report, &changes)
}

/// `value` as an optional Python string.
fn optional_text<'py>(py: Python<'py>, value: &Option<String>) -> Option<Bound<'py, PyAny>> {
    value
        .as_deref()
        .map(|text| PyString::new(py, text).into_any())
}

/// Run the query `request` selects over `lookup`.
fn query_result<'py>(
    py: Python<'py>,
    lookup: &Bound<'py, PyAny>,
    (request, target): (&Bound<'py, PyAny>, Option<String>),
) -> PyResult<Bound<'py, PyAny>> {
    let at: Option<String> = request.getattr("at")?.extract()?;
    let prospective: bool = at.is_some();
    let browse: Option<String> = request.getattr("browse")?.extract()?;
    if let Some(folder) = browse {
        return Ok(scope_browse(
            py,
            lookup,
            (folder, optional_text(py, &target), prospective),
        )?
        .into_bound(py));
    }
    let filters: Bound<'_, PyAny> = report_filters(py, request)?;
    let list_path: Option<String> = request.getattr("list_path")?.extract()?;
    if let Some(folder) = list_path {
        return Ok(scope_list(
            py,
            lookup,
            (
                folder,
                Some(filters),
                optional_text(py, &target),
                prospective,
            ),
        )?
        .into_bound(py));
    }
    let directory: bool = at
        .as_deref()
        .is_some_and(|at| at.ends_with('/') || at.ends_with('\\'));
    let mut report: Bound<'_, PyAny> = scope_report(
        py,
        lookup,
        (
            optional_text(py, &target),
            optional_text(py, &at),
            directory,
            Some(filters),
        ),
    )?
    .into_bound(py);
    let explain: Option<String> = request.getattr("explain")?.extract()?;
    if let Some(declaration) = explain {
        let (explanation, diagnostics): (Bound<'_, PyAny>, Bound<'_, PyAny>) = scope_explain(
            py,
            lookup,
            (
                PyString::new(py, &declaration).into_any(),
                optional_text(py, &target),
                optional_text(py, &at),
                directory,
            ),
        )
        .map(|(explanation, diagnostics)| {
            (explanation.into_bound(py), diagnostics.into_bound(py))
        })?;
        let complete: bool = explanation.getattr("complete")?.extract()?;
        report = merged(
            &report,
            ("explanation", explanation),
            (diagnostics, complete),
        )?;
    }
    let as_path: Option<String> = request.getattr("as_path")?.extract()?;
    if let Some(destination) = as_path {
        let (preview, diagnostics): (Bound<'_, PyAny>, Bound<'_, PyAny>) = scope_move_preview(
            py,
            lookup,
            &PyString::new(py, &target.clone().unwrap_or_default()).into_any(),
            &PyString::new(py, &destination).into_any(),
        )
        .map(|(preview, diagnostics)| {
            (
                preview.map_or_else(
                    || py.None().into_bound(py),
                    |preview| preview.into_bound(py),
                ),
                diagnostics.into_bound(py),
            )
        })?;
        let complete: bool = !preview.is_none() && preview.getattr("complete")?.extract()?;
        report = merged(&report, ("move_preview", preview), (diagnostics, complete))?;
    }
    Ok(report)
}

fn use_color(
    py: Python<'_>,
    request: &Bound<'_, PyAny>,
    output_stream: Option<&Bound<'_, PyAny>>,
) -> PyResult<bool> {
    if output_stream.is_some() || request.getattr("no_color")?.extract::<bool>()? {
        return Ok(false);
    }
    stdout_supports_color(py)
}

/// Load offline compiler facts, run one pure query, and present its result.
#[pyfunction]
#[pyo3(signature = (*, request, load_scope_index = None, output_stream = None))]
fn run_scope_command(
    py: Python<'_>,
    request: &Bound<'_, PyAny>,
    load_scope_index: Option<Bound<'_, PyAny>>,
    output_stream: Option<Bound<'_, PyAny>>,
) -> PyResult<i32> {
    let native: Bound<'_, PyModule> = py.import(NATIVE_MODULE)?;
    let project_dir: Bound<'_, PyAny> = match request.getattr("project_dir")? {
        directory if !directory.is_none() => directory,
        _ => py.import("pathlib")?.getattr("Path")?.call_method0("cwd")?,
    };
    let loader: Bound<'_, PyAny> = match load_scope_index {
        Some(loader) => loader,
        None => native.getattr("load_or_build_scope_index")?,
    };
    let options: Bound<'_, PyDict> = keywords(
        py,
        &[
            ("project_dir", project_dir),
            ("no_cache", request.getattr("no_cache")?),
        ],
    )?;
    let index: Bound<'_, PyAny> = loader.call((), Some(&options))?;
    let lookup: Bound<'_, PyAny> = build_scope_lookup(py, &index)?.into_bound(py);
    let target: Option<String> =
        qualify_target(py, &lookup, request.getattr("target")?.extract()?)?;
    let result: Bound<'_, PyAny> = query_result(py, &lookup, (request, target.clone()))?;
    let classes: ScopeClasses<'_> = ScopeClasses::new(py)?;
    let (output, native_result): (String, ScopeResult) =
        if request.getattr("json_output")?.extract()? {
            let output: String = serialize_scope_report(py, &result)?;
            (output, read_result(&classes, &result)?)
        } else {
            let native_result: ScopeResult = read_result(&classes, &result)?;
            let style: CliStyle = CliStyle {
                use_color: use_color(py, request, output_stream.as_ref())?,
            };
            let output: String =
                render_scope_text(&native_result, &text_request(request, target)?, style);
            (output, native_result)
        };
    let stream: Bound<'_, PyAny> = match output_stream {
        Some(stream) => stream,
        None => py.import("sys")?.getattr("stdout")?,
    };
    stream.call_method1("write", (output,))?;
    Ok(i32::from(scope_result_failed(&native_result)))
}

/// Render one compiler-owned scope result as `sqb scope` text.
#[pyfunction]
#[pyo3(signature = (*, result, request, use_color = false))]
fn render_scope_result(
    py: Python<'_>,
    result: &Bound<'_, PyAny>,
    request: &Bound<'_, PyAny>,
    use_color: bool,
) -> PyResult<String> {
    let classes: ScopeClasses<'_> = ScopeClasses::new(py)?;
    let target: Option<String> = request.getattr("target")?.extract()?;
    Ok(render_scope_text(
        &read_result(&classes, result)?,
        &text_request(request, target)?,
        CliStyle { use_color },
    ))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_scope_command, module)?)?;
    module.add_function(wrap_pyfunction!(render_scope_result, module)?)
}

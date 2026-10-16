//! Authored SQL expanded through project vars, declarations and macros, with each pass's spans.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::model_config::template_data::record_reads;
use crate::bindings::_helpers::model_config::unicode_environment::unicode_environment;
use crate::bindings::_helpers::render::declaration_expansion::{
    DeclarationExpansion, ExpandedDeclarations, ExpansionClasses, ExpansionConsumer, SpanRow,
    expand_declarations, span_rows,
};
use crate::bindings::_helpers::render::declaration_values::resolved_declaration_context;
use crate::bindings::_helpers::render::macro_expansion_result::expand_sql_macros;
use crate::bindings::_helpers::sqltext::declaration_references::declaration_scan;
use crate::bindings::_helpers::sqltext::static_sql::{InterpolationSources, interpolation_batch};

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild._native";
const COMPILE_ERRORS_MODULE: &str = "sqlbuild._native";
const SCOPE_MODELS_MODULE: &str = "sqlbuild._native";
const FUNCTOOLS_MODULE: &str = "functools";
const DECLARATION_FIELDS: [&str; 4] = [
    "enums",
    "constants",
    "inaccessible_enums",
    "inaccessible_constants",
];

/// `sql` with `@@` tokens interpolated and each substitution's span, raising its error.
fn substituted<'py>(
    sql: &Bound<'py, PyAny>,
    file_path: &Bound<'py, PyAny>,
    (effective_vars, context_values): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<(String, Vec<SpanRow>)> {
    let py: Python<'py> = sql.py();
    let sources = InterpolationSources(
        effective_vars.downcast()?.clone(),
        unicode_environment(py)?,
        if context_values.is_none() {
            None
        } else {
            Some(context_values.downcast()?.clone())
        },
        imported(py, NATIVE_MODULE, "render_project_var_text")?,
    );
    let text: String = sql.extract()?;
    let path: String = file_path.str()?.extract()?;
    let rows = interpolation_batch(sources, &[(text.clone(), path)])?;
    let Some((rendered, spans, reads, error)) = rows.into_iter().next() else {
        return Ok((text, Vec::new()));
    };
    record_reads(py, reads.iter().map(|(kind, name)| (*kind, name.as_str())))?;
    if let Some(message) = error {
        return Err(PyErr::from_value(
            imported(py, COMPILE_ERRORS_MODULE, "CompileInputError")?.call1((message,))?,
        ));
    }
    Ok((rendered.unwrap_or(text), spans))
}

/// `ExpansionSpan` objects for span rows, in order.
fn span_objects<'py>(py: Python<'py>, spans: &[SpanRow]) -> PyResult<Bound<'py, PyTuple>> {
    let span_class: Bound<'py, PyAny> = imported(py, NATIVE_RECORDS_MODULE, "ExpansionSpan")?;
    let objects: Vec<Bound<'py, PyAny>> = spans
        .iter()
        .map(|span| span_class.call1(*span))
        .collect::<PyResult<_>>()?;
    PyTuple::new(py, objects)
}

/// The authored SQL's public declaration context: visible and inaccessible enums and constants.
fn declaration_context<'py>(
    py: Python<'py>,
    declarations: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let fields: Vec<(&str, Bound<'py, PyAny>)> = DECLARATION_FIELDS
        .iter()
        .map(|field| {
            Ok((
                *field,
                if declarations.is_none() {
                    PyDict::new(py).into_any()
                } else {
                    declarations.getattr(*field)?
                },
            ))
        })
        .collect::<PyResult<_>>()?;
    call_with(
        &imported(py, COMPILE_MODELS_MODULE, "DeclarationResolutionContext")?,
        &fields,
    )
}

/// `sql` with natively scanned enum and constant references spliced, and their spans.
fn declarations_expanded<'py>(
    sql: &str,
    file_path: &Bound<'py, PyAny>,
    (declarations, value_renderer, collection_rendering): (
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
    ),
) -> PyResult<(String, Vec<SpanRow>)> {
    let py: Python<'py> = file_path.py();
    let (references, stop) = declaration_scan(sql);
    if references.is_empty() && stop.is_none() {
        return Ok((sql.to_owned(), Vec::new()));
    }
    let context: Bound<'py, PyAny> = declaration_context(py, declarations)?;
    let render_constant: Bound<'py, PyAny> = imported(py, FUNCTOOLS_MODULE, "partial")?.call(
        (imported(py, NATIVE_MODULE, "render_constant_declaration")?,),
        Some(&keywords(
            py,
            &[
                ("value_renderer", value_renderer.clone()),
                ("collection_rendering", collection_rendering.clone()),
                ("file_path", file_path.clone()),
            ],
        )?),
    )?;
    let classes = ExpansionClasses {
        usage_record: imported(py, SCOPE_MODELS_MODULE, "UsageRecord")?,
        compile_error: imported(py, COMPILE_ERRORS_MODULE, "CompileInputError")?,
    };
    let path: String = file_path.str()?.extract()?;
    let expanded: ExpandedDeclarations<'py> = expand_declarations(&DeclarationExpansion {
        sql,
        references: &references,
        stop,
        context: &context,
        consumer: ExpansionConsumer {
            identity: None,
            relationship_visibility: false,
            path: &path,
        },
        render_constant: &render_constant,
        classes: &classes,
    })?;
    let spans: Vec<SpanRow> = span_rows(&expanded.spliced);
    Ok((expanded.spliced.sql, spans))
}

/// Expand authored SQL, returning each pass's substitution spans in order.
fn authored_sql_with_spans<'py>(request: &Request<'_, 'py>) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = request.py();
    let none = || py.None().into_bound(py);
    let file_path: Bound<'py, PyAny> = request.get("file_path")?;
    let (interpolated, interpolation_spans) = substituted(
        &request.get("sql")?,
        &file_path,
        (
            &request.get("effective_vars")?,
            &request.optional("context_values")?.unwrap_or_else(none),
        ),
    )?;
    let (declared, declaration_spans) = declarations_expanded(
        &interpolated,
        &file_path,
        (
            &request.optional("declarations")?.unwrap_or_else(none),
            &request.get("value_renderer")?,
            &request.get("collection_rendering")?,
        ),
    )?;
    let macro_options: Bound<'py, PyDict> = keywords(
        py,
        &[
            ("sql", PyString::new(py, &declared).into_any()),
            ("file_path", file_path),
            ("loaded_macros", request.get("loaded_macros")?),
            ("macro_context", request.get("macro_context")?),
            (
                "declaration_resolver",
                request
                    .optional("declaration_resolver")?
                    .unwrap_or_else(none),
            ),
        ],
    )?;
    let expansion: Bound<'py, PyAny> = expand_sql_macros(py, Some(macro_options))?;
    let passes: Bound<'py, PyTuple> = PyTuple::new(
        py,
        [
            span_objects(py, &interpolation_spans)?.into_any(),
            span_objects(py, &declaration_spans)?.into_any(),
            expansion.getattr("spans")?,
        ],
    )?;
    PyTuple::new(py, [expansion.getattr("sql")?, passes.into_any()])
}

/// Expand authored SQL, returning each pass's substitution spans in order.
#[pyfunction]
#[pyo3(signature = (**request))]
fn expand_authored_sql_with_spans<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    authored_sql_with_spans(&Request::new("expand_authored_sql_with_spans", request)?)
}

/// The declarations visible to `file_path`: the resolver's, else the context's, plus model-local.
fn path_declarations<'py>(
    context: &Bound<'py, PyAny>,
    file_path: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.py();
    let resolution_class: Bound<'py, PyAny> =
        imported(py, COMPILE_MODELS_MODULE, "DeclarationResolutionContext")?;
    let resolver: Bound<'py, PyAny> = context.getattr("declaration_resolver")?;
    let declarations: Bound<'py, PyAny> = if resolver.is_none() {
        call_with(
            &resolution_class,
            &[
                ("enums", context.getattr("enums")?),
                ("constants", context.getattr("constants")?),
            ],
        )?
    } else {
        resolved_declaration_context(&resolver, file_path, None)?
    };
    let local: Bound<'py, PyAny> = context
        .getattr("local_declarations")?
        .call_method1("get", (file_path,))?;
    if local.is_none() {
        return Ok(declarations);
    }
    let merged = |field: &str| -> PyResult<Bound<'py, PyAny>> {
        declarations.getattr(field)?.bitor(local.getattr(field)?)
    };
    call_with(
        &resolution_class,
        &[
            ("enums", merged("enums")?),
            ("constants", merged("constants")?),
            (
                "inaccessible_enums",
                declarations.getattr("inaccessible_enums")?,
            ),
            (
                "inaccessible_constants",
                declarations.getattr("inaccessible_constants")?,
            ),
        ],
    )
}

/// Expand authored SQL with a project's expansion context and report each pass's spans.
#[pyfunction]
#[pyo3(signature = (*, sql, file_path, context))]
fn expand_sql_with_spans<'py>(
    sql: &Bound<'py, PyAny>,
    file_path: &Bound<'py, PyAny>,
    context: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = sql.py();
    let arguments: Bound<'py, PyDict> = keywords(
        py,
        &[
            ("sql", sql.clone()),
            ("file_path", file_path.clone()),
            ("effective_vars", context.getattr("effective_vars")?),
            ("loaded_macros", context.getattr("loaded_macros")?),
            ("macro_context", context.getattr("macro_context")?),
            ("declarations", path_declarations(context, file_path)?),
            (
                "declaration_resolver",
                context.getattr("declaration_resolver")?,
            ),
            ("value_renderer", context.getattr("value_renderer")?),
            (
                "collection_rendering",
                context.getattr("collection_rendering")?,
            ),
        ],
    )?;
    authored_sql_with_spans(&Request::new("expand_sql_with_spans", Some(&arguments))?)
}

/// Replace SQL interpolation tokens, returning the span of every substitution.
#[pyfunction]
#[pyo3(signature = (*, sql, file_path, effective_vars, context_values=None))]
fn substitute_sql_vars_with_spans<'py>(
    sql: &Bound<'py, PyAny>,
    file_path: &Bound<'py, PyAny>,
    effective_vars: &Bound<'py, PyAny>,
    context_values: Option<Bound<'py, PyAny>>,
) -> PyResult<(String, Bound<'py, PyTuple>)> {
    let py: Python<'py> = sql.py();
    let context_values: Bound<'py, PyAny> =
        context_values.unwrap_or_else(|| py.None().into_bound(py));
    let (substituted_sql, spans) = substituted(sql, file_path, (effective_vars, &context_values))?;
    Ok((substituted_sql, span_objects(py, &spans)?))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(expand_authored_sql_with_spans, module)?)?;
    module.add_function(wrap_pyfunction!(expand_sql_with_spans, module)?)?;
    module.add_function(wrap_pyfunction!(substitute_sql_vars_with_spans, module)?)?;
    Ok(())
}

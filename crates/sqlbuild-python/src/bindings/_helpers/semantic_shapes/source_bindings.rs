//! Rebind selected models to source columns the planner already inspected.

use std::collections::HashSet;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::analysis::binding_catalog::{
    self, CASE_SENSITIVE_BINDING_DIALECTS, NATIVE_DIALECT_ALIASES, schema_validations,
};
use crate::bindings::_helpers::attachments::cursor_intrinsics::analysis_cursor_sql;
use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::semantic_shapes::declarations::{declared_types, function_names};
use crate::bindings::_helpers::semantic_shapes::shapes::{
    model_inputs, project_shapes, published_shape,
};

const NATIVE_MODULE: &str = "sqlbuild._native";
const ANALYSIS_MODELS_MODULE: &str = "sqlbuild.compiler.analysis_session.models";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const LINEAGE_TYPES_MODULE: &str = "sqlbuild.compiler.lineage.types";
const BINDING_UNKNOWN_TABLE_INTERNAL_CODE: &str = "B000";
const BINDING_REQUESTS_MODULE: &str =
    "sqlbuild.compiler.compile._helpers.analysis.binding_requests";
const DATACLASSES_MODULE: &str = "dataclasses";
const GRAPHLIB_MODULE: &str = "graphlib";
const REF_KIND: &str = "ref";
const SOURCE_KIND: &str = "source";
const UNKNOWN: &str = "UNKNOWN";
const GENERIC_DIALECT: &str = "generic";

type Object<'py> = Bound<'py, PyAny>;

/// `source_binding_diagnostics(*, project, columns, profile, selected_keys)`.
#[pyfunction]
#[pyo3(signature = (**request))]
fn source_binding_diagnostics<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let request = Request::new("source_binding_diagnostics", request)?;
    let py: Python<'py> = request.py();
    let project: Object<'py> = request.get("project")?;
    let columns: Object<'py> = request.get("columns")?;
    if !project
        .getattr("settings")?
        .getattr("sql_analysis")?
        .is_truthy()?
        || !columns.is_truthy()?
    {
        return Ok(PyTuple::empty(py));
    }
    let profile: Object<'py> = request.get("profile")?;
    let raw_dialect: Object<'py> = profile.getattr("sql_analysis_dialect")?;
    let key: Object<'py> = if raw_dialect.is_truthy()? {
        raw_dialect.clone()
    } else {
        PyString::new(py, GENERIC_DIALECT).into_any()
    };
    let key: String = key.extract()?;
    let dialect: Object<'py> = match NATIVE_DIALECT_ALIASES
        .iter()
        .find(|(alias, _)| *alias == key)
    {
        Some((_, native)) => PyString::new(py, native).into_any(),
        None => raw_dialect.clone(),
    };
    let ignore_case: Object<'py> = ignores_quoted_case(&project, &raw_dialect)?;
    let profile: Object<'py> = replaced(
        &profile,
        &[
            ("sql_analysis_dialect", dialect.clone()),
            ("quoted_identifiers_ignore_case", ignore_case.clone()),
        ],
    )?;
    let shapes: Bound<'py, PyDict> = project_shapes(&project, Some(profile.clone()))?;
    let sensitive: bool = !dialect.is_none()
        && CASE_SENSITIVE_BINDING_DIALECTS.contains(&dialect.extract::<String>()?.as_str())
        && !ignore_case.is_truthy()?;
    let mut changed: HashSet<String> = HashSet::new();
    for item in columns.call_method0("items")?.try_iter()? {
        let (name, value): (String, Object<'py>) = item?.extract()?;
        if !value.is_truthy()? {
            continue;
        }
        let physical: Vec<(String, Option<String>)> = value
            .try_iter()?
            .map(|column| {
                let column: Object<'py> = column?;
                Ok((
                    column.getattr("name")?.extract()?,
                    column.getattr("type")?.extract()?,
                ))
            })
            .collect::<PyResult<_>>()?;
        if sensitive || adds_physical_evidence(&physical, shapes.get_item(&name)?.as_ref())? {
            changed.insert(name.clone());
        }
        let quoted: Bound<'py, PyDict> = PyDict::new(py);
        for (column, column_type) in physical {
            quoted.set_item(format!("\"{}\"", column.replace('"', "\"\"")), column_type)?;
        }
        shapes.set_item(name, quoted)?;
    }
    let binding_catalog: Object<'py> = project.getattr("binding_catalog")?;
    let mut physical_catalog: Object<'py> = if binding_catalog.is_none() {
        binding_catalog
    } else {
        binding_catalog.call_method1("with_relations", (&shapes,))?
    };
    let profile: Object<'py> =
        replaced(&profile, &[("binding_catalog", physical_catalog.clone())])?;
    let models: Vec<Object<'py>> = rebound_models(
        &project,
        &request.get("selected_keys")?,
        (&changed, &shapes),
        &profile,
    )?;
    if !physical_catalog.is_none() {
        physical_catalog = physical_catalog.call_method1("with_relations", (&shapes,))?;
    }
    validated_diagnostics(&project, &models, (&shapes, &physical_catalog), &dialect)
}

/// Selected models reading changed sources, re-analysed in dependency order; shapes updated.
fn rebound_models<'py>(
    project: &Object<'py>,
    selected_keys: &Object<'py>,
    (changed, shapes): (&HashSet<String>, &Bound<'py, PyDict>),
    profile: &Object<'py>,
) -> PyResult<Vec<Object<'py>>> {
    let py: Python<'py> = project.py();
    let by_name: Bound<'py, PyDict> = PyDict::new(py);
    for model in project.getattr("models")?.try_iter()? {
        let model: Object<'py> = model?;
        by_name.set_item(model.getattr("name")?, &model)?;
    }
    let graph: Bound<'py, PyDict> = PyDict::new(py);
    for model in project.getattr("models")?.try_iter()? {
        let model: Object<'py> = model?;
        let mut upstream: Vec<Object<'py>> = Vec::new();
        for reference in model.getattr("references")?.try_iter()? {
            let reference: Object<'py> = reference?;
            let name: Object<'py> = reference.getattr("ref_name")?;
            if reference.getattr("ref_kind")?.eq(REF_KIND)? && by_name.contains(&name)? {
                upstream.push(name);
            }
        }
        graph.set_item(model.getattr("name")?, PyTuple::new(py, upstream)?)?;
    }
    let order: Object<'py> = py
        .import(GRAPHLIB_MODULE)?
        .getattr("TopologicalSorter")?
        .call1((graph,))?
        .call_method0("static_order")?;
    let query_class: Object<'py> = py
        .import(ANALYSIS_MODELS_MODULE)?
        .getattr("NativeColumnQuery")?;
    let unknown: Object<'py> = py
        .import(LINEAGE_TYPES_MODULE)?
        .getattr("InferredNullability")?
        .getattr("UNKNOWN")?;
    let infer: Object<'py> = py
        .import(NATIVE_MODULE)?
        .getattr("infer_native_query_columns")?;
    let mut affected: HashSet<String> = HashSet::new();
    let mut models: Vec<Object<'py>> = Vec::new();
    for name in order.try_iter()? {
        let model: Object<'py> = by_name.as_any().get_item(name?)?;
        let opted: Object<'py> = model
            .getattr("config")?
            .getattr("values")?
            .call_method1("get", ("sql_analysis",))?;
        if !selected_keys.contains(model.getattr("key")?)? || opted.is(PyBool::new(py, false)) {
            continue;
        }
        let mut reads_changed: bool = false;
        for reference in model.getattr("references")?.try_iter()? {
            let reference: Object<'py> = reference?;
            let kind: String = reference.getattr("ref_kind")?.str()?.extract()?;
            let upstream: String = reference.getattr("ref_name")?.extract()?;
            if (kind == SOURCE_KIND && changed.contains(&upstream))
                || (kind == REF_KIND && affected.contains(&upstream))
            {
                reads_changed = true;
                break;
            }
        }
        if !reads_changed {
            continue;
        }
        let model_name: String = model.getattr("name")?.extract()?;
        affected.insert(model_name.clone());
        models.push(model.clone());
        let inputs: Bound<'py, PyDict> = model_inputs(&model, shapes)?;
        let nullability: Bound<'py, PyDict> = PyDict::new(py);
        for (table, shape) in inputs.iter() {
            let defaults: Object<'py> = PyDict::new(py)
                .into_any()
                .getattr("fromkeys")?
                .call1((shape, &unknown))?;
            nullability.set_item(table, defaults)?;
        }
        let query: Object<'py> = call(
            &query_class,
            &[
                ("sql", model.getattr("query_sql")?),
                ("mode", PyString::new(py, "reanalysis").into_any()),
                ("placeholders", placeholders(&model)?),
                ("references", model.getattr("references")?),
            ],
        )?;
        let analysis: Object<'py> = call(
            &infer,
            &[
                ("queries", PyTuple::new(py, [query])?.into_any()),
                ("profile", profile.clone()),
                ("column_types_by_table", inputs.clone().into_any()),
                ("column_nullability_by_table", nullability.into_any()),
            ],
        )?
        .get_item(0)?;
        let inferred: Object<'py> = analysis.getattr("columns")?;
        let mut all_inputs_closed: bool = true;
        for shape in inputs.values() {
            if !shape.is_truthy()? {
                all_inputs_closed = false;
                break;
            }
        }
        if inferred.is_truthy()?
            && (!analysis.getattr("has_star")?.is_truthy()? || all_inputs_closed)
        {
            let columns: Bound<'py, PyDict> = PyDict::new(py);
            for column in inferred.try_iter()? {
                let column: Object<'py> = column?;
                let column_type: Object<'py> = column.getattr("type")?;
                let column_type: Object<'py> = if column_type.is_truthy()? {
                    column_type
                } else {
                    PyString::new(py, UNKNOWN).into_any()
                };
                columns.set_item(column.getattr("name")?, column_type)?;
            }
            shapes.set_item(
                &model_name,
                published_shape(&model, &columns, &inputs, profile)?,
            )?;
        } else if shapes.contains(&model_name)? {
            shapes.del_item(&model_name)?;
        }
    }
    Ok(models)
}

/// Each rebound model's binding diagnostics, located in its authored file.
fn validated_diagnostics<'py>(
    project: &Object<'py>,
    models: &[Object<'py>],
    (shapes, catalog): (&Bound<'py, PyDict>, &Object<'py>),
    dialect: &Object<'py>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = project.py();
    let functions: Object<'py> = project.getattr("functions")?;
    let known_functions: Object<'py> = PyTuple::new(py, function_names(&functions)?)?.into_any();
    let known_types: Object<'py> =
        PyTuple::new(py, declared_types(&functions, shapes.as_any())?)?.into_any();
    let request_builder: Object<'py> = py
        .import(BINDING_REQUESTS_MODULE)?
        .getattr("get_complete_schema_binding_request")?;
    let ignores: Object<'py> = ignores_quoted_case(project, dialect)?;
    let mut requests: Vec<Object<'py>> = Vec::with_capacity(models.len());
    for model in models {
        let query_sql: Object<'py> = PyString::new(
            py,
            &analysis_cursor_sql(
                py,
                &model.getattr("query_sql")?.extract::<String>()?,
                &model
                    .getattr("config")?
                    .getattr("values")?
                    .call_method1("get", ("cursor_type",))?,
            )?,
        )
        .into_any();
        let request: Object<'py> = call(
            &request_builder,
            &[
                ("known_functions", known_functions.clone()),
                ("known_types", known_types.clone()),
                ("query_sql", query_sql),
                ("placeholders", placeholders(model)?),
                ("dialect", dialect.clone()),
                ("binding_schema", model_inputs(model, shapes)?.into_any()),
            ],
        )?;
        requests.push(replaced(
            &request,
            &[
                ("catalog", catalog.clone()),
                ("quoted_identifiers_ignore_case", ignores.clone()),
            ],
        )?);
    }
    let results: Object<'py> =
        schema_validations(py, PyTuple::new(py, &requests)?.as_any())?.into_any();
    let expansions: Bound<'py, PyDict> = PyDict::new(py);
    for item in project
        .getattr("sql_expansions")?
        .call_method0("items")?
        .try_iter()?
    {
        let (path, expansion): (Object<'py>, Object<'py>) = item?.extract()?;
        expansions.set_item(path.getattr("stem")?, expansion)?;
    }
    let skipped: Object<'py> = PyString::new(py, BINDING_UNKNOWN_TABLE_INTERNAL_CODE).into_any();
    let models_module = py.import(COMPILE_MODELS_MODULE)?;
    let types = py.import(COMPILE_TYPES_MODULE)?;
    let diagnostic_class: Object<'py> = models_module.getattr("CompilerDiagnostic")?;
    let severity_class: Object<'py> = types.getattr("DiagnosticSeverity")?;
    let phase: Object<'py> = types.getattr("DiagnosticPhase")?.getattr("COMPILE")?;
    let model_type: Object<'py> = types.getattr("CompiledResourceType")?.getattr("MODEL")?;
    let mut diagnostics: Vec<Object<'py>> = Vec::new();
    for ((model, request), result) in models.iter().zip(&requests).zip(results.try_iter()?) {
        let result: Object<'py> = result?;
        let expansion: Option<Object<'py>> = expansions.get_item(model.getattr("name")?)?;
        let mut mapper: Option<Object<'py>> = None;
        for diagnostic in result.getattr("diagnostics")?.try_iter()? {
            let diagnostic: Object<'py> = diagnostic?;
            if diagnostic.getattr("code")?.eq(&skipped)? {
                continue;
            }
            let built: Object<'py> = match mapper.take() {
                Some(built) => built,
                None => positions(model, &request.getattr("sql")?, expansion.as_ref())?,
            };
            let position: Object<'py> = built.getattr("position")?;
            mapper = Some(built);
            let (line, column): (Object<'py>, Object<'py>) = call(
                &position,
                &[
                    ("start", diagnostic.getattr("start")?),
                    ("line", diagnostic.getattr("line")?),
                    ("column", diagnostic.getattr("column")?),
                    ("message", diagnostic.getattr("message")?),
                ],
            )?
            .extract()?;
            diagnostics.push(call(
                &diagnostic_class,
                &[
                    ("phase", phase.clone()),
                    (
                        "severity",
                        severity_class.call1((diagnostic.getattr("severity")?,))?,
                    ),
                    ("code", diagnostic.getattr("code")?),
                    ("message", diagnostic.getattr("message")?),
                    ("resource_type", model_type.clone()),
                    ("resource_name", model.getattr("name")?),
                    ("path", model.getattr("relative_path")?),
                    ("line", line),
                    ("column", column),
                ],
            )?);
        }
    }
    PyTuple::new(py, diagnostics)
}

/// The native position mapper from cleaned binding SQL back to the authored model file.
fn positions<'py>(
    model: &Object<'py>,
    cleaned: &Object<'py>,
    expansion: Option<&Object<'py>>,
) -> PyResult<Object<'py>> {
    let py: Python<'py> = model.py();
    let authored_query: Object<'py> = model.getattr("authored_query_sql")?;
    let mut passes: Vec<Object<'py>> = Vec::new();
    let expanded: Object<'py> = match expansion {
        None => authored_query.clone(),
        Some(expansion) => {
            for spans in expansion.getattr("passes")?.try_iter()? {
                let mut rows: Vec<Object<'py>> = Vec::new();
                for span in spans?.try_iter()? {
                    let span: Object<'py> = span?;
                    let fields: Vec<Object<'py>> =
                        ["source_start", "source_end", "output_start", "output_end"]
                            .into_iter()
                            .map(|name| span.getattr(name))
                            .collect::<PyResult<_>>()?;
                    rows.push(PyTuple::new(py, fields)?.into_any());
                }
                passes.push(PyTuple::new(py, rows)?.into_any());
            }
            expansion.getattr("expanded_sql")?
        }
    };
    let request: Bound<'py, PyDict> = PyDict::new(py);
    request.set_item("authored", model.getattr("authored_sql")?)?;
    request.set_item("query", authored_query)?;
    request.set_item("expanded", expanded)?;
    request.set_item("cleaned", cleaned)?;
    request.set_item("passes", passes)?;
    py.import(NATIVE_MODULE)?
        .getattr("BindingPositions")?
        .call1((request,))
}

/// Whether inspected columns differ from the known shape; untyped names match any type.
fn adds_physical_evidence(
    physical: &[(String, Option<String>)],
    known: Option<&Object<'_>>,
) -> PyResult<bool> {
    let Some(known) = known else {
        return Ok(true);
    };
    let known: Vec<(String, String)> = known
        .call_method0("items")?
        .try_iter()?
        .map(|item| item?.extract())
        .collect::<PyResult<_>>()?;
    let physical_names: HashSet<&str> = physical.iter().map(|(name, _)| name.as_str()).collect();
    let known_names: HashSet<&str> = known.iter().map(|(name, _)| name.as_str()).collect();
    if physical_names != known_names {
        return Ok(true);
    }
    for (name, physical_type) in physical {
        let Some(physical_type) = physical_type.as_deref() else {
            continue;
        };
        if physical_type.is_empty() {
            continue;
        }
        let known_type: Option<&String> = known
            .iter()
            .rev()
            .find(|(known_name, _)| known_name == name)
            .map(|(_, known_type)| known_type);
        if known_type.is_some_and(|known_type| known_type != physical_type) {
            return Ok(true);
        }
    }
    Ok(false)
}

/// `{str(key): str(value)}` of a dict `placeholders` config, else None.
fn placeholders<'py>(model: &Object<'py>) -> PyResult<Object<'py>> {
    let py: Python<'py> = model.py();
    let values: Object<'py> = model
        .getattr("config")?
        .getattr("values")?
        .call_method1("get", ("placeholders",))?;
    if !values.is_instance_of::<PyDict>() {
        return Ok(py.None().into_bound(py));
    }
    let placeholders: Bound<'py, PyDict> = PyDict::new(py);
    for item in values.call_method0("items")?.try_iter()? {
        let (key, value): (Object<'py>, Object<'py>) = item?.extract()?;
        placeholders.set_item(key.str()?, value.str()?)?;
    }
    Ok(placeholders.into_any())
}

fn ignores_quoted_case<'py>(project: &Object<'py>, dialect: &Object<'py>) -> PyResult<Object<'py>> {
    let ignores: bool =
        binding_catalog::ignores_quoted_case(&project.getattr("effective_connection")?, dialect)?;
    Ok(PyBool::new(project.py(), ignores).to_owned().into_any())
}

fn replaced<'py>(value: &Object<'py>, pairs: &[(&str, Object<'py>)]) -> PyResult<Object<'py>> {
    let py: Python<'py> = value.py();
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    for (name, item) in pairs {
        arguments.set_item(*name, item)?;
    }
    py.import(DATACLASSES_MODULE)?
        .getattr("replace")?
        .call((value,), Some(&arguments))
}

fn call<'py>(callable: &Object<'py>, pairs: &[(&str, Object<'py>)]) -> PyResult<Object<'py>> {
    let arguments: Bound<'py, PyDict> = PyDict::new(callable.py());
    for (name, value) in pairs {
        arguments.set_item(*name, value)?;
    }
    callable.call((), Some(&arguments))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(source_binding_diagnostics, module)?)
}

//! Closed relation shapes of a compiled project, as binding and semantic checks read them.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::analysis::binding_catalog::{
    BindingCatalog, CASE_SENSITIVE_BINDING_DIALECTS,
};
use crate::bindings::_helpers::boundary::keyword_request::Request;

const ADAPTER_MODELS_MODULE: &str = "sqlbuild.adapter.contract.models";
const PLANNER_TYPES_MODULE: &str = "sqlbuild.compiler.planner.types";
const NATIVE_MODULE: &str = "sqlbuild._native";
const DATACLASSES_MODULE: &str = "dataclasses";
const UNKNOWN: &str = "UNKNOWN";
const GENERIC_DIALECT: &str = "generic";
const VALID_FROM_DEFAULT: &str = "valid_from";
const VALID_TO_DEFAULT: &str = "valid_to";
const TABLE_FUNCTION_PREFIX: &str = "__sqlbuild_table_function_";
const UDF_KIND: &str = "udf";
const TABLE_FUNCTION_KIND: &str = "table_fn";

/// The relation names `(kind, name, package, count)` reference rows bind, UDFs excluded.
pub(crate) fn relation_row_names<'py>(rows: &Bound<'py, PyAny>) -> PyResult<Vec<String>> {
    let mut names: Vec<String> = Vec::new();
    for row in rows.try_iter()? {
        let row: Bound<'py, PyAny> = row?;
        let kind: String = row.get_item(0)?.str()?.extract()?;
        let name: String = row.get_item(1)?.extract()?;
        if kind == UDF_KIND {
            continue;
        }
        let name: String = if kind == TABLE_FUNCTION_KIND {
            format!("{TABLE_FUNCTION_PREFIX}{name}")
        } else {
            name
        };
        if !names.contains(&name) {
            names.push(name);
        }
    }
    Ok(names)
}

/// `{name: shapes.get(name, {})}` for each relation a model's reference rows bind.
pub(crate) fn model_inputs<'py>(
    model: &Bound<'py, PyAny>,
    shapes: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = model.py();
    let inputs: Bound<'py, PyDict> = PyDict::new(py);
    for name in relation_row_names(&model.getattr("reference_rows")?)? {
        let shape: Bound<'py, PyAny> = match shapes.get_item(&name)? {
            Some(shape) => shape,
            None => PyDict::new(py).into_any(),
        };
        inputs.set_item(name, shape)?;
    }
    Ok(inputs)
}

/// A model relation's shape, with snapshot validity columns.
pub(crate) fn published_shape<'py>(
    model: &Bound<'py, PyAny>,
    columns: &Bound<'py, PyDict>,
    inputs: &Bound<'py, PyDict>,
    profile: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = model.py();
    let shape: Bound<'py, PyDict> = binding_shape(model, columns, inputs, profile)?;
    let values: Bound<'py, PyAny> = model.getattr("config")?.getattr("values")?;
    let snapshot: Bound<'py, PyAny> = py
        .import(PLANNER_TYPES_MODULE)?
        .getattr("MaterializationType")?
        .getattr("SNAPSHOT")?;
    if values
        .call_method1("get", ("materialized",))?
        .eq(snapshot)?
    {
        for (key, default) in [
            ("valid_from_column", VALID_FROM_DEFAULT),
            ("valid_to_column", VALID_TO_DEFAULT),
        ] {
            let name: Bound<'py, PyAny> = values.call_method1("get", (key,))?;
            let name: Bound<'py, PyAny> = if name.is_truthy()? {
                name
            } else {
                PyString::new(py, default).into_any()
            };
            shape.set_item(name.str()?, UNKNOWN)?;
        }
    }
    Ok(shape)
}

/// Inferred columns, re-quoted from authored SQL where the dialect keeps quoted case.
fn binding_shape<'py>(
    model: &Bound<'py, PyAny>,
    columns: &Bound<'py, PyDict>,
    inputs: &Bound<'py, PyDict>,
    profile: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = model.py();
    let dialect: Bound<'py, PyAny> = profile.getattr("sql_analysis_dialect")?;
    let sensitive: bool = !dialect.is_none()
        && CASE_SENSITIVE_BINDING_DIALECTS.contains(&dialect.extract::<String>()?.as_str());
    if profile
        .getattr("quoted_identifiers_ignore_case")?
        .is_truthy()?
        || !sensitive
    {
        return Ok(columns.clone());
    }
    let mut catalog: Bound<'py, PyAny> = profile.getattr("binding_catalog")?;
    if !catalog.is_truthy()? {
        let created: BindingCatalog = BindingCatalog::create(
            py,
            (
                or_generic(&dialect)?.extract()?,
                false,
                profile.getattr("semantic_known_functions")?.extract()?,
                profile.getattr("semantic_known_types")?.extract()?,
            ),
            inputs.as_any(),
        )?;
        catalog = Bound::new(py, created)?.into_any();
    }
    let request: Bound<'py, PyDict> = PyDict::new(py);
    request.set_item("sql", model.getattr("query_sql")?)?;
    request.set_item("dialect", or_generic(&dialect)?)?;
    request.set_item("stubs", PyDict::new(py))?;
    request.set_item("placeholders", PyDict::new(py))?;
    let sql: Bound<'py, PyAny> = py
        .import(NATIVE_MODULE)?
        .getattr("normalize_analysis_sql")?
        .call1((request,))?;
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item("sql", sql)?;
    arguments.set_item("columns", columns)?;
    arguments.set_item("inputs", inputs)?;
    Ok(catalog
        .getattr("inferred_schema")?
        .call((), Some(&arguments))?
        .downcast_into::<PyDict>()?)
}

fn or_generic<'py>(dialect: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    if dialect.is_truthy()? {
        return Ok(dialect.clone());
    }
    Ok(PyString::new(dialect.py(), GENERIC_DIALECT).into_any())
}

/// `{name: type or "UNKNOWN"}` over `(name, type, ...)` rows.
fn typed_columns<'py>(py: Python<'py>, rows: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let columns: Bound<'py, PyDict> = PyDict::new(py);
    for row in rows.try_iter()? {
        let row: Bound<'py, PyAny> = row?;
        columns.set_item(row.get_item(0)?, or_unknown(&row.get_item(1)?)?)?;
    }
    Ok(columns)
}

fn or_unknown<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    if value.is_truthy()? {
        return Ok(value.clone());
    }
    Ok(PyString::new(value.py(), UNKNOWN).into_any())
}

/// `{column.name: column.type or "UNKNOWN"}`.
fn declared_columns<'py>(
    py: Python<'py>,
    columns: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let shape: Bound<'py, PyDict> = PyDict::new(py);
    for column in columns.try_iter()? {
        let column: Bound<'py, PyAny> = column?;
        shape.set_item(
            column.getattr("name")?,
            or_unknown(&column.getattr("type")?)?,
        )?;
    }
    Ok(shape)
}

/// The profile shapes are read under, bound to the project's catalog.
pub(crate) fn project_profile<'py>(
    project: &Bound<'py, PyAny>,
    profile: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    let profile: Bound<'py, PyAny> = match profile {
        Some(profile) if profile.is_truthy()? => profile,
        _ => {
            let arguments: Bound<'py, PyDict> = PyDict::new(py);
            arguments.set_item(
                "sql_analysis_dialect",
                project.getattr("sql_analysis_dialect")?,
            )?;
            py.import(ADAPTER_MODELS_MODULE)?
                .getattr("ExpressionInferenceProfile")?
                .call((), Some(&arguments))?
        }
    };
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item("binding_catalog", project.getattr("binding_catalog")?)?;
    py.import(DATACLASSES_MODULE)?
        .getattr("replace")?
        .call((profile,), Some(&arguments))
}

/// Closed shapes by relation name; absence means open, never an empty physical table.
pub(crate) fn project_shapes<'py>(
    project: &Bound<'py, PyAny>,
    profile: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = project.py();
    let profile: Bound<'py, PyAny> = project_profile(project, profile)?;
    let shapes: Bound<'py, PyDict> = PyDict::new(py);
    for seed in project.getattr("seeds")?.try_iter()? {
        let seed: Bound<'py, PyAny> = seed?;
        shapes.set_item(
            seed.getattr("name")?,
            declared_columns(py, &seed.getattr("schema_entry")?.getattr("columns")?)?,
        )?;
    }
    for function in project.getattr("functions")?.try_iter()? {
        let function: Bound<'py, PyAny> = function?;
        let returns: Bound<'py, PyAny> = function.getattr("return_columns")?;
        if returns.is_truthy()? {
            let shape: Bound<'py, PyDict> = PyDict::new(py);
            for column in returns.try_iter()? {
                let column: Bound<'py, PyAny> = column?;
                shape.set_item(column.getattr("name")?, column.getattr("type")?)?;
            }
            let name: String = function.getattr("name")?.extract()?;
            shapes.set_item(format!("{TABLE_FUNCTION_PREFIX}{name}"), shape)?;
        }
    }
    let enforced: Bound<'py, PyAny> = py
        .import(PLANNER_TYPES_MODULE)?
        .getattr("ContractPolicy")?
        .getattr("ENFORCED")?;
    let mut expression_names: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut expressions: Vec<Bound<'py, PyAny>> = Vec::new();
    for source in project.getattr("sources")?.try_iter()? {
        let source: Bound<'py, PyAny> = source?;
        let entry: Bound<'py, PyAny> = source.getattr("source_entry")?;
        if entry.getattr("contract")?.eq(&enforced)? {
            shapes.set_item(
                source.getattr("name")?,
                declared_columns(py, &entry.getattr("columns")?)?,
            )?;
        } else {
            let expression: Bound<'py, PyAny> = entry.getattr("expression")?;
            if expression.is_truthy()? {
                expression_names.push(source.getattr("name")?);
                expressions.push(expression);
            }
        }
    }
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item("expressions", PyTuple::new(py, expressions)?)?;
    arguments.set_item("profile", &profile)?;
    let source_shapes: Bound<'py, PyAny> = py
        .import(NATIVE_MODULE)?
        .getattr("infer_native_expression_source_shapes")?
        .call((), Some(&arguments))?;
    for (name, shape) in expression_names.iter().zip(source_shapes.try_iter()?) {
        let shape: Bound<'py, PyAny> = shape?;
        if !shape.is_none() {
            shapes.set_item(name, shape)?;
        }
    }
    model_shapes(project, &profile, &enforced, &shapes)?;
    Ok(shapes)
}

/// Publish model shapes in dependency rounds until no pending model can close.
fn model_shapes<'py>(
    project: &Bound<'py, PyAny>,
    profile: &Bound<'py, PyAny>,
    enforced: &Bound<'py, PyAny>,
    shapes: &Bound<'py, PyDict>,
) -> PyResult<()> {
    let py: Python<'py> = project.py();
    let mut pending: Vec<Bound<'py, PyAny>> = project
        .getattr("models")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    while !pending.is_empty() {
        let mut remaining: Vec<Bound<'py, PyAny>> = Vec::new();
        for model in &pending {
            let declared: Bound<'py, PyAny> = model.getattr("schema_column_rows")?;
            let inferred: Bound<'py, PyAny> = model.getattr("inferred_rows")?;
            let rows: Bound<'py, PyAny> = model.getattr("reference_rows")?;
            let relations: Vec<String> = relation_row_names(&rows)?;
            let contract: Bound<'py, PyAny> = model
                .getattr("config")?
                .getattr("values")?
                .call_method1("get", ("contract",))?;
            if contract.eq(enforced)?
                && !declared.is_none()
                && !model.getattr("has_dynamic_columns")?.is_truthy()?
            {
                let unchecked: Bound<'py, PyAny> = model.getattr("unchecked_output_columns")?;
                let shape: Bound<'py, PyDict> = PyDict::new(py);
                for row in declared.try_iter()? {
                    let row: Bound<'py, PyAny> = row?;
                    let name: Bound<'py, PyAny> = row.get_item(0)?;
                    let column_type: Bound<'py, PyAny> = if unchecked.contains(&name)? {
                        PyString::new(py, UNKNOWN).into_any()
                    } else {
                        or_unknown(&row.get_item(1)?)?
                    };
                    shape.set_item(name, column_type)?;
                }
                shapes.set_item(model.getattr("name")?, shape)?;
                continue;
            }
            let closes: bool = inferred.is_truthy()?
                && (!model.getattr("fast_lineage_has_star")?.is_truthy()?
                    || (model.getattr("fast_lineage_star_resolved")?.is_truthy()?
                        && rows.is_truthy()?
                        && all_known(&relations, shapes)?));
            if closes {
                let inputs: Bound<'py, PyDict> = model_inputs(model, shapes)?;
                let columns: Bound<'py, PyDict> = typed_columns(py, &inferred)?;
                shapes.set_item(
                    model.getattr("name")?,
                    published_shape(model, &columns, &inputs, profile)?,
                )?;
            } else {
                remaining.push(model.clone());
            }
        }
        if remaining.len() == pending.len() {
            break;
        }
        pending = remaining;
    }
    Ok(())
}

fn all_known(names: &[String], shapes: &Bound<'_, PyDict>) -> PyResult<bool> {
    for name in names {
        if !shapes.contains(name)? {
            return Ok(false);
        }
    }
    Ok(true)
}

/// Closed relation shapes; `profile` defaults to the project's dialect.
#[pyfunction]
#[pyo3(signature = (**request))]
fn semantic_shapes<'py>(request: Option<&Bound<'py, PyDict>>) -> PyResult<Bound<'py, PyDict>> {
    let request = Request::new("semantic_shapes", request)?;
    project_shapes(&request.get("project")?, request.optional("profile")?)
}

/// The analysis names the references bind, UDFs excluded.
#[pyfunction]
fn binding_relation_names<'py>(
    references: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let py: Python<'py> = references.py();
    let mut rows: Vec<Bound<'py, PyAny>> = Vec::new();
    for reference in references.try_iter()? {
        let reference: Bound<'py, PyAny> = reference?;
        rows.push(
            PyTuple::new(
                py,
                [
                    reference.getattr("ref_kind")?.str()?.into_any(),
                    reference.getattr("ref_name")?,
                ],
            )?
            .into_any(),
        );
    }
    let names: Vec<String> = relation_row_names(&PyTuple::new(py, rows)?.into_any())?;
    PyFrozenSet::new(py, names)
}

/// A model relation's published shape: `published_model_shape(*, model, columns, inputs, profile)`.
#[pyfunction]
#[pyo3(signature = (**request))]
fn published_model_shape<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyDict>> {
    let request = Request::new("published_model_shape", request)?;
    published_shape(
        &request.get("model")?,
        request.get("columns")?.downcast()?,
        request.get("inputs")?.downcast()?,
        &request.get("profile")?,
    )
}

/// `{name: shapes.get(name, {})}` for each relation the model's reference rows bind.
#[pyfunction]
fn model_binding_inputs<'py>(
    model: &Bound<'py, PyAny>,
    shapes: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    model_inputs(model, shapes)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(semantic_shapes, module)?)?;
    module.add_function(wrap_pyfunction!(published_model_shape, module)?)?;
    module.add_function(wrap_pyfunction!(model_binding_inputs, module)?)?;
    module.add_function(wrap_pyfunction!(binding_relation_names, module)?)
}

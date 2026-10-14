//! Resolve authored migration origins at the adapter and inspection boundaries.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PySet, PySetMethods, PyTuple};
use pyo3::{PyErr, pyfunction, wrap_pyfunction};

pub(super) fn location<'py>(
    runtime: &Bound<'py, PyAny>,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let qualified = call_with(
        &runtime
            .getattr("adapter")?
            .getattr("render_qualified_name")?,
        fields,
    )?;
    let mut fields = fields.to_vec();
    fields.push(("qualified_name", qualified));
    call_with(
        &imported(
            runtime.py(),
            "sqlbuild.compiler.compile.models",
            "CompiledRelationLocation",
        )?,
        &fields,
    )
}

fn named<'py>(
    name: &Bound<'py, PyAny>,
    destination: &Bound<'py, PyAny>,
    runtime: &Bound<'py, PyAny>,
    state: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    for item in runtime.getattr("project")?.getattr("models")?.try_iter()? {
        let item = item?;
        if item.getattr("name")?.eq(name)? {
            return Ok(
                PyTuple::new(runtime.py(), [item.getattr("destination")?, name.clone()])?
                    .into_any(),
            );
        }
    }
    let fingerprint = call_with(
        &state.getattr("named_fingerprint")?,
        &[("model_name", name.clone())],
    )?;
    let fields = if !fingerprint.is_none() && !fingerprint.getattr("target_name")?.is_none() {
        [
            ("database", fingerprint.getattr("target_database")?),
            ("schema", fingerprint.getattr("target_schema")?),
            ("name", fingerprint.getattr("target_name")?),
        ]
    } else {
        [
            ("database", destination.getattr("database")?),
            ("schema", destination.getattr("schema")?),
            ("name", name.clone()),
        ]
    };
    Ok(PyTuple::new(runtime.py(), [location(runtime, &fields)?, name.clone()])?.into_any())
}

fn input_error(py: Python<'_>, message: String) -> PyResult<PyErr> {
    Ok(PyErr::from_value(
        imported(
            py,
            "sqlbuild.compiler.planner.exceptions",
            "PlannerInputError",
        )?
        .call1((message,))?,
    ))
}

#[pyfunction]
#[pyo3(signature = (*, runtime))]
fn migration_planning_database<'py>(runtime: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let project = runtime.getattr("project")?;
    let fallback = project.getattr("effective_target_database")?;
    for item in project.getattr("models")?.try_iter()? {
        let database = item?.getattr("destination")?.getattr("database")?;
        if !database.is_none() {
            return Ok(database);
        }
    }
    Ok(fallback)
}

#[pyfunction]
#[pyo3(signature = (*, runtime))]
fn migration_project_schemas<'py>(runtime: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let schemas = PySet::empty(runtime.py())?;
    for item in runtime.getattr("project")?.getattr("models")?.try_iter()? {
        let schema = item?.getattr("destination")?.getattr("schema")?;
        if !schema.is_none() {
            schemas.add(schema)?;
        }
    }
    Ok(schemas.into_any())
}

#[pyfunction]
#[pyo3(signature = (*, state, location))]
fn migration_require_same_database(
    state: &Bound<'_, PyAny>,
    location: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let database = location.getattr("database")?;
    if database.is_none() {
        return Ok(());
    }
    let inspected = state.getattr("database")?;
    if inspected.is_none()
        || database
            .call_method0("lower")?
            .eq(inspected.call_method0("lower")?)?
    {
        return Ok(());
    }
    let qualified = location.getattr("qualified_name")?;
    let label = if qualified.is_truthy()? {
        qualified
    } else {
        location.getattr("name")?
    };
    Err(input_error(
        state.py(),
        format!(
            "migration origin {label} is in database '{database}', but direct planning inspects '{inspected}'; cross-database migrations are not supported"
        ),
    )?)
}

#[pyfunction]
#[pyo3(signature = (*, request, runtime, state))]
fn migration_resolve_origin<'py>(
    request: &Bound<'py, PyAny>,
    runtime: &Bound<'py, PyAny>,
    state: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = runtime.py();
    let explicit = request.getattr("origin_location")?;
    if !explicit.is_none() {
        return Ok(PyTuple::new(py, [explicit, request.getattr("origin_model")?])?.into_any());
    }
    let raw = request.getattr("raw_origin")?;
    let raw = if raw.is_truthy()? {
        raw
    } else {
        super::column_objects::text(py, "")
    };
    let item = request.getattr("model")?;
    let destination = item.getattr("destination")?;
    let mut parts: Vec<Bound<'py, PyAny>> = Vec::new();
    for part in raw.call_method1("split", (".",))?.try_iter()? {
        parts.push(
            part?
                .call_method0("strip")?
                .call_method1("strip", ("\"`",))?,
        );
    }
    let maximum: usize = imported(
        py,
        "sqlbuild.compiler.planner.constants",
        "QUALIFIED_RELATION_MAX_PARTS",
    )?
    .extract()?;
    let mut invalid = parts.len() > maximum;
    for part in &parts {
        invalid |= !part.is_truthy()?;
    }
    if invalid {
        return Err(input_error(
            py,
            format!(
                "model '{}': migrate_from '{raw}' is not a model name or a qualified relation",
                item.getattr("name")?
            ),
        )?);
    }
    if parts.len() == 1 {
        return named(&parts[0], &destination, runtime, state);
    }
    let database = if parts.len() == maximum {
        parts[0].clone()
    } else {
        destination.getattr("database")?
    };
    let origin = location(
        runtime,
        &[
            ("database", database),
            ("schema", parts[parts.len() - 2].clone()),
            ("name", parts[parts.len() - 1].clone()),
        ],
    )?;
    Ok(PyTuple::new(py, [origin, py.None().into_bound(py)])?.into_any())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(migration_planning_database, module)?)?;
    module.add_function(wrap_pyfunction!(migration_project_schemas, module)?)?;
    module.add_function(wrap_pyfunction!(migration_require_same_database, module)?)?;
    module.add_function(wrap_pyfunction!(migration_resolve_origin, module)?)
}

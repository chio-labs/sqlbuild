//! Cursor input relations and authored cursor input column checks of model plan entries.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyBool, PyDict, PyFrozenSet, PyString, PyTuple};

use sqlbuild_analysis::planner_strategy::main::cursor_input_column::cursor_input_column_failure;
use sqlbuild_analysis::planner_strategy::models::{CursorInputColumnCheck, CursorInputColumnOwner};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_attachment::cursor_roles::resolve_cursor_input_roles;
use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::cursor::scalars::parse_value;
use crate::bindings::_helpers::model_config::config_values::{config_cursor_bound, config_str};
use crate::bindings::_helpers::planner_identity::metadata::or_empty;
use crate::bindings::_helpers::planner_strategy::constants::{
    ENFORCED_CONTRACT, INCREMENTAL_MATERIALIZATION, MODEL_REFERENCE, SEED_REFERENCE,
    SOURCE_REFERENCE, TIMESTAMP_CURSOR,
};
use crate::bindings::_helpers::planner_strategy::lineage::resolve_lineage_reference;
use crate::bindings::_helpers::planner_strategy::values::{input_error, text};
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::references::source_relations::render_source_relation;

/// A model's authored config values.
pub(crate) fn model_values<'py>(model: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    model.getattr("config")?.getattr("values")
}

/// Whether a model is incremental with a cursor column.
fn incremental_cursor_flag(
    model: &Bound<'_, PyAny>,
    cursor_column: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    let materialized: Option<Bound<'_, PyAny>> = config_str(&model_values(model)?, "materialized")?;
    Ok(!cursor_column.is_none()
        && match materialized {
            Some(materialized) => materialized.eq(INCREMENTAL_MATERIALIZATION)?,
            None => false,
        })
}

/// The names of a sequence of objects with a `name`.
fn names(items: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    items
        .try_iter()?
        .map(|item| text(&item?.getattr("name")?))
        .collect()
}

/// Raise the planner error of a cursor input column its input does not expose.
fn check_column(check: CursorInputColumnCheck, py: Python<'_>) -> PyResult<()> {
    match cursor_input_column_failure(&check) {
        Some((message, code)) => Err(input_error(py, ErrorId::PlannerInput, &message, Some(code))),
        None => Ok(()),
    }
}

/// Validate authored cursor input columns against contracts, then source warehouse metadata.
#[pyfunction(name = "validate_source_cursor_input_columns")]
#[pyo3(signature = (**request))]
pub(crate) fn reject_unexposed_cursor_input_columns<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<()> {
    let request = Request::new("validate_source_cursor_input_columns", request)?;
    let py: Python<'py> = request.py();
    let model: Bound<'py, PyAny> = request.get("model")?;
    if !incremental_cursor_flag(&model, &request.get("cursor_column")?)? {
        return Ok(());
    }
    let roles: Bound<'py, PyAny> = resolve_cursor_input_roles(&model)?;
    let models_by_name = or_empty(request.optional("models_by_name")?, py)?;
    let functions_by_name = or_empty(request.optional("functions_by_name")?, py)?;
    let source_map = or_empty(request.optional("source_map")?, py)?;
    let warehouse_columns: Bound<'py, PyAny> = request.get("source_warehouse_columns")?;
    let model_name: String = text(&model.getattr("name")?)?;
    for role in ["filter_inputs", "watermark_inputs"] {
        for item in roles.getattr(role)?.call_method0("items")?.try_iter()? {
            let (input_name, column): (String, String) = item?.extract()?;
            let reference: Bound<'py, PyAny> = resolve_lineage_reference(
                &model,
                &input_name,
                models_by_name.clone(),
                functions_by_name.clone(),
            )?;
            let kind: String = text(&reference.getattr("ref_kind")?)?;
            let name: String = text(&reference.getattr("ref_name")?)?;
            let check = |owner, known_columns| CursorInputColumnCheck {
                model_name: model_name.clone(),
                owner,
                input_name: name.clone(),
                column: column.clone(),
                known_columns,
            };
            if kind == MODEL_REFERENCE {
                let upstream: Bound<'py, PyAny> = models_by_name.call_method1("get", (&name,))?;
                if upstream.is_none()
                    || !model_values(&upstream)?
                        .call_method1("get", ("contract",))?
                        .eq(ENFORCED_CONTRACT)?
                {
                    continue;
                }
                let entry: Bound<'py, PyAny> = upstream.getattr("schema_entry")?;
                let declared: Vec<String> = if entry.is_none() {
                    Vec::new()
                } else {
                    names(&entry.getattr("columns")?)?
                };
                check_column(check(CursorInputColumnOwner::ModelContract, declared), py)?;
                continue;
            }
            if kind != SOURCE_REFERENCE {
                continue;
            }
            let source: Bound<'py, PyAny> = source_map.call_method1("get", (&name,))?;
            if !source.is_none() && source.getattr("contract")?.eq(ENFORCED_CONTRACT)? {
                let declared: Vec<String> = names(&source.getattr("columns")?)?;
                check_column(check(CursorInputColumnOwner::SourceContract, declared), py)?;
                continue;
            }
            let known: Bound<'py, PyAny> = warehouse_columns.call_method1("get", (&name,))?;
            if known.is_none() {
                continue;
            }
            check_column(
                check(CursorInputColumnOwner::SourceWarehouse, names(&known)?),
                py,
            )?;
        }
    }
    Ok(())
}

/// The qualified relation one cursor input reference reads, when it resolves.
fn input_relation<'py>(
    request: &Request<'_, 'py>,
    (kind, name): (&str, &str),
) -> PyResult<Option<String>> {
    let py: Python<'py> = request.py();
    let location: Bound<'py, PyAny> = match kind {
        MODEL_REFERENCE => {
            let model: Bound<'py, PyAny> = request
                .get("model_locations")?
                .call_method1("get", (name,))?;
            if model.is_none() {
                request
                    .get("seed_locations")?
                    .call_method1("get", (name,))?
            } else {
                model
            }
        }
        SEED_REFERENCE => request
            .get("seed_locations")?
            .call_method1("get", (name,))?,
        SOURCE_REFERENCE => {
            let source: Bound<'py, PyAny> =
                request.get("source_map")?.call_method1("get", (name,))?;
            if source.is_none() {
                return Ok(None);
            }
            let adapter: Bound<'py, PyAny> = request.get("adapter")?;
            return render_source_relation(&source, Some(&adapter)).map(Some);
        }
        _ => py.None().into_bound(py),
    };
    if location.is_none() {
        return Ok(None);
    }
    location.getattr("qualified_name")?.extract()
}

/// The resource kind a resolved cursor input reference reads.
fn input_kind<'py>(
    py: Python<'py>,
    (kind, model_backed): (&str, bool),
) -> PyResult<Bound<'py, PyAny>> {
    let value: &str = match kind {
        MODEL_REFERENCE if model_backed => "model",
        MODEL_REFERENCE | SEED_REFERENCE => "seed",
        SOURCE_REFERENCE => "source",
        _ => return Ok(py.None().into_bound(py)),
    };
    registry::class(py, RecordId::GraphResourceKind)?.call1((value,))
}

/// A producer model's terminal cursor bound parsed with the consumer's cursor type.
fn terminal_bound<'py>(
    producer: Option<&Bound<'py, PyAny>>,
    (key, cursor_type): (&str, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = cursor_type.py();
    let Some(producer) = producer else {
        return Ok(py.None().into_bound(py));
    };
    match config_cursor_bound(&model_values(producer)?, key)? {
        Some(raw) => parse_value(&raw, cursor_type),
        None => Ok(py.None().into_bound(py)),
    }
}

/// Cursor-bearing input relations of an incremental model, for runtime range discovery.
#[pyfunction]
#[pyo3(signature = (**request))]
pub(crate) fn build_cursor_input_relations<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let request = Request::new("build_cursor_input_relations", request)?;
    let py: Python<'py> = request.py();
    let model: Bound<'py, PyAny> = request.get("model")?;
    if !incremental_cursor_flag(&model, &request.get("cursor_column")?)? {
        return Ok(PyTuple::empty(py));
    }
    let models_by_name: Bound<'py, PyAny> = request.get("models_by_name")?;
    let functions_by_name = or_empty(request.optional("functions_by_name")?, py)?;
    let model_locations: Bound<'py, PyAny> = request.get("model_locations")?;
    let producers: Bound<'py, PyAny> = request.get("runtime_cursor_producer_names")?;
    let cursor_type: Bound<'py, PyAny> = match config_str(&model_values(&model)?, "cursor_type")? {
        Some(cursor_type) if cursor_type.is_truthy()? => cursor_type,
        _ => PyString::new(py, TIMESTAMP_CURSOR).into_any(),
    };
    let class: Bound<'py, PyAny> = registry::class(py, RecordId::CursorInputRelation)?;
    let mut relations: Vec<Bound<'py, PyAny>> = Vec::new();
    let watermarks: Bound<'py, PyAny> =
        resolve_cursor_input_roles(&model)?.getattr("watermark_inputs")?;
    for item in watermarks.call_method0("items")?.try_iter()? {
        let (input_name, column): (String, Bound<'py, PyAny>) = item?.extract()?;
        let reference: Bound<'py, PyAny> = resolve_lineage_reference(
            &model,
            &input_name,
            models_by_name.clone(),
            functions_by_name.clone(),
        )?;
        let kind: String = text(&reference.getattr("ref_kind")?)?;
        let name: Bound<'py, PyAny> = reference.getattr("ref_name")?;
        let name_text: String = text(&name)?;
        let Some(relation) = input_relation(&request, (&kind, &name_text))? else {
            continue;
        };
        let producer: Option<Bound<'py, PyAny>> = if kind == MODEL_REFERENCE {
            Some(models_by_name.call_method1("get", (&name,))?).filter(|model| !model.is_none())
        } else {
            None
        };
        let grain: Bound<'py, PyAny> = match &producer {
            Some(producer) => config_str(&model_values(producer)?, "cursor_grain")?
                .unwrap_or_else(|| py.None().into_bound(py)),
            None => py.None().into_bound(py),
        };
        let model_backed: bool = kind == MODEL_REFERENCE && model_locations.contains(&name)?;
        relations.push(call_with(
            &class,
            &[
                ("relation", PyString::new(py, &relation).into_any()),
                ("cursor_column", column),
                ("cursor_grain", grain),
                (
                    "is_model_backed",
                    PyBool::new(py, model_backed).to_owned().into_any(),
                ),
                (
                    "is_runtime_produced",
                    PyBool::new(py, producers.contains(&name)?)
                        .to_owned()
                        .into_any(),
                ),
                ("input_name", name.clone()),
                ("input_kind", input_kind(py, (&kind, model_backed))?),
                (
                    "terminal_cursor_start",
                    terminal_bound(producer.as_ref(), ("cursor_start", &cursor_type))?,
                ),
                (
                    "terminal_cursor_end",
                    terminal_bound(producer.as_ref(), ("cursor_end", &cursor_type))?,
                ),
            ],
        )?);
    }
    PyTuple::new(py, relations)
}

/// Selected models and seeds, and selected sources with loaders, whose relations this invocation produces.
#[pyfunction]
#[pyo3(signature = (*, scope, source_map))]
pub(crate) fn runtime_cursor_producer_names<'py>(
    scope: &Bound<'py, PyAny>,
    source_map: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let py: Python<'py> = scope.py();
    let mut names: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in scope.getattr("selected_keys")?.try_iter()? {
        let key: Bound<'py, PyAny> = key?;
        let name: Bound<'py, PyAny> = key.getattr("name")?;
        match text(&key.getattr("resource_type")?)?.as_str() {
            "model" | "seed" => names.push(name),
            "source" => {
                let source: Bound<'py, PyAny> = source_map.call_method1("get", (&name,))?;
                if !source.is_none() && !source.getattr("loader")?.is_none() {
                    names.push(name);
                }
            }
            _ => {}
        }
    }
    PyFrozenSet::new(py, names)
}

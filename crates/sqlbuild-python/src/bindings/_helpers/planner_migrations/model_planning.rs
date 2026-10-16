//! Model migration orchestration over Python-owned live inspection.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_migrations::column_objects::{config, native, replace};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{
    PyBool, PyDict, PyDictMethods, PyFrozenSet, PySet, PySetMethods, PyString, PyTuple,
};
use pyo3::{pyfunction, wrap_pyfunction};

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

fn declared<'py>(item: &Bound<'py, PyAny>) -> PyResult<Option<Bound<'py, PyAny>>> {
    let py = item.py();
    let values = item.getattr("config")?.getattr("values")?;
    let origin = values.call_method1("get", ("migrate_from",))?;
    if !origin.is_instance_of::<PyString>() {
        return Ok(None);
    }
    let materialization = config(item, "materialized")?;
    Ok(Some(native(
        py,
        "ModelMigrationRequest",
        &[
            ("model", item.clone()),
            (
                "discovery",
                imported(py, NATIVE_RECORDS_MODULE, "MigrationDiscovery")?.getattr("MANUAL")?,
            ),
            ("raw_origin", origin.call_method0("strip")?),
            (
                "force",
                PyBool::new(
                    py,
                    values
                        .call_method1("get", ("migrate_force",))?
                        .is(PyBool::new(py, true)),
                )
                .to_owned()
                .into_any(),
            ),
            (
                "identity_only",
                PyBool::new(
                    py,
                    materialization.eq("table")? || materialization.eq("view")?,
                )
                .to_owned()
                .into_any(),
            ),
        ],
    )?))
}

#[pyfunction]
#[pyo3(signature = (*, scope))]
fn manual_migration_requests<'py>(scope: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let mut requests: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in scope.getattr("execution_order")?.try_iter()? {
        let key = key?;
        if !scope.getattr("selected_keys")?.contains(&key)?
            || !key.getattr("resource_type")?.eq("model")?
        {
            continue;
        }
        let item = scope
            .getattr("models_by_name")?
            .call_method1("get", (key.getattr("name")?,))?;
        if !item.is_none()
            && let Some(request) = declared(&item)?
        {
            requests.push(request);
        }
    }
    Ok(PyTuple::new(scope.py(), requests)?.into_any())
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn decide_model_migration<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    super::model_entries::decide(&KeywordArguments::read(
        py,
        "decide_model_migration",
        options,
        (
            &[
                "runtime",
                "request",
                "origin",
                "origin_model",
                "snapshot",
                "state",
                "snapshots_config",
            ],
            &[],
        ),
    )?)
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn plan_model_migrations<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "plan_model_migrations",
        options,
        (
            &[
                "runtime",
                "scope",
                "snapshot",
                "overrides",
                "deferral",
                "fingerprints",
            ],
            &[],
        ),
    )?;
    let runtime = args.value("runtime")?;
    let snapshot = args.value("snapshot")?;
    let schemas = call_with(
        &imported(py, "sqlbuild._native", "migration_project_schemas")?,
        &[("runtime", runtime.clone())],
    )?;
    let state = call_with(
        &imported(py, "sqlbuild._native", "MigrationStateInspection")?,
        &[
            ("adapter", runtime.getattr("adapter")?),
            ("connection", runtime.getattr("connection")?),
            (
                "database",
                call_with(
                    &imported(py, "sqlbuild._native", "migration_planning_database")?,
                    &[("runtime", runtime.clone())],
                )?,
            ),
            ("known_fingerprints", snapshot.getattr("fingerprints")?),
        ],
    )?;
    let discovery = discover(&args, &state, &schemas)?;
    finish(&args, &state, &schemas, &discovery)
}

fn discover<'py>(
    args: &KeywordArguments<'py>,
    state: &Bound<'py, PyAny>,
    schemas: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let runtime = args.value("runtime")?;
    let py = runtime.py();
    let scope = args.value("scope")?;
    let snapshot = args.value("snapshot")?;
    let mut declared_requests: Vec<Bound<'py, PyAny>> = Vec::new();
    for item in runtime.getattr("project")?.getattr("models")?.try_iter()? {
        if let Some(request) = declared(&item?)? {
            declared_requests.push(request);
        }
    }
    if !declared_requests.is_empty() {
        call_with(
            &state.getattr("inspect_schemas")?,
            &[("schemas", schemas.clone())],
        )?;
    }
    let mut declarations: Vec<Bound<'py, PyAny>> = Vec::new();
    for request in declared_requests {
        let resolved = call_with(
            &imported(py, "sqlbuild._native", "migration_resolve_origin")?,
            &[
                ("request", request.clone()),
                ("runtime", runtime.clone()),
                ("state", state.clone()),
            ],
        )?;
        declarations.push(native(
            py,
            "ModelMigrationDeclaration",
            &[
                ("model_name", request.getattr("model")?.getattr("name")?),
                ("origin_location", resolved.get_item(0)?),
                ("origin_model", resolved.get_item(1)?),
            ],
        )?);
    }
    call_with(
        &imported(py, "sqlbuild._native", "discover_model_migrations")?,
        &[
            ("runtime", runtime.clone()),
            ("scope", scope.clone()),
            ("snapshot", snapshot.clone()),
            ("manual_requests", manual_migration_requests(&scope)?),
            ("declarations", PyTuple::new(py, declarations)?.into_any()),
            ("state", state.clone()),
            ("project_schemas", schemas.clone()),
            ("fingerprints", args.value("fingerprints")?),
        ],
    )
}

fn finish<'py>(
    args: &KeywordArguments<'py>,
    state: &Bound<'py, PyAny>,
    schemas: &Bound<'py, PyAny>,
    discovery: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let runtime = args.value("runtime")?;
    let py = runtime.py();
    let scope = args.value("scope")?;
    let snapshot = args.value("snapshot")?;
    let mut resolved: Vec<(Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>)> = Vec::new();
    for request in discovery.getattr("requests")?.try_iter()? {
        let request = request?;
        let origin = call_with(
            &imported(py, "sqlbuild._native", "migration_resolve_origin")?,
            &[
                ("request", request.clone()),
                ("runtime", runtime.clone()),
                ("state", state.clone()),
            ],
        )?;
        resolved.push((request, origin.get_item(0)?, origin.get_item(1)?));
    }
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    let handovers = PyDict::new(py);
    if !resolved.is_empty() {
        let origin_schemas = PySet::empty(py)?;
        let mut origins: Vec<Bound<'py, PyAny>> = Vec::new();
        for (_, origin, _) in &resolved {
            call_with(
                &imported(py, "sqlbuild._native", "migration_require_same_database")?,
                &[("state", state.clone()), ("location", origin.clone())],
            )?;
            let schema = origin.getattr("schema")?;
            if !schema.is_none() {
                origin_schemas.add(schema)?;
            }
            origins.push(origin.clone());
        }
        call_with(
            &state.getattr("inspect_schemas")?,
            &[("schemas", origin_schemas.into_any())],
        )?;
        call_with(
            &state.getattr("inspect_relations")?,
            &[("locations", PyTuple::new(py, origins)?.into_any())],
        )?;
        let project_config = runtime.getattr("project_config")?;
        let snapshots_config = if project_config.is_none() {
            imported(py, "sqlbuild._native", "SnapshotsConfig")?.call0()?
        } else {
            project_config.getattr("snapshots")?
        };
        let policy = call_with(
            &imported(py, "sqlbuild._native", "migration_missing_origin_policy")?,
            &[("runtime", runtime.clone())],
        )?;
        for (request, origin, origin_model) in resolved {
            let item = request.getattr("model")?;
            let name = item.getattr("name")?;
            let decided = native(
                py,
                "decide_model_migration",
                &[
                    ("runtime", runtime.clone()),
                    ("request", request),
                    ("origin", origin),
                    ("origin_model", origin_model),
                    ("snapshot", snapshot.clone()),
                    ("state", state.clone()),
                    ("snapshots_config", snapshots_config.clone()),
                ],
            )?;
            entries.push(replace(
                &decided.get_item(0)?,
                &[("missing_origin_policy", policy.clone())],
            )?);
            if decided.get_item(2)?.is_truthy()? {
                let destinations = discovery
                    .getattr("destination_fingerprints")?
                    .call_method1("get", (&name, PyTuple::empty(py)))?;
                handovers.set_item(
                    name,
                    super::model_handover::equivalent(
                        &item,
                        decided.get_item(1)?,
                        &destinations,
                        &snapshot.getattr("column_dialect")?,
                    )?,
                )?;
            }
        }
    }
    let planned = PyDict::new(py);
    let mut renamed: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    for warning in discovery.getattr("warnings")?.try_iter()? {
        warnings.push(warning?);
    }
    for entry in &entries {
        let name = entry.getattr("model_name")?;
        if let Some(handover) = handovers.get_item(&name)? {
            if !handover.is_none() && entry.getattr("decision")?.eq("renamed")? {
                renamed.push(name.clone());
            }
            let origin_model = entry.getattr("origin_model")?;
            if !origin_model.is_none() {
                planned.set_item(&name, origin_model)?;
            }
        }
        if let Some(warning) = super::model_warnings::entry_warning(entry)? {
            warnings.push(warning);
        }
    }
    let overlaid = if entries.is_empty() {
        snapshot.clone()
    } else {
        super::model_overlay::overlay(args, state, &entries, &handovers)?
    };
    let reference_renames = native(
        py,
        "plan_reference_renames",
        &[
            ("runtime", runtime),
            ("scope", scope),
            ("snapshot", snapshot),
            ("state", state.clone()),
            ("schemas", schemas.clone()),
            ("planned", planned.into_any()),
        ],
    )?;
    let mut fields = vec![("reference_renames", reference_renames)];
    if !entries.is_empty() {
        fields.push(("renamed_models", PyFrozenSet::new(py, renamed)?.into_any()));
    }
    native(
        py,
        "ModelMigrationPlanning",
        &[
            ("snapshot", replace(&overlaid, &fields)?),
            ("entries", PyTuple::new(py, entries)?.into_any()),
            ("warnings", PyTuple::new(py, warnings)?.into_any()),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(manual_migration_requests, module)?)?;
    module.add_function(wrap_pyfunction!(decide_model_migration, module)?)?;
    module.add_function(wrap_pyfunction!(plan_model_migrations, module)?)
}

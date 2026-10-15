//! Live candidate inspection and automatic request materialization.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::planner_migrations::column_objects::config;
use crate::bindings::_helpers::planner_migrations::column_objects::native;
use crate::bindings::_helpers::planner_migrations::discovery_events::{
    identity, key, newest, relation,
};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{
    PyBool, PyDict, PyDictMethods, PyFrozenSet, PyListMethods, PySet, PySetMethods, PyString,
    PyTuple,
};
use sqlbuild_analysis::planner_migrations::main::discovery_materialization::discovery_materialization;
use sqlbuild_analysis::planner_migrations::main::stored_migration_fingerprint::stored_migration_fingerprint;
use std::collections::BTreeMap;

fn location<'py>(
    runtime: &Bound<'py, PyAny>,
    item: &Bound<'py, PyAny>,
    event: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let fields = if event {
        [
            ("database", item.getattr("database")?),
            ("schema", item.getattr("schema")?),
            ("name", item.getattr("name")?),
        ]
    } else {
        let target = item.getattr("target_name")?;
        let name = if target.is_truthy()? {
            target
        } else {
            item.getattr("node_name")?
        };
        [
            ("database", item.getattr("target_database")?),
            ("schema", item.getattr("target_schema")?),
            ("name", name),
        ]
    };
    super::planning_origin::location(runtime, &fields)
}

pub(super) fn candidates<'py>(
    runtime: &Bound<'py, PyAny>,
    state: &Bound<'py, PyAny>,
    names: &Bound<'py, PyDict>,
    claims: (&Bound<'py, PyAny>, &Bound<'py, PyDict>),
) -> PyResult<Bound<'py, PyTuple>> {
    let py = runtime.py();
    let excluded = PySet::empty(py)?;
    for declaration in claims.0.try_iter()? {
        excluded.add(key(&declaration?.getattr("origin_location")?)?)?;
    }
    for (_, event) in claims.1.iter() {
        excluded.add(key(&event.getattr("origin")?)?)?;
    }
    let orphans = call_with(
        &state.getattr("orphan_fingerprints")?,
        &[(
            "project_model_names",
            PyFrozenSet::new(py, names.keys().iter())?.into_any(),
        )],
    )?;
    let mut fingerprints: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut locations: Vec<Bound<'py, PyAny>> = Vec::new();
    for item in orphans.try_iter()? {
        let item = item?;
        let metadata: String = item.getattr("metadata_json")?.extract()?;
        if stored_migration_fingerprint(&metadata).is_some()
            && !item.getattr("target_name")?.is_none()
        {
            locations.push(location(runtime, &item, false)?);
            fingerprints.push(item);
        }
    }
    call_with(
        &state.getattr("inspect_relations")?,
        &[("locations", PyTuple::new(py, &locations)?.into_any())],
    )?;
    let mut result: Vec<Bound<'py, PyAny>> = Vec::new();
    for (fingerprint, location) in fingerprints.into_iter().zip(locations) {
        if state.call_method1("relation", (&location,))?.is_none()
            || excluded.contains(key(&location)?)?
        {
            continue;
        }
        let event = newest(&state.getattr("events")?, &location)?;
        if !event.is_none()
            && event
                .getattr("origin")?
                .call_method1("matches", (relation(&location)?,))?
                .is_truthy()?
        {
            continue;
        }
        result.push(fingerprint);
    }
    PyTuple::new(py, result)
}

pub(super) fn automatic<'py>(
    runtime: &Bound<'py, PyAny>,
    scope: &Bound<'py, PyAny>,
    models: &[Bound<'py, PyAny>],
    matches: (&Bound<'py, PyAny>, &Bound<'py, PyDict>),
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py = runtime.py();
    let mut requests: Vec<Bound<'py, PyAny>> = Vec::new();
    for item in models {
        if !scope
            .getattr("selected_keys")?
            .contains(item.getattr("key")?)?
        {
            continue;
        }
        let name = item.getattr("name")?;
        let event = matches.1.get_item(&name)?;
        let candidate = matches.0.call_method1("get", (&name,))?;
        let origin = if let Some(event) = event {
            Some((
                location(runtime, &event.getattr("origin")?, true)?,
                event.getattr("origin_model")?,
            ))
        } else if !candidate.is_none() {
            let materialized: Option<String> = config(item, "materialized")?.extract()?;
            let metadata: String = candidate.getattr("metadata_json")?.extract()?;
            if discovery_materialization(materialized.as_deref().unwrap_or_default(), &metadata) {
                Some((
                    location(runtime, &candidate, false)?,
                    candidate.getattr("node_name")?,
                ))
            } else {
                None
            }
        } else {
            None
        };
        if let Some((location, origin_model)) = origin {
            requests.push(native(
                py,
                "ModelMigrationRequest",
                &[
                    ("model", item.clone()),
                    (
                        "discovery",
                        imported(py, "sqlbuild._native", "MigrationDiscovery")?
                            .getattr("AUTOMATIC")?,
                    ),
                    ("origin_location", location),
                    ("origin_model", origin_model),
                    (
                        "identity_only",
                        PyBool::new(py, identity(item)?).to_owned().into_any(),
                    ),
                ],
            )?);
        }
    }
    Ok(requests)
}

pub(super) fn warnings<'py>(
    models: &[Bound<'py, PyAny>],
    scope: &Bound<'py, PyAny>,
    ambiguous: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py = scope.py();
    let selected = PySet::empty(py)?;
    for item in models {
        if scope
            .getattr("selected_keys")?
            .contains(item.getattr("key")?)?
        {
            selected.add(item.getattr("name")?)?;
        }
    }
    let ambiguous: BTreeMap<String, String> = ambiguous.extract()?;
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    for (name, detail) in ambiguous {
        if selected.contains(&name)? {
            warnings.push(native(py, "PlanWarning", &[
                ("model_name", PyString::new(py, &name).into_any()),
                ("severity", imported(py, "sqlbuild._native", "WarningSeverity")?.getattr("WARNING")?),
                ("message", PyString::new(py, &format!("'{name}' matches {detail}; no automatic migration was inferred. Add migrate_from to choose one.")).into_any()),
                ("code", PyString::new(py, "M107").into_any()),
            ])?);
        }
    }
    PyTuple::new(py, warnings)
}

//! Native migration discovery over existing inspection and fingerprint cache boundaries.

use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::planner_migrations::column_objects::{model, native};
use crate::bindings::_helpers::planner_migrations::{
    discovery_events, discovery_models, discovery_requests,
};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyListMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

#[pyfunction]
#[pyo3(signature = (**options))]
fn discover_model_migrations<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "discover_model_migrations",
        options,
        (
            &[
                "runtime",
                "scope",
                "snapshot",
                "manual_requests",
                "declarations",
                "state",
                "project_schemas",
                "fingerprints",
            ],
            &[],
        ),
    )?;
    let runtime = args.value("runtime")?;
    let scope = args.value("scope")?;
    let state = args.value("state")?;
    let manual = args.value("manual_requests")?;
    let declarations = args.value("declarations")?;
    let models = discovery_models::ordered(&runtime)?;
    let declared_names = PyDict::new(py);
    for declaration in declarations.try_iter()? {
        declared_names.set_item(declaration?.getattr("model_name")?, py.None())?;
    }
    let triggered =
        discovery_models::triggered(&models, &scope, &args.value("snapshot")?, &declared_names)?;
    if !triggered && !manual.is_truthy()? {
        return model(py, "ModelMigrationDiscovery", &[]);
    }
    let metadata = discovery_models::metadata(&runtime, &models)?;
    let dialect = runtime
        .getattr("adapter")?
        .call_method0("sql_analysis_dialect")?;
    call_with(
        &state.getattr("inspect_schemas")?,
        &[("schemas", args.value("project_schemas")?)],
    )?;
    let declared = discovery_events::declared(&declarations, &state)?;
    let names = PyDict::new(py);
    for item in &models {
        names.set_item(item.getattr("name")?, item)?;
    }
    let event_renames = discovery_events::renames(&runtime, &names, &state)?;
    for (name, origin) in declared.iter() {
        event_renames.set_item(name, origin)?;
    }
    let seeds = PyTuple::new(py, [event_renames, declared])?;
    let cache = args.value("fingerprints")?;
    if !triggered {
        let hashes = native(
            py,
            "migration_destination_fingerprints",
            &[
                ("requests", manual.clone()),
                ("variants", seeds.into_any()),
                ("metadata_jsons", metadata.into_any()),
                ("dialect", dialect),
                ("fingerprints", cache),
            ],
        )?;
        return model(
            py,
            "ModelMigrationDiscovery",
            &[("requests", manual), ("destination_fingerprints", hashes)],
        );
    }
    let unbuilt = PyDict::new(py);
    for item in &models {
        let name = item.getattr("name")?;
        if !declared_names.contains(&name)?
            && call_with(
                &state.getattr("named_fingerprint")?,
                &[("model_name", name.clone())],
            )?
            .is_none()
        {
            unbuilt.set_item(name, item)?;
        }
    }
    let resumed = discovery_events::resumed(&runtime, &models, &unbuilt, &state)?;
    let candidates =
        discovery_requests::candidates(&runtime, &state, &names, (&declarations, &resumed))?;
    for (name, _) in resumed.iter() {
        unbuilt.del_item(name)?;
    }
    let matched = native(
        py,
        "match_migration_fingerprints",
        &[
            ("models", PyTuple::new(py, &models)?.into_any()),
            (
                "new_names",
                PyFrozenSet::new(py, unbuilt.keys().iter())?.into_any(),
            ),
            ("seed_variants", seeds.into_any()),
            ("candidates", candidates.into_any()),
            ("metadata_jsons", metadata.clone().into_any()),
            ("dialect", dialect.clone()),
            ("fingerprints", cache.clone()),
        ],
    )?;
    let mut requests: Vec<Bound<'py, PyAny>> = manual.try_iter()?.collect::<PyResult<_>>()?;
    requests.extend(discovery_requests::automatic(
        &runtime,
        &scope,
        &models,
        (&matched.get_item(1)?, &resumed),
    )?);
    let requests = PyTuple::new(py, requests)?;
    let warnings = discovery_requests::warnings(&models, &scope, &matched.get_item(2)?)?;
    let hashes = native(
        py,
        "migration_destination_fingerprints",
        &[
            ("requests", requests.clone().into_any()),
            ("variants", matched.get_item(0)?),
            ("metadata_jsons", metadata.into_any()),
            ("dialect", dialect),
            ("fingerprints", cache),
        ],
    )?;
    model(
        py,
        "ModelMigrationDiscovery",
        &[
            ("requests", requests.into_any()),
            ("warnings", warnings.into_any()),
            ("destination_fingerprints", hashes),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(discover_model_migrations, module)?)
}

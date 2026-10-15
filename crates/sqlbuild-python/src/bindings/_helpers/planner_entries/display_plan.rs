//! Display-only plans for external plan surfaces when warehouse planning cannot resolve.

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::planner_entries::values::{
    NATIVE_MODULE, boolean, native, none, planner_model, planner_type, string,
};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyFrozenSet, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

const VIEW: &str = "view";
const INCREMENTAL: &str = "incremental";
const CUSTOM: &str = "custom";

fn display_action(
    materialization_type: &Bound<'_, PyAny>,
    full_refresh: bool,
) -> PyResult<&'static str> {
    Ok(if materialization_type.eq(VIEW)? {
        "CREATE_VIEW"
    } else if materialization_type.eq(INCREMENTAL)? {
        if full_refresh {
            "CREATE_TABLE"
        } else {
            "INCREMENTAL_APPEND"
        }
    } else if materialization_type.eq(CUSTOM)? {
        "CUSTOM"
    } else {
        "CREATE_TABLE"
    })
}

fn config<'py>(model: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    native(
        model.py(),
        "get_config_str",
        &[
            ("values", model.getattr("config")?.getattr("values")?),
            ("key", string(model.py(), key)),
        ],
    )
}

fn display_entry<'py>(
    model: &Bound<'py, PyAny>,
    full_refresh: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let py = model.py();
    let materialization_type = native(py, "get_materialization_type", &[("model", model.clone())])?;
    let effective = native(
        py,
        "resolve_model_full_refresh",
        &[
            ("model", model.clone()),
            ("cli_full_refresh", boolean(py, full_refresh)?),
        ],
    )?
    .is_truthy()?;
    let query_sql = model.getattr("query_sql")?;
    let custom_name = if materialization_type.eq(CUSTOM)? {
        config(model, "materialized")?
    } else {
        none(py)
    };
    planner_model(
        py,
        "ModelPlanEntry",
        &[
            ("key", model.getattr("key")?),
            ("name", model.getattr("name")?),
            ("relative_path", model.getattr("relative_path")?),
            (
                "action",
                planner_type(
                    py,
                    "PlanAction",
                    display_action(&materialization_type, effective)?,
                )?,
            ),
            ("materialization_type", materialization_type),
            (
                "reason",
                planner_type(
                    py,
                    "PlanReason",
                    if effective {
                        "FULL_REFRESH"
                    } else {
                        "NO_CHANGE"
                    },
                )?,
            ),
            ("destination", model.getattr("destination")?),
            ("fingerprint_query_sql", query_sql.clone()),
            ("resolved_sql", query_sql),
            ("logical_ddl", string(py, "")),
            (
                "incremental_strategy",
                config(model, "incremental_strategy")?,
            ),
            ("incremental_mode", config(model, "incremental_mode")?),
            ("cursor_column", config(model, "cursor_column")?),
            ("cursor_type", config(model, "cursor_type")?),
            (
                "backfill",
                planner_model(
                    py,
                    "BackfillResult",
                    &[(
                        "action",
                        planner_type(
                            py,
                            "BackfillAction",
                            if effective { "FULL" } else { "FORWARD_ONLY" },
                        )?,
                    )],
                )?,
            ),
            ("custom_materialization_name", custom_name),
        ],
    )
}

/// Build a display-only plan when warehouse planning cannot fully resolve.
#[pyfunction]
#[pyo3(signature = (*, project, selected_model_names, full_refresh))]
fn build_display_only_sqlbuild_plan<'py>(
    project: &Bound<'py, PyAny>,
    selected_model_names: &Bound<'py, PyAny>,
    full_refresh: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    let selected = PyFrozenSet::new(
        py,
        selected_model_names
            .try_iter()?
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    for model in project.getattr("models")?.try_iter()? {
        let model = model?;
        if selected.contains(model.getattr("name")?)? {
            entries.push(display_entry(&model, full_refresh)?);
        }
    }
    let keys: Vec<Bound<'py, PyAny>> = entries
        .iter()
        .map(|entry| entry.getattr("key"))
        .collect::<PyResult<_>>()?;
    let upstream =
        imported(py, NATIVE_MODULE, "build_execution_upstream_deps")?.call1((project,))?;
    let downstream = imported(py, NATIVE_MODULE, "build_downstream_deps")?.call1((&upstream,))?;
    planner_model(
        py,
        "PlanOutput",
        &[
            ("execution_order", PyTuple::new(py, &keys)?.into_any()),
            ("model_entries", PyTuple::new(py, entries)?.into_any()),
            ("selected_keys", PyFrozenSet::new(py, keys)?.into_any()),
            ("upstream_deps", upstream),
            ("downstream_deps", downstream),
        ],
    )
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_display_only_sqlbuild_plan, module)?)
}

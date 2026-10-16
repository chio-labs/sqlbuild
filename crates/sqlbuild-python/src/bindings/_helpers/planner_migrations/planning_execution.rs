//! Preserve adapter overrides when describing migration execution.

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::native_host::adapter::AdapterHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::planner_migrations::column_objects::replace;
use crate::bindings::_helpers::planner_phases::runtime::runtime_field;
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::PyBool;
use pyo3::{pyfunction, wrap_pyfunction};

fn label<'py>(location: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let qualified = location.getattr("qualified_name")?;
    if qualified.is_truthy()? {
        Ok(qualified)
    } else {
        location.getattr("name")
    }
}

#[pyfunction]
#[pyo3(signature = (*, runtime, decision))]
fn migration_promotion<'py>(
    runtime: &Bound<'py, PyAny>,
    decision: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let adapter = runtime_field(runtime, |runtime| &runtime.adapter)?;
    let promotion = registry::class(runtime.py(), RecordId::MigrationPromotion)?;
    if adapter
        .call_method0("supports_transactional_ddl")?
        .is_truthy()?
    {
        return promotion.getattr("TRANSACTIONAL_RENAME");
    }
    if !decision.eq("migrate")? && adapter.getattr("adapter_name")?.eq("snowflake")? {
        return promotion.getattr("SWAP");
    }
    promotion.getattr("RENAME")
}

#[pyfunction]
#[pyo3(signature = (*, runtime, model, entry))]
fn migration_with_execution<'py>(
    runtime: &Bound<'py, PyAny>,
    model: &Bound<'py, PyAny>,
    entry: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = runtime.py();
    let adapter = runtime_field(runtime, |runtime| &runtime.adapter)?;
    let transient = if adapter.getattr("adapter_name")?.eq("snowflake")? {
        PyBool::new(
            py,
            model
                .getattr("config")?
                .getattr("table_type")?
                .getattr("value")?
                .eq("transient")?,
        )
        .to_owned()
        .into_any()
    } else {
        py.None().into_bound(py)
    };
    let stage = call_with(
        &adapter.getattr("render_migration_stage")?,
        &[
            ("origin", label(&entry.getattr("origin")?)?),
            ("stage", label(&entry.getattr("destination")?)?),
            ("origin_is_transient", entry.getattr("origin_is_transient")?),
            ("stage_is_transient", transient.clone()),
        ],
    )?;
    let transfer = stage.getattr("transfer")?;
    let fallback = if stage.getattr("fallback_statements")?.is_truthy()? {
        host::entry(py, AdapterHost::MigrationTransfer)?.getattr("COPY")?
    } else {
        py.None().into_bound(py)
    };
    replace(
        entry,
        &[
            ("stage_is_transient", transient),
            ("transfer", transfer),
            ("transfer_fallback", fallback),
            (
                "promotion",
                migration_promotion(runtime, &entry.getattr("decision")?)?,
            ),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(migration_promotion, module)?)?;
    module.add_function(wrap_pyfunction!(migration_with_execution, module)?)
}

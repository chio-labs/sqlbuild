//! Plan output assembly: storage policies, warnings and direct-mode metadata.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::planner_entries::models::PlanOutputInputs;
use crate::bindings::_helpers::planner_entries::plan_output::plan_output_fields;
use crate::bindings::_helpers::planner_phases::models::{
    ChangeReconciliation, ModelEntryResults, PlanOutputFields,
};
use crate::bindings::_helpers::planner_phases::objects::{
    native, replace, sorted_names, strings, text, tuple,
};
use crate::bindings::_helpers::planner_phases::runtime::runtime_field;
use crate::bindings::_helpers::planner_phases::runtime::warehouse_field;
use crate::bindings::_helpers::planner_warehouse::source_freshness::source_freshness_unknown_warnings;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyTuple};

fn concat<'py>(py: Python<'py>, parts: &[Bound<'py, PyAny>]) -> PyResult<Bound<'py, PyAny>> {
    let mut items: Vec<_> = Vec::new();
    for part in parts {
        for item in part.try_iter()? {
            items.push(item?);
        }
    }
    tuple(py, items)
}

impl<'py> PlanOutputFields<'py> {
    fn field(&self, name: &str) -> PyResult<Bound<'py, PyAny>> {
        self.fields
            .iter()
            .find(|(field, _)| *field == name)
            .map(|(_, value)| value.clone())
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(name.to_owned()))
    }

    fn set(&mut self, name: &'static str, value: Bound<'py, PyAny>) {
        match self.fields.iter_mut().find(|(field, _)| *field == name) {
            Some(existing) => existing.1 = value,
            None => self.fields.push((name, value)),
        }
    }

    /// The `PlanOutput` hand-off, built once from every field the phases set.
    pub(crate) fn build(mut self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        if !self.metadata.is_empty() {
            let metadata = PyDict::new(py);
            for (name, value) in &self.metadata {
                metadata.set_item(*name, value)?;
            }
            self.set("metadata", metadata.into_any());
        }
        call_with(&registry::class(py, RecordId::PlanOutput)?, &self.fields)
    }
}

/// The plan output's base fields from the planned entries, relations and source freshness.
pub(crate) fn base_plan_output<'py>(
    (runtime, warehouse, identities, overrides): (
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
    ),
    (execution_scope, reconciliation, entries, source_freshness): (
        &Bound<'py, PyAny>,
        &ChangeReconciliation<'py>,
        ModelEntryResults<'py>,
        &Bound<'py, PyAny>,
    ),
    planned_sql_tests: &Bound<'py, PyAny>,
) -> PyResult<PlanOutputFields<'py>> {
    let py = runtime.py();
    let version = identities.getattr("version_identities")?;
    let extras = native(
        py,
        RecordId::PlanOutputExtras,
        &[
            (
                "seed_version_hashes",
                version.getattr("seed_version_hashes")?,
            ),
            (
                "seed_metadata_jsons",
                version.getattr("seed_metadata_jsons")?,
            ),
            ("planned_sql_tests", planned_sql_tests.clone()),
        ],
    )?;
    let mut output = PlanOutputFields {
        fields: plan_output_fields(PlanOutputInputs {
            project: runtime_field(&runtime, |runtime| &runtime.project)?,
            adapter: runtime_field(&runtime, |runtime| &runtime.adapter)?,
            scope: execution_scope.clone(),
            snapshot: warehouse_field(&warehouse, |warehouse| &warehouse.snapshot)?,
            relations: warehouse_field(&warehouse, |warehouse| &warehouse.inspection_relations)?,
            changes: reconciliation.changes.clone(),
            model_entries: entries.entries,
            model_warnings: entries.warnings,
            reload_sources: overrides.getattr("reload_sources")?,
            extras,
        })?,
        metadata: Vec::new(),
    };
    output.set("source_freshness", source_freshness.clone());
    output.set("cursor_overrides", overrides.getattr("cursor_overrides")?);
    Ok(output)
}

/// Attach near-match column rename hints to the model entries they describe.
#[pyfunction]
#[pyo3(signature = (*, entries, hints))]
pub(crate) fn with_column_rename_hints<'py>(
    entries: &Bound<'py, PyAny>,
    hints: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = entries.py();
    let by_model = PyDict::new(py);
    for hint in hints.try_iter()? {
        let hint = hint?;
        let name = hint.getattr("model_name")?;
        if let Some(existing) = by_model.get_item(&name)? {
            existing.call_method1("append", (hint,))?;
        } else {
            by_model.set_item(name, pyo3::types::PyList::new(py, [hint])?)?;
        }
    }
    let mut attached: Vec<_> = Vec::new();
    for entry in entries.try_iter()? {
        let entry = entry?;
        match by_model.get_item(entry.getattr("name")?)? {
            Some(found) => attached.push(replace(
                &entry,
                &[(
                    "column_rename_hints",
                    PyTuple::new(py, found.try_iter()?.collect::<PyResult<Vec<_>>>()?)?.into_any(),
                )],
            )?),
            None => attached.push(entry),
        }
    }
    tuple(py, attached)
}

/// Add migration fingerprints, rename hints, migration, table-type and retention entries.
pub(crate) fn add_storage_policies<'py>(
    mut output: PlanOutputFields<'py>,
    (runtime, warehouse, scopes, policies): (
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
    ),
) -> PyResult<PlanOutputFields<'py>> {
    let py = runtime.py();
    let mut entries = output.field("model_entries")?;
    if policies
        .getattr("record_migration_fingerprints")?
        .is_truthy()?
    {
        let models = PyDict::new(py);
        for model in runtime_field(&runtime, |runtime| &runtime.project)?
            .getattr("models")?
            .try_iter()?
        {
            let model = model?;
            models.set_item(model_reads::name_object(&model)?, model)?;
        }
        entries = native(
            py,
            NativeAttr::WithMigrationFingerprints,
            &[
                ("entries", entries),
                ("models_by_name", models.into_any()),
                (
                    "fingerprints",
                    warehouse_field(&warehouse, |warehouse| &warehouse.migration_fingerprints)?,
                ),
                (
                    "dialect",
                    runtime
                        .getattr("adapter")?
                        .call_method0("sql_analysis_dialect")?,
                ),
            ],
        )?;
    }
    let entries = with_column_rename_hints(
        &entries,
        &warehouse_field(&warehouse, |warehouse| &warehouse.column_rename_hints)?,
    )?;
    let migration_entries = warehouse_field(&warehouse, |warehouse| &warehouse.migration_entries)?;
    let column_entries =
        warehouse_field(&warehouse, |warehouse| &warehouse.column_migration_entries)?;
    let old_name_entries =
        warehouse_field(&warehouse, |warehouse| &warehouse.old_name_view_entries)?;
    let old_name_views = warehouse_field(&warehouse, |warehouse| &warehouse.old_name_views)?;
    let warnings = concat(
        py,
        &[
            warehouse_field(&warehouse, |warehouse| &warehouse.migration_warnings)?,
            output.field("warnings")?,
        ],
    )?;
    let selected = scopes.getattr("selected_scope")?;
    let storage = [
        ("runtime", runtime.clone()),
        ("warehouse", warehouse.clone()),
        ("scope", selected),
    ];
    let table_types = native(py, NativeAttr::PlanTableTypes, &storage)?;
    let retention = native(py, NativeAttr::PlanRetention, &storage)?;
    output.set("model_entries", entries);
    output.set("migration_entries", migration_entries);
    output.set("column_migration_entries", column_entries);
    output.set("old_name_view_entries", old_name_entries);
    output.set("old_name_views", old_name_views);
    output.set("warnings", warnings);
    output.set("table_type_entries", table_types);
    output.set("retention_entries", retention);
    Ok(output)
}

/// Add unknown source freshness warnings and, with selection diagnostics, stale-selection warnings.
pub(crate) fn add_plan_warnings<'py>(
    mut output: PlanOutputFields<'py>,
    (scopes, warehouse, identities, stale_warning_changes): (
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
    ),
    (source_freshness, policies): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<PlanOutputFields<'py>> {
    let py = scopes.py();
    let freshness = source_freshness_unknown_warnings(source_freshness)?;
    if freshness.is_truthy()? {
        let warnings = concat(py, &[output.field("warnings")?, freshness])?;
        output.set("warnings", warnings);
    }
    if !policies.getattr("selection_diagnostics")?.is_truthy()? {
        return Ok(output);
    }
    let stale = native(
        py,
        NativeAttr::BuildStaleOutOfSelectionWarnings,
        &[
            ("original_scope", scopes.getattr("stale_warning_scope")?),
            ("execution_scope", scopes.getattr("inspection_scope")?),
            ("changes", stale_warning_changes.clone()),
            (
                "snapshot",
                warehouse_field(&warehouse, |warehouse| &warehouse.snapshot)?,
            ),
            (
                "version_identities",
                identities.getattr("stale_warning_identities")?,
            ),
            ("source_freshness", source_freshness.clone()),
            (
                "include_sources",
                PyBool::new(py, false).to_owned().into_any(),
            ),
            (
                "model_changes_complete",
                PyBool::new(py, true).to_owned().into_any(),
            ),
        ],
    )?;
    if stale.is_truthy()? {
        let warnings = concat(py, &[output.field("warnings")?, stale])?;
        output.set("warnings", warnings);
    }
    Ok(output)
}

fn source_names<'py>(items: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let mut names: Vec<_> = Vec::new();
    for item in items.try_iter()? {
        names.push(item?.getattr("source_name")?.extract::<String>()?);
    }
    sorted_names(items.py(), names)
}

fn age_names<'py>(statuses: &Bound<'py, PyAny>, wanted: &str) -> PyResult<Bound<'py, PyAny>> {
    let mut names: Vec<_> = Vec::new();
    for item in statuses.call_method0("items")?.try_iter()? {
        let (identity, status): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        if status.eq(wanted)? {
            names.push(identity.getattr("source_name")?.extract::<String>()?);
        }
    }
    sorted_names(statuses.py(), names)
}

fn freshness_metadata<'py>(source_freshness: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py = source_freshness.py();
    let propagation = source_freshness.getattr("propagation")?;
    let propagated = |field: &str| -> PyResult<Bound<'py, PyAny>> {
        if propagation.is_none() {
            return tuple(py, Vec::new());
        }
        sorted_names(py, strings(&propagation.getattr(field)?)?)
    };
    let mut details: Vec<_> = Vec::new();
    for unknown in source_freshness
        .getattr("unknown_sources")?
        .call_method0("values")?
        .try_iter()?
    {
        let unknown = unknown?;
        let detail = PyDict::new(py);
        detail.set_item("source_name", unknown.getattr("source_name")?)?;
        detail.set_item("reason", unknown.getattr("reason")?.getattr("value")?)?;
        detail.set_item("message", unknown.getattr("message")?)?;
        details.push(detail.into_any());
    }
    let statuses = source_freshness.getattr("age_statuses")?;
    let metadata = PyDict::new(py);
    metadata.set_item(
        "observed_source_names",
        source_names(&source_freshness.getattr("observed_records")?)?,
    )?;
    metadata.set_item(
        "changed_source_names",
        source_names(&source_freshness.getattr("changed_identities")?)?,
    )?;
    metadata.set_item(
        "unchanged_source_names",
        source_names(&source_freshness.getattr("unchanged_identities")?)?,
    )?;
    metadata.set_item(
        "unknown_source_names",
        sorted_names(
            py,
            strings(&source_freshness.getattr("unknown_source_names")?)?,
        )?,
    )?;
    metadata.set_item("unknown_source_details", tuple(py, details)?)?;
    metadata.set_item("age_warning_source_names", age_names(&statuses, "warn")?)?;
    metadata.set_item("age_error_source_names", age_names(&statuses, "error")?)?;
    metadata.set_item("stale_model_names", propagated("stale_model_names")?)?;
    metadata.set_item("blocked_model_names", propagated("blocked_model_names")?)?;
    Ok(metadata.into_any())
}

/// Add the direct-mode source freshness, remaining stale models and selection diagnostics metadata.
pub(crate) fn add_plan_metadata<'py>(
    mut output: PlanOutputFields<'py>,
    source_freshness: &Bound<'py, PyAny>,
    policies: &Bound<'py, PyAny>,
) -> PyResult<PlanOutputFields<'py>> {
    let py = source_freshness.py();
    let diagnostics = PyDict::new(py);
    diagnostics.set_item("mode", text(py, "direct"))?;
    diagnostics.set_item("enabled", policies.getattr("selection_diagnostics")?)?;
    output.metadata.push((
        "direct_source_freshness",
        freshness_metadata(source_freshness)?,
    ));
    output.metadata.push((
        "direct_remaining_stale_model_names",
        sorted_names(py, Vec::new())?,
    ));
    output
        .metadata
        .push(("selection_diagnostics", diagnostics.into_any()));
    Ok(output)
}

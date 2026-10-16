//! Plan output assembly: storage policies, warnings and direct-mode metadata.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::planner_phases::objects::{
    model_key_names, native, replace, sorted_names, strings, text, tuple,
};
use crate::bindings::_helpers::planner_warehouse::source_freshness::source_freshness_unknown_warnings;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::PyDict as KeywordDict;
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyTuple};
use std::collections::BTreeSet;

fn concat<'py>(py: Python<'py>, parts: &[Bound<'py, PyAny>]) -> PyResult<Bound<'py, PyAny>> {
    let mut items: Vec<_> = Vec::new();
    for part in parts {
        for item in part.try_iter()? {
            items.push(item?);
        }
    }
    tuple(py, items)
}

fn with_metadata<'py>(
    plan_output: &Bound<'py, PyAny>,
    items: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let py = plan_output.py();
    let metadata = PyDict::new(py);
    metadata.update(
        plan_output
            .getattr("metadata")?
            .downcast::<pyo3::types::PyMapping>()?,
    )?;
    for (name, value) in items {
        metadata.set_item(*name, value)?;
    }
    replace(plan_output, &[("metadata", metadata.into_any())])
}

#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn assemble_base_plan_output<'py>(
    py: pyo3::Python<'py>,
    options: Option<Bound<'py, KeywordDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "assemble_base_plan_output",
        options,
        (
            &[
                "runtime",
                "warehouse",
                "identities",
                "overrides",
                "pruning",
                "reconciliation",
                "entries",
                "source_freshness",
            ],
            &["planned_sql_tests"],
        ),
    )?;
    let runtime = &args.value("runtime")?;
    let warehouse = &args.value("warehouse")?;
    let identities = &args.value("identities")?;
    let overrides = &args.value("overrides")?;
    let pruning = &args.value("pruning")?;
    let reconciliation = &args.value("reconciliation")?;
    let entries = &args.value("entries")?;
    let source_freshness = &args.value("source_freshness")?;
    let planned_sql_tests = &args.value("planned_sql_tests")?;

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
    let plan_output = call_with(
        &registry::native(py, NativeAttr::BuildPlanOutput)?,
        &[
            ("project", runtime.getattr("project")?),
            ("adapter", runtime.getattr("adapter")?),
            ("scope", pruning.getattr("execution_scope")?),
            ("snapshot", warehouse.getattr("snapshot")?),
            ("relations", warehouse.getattr("inspection_relations")?),
            ("changes", reconciliation.getattr("changes")?),
            (
                "model_entry_results",
                entries.getattr("model_entry_results")?,
            ),
            ("reload_sources", overrides.getattr("reload_sources")?),
            ("extras", extras),
        ],
    )?;
    let plan_output = replace(
        &plan_output,
        &[
            ("source_freshness", source_freshness.clone()),
            ("cursor_overrides", overrides.getattr("cursor_overrides")?),
        ],
    )?;
    let pruned = pruning.getattr("pruned_direct_model_names")?;
    if pruned.is_truthy()? {
        return with_metadata(&plan_output, &[("direct_pruned_model_names", pruned)]);
    }
    Ok(plan_output)
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

#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn with_storage_policies<'py>(
    py: pyo3::Python<'py>,
    options: Option<Bound<'py, KeywordDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "with_storage_policies",
        options,
        (
            &["plan_output", "runtime", "warehouse", "scopes", "policies"],
            &[],
        ),
    )?;
    let plan_output = &args.value("plan_output")?;
    let runtime = &args.value("runtime")?;
    let warehouse = &args.value("warehouse")?;
    let scopes = &args.value("scopes")?;
    let policies = &args.value("policies")?;

    let py = runtime.py();
    let mut entries = plan_output.getattr("model_entries")?;
    if policies
        .getattr("record_migration_fingerprints")?
        .is_truthy()?
    {
        let models = PyDict::new(py);
        for model in runtime.getattr("project")?.getattr("models")?.try_iter()? {
            let model = model?;
            models.set_item(model_reads::name_object(&model)?, model)?;
        }
        entries = native(
            py,
            NativeAttr::WithMigrationFingerprints,
            &[
                ("entries", entries),
                ("models_by_name", models.into_any()),
                ("fingerprints", warehouse.getattr("migration_fingerprints")?),
                (
                    "dialect",
                    runtime
                        .getattr("adapter")?
                        .call_method0("sql_analysis_dialect")?,
                ),
            ],
        )?;
    }
    let entries = with_column_rename_hints(&entries, &warehouse.getattr("column_rename_hints")?)?;
    let migration_entries = warehouse.getattr("migration_entries")?;
    let column_entries = warehouse.getattr("column_migration_entries")?;
    let old_name_entries = warehouse.getattr("old_name_view_entries")?;
    let old_name_views = warehouse.getattr("old_name_views")?;
    let warnings = concat(
        py,
        &[
            warehouse.getattr("migration_warnings")?,
            plan_output.getattr("warnings")?,
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
    replace(
        plan_output,
        &[
            ("model_entries", entries),
            ("migration_entries", migration_entries),
            ("column_migration_entries", column_entries),
            ("old_name_view_entries", old_name_entries),
            ("old_name_views", old_name_views),
            ("warnings", warnings),
            ("table_type_entries", table_types),
            ("retention_entries", retention),
        ],
    )
}

#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn with_plan_warnings<'py>(
    py: pyo3::Python<'py>,
    options: Option<Bound<'py, KeywordDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "with_plan_warnings",
        options,
        (
            &[
                "runtime",
                "scopes",
                "warehouse",
                "identities",
                "stale_warning_changes",
                "pruning",
                "source_freshness",
                "plan_output",
                "policies",
            ],
            &[],
        ),
    )?;
    let runtime = &args.value("runtime")?;
    let scopes = &args.value("scopes")?;
    let warehouse = &args.value("warehouse")?;
    let identities = &args.value("identities")?;
    let stale_warning_changes = &args.value("stale_warning_changes")?;
    let pruning = &args.value("pruning")?;
    let source_freshness = &args.value("source_freshness")?;
    let plan_output = &args.value("plan_output")?;
    let policies = &args.value("policies")?;

    let py = runtime.py();
    let mut plan_output = plan_output.clone();
    let freshness = source_freshness_unknown_warnings(source_freshness)?;
    if freshness.is_truthy()? {
        let warnings = concat(py, &[plan_output.getattr("warnings")?, freshness])?;
        plan_output = replace(&plan_output, &[("warnings", warnings)])?;
    }
    if !policies.getattr("selection_diagnostics")?.is_truthy()? {
        return Ok(plan_output);
    }
    let stale = native(
        py,
        NativeAttr::BuildStaleOutOfSelectionWarnings,
        &[
            ("original_scope", scopes.getattr("stale_warning_scope")?),
            ("execution_scope", pruning.getattr("execution_scope")?),
            ("changes", stale_warning_changes.clone()),
            ("snapshot", warehouse.getattr("snapshot")?),
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
        let warnings = concat(py, &[plan_output.getattr("warnings")?, stale])?;
        plan_output = replace(&plan_output, &[("warnings", warnings)])?;
    }
    Ok(plan_output)
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

#[pyfunction]
#[pyo3(signature = (*, plan_output, pruning, source_freshness, policies))]
pub(crate) fn with_plan_metadata<'py>(
    plan_output: &Bound<'py, PyAny>,
    pruning: &Bound<'py, PyAny>,
    source_freshness: &Bound<'py, PyAny>,
    policies: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = plan_output.py();
    let selected: BTreeSet<String> = model_key_names(
        &pruning
            .getattr("inspection_scope")?
            .getattr("selected_keys")?,
    )?
    .into_iter()
    .collect();
    let remaining: Vec<String> = strings(&pruning.getattr("direct_identity_stale_model_names")?)?
        .into_iter()
        .filter(|name| !selected.contains(name))
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    let diagnostics = PyDict::new(py);
    diagnostics.set_item("mode", text(py, "direct"))?;
    diagnostics.set_item("enabled", policies.getattr("selection_diagnostics")?)?;
    with_metadata(
        plan_output,
        &[
            (
                "direct_source_freshness",
                freshness_metadata(source_freshness)?,
            ),
            (
                "direct_remaining_stale_model_names",
                sorted_names(py, remaining)?,
            ),
            ("selection_diagnostics", diagnostics.into_any()),
        ],
    )
}

//! Assemble model migration decisions from inspected warehouse facts.

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::planner_migrations::column_objects::{lower, model, replace, text};
use crate::bindings::_helpers::planner_migrations::compatibility::check_migration_compatibility;
use crate::bindings::_helpers::planner_migrations::model_handover::{
    applies, empty_version, handover,
};
use crate::bindings::_helpers::planner_migrations::models::{
    CompatibilityCheck, MigrationDecisionRequest,
};
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::state_rows::migration_projections::newest_move;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::PyBool;
use sqlbuild_analysis::planner_migrations::main::model_decision::model_decision;

pub(super) fn relation<'py>(location: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    host::entry(location.py(), ExecutorHost::MigrationRelationForLocation)?.call1((location,))
}

fn key(location: &Bound<'_, PyAny>) -> PyResult<(String, String)> {
    let schema = location.getattr("schema")?;
    Ok((
        if schema.is_truthy()? {
            lower(&schema)?
        } else {
            String::new()
        },
        lower(&location.getattr("name")?)?,
    ))
}

pub(super) fn decision<'py>(entry: &Bound<'py, PyAny>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    replace(
        entry,
        &[(
            "decision",
            registry::class(entry.py(), RecordId::MigrationDecision)?.call1((name,))?,
        )],
    )
}

fn result<'py>(
    entry: Bound<'py, PyAny>,
    inherited: Bound<'py, PyAny>,
    applies: bool,
) -> PyResult<MigrationDecision<'py>> {
    Ok(MigrationDecision {
        entry,
        inherited,
        applies,
    })
}

/// The decided plan entry, the inherited fingerprint, and whether the history handover applies.
pub(super) struct MigrationDecision<'py> {
    pub(super) entry: Bound<'py, PyAny>,
    pub(super) inherited: Bound<'py, PyAny>,
    pub(super) applies: bool,
}

pub(super) fn decide<'py>(
    decision_request: &MigrationDecisionRequest<'_, 'py>,
) -> PyResult<MigrationDecision<'py>> {
    let runtime = decision_request.runtime.clone();
    let py = runtime.py();
    let request = decision_request.request;
    let item = request.model.clone();
    let destination = item.getattr("destination")?;
    let origin = decision_request.origin.clone();
    let snapshot = decision_request.snapshot.clone();
    let state = decision_request.state.clone();
    let origin_model = decision_request.origin_model.clone();
    if key(&origin)? == key(&destination)? {
        let name: String = item.getattr("name")?.extract()?;
        return Err(pyo3::PyErr::from_value(
            registry::error(py, ErrorId::PlannerInput)?.call1((format!(
                "model '{name}': migrate_from names the model's own relation"
            ),))?,
        ));
    }
    let newest = newest_move(&state.getattr("events")?, &relation(&destination)?)?;
    let origin_relation = state.call_method1("relation", (&origin,))?;
    let fingerprint = call_with(
        &state.getattr("model_fingerprint")?,
        &[
            ("location", origin.clone()),
            ("model_name", origin_model.clone()),
        ],
    )?;
    let base = model(
        py,
        RecordId::ModelMigrationPlanEntry,
        &[
            ("model_name", item.getattr("name")?),
            ("discovery", request.discovery.clone()),
            (
                "decision",
                registry::class(py, RecordId::MigrationDecision)?.getattr("MIGRATE")?,
            ),
            (
                "compatibility",
                registry::class(py, RecordId::MigrationCompatibility)?.getattr("NOT_CHECKED")?,
            ),
            ("origin_model", origin_model),
            ("origin", origin.clone()),
            ("destination", destination.clone()),
            (
                "target_name",
                runtime
                    .getattr("project")?
                    .getattr("effective_target_name")?,
            ),
            (
                "origin_version_hash",
                if fingerprint.is_none() {
                    text(py, "")
                } else {
                    fingerprint.getattr("version_hash")?
                },
            ),
            (
                "origin_is_transient",
                PyBool::new(
                    py,
                    !origin_relation.is_none()
                        && origin_relation.getattr("is_transient")?.is_truthy()?,
                )
                .to_owned()
                .into_any(),
            ),
            (
                "origin_tracked",
                PyBool::new(py, !fingerprint.is_none())
                    .to_owned()
                    .into_any(),
            ),
        ],
    )?;
    let recorded = !newest.is_none()
        && newest
            .getattr("destination")?
            .call_method1("matches", (relation(&destination)?,))?
            .is_truthy()?
        && newest
            .getattr("origin")?
            .call_method1("matches", (relation(&origin)?,))?
            .is_truthy()?;
    if request.identity_only {
        let recorded = recorded && newest.getattr("decision")?.eq("renamed")?;
        if request.discovery.eq("manual")? && !recorded && origin_relation.is_none() {
            return result(
                decision(&base, "origin_missing")?,
                py.None().into_bound(py),
                false,
            );
        }
        let inherited = if recorded && !applies(&item, &newest, &snapshot)? {
            snapshot
                .getattr("fingerprints")?
                .getattr("models")?
                .call_method1("get", (item.getattr("name")?,))?
        } else {
            empty_version(&item, &fingerprint)?
        };
        return result(
            replace(
                &decision(&base, "renamed")?,
                &[(
                    "completed_at",
                    if recorded {
                        newest.getattr("created_at")?
                    } else {
                        py.None().into_bound(py)
                    },
                )],
            )?,
            inherited,
            true,
        );
    }
    if recorded {
        let applies = applies(&item, &newest, &snapshot)?;
        let inherited = if applies {
            handover(&item, &fingerprint, &newest.getattr("origin_version_hash")?)?
        } else {
            snapshot
                .getattr("fingerprints")?
                .getattr("models")?
                .call_method1("get", (item.getattr("name")?,))?
        };
        return result(
            replace(
                &decision(&base, "done")?,
                &[
                    ("completed_at", newest.getattr("created_at")?),
                    (
                        "origin_version_hash",
                        newest.getattr("origin_version_hash")?,
                    ),
                    ("target_name", newest.getattr("target_name")?),
                ],
            )?,
            inherited,
            applies,
        );
    }
    if origin_relation.is_none() {
        return result(
            decision(&base, "origin_missing")?,
            py.None().into_bound(py),
            false,
        );
    }
    let compatibility = check_migration_compatibility(&CompatibilityCheck {
        model: item.clone(),
        origin_relation,
        origin_columns: state.call_method1("relation_columns", (&origin,))?,
        sql_analysis_enabled: runtime
            .getattr("project")?
            .getattr("settings")?
            .getattr("sql_analysis")?,
        column_dialect: snapshot.getattr("column_dialect")?,
        snapshots_config: decision_request.snapshots_config.clone(),
    })?;
    let name = model_decision(
        snapshot
            .getattr("existing_relations")?
            .contains(item.getattr("name")?)?,
        (
            !newest.is_none(),
            !newest.is_none()
                && newest
                    .getattr("origin")?
                    .call_method1("matches", (relation(&destination)?,))?
                    .is_truthy()?,
            snapshot
                .getattr("fingerprints")?
                .getattr("models")?
                .contains(item.getattr("name")?)?,
        ),
        request.force,
    );
    let entry = replace(
        &decision(&base, name)?,
        &[
            ("compatibility", compatibility.status),
            ("compatibility_findings", compatibility.findings),
        ],
    )?;
    if !entry
        .getattr("decision")?
        .getattr("moves_data")?
        .is_truthy()?
        || entry.getattr("blocks_build")?.is_truthy()?
    {
        return result(entry, py.None().into_bound(py), false);
    }
    let inherited = handover(&item, &fingerprint, &entry.getattr("origin_version_hash")?)?;
    result(
        super::planning_execution::migration_with_execution(&runtime, &item, &entry)?,
        inherited,
        true,
    )
}

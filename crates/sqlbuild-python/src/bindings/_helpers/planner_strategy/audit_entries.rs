//! Assemble audit plan dataclasses using native rendering and scheduling.

use crate::bindings::_helpers::attachments::reference_markers::assert_no_unresolved_sql_markers;
use crate::bindings::_helpers::auditing::render::render_audit_sql;
use crate::bindings::_helpers::compile_driver::python_calls::keywords;
use crate::bindings::_helpers::graph::views::project_lineage_views;
use crate::bindings::_helpers::planner_phases::objects::object;
use crate::bindings::_helpers::planner_strategy::audits::{
    reads_outside_target_lineage, resolve_attachment_kind, resolve_effective_run_scope,
};
use crate::bindings::_helpers::records::construct::{enum_from_value, new_record, new_record_with};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::pyfunction;
use pyo3::types::{
    PyBool, PyDict, PyDictMethods, PyList, PyListMethods, PyString, PyTuple, PyTupleMethods,
};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::imported;

use crate::bindings::_helpers::planner_strategy::constants::{
    AUDIT_TYPES_MODULE, COMPILE_TYPES_MODULE, MODEL_ATTACHMENT, SOURCE_ATTACHMENT,
};
use crate::bindings::_helpers::planner_strategy::models::AuditPlanning;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_get;
use crate::bindings::_helpers::records::ids::RecordId;

/// Render and validate one audit query with the supplied adapter callbacks.
fn render_query<'py>(
    request: &AuditPlanning<'py>,
    sql: Bound<'py, PyAny>,
    context: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let py = sql.py();
    let resolved = object(
        py,
        render_audit_sql(Some(&keywords(
            py,
            &[
                ("unresolved_sql", sql),
                ("model_locations", request.model_locations.clone()),
                ("seed_locations", request.seed_locations.clone()),
                ("source_map", request.source_map.clone()),
                ("adapter", request.adapter.clone()),
            ],
        )?))?,
    )?;
    object(
        py,
        assert_no_unresolved_sql_markers(py, resolved.downcast::<PyString>()?, context)?,
    )?;
    Ok(resolved)
}

/// Resolve an audit enum, applying the default only to absent values.
fn audit_enum<'py>(
    audit: &Bound<'py, PyAny>,
    attribute: &str,
    enum_name: &str,
    default: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let py = audit.py();
    let value = native_field(audit, attribute)?;
    imported(py, AUDIT_TYPES_MODULE, enum_name)?.call1((if value.is_none() {
        PyString::new(py, default).into_any()
    } else {
        value
    },))
}

/// Build an audit entry while retaining the public Python plan dataclass.
#[pyfunction(name = "plan_audit")]
#[pyo3(signature = (**request))]
pub(crate) fn plan_audit_of<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let request = Request::new("plan_audit", request)?;
    plan_audit(
        &request.get("audit")?,
        &AuditPlanning {
            model_locations: request.get("model_locations")?,
            seed_locations: request.get("seed_locations")?,
            source_map: request.get("source_map")?,
            adapter: request.get("adapter")?,
            model_materializations: request.get("model_materializations")?,
            lineage_upstream_deps: request.get("lineage_upstream_deps")?,
            lineage_downstream_deps: request.get("lineage_downstream_deps")?,
        },
    )
}

/// One audit's plan entry, rendered against the planning relations.
fn plan_audit<'py>(
    audit: &Bound<'py, PyAny>,
    request: &AuditPlanning<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = audit.py();
    let audit = audit.clone();
    let name: String = native_field(&audit, "name")?.extract()?;
    let resolved = render_query(
        request,
        native_field(&audit, "sql_body")?,
        &format!("audit '{name}' planned SQL"),
    )?;
    let evidence = native_field(&audit, "evidence_sql")?;
    let evidence_resolved = if evidence.is_none() {
        py.None().into_bound(py)
    } else {
        render_query(
            request,
            evidence,
            &format!("audit '{name}' planned evidence SQL"),
        )?
    };
    let attachment: Bound<'_, PyTuple> =
        resolve_attachment_kind(&audit, &request.lineage_downstream_deps)?;
    let kind = attachment.get_item(0)?;
    let target = attachment.get_item(1)?;
    let kind_text: String = kind.extract()?;
    let materialization = if kind_text == MODEL_ATTACHMENT && !target.is_none() {
        mapping_get(&request.model_materializations, &target)?
    } else {
        py.None().into_bound(py)
    };
    let requested = audit_enum(&audit, "run_scope", "AuditRunScope", "final")?;
    let severity = audit_enum(&audit, "severity", "AuditSeverity", "warn")?;
    let effective = resolve_effective_run_scope(&requested, &materialization)?;
    let mut target_kind = native_field(&audit, "attached_target_kind")?;
    if target_kind.is_none() && (kind_text == MODEL_ATTACHMENT || kind_text == SOURCE_ATTACHMENT) {
        target_kind =
            imported(py, COMPILE_TYPES_MODULE, "AttachedAuditTargetKind")?.call1((kind_text,))?;
    }
    let values = PyDict::new(py);
    for field in [
        "key",
        "name",
        "definition_name",
        "evaluation_mode",
        "thresholds",
        "minimum_samples",
        "evidence_limit",
        "scope_deps",
        "attached_column_name",
        "always_run",
        "description",
        "meta",
    ] {
        values.set_item(field, native_field(&audit, field)?)?;
    }
    let measurement = native_field(&audit, "measurement_contract")?;
    for field in ["value_column", "sample_count_column", "sample_unit"] {
        values.set_item(
            field,
            if measurement.is_none() {
                py.None().into_bound(py)
            } else {
                native_field(&measurement, field)?
            },
        )?;
    }
    for (field, value) in [
        ("resolved_sql", resolved),
        ("unresolved_sql", native_field(&audit, "sql_body")?),
        ("attachment_kind", kind),
        ("severity", severity),
        ("requested_run_scope", requested),
        ("effective_run_scope", effective),
        ("evidence_resolved_sql", evidence_resolved),
        (
            "evidence_unresolved_sql",
            native_field(&audit, "evidence_sql")?,
        ),
        ("attached_target_kind", target_kind),
        ("attached_target_name", target),
        (
            "reads_outside_target_lineage",
            PyBool::new(
                py,
                reads_outside_target_lineage(&audit, &request.lineage_upstream_deps)?,
            )
            .to_owned()
            .into_any(),
        ),
    ] {
        values.set_item(field, value)?;
    }
    new_record(py, RecordId::AuditPlanEntry, (), Some(&values))
}

/// Select attached audits by their logical target and singular audits by dependency overlap.
#[pyfunction]
#[pyo3(signature = (*, audit, selected_keys))]
pub(crate) fn audit_is_selected(
    audit: &Bound<'_, PyAny>,
    selected_keys: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    let py = audit.py();
    let kind = native_field(audit, "attached_target_kind")?;
    let name = native_field(audit, "attached_target_name")?;
    if !kind.is_none() && !name.is_none() {
        let target_value = imported(py, COMPILE_TYPES_MODULE, "AttachedAuditTargetKind")?
            .call1((kind,))?
            .getattr("value")?;
        let resource_type = enum_from_value(py, RecordId::CompiledResourceType, target_value)?;
        let key = new_record_with(
            py,
            RecordId::CompiledObjectKey,
            &[("resource_type", resource_type), ("name", name)],
        )?;
        return selected_keys.contains(key);
    }
    for dependency in native_field(audit, "scope_deps")?.try_iter()? {
        if selected_keys.contains(dependency?)? {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Assemble selected audits in compiled-project order without querying lineage for an empty selection.
#[pyfunction]
#[pyo3(signature = (**request))]
pub(crate) fn build_selected_audit_entries<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyList>> {
    let request = Request::new("build_selected_audit_entries", request)?;
    let py = request.py();
    let project = request.get("project")?;
    let selected_keys = native_field(&request.get("scope")?, "selected_keys")?;
    let mut selected: Vec<Bound<'py, PyAny>> = Vec::new();
    for audit in native_field(&project, "audits")?.try_iter()? {
        let audit = audit?;
        if audit_is_selected(&audit, &selected_keys)? {
            selected.push(audit);
        }
    }
    let entries = PyList::empty(py);
    if selected.is_empty() {
        return Ok(entries);
    }
    let lineage = project_lineage_views(py, &project)?;
    let relations = request.get("relations")?;
    let planning = AuditPlanning {
        model_locations: native_field(&relations, "model_locations")?,
        seed_locations: native_field(&relations, "seed_locations")?,
        source_map: native_field(&relations, "source_read_map")?,
        adapter: request.get("adapter")?,
        model_materializations: request.get("model_materializations")?,
        lineage_upstream_deps: native_field(&lineage, "upstream_deps")?,
        lineage_downstream_deps: native_field(&lineage, "downstream_deps")?,
    };
    for audit in selected {
        entries.append(plan_audit(&audit, &planning)?)?;
    }
    Ok(entries)
}

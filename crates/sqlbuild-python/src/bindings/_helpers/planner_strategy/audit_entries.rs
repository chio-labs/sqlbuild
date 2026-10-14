//! Assemble audit plan dataclasses using native rendering and scheduling.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::pyfunction;
use pyo3::types::{
    PyDict, PyDictMethods, PyList, PyListMethods, PyString, PyTuple, PyTupleMethods,
};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

use crate::bindings::_helpers::planner_strategy::constants::{
    AUDIT_TYPES_MODULE, COMPILE_MODELS_MODULE, COMPILE_TYPES_MODULE, MODEL_ATTACHMENT,
    NATIVE_MODULE, PLAN_MODELS_MODULE, SOURCE_ATTACHMENT,
};

/// Render and validate one audit query with the supplied adapter callbacks.
fn render_query<'py>(
    request: &Request<'_, 'py>,
    sql: Bound<'py, PyAny>,
    context: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let py = request.py();
    let resolved = call_with(
        &imported(py, NATIVE_MODULE, "render_audit_sql")?,
        &[
            ("unresolved_sql", sql),
            ("model_locations", request.get("model_locations")?),
            ("seed_locations", request.get("seed_locations")?),
            ("source_map", request.get("source_map")?),
            ("adapter", request.get("adapter")?),
        ],
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "assert_no_unresolved_sql_markers")?,
        &[
            ("sql", resolved.clone()),
            ("context", PyString::new(py, context).into_any()),
        ],
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
    let value = audit.getattr(attribute)?;
    imported(py, AUDIT_TYPES_MODULE, enum_name)?.call1((if value.is_none() {
        PyString::new(py, default).into_any()
    } else {
        value
    },))
}

/// Build an audit entry while retaining the public Python plan dataclass.
#[pyfunction]
#[pyo3(signature = (**request))]
pub(crate) fn plan_audit<'py>(request: Option<&Bound<'py, PyDict>>) -> PyResult<Bound<'py, PyAny>> {
    let request = Request::new("plan_audit", request)?;
    let py = request.py();
    let audit = request.get("audit")?;
    let name: String = audit.getattr("name")?.extract()?;
    let resolved = render_query(
        &request,
        audit.getattr("sql_body")?,
        &format!("audit '{name}' planned SQL"),
    )?;
    let evidence = audit.getattr("evidence_sql")?;
    let evidence_resolved = if evidence.is_none() {
        py.None().into_bound(py)
    } else {
        render_query(
            &request,
            evidence,
            &format!("audit '{name}' planned evidence SQL"),
        )?
    };
    let attachment = call_with(
        &imported(py, NATIVE_MODULE, "resolve_attachment_kind")?,
        &[
            ("audit", audit.clone()),
            ("downstream_deps", request.get("lineage_downstream_deps")?),
        ],
    )?;
    let attachment = attachment.cast::<PyTuple>()?;
    let kind = attachment.get_item(0)?;
    let target = attachment.get_item(1)?;
    let kind_text: String = kind.extract()?;
    let materialization = if kind_text == MODEL_ATTACHMENT && !target.is_none() {
        request
            .get("model_materializations")?
            .call_method1("get", (&target,))?
    } else {
        py.None().into_bound(py)
    };
    let requested = audit_enum(&audit, "run_scope", "AuditRunScope", "final")?;
    let severity = audit_enum(&audit, "severity", "AuditSeverity", "warn")?;
    let effective = call_with(
        &imported(py, NATIVE_MODULE, "resolve_effective_run_scope")?,
        &[
            ("requested_run_scope", requested.clone()),
            ("attached_model_materialization", materialization),
        ],
    )?;
    let mut target_kind = audit.getattr("attached_target_kind")?;
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
    ] {
        values.set_item(field, audit.getattr(field)?)?;
    }
    let measurement = audit.getattr("measurement_contract")?;
    for field in ["value_column", "sample_count_column", "sample_unit"] {
        values.set_item(
            field,
            if measurement.is_none() {
                py.None().into_bound(py)
            } else {
                measurement.getattr(field)?
            },
        )?;
    }
    for (field, value) in [
        ("resolved_sql", resolved),
        ("unresolved_sql", audit.getattr("sql_body")?),
        ("attachment_kind", kind),
        ("severity", severity),
        ("requested_run_scope", requested),
        ("effective_run_scope", effective),
        ("evidence_resolved_sql", evidence_resolved),
        ("evidence_unresolved_sql", audit.getattr("evidence_sql")?),
        ("attached_target_kind", target_kind),
        ("attached_target_name", target),
        (
            "reads_outside_target_lineage",
            call_with(
                &imported(py, NATIVE_MODULE, "reads_outside_target_lineage")?,
                &[
                    ("audit", audit),
                    ("upstream_deps", request.get("lineage_upstream_deps")?),
                ],
            )?,
        ),
    ] {
        values.set_item(field, value)?;
    }
    imported(py, PLAN_MODELS_MODULE, "AuditPlanEntry")?.call((), Some(&values))
}

/// Select attached audits by their logical target and singular audits by dependency overlap.
#[pyfunction]
#[pyo3(signature = (*, audit, selected_keys))]
pub(crate) fn audit_is_selected(
    audit: &Bound<'_, PyAny>,
    selected_keys: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    let py = audit.py();
    let kind = audit.getattr("attached_target_kind")?;
    let name = audit.getattr("attached_target_name")?;
    if !kind.is_none() && !name.is_none() {
        let resource_type = imported(py, COMPILE_TYPES_MODULE, "AttachedAuditTargetKind")?
            .call1((kind,))?
            .getattr("resource_type")?;
        let key = call_with(
            &imported(py, COMPILE_MODELS_MODULE, "CompiledObjectKey")?,
            &[("resource_type", resource_type), ("name", name)],
        )?;
        return selected_keys.contains(key);
    }
    for dependency in audit.getattr("scope_deps")?.try_iter()? {
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
    let selected_keys = request.get("scope")?.getattr("selected_keys")?;
    let mut selected: Vec<Bound<'py, PyAny>> = Vec::new();
    for audit in project.getattr("audits")?.try_iter()? {
        let audit = audit?;
        if audit_is_selected(&audit, &selected_keys)? {
            selected.push(audit);
        }
    }
    let entries = PyList::empty(py);
    if selected.is_empty() {
        return Ok(entries);
    }
    let lineage = imported(py, NATIVE_MODULE, "project_lineage_views")?.call1((project,))?;
    let relations = request.get("relations")?;
    let arguments = PyDict::new(py);
    for field in ["model_locations", "seed_locations"] {
        arguments.set_item(field, relations.getattr(field)?)?;
    }
    arguments.set_item("source_map", relations.getattr("source_read_map")?)?;
    arguments.set_item("adapter", request.get("adapter")?)?;
    arguments.set_item(
        "model_materializations",
        request.get("model_materializations")?,
    )?;
    arguments.set_item("lineage_upstream_deps", lineage.getattr("upstream_deps")?)?;
    arguments.set_item(
        "lineage_downstream_deps",
        lineage.getattr("downstream_deps")?,
    )?;
    for audit in selected {
        arguments.set_item("audit", audit)?;
        entries.append(plan_audit(Some(&arguments))?)?;
    }
    Ok(entries)
}

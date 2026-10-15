//! Audit gate identities of planned audits, built as `AuditGateIdentity` objects.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_analysis::auditing::main::audit_gate_identity::audit_gate_identity;
use sqlbuild_analysis::auditing::models::{
    GateIdentity, MeasurementFacts, PlannedAudit, ThresholdBound, Thresholds,
};

const AUDITING_MODELS_MODULE: &str = "sqlbuild._native";
const MEASUREMENT_MODE: &str = "measurement";

fn enum_value(value: &Bound<'_, PyAny>) -> PyResult<String> {
    value.getattr("value")?.extract()
}

/// One `MeasurementThresholdBound`, or `None`.
pub(crate) fn threshold_bound(bound: &Bound<'_, PyAny>) -> PyResult<Option<ThresholdBound>> {
    if bound.is_none() {
        return Ok(None);
    }
    let operator: String = enum_value(&bound.getattr("operator")?)?;
    Ok(Some(match operator.as_str() {
        "below" => ThresholdBound::Below(bound.getattr("limit")?.extract()?),
        "above" => ThresholdBound::Above(bound.getattr("limit")?.extract()?),
        _ => ThresholdBound::Outside(
            bound.getattr("lower")?.extract()?,
            bound.getattr("upper")?.extract()?,
        ),
    }))
}

/// One `MeasurementThresholds`, or `None`.
pub(crate) fn thresholds(value: &Bound<'_, PyAny>) -> PyResult<Option<Thresholds>> {
    if value.is_none() {
        return Ok(None);
    }
    Ok(Some(Thresholds {
        warn: threshold_bound(&value.getattr("warn")?)?,
        error: threshold_bound(&value.getattr("error")?)?,
    }))
}

fn planned_audit(audit: &Bound<'_, PyAny>) -> PyResult<PlannedAudit> {
    let measurement: Option<MeasurementFacts> =
        if enum_value(&audit.getattr("evaluation_mode")?)? == MEASUREMENT_MODE {
            Some(MeasurementFacts {
                value_column: audit.getattr("value_column")?.extract()?,
                sample_count_column: audit.getattr("sample_count_column")?.extract()?,
                sample_unit: audit.getattr("sample_unit")?.extract()?,
                thresholds: thresholds(&audit.getattr("thresholds")?)?,
                minimum_samples: audit.getattr("minimum_samples")?.extract()?,
                evidence_unresolved_sql: audit.getattr("evidence_unresolved_sql")?.extract()?,
                evidence_resolved_sql: audit.getattr("evidence_resolved_sql")?.extract()?,
            })
        } else {
            None
        };
    Ok(PlannedAudit {
        name: audit.getattr("name")?.extract()?,
        attachment_kind: enum_value(&audit.getattr("attachment_kind")?)?,
        attached_target_name: audit.getattr("attached_target_name")?.extract()?,
        attached_column_name: audit.getattr("attached_column_name")?.extract()?,
        severity: enum_value(&audit.getattr("severity")?)?,
        run_scope: enum_value(&audit.getattr("effective_run_scope")?)?,
        always_run: audit.getattr("always_run")?.is_truthy()?,
        unresolved_sql: audit.getattr("unresolved_sql")?.extract()?,
        resolved_sql: audit.getattr("resolved_sql")?.extract()?,
        measurement,
    })
}

fn keyword_call<'py>(
    callable: &Bound<'py, PyAny>,
    pairs: Vec<(&str, Bound<'py, PyAny>)>,
) -> PyResult<Bound<'py, PyAny>> {
    let keywords: Bound<'py, PyDict> = PyDict::new(callable.py());
    for (name, value) in pairs {
        keywords.set_item(name, value)?;
    }
    callable.call((), Some(&keywords))
}

/// Target-neutral and target-specific identity hashes for planned audits.
#[pyfunction]
#[pyo3(signature = (*, audits))]
fn build_audit_gate_identity<'py>(
    py: Python<'py>,
    audits: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let entries: Vec<Bound<'py, PyAny>> = audits.try_iter()?.collect::<PyResult<_>>()?;
    let planned: Vec<PlannedAudit> = entries.iter().map(planned_audit).collect::<PyResult<_>>()?;
    let gate: GateIdentity = audit_gate_identity(&planned);
    let models: Bound<'py, PyModule> = py.import(AUDITING_MODELS_MODULE)?;
    let identity_type: Bound<'py, PyAny> = models.getattr("AuditIdentity")?;
    let mut identities: Vec<Bound<'py, PyAny>> = Vec::with_capacity(gate.audits.len());
    for identity in gate.audits {
        let entry: &Bound<'py, PyAny> = &entries[identity.index];
        identities.push(keyword_call(
            &identity_type,
            vec![
                (
                    "binding_key",
                    identity.binding_key.into_pyobject(py)?.into_any(),
                ),
                ("audit_name", entry.getattr("name")?),
                (
                    "definition_fingerprint",
                    identity
                        .definition_fingerprint
                        .into_pyobject(py)?
                        .into_any(),
                ),
                (
                    "execution_fingerprint",
                    identity.execution_fingerprint.into_pyobject(py)?.into_any(),
                ),
                ("severity", entry.getattr("severity")?),
                (
                    "run_scope_phase",
                    entry.getattr("effective_run_scope")?.getattr("value")?,
                ),
                (
                    "attachment_kind",
                    entry.getattr("attachment_kind")?.getattr("value")?,
                ),
                (
                    "attached_target_name",
                    entry.getattr("attached_target_name")?,
                ),
                (
                    "attached_column_name",
                    entry.getattr("attached_column_name")?,
                ),
                ("always_run", entry.getattr("always_run")?),
            ],
        )?);
    }
    keyword_call(
        &models.getattr("AuditGateIdentity")?,
        vec![
            (
                "binding_set_hash",
                gate.binding_set_hash.into_pyobject(py)?.into_any(),
            ),
            (
                "blocking_set_hash",
                gate.blocking_set_hash.into_pyobject(py)?.into_any(),
            ),
            ("audits", PyTuple::new(py, identities)?.into_any()),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_audit_gate_identity, module)?)?;
    Ok(())
}

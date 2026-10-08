//! Attached generic audit rendering for the preview compile attachments.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::types::PyDict;
use pyo3::{FromPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_attachments::audits::main::render_attached_audit::render_attached_audit;
use sqlbuild_attachments::audits::models::{AuditAttachment, PolicySource, RenderedAudit};

use crate::bindings::_helpers::attachments::argument_values::argument_pairs;
use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// `(sql body, evidence sql, severity, run scope source)`.
type RenderedRow = (String, Option<String>, &'static str, &'static str);

/// Authored policies of one attachment: mode and threshold flags, severities and run scopes.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct AuditPolicies {
    measurement: bool,
    has_thresholds: bool,
    has_minimum_samples: bool,
    threshold_error: bool,
    instance_severity: Option<String>,
    default_severity: Option<String>,
    instance_run_scope: Option<String>,
    default_run_scope: Option<String>,
}

/// Render `(sql body, evidence)` with `(implicit, explicit)` arguments, or `None` for Python.
#[pyfunction]
fn render_attached_generic_audit(
    sql: (String, Option<String>),
    arguments: (Bound<'_, PyDict>, Bound<'_, PyDict>),
    policies: AuditPolicies,
) -> PyResult<Option<RenderedRow>> {
    compiler_guard(|| {
        let (Some(implicit), Some(explicit)) =
            (argument_pairs(&arguments.0)?, argument_pairs(&arguments.1)?)
        else {
            return Ok(None);
        };
        let attachment: AuditAttachment = AuditAttachment {
            sql_body: sql.0,
            evidence_sql: sql.1,
            implicit_arguments: implicit,
            explicit_arguments: explicit,
            measurement: policies.measurement,
            has_thresholds: policies.has_thresholds,
            has_minimum_samples: policies.has_minimum_samples,
            threshold_error: policies.threshold_error,
            instance_severity: policies.instance_severity,
            default_severity: policies.default_severity,
            instance_run_scope: policies.instance_run_scope,
            default_run_scope: policies.default_run_scope,
        };
        Ok(render_attached_audit(&attachment).map(rendered_row))
    })
}

fn rendered_row(rendered: RenderedAudit) -> RenderedRow {
    let source: &'static str = match rendered.run_scope_source {
        PolicySource::Instance => "instance",
        PolicySource::Default => "default",
        PolicySource::Fallback => "fallback",
    };
    (
        rendered.sql_body,
        rendered.evidence_sql,
        rendered.severity,
        source,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(render_attached_generic_audit, module)?)?;
    Ok(())
}

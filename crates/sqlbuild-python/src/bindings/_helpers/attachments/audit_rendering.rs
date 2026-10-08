//! Attached generic audit rendering for the preview compile attachments.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::types::PyDict;
use pyo3::{FromPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_attachments::audits::main::render_attached_audit::render_attached_audit;
use sqlbuild_attachments::audits::models::{AuditAttachment, AuditRendering, PolicySource};

use crate::bindings::_helpers::attachments::argument_values::argument_pairs;
use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// `(render error, sql body, evidence sql, severity, run scope source, policy error)`.
type RenderedRow = (
    Option<String>,
    String,
    Option<String>,
    &'static str,
    &'static str,
    Option<String>,
);

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

/// Render one `(owner, audit)` attachment with Python's errors, or `None` for Python.
#[pyfunction]
fn render_attached_generic_audit(
    labels: (String, String),
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
            owner_label: labels.0,
            definition_name: labels.1,
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

fn rendered_row(rendering: AuditRendering) -> RenderedRow {
    let rendered = match rendering {
        AuditRendering::Failed(message) => {
            return (Some(message), String::new(), None, "", "", None);
        }
        AuditRendering::Rendered(rendered) => rendered,
    };
    let (severity, source, policy_error): (&'static str, &'static str, Option<String>) =
        match rendered.policies {
            Ok((severity, source)) => (severity, source_name(source), None),
            Err(message) => ("", "", Some(message)),
        };
    (
        None,
        rendered.sql_body,
        rendered.evidence_sql,
        severity,
        source,
        policy_error,
    )
}

fn source_name(source: PolicySource) -> &'static str {
    match source {
        PolicySource::Instance => "instance",
        PolicySource::Default => "default",
        PolicySource::Fallback => "fallback",
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(render_attached_generic_audit, module)?)?;
    Ok(())
}

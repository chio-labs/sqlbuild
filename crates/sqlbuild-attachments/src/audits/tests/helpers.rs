use crate::audits::_helpers::parameters::render_parameterized_sql;
use crate::audits::main::render_attached_audit::render_attached_audit;
use crate::audits::models::{ArgumentValue, AuditAttachment, RenderedAudit};

/// Arguments shared by the parameter rendering cases.
pub(super) fn order_arguments() -> Vec<(String, ArgumentValue)> {
    vec![
        (
            "column".to_owned(),
            ArgumentValue::Text("status".to_owned()),
        ),
        (
            "values".to_owned(),
            ArgumentValue::List(vec![
                ArgumentValue::Text("it's".to_owned()),
                ArgumentValue::Number("2".to_owned()),
                ArgumentValue::Null,
                ArgumentValue::Boolean(true),
            ]),
        ),
    ]
}

pub(super) fn rendered_sql(sql: &str, reject_unused: bool) -> Option<String> {
    render_parameterized_sql(sql, &order_arguments(), reject_unused)
}

/// A violations audit over `@column` with the given explicit arguments and policies.
pub(super) fn attachment(
    explicit: Vec<(String, ArgumentValue)>,
    severity: Option<&str>,
    run_scope: Option<&str>,
) -> AuditAttachment {
    AuditAttachment {
        sql_body: "SELECT * FROM t WHERE @column NOT IN (@'values')".to_owned(),
        evidence_sql: Some("SELECT @column FROM t".to_owned()),
        implicit_arguments: vec![(
            "column".to_owned(),
            ArgumentValue::Text("status".to_owned()),
        )],
        explicit_arguments: explicit,
        measurement: false,
        has_thresholds: false,
        has_minimum_samples: false,
        threshold_error: false,
        instance_severity: severity.map(str::to_owned),
        default_severity: None,
        instance_run_scope: run_scope.map(str::to_owned),
        default_run_scope: None,
    }
}

pub(super) fn rendering_text(attachment: &AuditAttachment) -> Option<String> {
    let rendered: RenderedAudit = render_attached_audit(attachment)?;
    Some(format!(
        "{} | {} | {} | {:?}",
        rendered.sql_body,
        rendered.evidence_sql.unwrap_or_default(),
        rendered.severity,
        rendered.run_scope_source
    ))
}

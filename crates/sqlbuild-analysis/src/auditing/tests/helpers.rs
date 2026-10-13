use crate::auditing::models::{MeasurementFacts, PlannedAudit, ThresholdBound, Thresholds};

pub(crate) fn planned(
    name: &str,
    severity: &str,
    measurement: Option<MeasurementFacts>,
) -> PlannedAudit {
    PlannedAudit {
        name: name.to_owned(),
        attachment_kind: "model".to_owned(),
        attached_target_name: Some("orders".to_owned()),
        attached_column_name: measurement.is_none().then(|| "order_id".to_owned()),
        severity: severity.to_owned(),
        run_scope: "final".to_owned(),
        always_run: false,
        unresolved_sql: "SELECT  *\n FROM __ref(\"orders\")".to_owned(),
        resolved_sql: "SELECT * FROM main.orders".to_owned(),
        measurement,
    }
}

pub(crate) fn ratio_measurement() -> MeasurementFacts {
    MeasurementFacts {
        value_column: Some("ratio".to_owned()),
        sample_count_column: Some("n".to_owned()),
        sample_unit: Some("rows".to_owned()),
        thresholds: Some(Thresholds {
            warn: Some(ThresholdBound::Outside(0.1, 1e16)),
            error: Some(ThresholdBound::Outside(0.0, 2e16)),
        }),
        minimum_samples: Some(10),
        evidence_unresolved_sql: None,
        evidence_resolved_sql: Some("SELECT 1  ".to_owned()),
    }
}

use crate::build_progress::models::{
    AuditResultText, ErrorText, ModelResultText, ProgressLayout, TestResultText, TestStepText,
};

pub(super) fn layout(verbose: bool) -> ProgressLayout {
    ProgressLayout {
        total: 3,
        name_width: 24,
        columns: 80,
        verbose,
    }
}

pub(super) fn model(name: &str, status: &str) -> ModelResultText {
    ModelResultText {
        name: name.to_owned(),
        status: status.to_owned(),
        duration_ms: Some(1234.0),
        ..ModelResultText::default()
    }
}

pub(super) fn failed_model(name: &str, message: &str) -> ModelResultText {
    ModelResultText {
        failed_phase: Some("staging".to_owned()),
        error: ErrorText {
            code: Some("E100".to_owned()),
            message: Some(message.to_owned()),
            help: None,
        },
        ..model(name, "failed")
    }
}

pub(super) fn audit(name: &str, outcome: &str, row_count: i64) -> AuditResultText {
    AuditResultText {
        audit_name: name.to_owned(),
        run_scope_phase: "final".to_owned(),
        outcome: outcome.to_owned(),
        row_count,
        measured_value: "None".to_owned(),
        ..AuditResultText::default()
    }
}

pub(super) fn test(label: &str, outcome: &str, step_outcome: &str) -> TestResultText {
    TestResultText {
        label: label.to_owned(),
        outcome: outcome.to_owned(),
        steps: vec![TestStepText {
            model_name: "orders".to_owned(),
            outcome: step_outcome.to_owned(),
            detail: String::new(),
        }],
        error: ErrorText::default(),
    }
}

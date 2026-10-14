use crate::build_command::main::plan_safety_steps::plan_safety_steps;
use crate::build_command::models::{
    ModelLimit, ModelMigrationFact, PlanSafetyFacts, PlanSafetyGates, PolicyStep, RetentionFact,
    SnapshotPolicies, SnapshotRefreshFact, TableTypeFact,
};

/// Build-command gates with every allow flag off.
pub(super) fn build_gates() -> PlanSafetyGates {
    PlanSafetyGates {
        missing_origin_help: "origin help".to_owned(),
        snapshot_full_refresh_help: "snapshot help".to_owned(),
        table_type_downgrade_help: "table help".to_owned(),
        retention_decrease_help: "retention help".to_owned(),
        execution_limit_note: "No warehouse changes were made.".to_owned(),
        ..PlanSafetyGates::default()
    }
}

/// Each step as one comparable line.
pub(super) fn described_steps(
    facts: &PlanSafetyFacts,
    gates: &PlanSafetyGates,
    max_models: Option<i64>,
) -> Vec<String> {
    let limit: ModelLimit = ModelLimit {
        target_name: Some("dev".to_owned()),
        max_models,
        remediation: None,
    };
    let policies: SnapshotPolicies = SnapshotPolicies {
        historical: "require_confirmation".to_owned(),
        current_state: "deny".to_owned(),
    };
    plan_safety_steps(facts, gates, (&limit, &policies)).map_or_else(
        |error| vec![format!("error:{}", error.message)],
        |steps| steps.iter().map(describe_step).collect(),
    )
}

fn describe_step(step: &PolicyStep) -> String {
    let refusal: Option<String> = step.refusal().map(|error| {
        format!(
            "refuse:{}:{}",
            error.code.clone().unwrap_or_default(),
            error.message
        )
    });
    let confirmation: Option<String> = step.confirmation().map(|confirmation| {
        format!(
            "confirm:{}:{}:{}",
            confirmation.expected, confirmation.refusal.message, confirmation.cancellation.message
        )
    });
    refusal.or(confirmation).unwrap_or_default()
}

pub(super) fn missing_origin(name: &str) -> ModelMigrationFact {
    ModelMigrationFact {
        model_name: name.to_owned(),
        origin_label: format!("old_{name}"),
        decision: "origin_missing".to_owned(),
        origin_missing: true,
        confirm_missing_origin: true,
        ..ModelMigrationFact::default()
    }
}

pub(super) fn snapshot(
    name: &str,
    historical: bool,
    model_policy: Option<&str>,
) -> SnapshotRefreshFact {
    SnapshotRefreshFact {
        name: name.to_owned(),
        historical,
        model_policy: model_policy.map(str::to_owned),
    }
}

pub(super) fn table_type(name: &str, policy: &str) -> TableTypeFact {
    TableTypeFact {
        model_name: name.to_owned(),
        policy: policy.to_owned(),
    }
}

pub(super) fn retention(names: &[&str], policy: &str) -> RetentionFact {
    RetentionFact {
        model_names: names.iter().map(|name| (*name).to_owned()).collect(),
        policy: policy.to_owned(),
    }
}

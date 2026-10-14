//! Snapshot full-refresh, table-type downgrade and retention decrease gates.

use crate::build_command::constants::{
    POLICY_ALLOW, POLICY_DENY, POLICY_REQUIRE_CONFIRMATION, RETENTION_DENIED_HELP,
    SNAPSHOT_CANCELLED_CODE, SNAPSHOT_CONFIRMATION_CODE, SNAPSHOT_DENIED_CODE,
    SNAPSHOT_DENIED_HELP,
};
use crate::build_command::errors::BuildCommandError;
use crate::build_command::models::{
    Confirmation, PolicyStep, RetentionFact, SnapshotPolicies, SnapshotRefreshFact, TableTypeFact,
};

fn strictness(policy: &str) -> Result<u8, BuildCommandError> {
    match policy {
        POLICY_ALLOW => Ok(0),
        POLICY_REQUIRE_CONFIRMATION => Ok(1),
        POLICY_DENY => Ok(2),
        _ => Err(BuildCommandError::new(
            None,
            format!("'{policy}' is not a valid SnapshotFullRefreshPolicy"),
            None,
        )),
    }
}

fn effective_snapshot_policy<'a>(
    entry: &'a SnapshotRefreshFact,
    policies: &'a SnapshotPolicies,
) -> Result<&'a str, BuildCommandError> {
    let project: &str = if entry.historical {
        &policies.historical
    } else {
        &policies.current_state
    };
    let project_strictness: u8 = strictness(project)?;
    let Some(model) = entry.model_policy.as_deref() else {
        return Ok(project);
    };
    if strictness(model)? > project_strictness {
        return Ok(model);
    }
    Ok(project)
}

fn quoted(names: &[&str]) -> String {
    names
        .iter()
        .map(|name| format!("'{name}'"))
        .collect::<Vec<String>>()
        .join(", ")
}

fn confirmation(
    (warning, expected): (String, String),
    (subject, help): (&str, &str),
    codes: (Option<&str>, Option<&str>),
) -> Confirmation {
    Confirmation {
        warning,
        expected,
        refusal: BuildCommandError::new(
            codes.0,
            format!("{subject} requires confirmation"),
            Some(help),
        ),
        cancellation: BuildCommandError::new(codes.1, format!("{subject} cancelled"), None),
    }
}

/// Fail or confirm before executing protected snapshot full refreshes.
pub(crate) fn snapshot_steps(
    entries: &[SnapshotRefreshFact],
    policies: &SnapshotPolicies,
    (allowed, help): (bool, &str),
) -> Result<Option<PolicyStep>, BuildCommandError> {
    let mut denied: Vec<&str> = Vec::new();
    let mut confirm: Vec<&str> = Vec::new();
    for entry in entries {
        match effective_snapshot_policy(entry, policies)? {
            POLICY_DENY => denied.push(&entry.name),
            POLICY_REQUIRE_CONFIRMATION => confirm.push(&entry.name),
            _ => {}
        }
    }
    if !denied.is_empty() {
        return Ok(Some(PolicyStep::Refuse(BuildCommandError::new(
            Some(SNAPSHOT_DENIED_CODE),
            format!(
                "full refresh is denied for snapshot model {} by snapshot_full_refresh policy",
                quoted(&denied)
            ),
            Some(SNAPSHOT_DENIED_HELP),
        ))));
    }
    if confirm.is_empty() || allowed {
        return Ok(None);
    }
    let expected: String = if confirm.len() == 1 {
        format!("discard snapshot history for {}", confirm[0])
    } else {
        format!("discard snapshot history for {} models", confirm.len())
    };
    Ok(Some(PolicyStep::Confirm(confirmation(
        (
            format!(
                "Full refresh of snapshot model {} may permanently discard unrecoverable history.",
                quoted(&confirm)
            ),
            expected,
        ),
        ("snapshot full refresh", help),
        (
            Some(SNAPSHOT_CONFIRMATION_CODE),
            Some(SNAPSHOT_CANCELLED_CODE),
        ),
    ))))
}

/// Fail or confirm before executing permanent-to-transient conversions.
pub(crate) fn table_type_step(
    entries: &[TableTypeFact],
    (allowed, help): (bool, &str),
) -> Option<PolicyStep> {
    let denied: Vec<&str> = entries
        .iter()
        .filter(|entry| entry.policy == POLICY_DENY)
        .map(|entry| entry.model_name.as_str())
        .collect();
    if !denied.is_empty() {
        return Some(PolicyStep::Refuse(BuildCommandError::new(
            None,
            format!(
                "table-type downgrade is denied for {} by table_type_downgrade policy",
                quoted(&denied)
            ),
            None,
        )));
    }
    let confirm: Vec<&str> = entries
        .iter()
        .filter(|entry| entry.policy == POLICY_REQUIRE_CONFIRMATION)
        .map(|entry| entry.model_name.as_str())
        .collect();
    if confirm.is_empty() || allowed {
        return None;
    }
    let expected: String = if confirm.len() == 1 {
        format!("downgrade table type for {}", confirm[0])
    } else {
        format!("downgrade table type for {} models", confirm.len())
    };
    Some(PolicyStep::Confirm(confirmation(
        (
            format!(
                "Downgrading {} to transient may discard up to 90 days of time-travel history.",
                quoted(&confirm)
            ),
            expected,
        ),
        ("table-type downgrade", help),
        (None, None),
    )))
}

fn retention_names<'a>(entries: &[&'a RetentionFact]) -> Vec<&'a str> {
    let mut names: Vec<&str> = Vec::new();
    for entry in entries {
        for name in &entry.model_names {
            if !names.contains(&name.as_str()) {
                names.push(name);
            }
        }
    }
    names
}

/// Fail or confirm before lowering live time-travel retention.
pub(crate) fn retention_step(
    entries: &[RetentionFact],
    (allowed, help): (bool, &str),
) -> Option<PolicyStep> {
    let denied: Vec<&RetentionFact> = entries
        .iter()
        .filter(|entry| entry.policy == POLICY_DENY)
        .collect();
    if !denied.is_empty() {
        return Some(PolicyStep::Refuse(BuildCommandError::new(
            None,
            format!(
                "time travel retention decrease is denied for {}",
                quoted(&retention_names(&denied))
            ),
            Some(RETENTION_DENIED_HELP),
        )));
    }
    let confirm: Vec<&RetentionFact> = entries
        .iter()
        .filter(|entry| entry.policy == POLICY_REQUIRE_CONFIRMATION)
        .collect();
    if confirm.is_empty() || allowed {
        return None;
    }
    let names: Vec<&str> = retention_names(&confirm);
    let expected: String = if names.len() == 1 {
        format!("decrease retention for {}", names[0])
    } else {
        format!("decrease retention for {} models", names.len())
    };
    Some(PolicyStep::Confirm(confirmation(
        (
            format!(
                "Decreasing time travel retention for {} permanently discards history older than the new retention.",
                quoted(&names)
            ),
            expected,
        ),
        ("time travel retention decrease", help),
        (None, None),
    )))
}

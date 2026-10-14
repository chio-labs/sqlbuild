//! Origin column compatibility under incremental and snapshot policies.

use crate::planner_migrations::constants::{
    COLUMN_ADDED, COLUMN_TYPE_CHANGED, POLICY_DENY, POLICY_FAIL,
};
use crate::planner_migrations::models::CompatibilityFinding;
use crate::type_system::main::normalize_type::normalize_type;
use crate::type_system::models::TypeFamily;

/// Return blocking findings in their original order.
pub(crate) fn compatibility_findings(
    findings: &[CompatibilityFinding],
    policy: (&str, bool),
    dialect: &str,
) -> Result<Vec<String>, String> {
    let (policy, snapshot) = policy;
    let mut blocking: Vec<String> = Vec::new();
    for finding in findings {
        let suffix = if snapshot {
            if finding.kind == COLUMN_TYPE_CHANGED && !convertible(finding, dialect, true)? {
                Some("snapshot type change")
            } else if finding.kind == COLUMN_ADDED && policy == POLICY_DENY {
                Some("snapshot_schema_change deny")
            } else {
                None
            }
        } else if policy == POLICY_FAIL {
            Some("on_schema_change fail")
        } else if finding.kind == COLUMN_TYPE_CHANGED && !convertible(finding, dialect, false)? {
            Some("incompatible types")
        } else {
            None
        };
        if let Some(suffix) = suffix {
            blocking.push(format!("{} ({suffix})", describe(finding)));
        }
    }
    Ok(blocking)
}

fn describe(finding: &CompatibilityFinding) -> String {
    let name = &finding.column_name;
    match finding.kind.as_str() {
        "column_added" => format!("column {name} is missing from the origin"),
        "column_removed" => format!("origin column {name} is not produced by the model"),
        _ => format!(
            "column {name} is {} in the origin but the model produces {}",
            finding.actual_type.as_deref().unwrap_or("None"),
            finding.expected_type.as_deref().unwrap_or("None")
        ),
    }
}

fn convertible(
    finding: &CompatibilityFinding,
    dialect: &str,
    snapshot: bool,
) -> Result<bool, String> {
    let (Some(expected), Some(actual)) = (&finding.expected_type, &finding.actual_type) else {
        return Ok(true);
    };
    let incoming = normalize_type(expected, dialect)
        .map_err(|error| error.message())?
        .normalized;
    let target = normalize_type(actual, dialect)
        .map_err(|error| error.message())?
        .normalized;
    if snapshot {
        if incoming == target {
            return Ok(true);
        }
        if incoming.family != TypeFamily::String || target.family != TypeFamily::String {
            return Ok(false);
        }
        return Ok(match (&incoming.length, &target.length) {
            (_, None) => true,
            (Some(incoming), Some(target)) => integer_le(incoming.as_str(), target.as_str()),
            (None, Some(_)) => false,
        });
    }
    Ok(incoming.family == target.family
        || incoming.family == TypeFamily::Other
        || target.family == TypeFamily::Other
        || numeric(incoming.family) && numeric(target.family)
        || temporal(incoming.family) && temporal(target.family))
}

fn integer_le(left: &str, right: &str) -> bool {
    let left_negative = left.starts_with('-');
    let right_negative = right.starts_with('-');
    if left_negative != right_negative {
        return left_negative;
    }
    let order = (left.len(), left).cmp(&(right.len(), right));
    if left_negative {
        order.is_ge()
    } else {
        order.is_le()
    }
}

fn numeric(family: TypeFamily) -> bool {
    matches!(
        family,
        TypeFamily::Integer | TypeFamily::Decimal | TypeFamily::Float
    )
}

fn temporal(family: TypeFamily) -> bool {
    matches!(
        family,
        TypeFamily::Timestamp | TypeFamily::Date | TypeFamily::Datetime
    )
}

//! Deal planned invocations across hosts.

use crate::custom_host_pool::constants::CUSTOM_RULE_PROJECT_SUBJECT;
use crate::custom_host_pool::types::{HostInvocation, HostPlan};

/// Project invocations and whole model subjects dealt round-robin across at most `hosts` plans.
#[must_use]
pub fn partition_host_plan(
    plan: &HostPlan,
    invocations: &[HostInvocation],
    hosts: usize,
) -> Vec<HostPlan> {
    let mut units: Vec<Vec<&HostInvocation>> = Vec::new();
    for invocation in invocations {
        let starts_unit: bool = invocation.1 == CUSTOM_RULE_PROJECT_SUBJECT
            || units
                .last()
                .and_then(|unit| unit.first())
                .is_none_or(|first| first.1 != invocation.1);
        if starts_unit {
            units.push(Vec::new());
        }
        if let Some(unit) = units.last_mut() {
            unit.push(invocation);
        }
    }
    let count: usize = hosts.min(units.len()).max(1);
    if count == 1 {
        return vec![plan.clone()];
    }
    let mut partitions: Vec<HostPlan> = (0..count).map(|_| empty_partition(plan)).collect();
    for (index, unit) in units.into_iter().enumerate() {
        for (code, subject) in unit {
            if let Some(Some(subjects)) = partitions[index % count].get_mut(code) {
                subjects.push(subject.clone());
            }
        }
    }
    partitions
}

/// Every planned rule with no subjects yet.
fn empty_partition(plan: &HostPlan) -> HostPlan {
    plan.keys()
        .map(|code| (code.clone(), Some(Vec::new())))
        .collect()
}

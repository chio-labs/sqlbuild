//! Planned `(rule, subject)` invocations in the order one host evaluates them.

use crate::custom_host_pool::constants::CUSTOM_RULE_PROJECT_SUBJECT;
use crate::custom_host_pool::models::HostRuleSubject;
use crate::custom_host_pool::types::{HostInvocation, HostPlan};

/// Project rules first, then each model path's selected model rules, all in rule code order.
#[must_use]
pub fn planned_invocations(
    plan: &HostPlan,
    rules: &[(String, HostRuleSubject)],
    model_paths: &[String],
) -> Vec<HostInvocation> {
    let mut planned: Vec<&(String, HostRuleSubject)> = rules
        .iter()
        .filter(|(code, _)| plan.contains_key(code))
        .collect();
    planned.sort_by(|left, right| left.0.cmp(&right.0));
    let mut invocations: Vec<HostInvocation> = planned
        .iter()
        .filter(|(_, subject)| *subject == HostRuleSubject::Project)
        .map(|(code, _)| (code.clone(), CUSTOM_RULE_PROJECT_SUBJECT.to_owned()))
        .collect();
    let model_rules: Vec<(&String, Option<&Vec<String>>)> = planned
        .iter()
        .filter(|(_, subject)| *subject == HostRuleSubject::Model)
        .map(|(code, _)| (code, plan.get(code).and_then(Option::as_ref)))
        .collect();
    if model_rules.is_empty() {
        return invocations;
    }
    for path in model_paths {
        for (code, selected) in &model_rules {
            if selected.is_none_or(|subjects| subjects.contains(path)) {
                invocations.push(((*code).clone(), path.clone()));
            }
        }
    }
    invocations
}

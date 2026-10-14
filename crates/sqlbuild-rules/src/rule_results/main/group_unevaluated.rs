//! Unevaluated findings grouped per resource and reason, in deterministic finding order.

use crate::rule_results::constants::UNEVALUATED_CODE;
use crate::rule_results::models::RuleFinding;

/// One `rules-unevaluated` finding per path and reason, then every finding sorted by location.
pub fn group_unevaluated(findings: Vec<RuleFinding>) -> Vec<RuleFinding> {
    let mut result: Vec<RuleFinding> = Vec::with_capacity(findings.len());
    let mut groups: Vec<((String, String), Vec<RuleFinding>)> = Vec::new();
    for finding in findings {
        if !finding.unevaluated {
            result.push(finding);
            continue;
        }
        let prefix: String = format!("Rule {} could not be evaluated", finding.code);
        let reason: String = finding
            .message
            .strip_prefix(&prefix)
            .unwrap_or(&finding.message)
            .trim_start_matches([':', ' '])
            .to_owned();
        let key: (String, String) = (finding.path.clone(), reason);
        match groups.iter_mut().find(|(existing, _)| *existing == key) {
            Some((_, failures)) => failures.push(finding),
            None => groups.push((key, vec![finding])),
        }
    }
    for ((_, reason), failures) in groups {
        let mut affected: Vec<String> = failures.iter().map(|f| f.code.clone()).collect();
        affected.sort();
        affected.dedup();
        let Some(first) = failures.into_iter().reduce(|best, item| {
            if (item.line, item.column) < (best.line, best.column) {
                item
            } else {
                best
            }
        }) else {
            continue;
        };
        result.push(RuleFinding {
            code: UNEVALUATED_CODE.into(),
            message: format!(
                "{} selected Rules could not evaluate this resource: {reason}",
                affected.len()
            ),
            affected_rules: affected,
            ..first
        });
    }
    result.sort_by(|left, right| {
        (&left.path, left.line, left.column, &left.code).cmp(&(
            &right.path,
            right.line,
            right.column,
            &right.code,
        ))
    });
    result
}

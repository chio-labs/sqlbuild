//! Compare the edited project's errors with the rule failures the project already had.

use std::collections::BTreeSet;

use crate::refactor_command::_helpers::baseline::{first_unused, original_path, reduced};
use crate::refactor_command::models::{BaselineComparison, RefactorDiagnostic};
use crate::refactoring::models::FileChange;

/// How the edited project's `result` errors compare with the project's `baseline` errors.
#[must_use]
pub fn compare_with_baseline(
    baseline: &[RefactorDiagnostic],
    result: &[RefactorDiagnostic],
    changes: &[FileChange],
) -> BaselineComparison {
    let before: Vec<RefactorDiagnostic> = baseline
        .iter()
        .filter(|diagnostic| diagnostic.rule)
        .cloned()
        .collect();
    let original = |path: &Option<String>| original_path(changes, path.as_deref());
    let mut used: Vec<bool> = vec![false; before.len()];
    let mut matched: Vec<Option<usize>> = vec![None; result.len()];
    for (index, diagnostic) in result.iter().enumerate() {
        if !diagnostic.rule {
            continue;
        }
        let path: Option<String> = original(&diagnostic.path);
        matched[index] = first_unused(&before, &used, |earlier| {
            earlier.code == diagnostic.code
                && earlier.path == path
                && earlier.message == diagnostic.message
        });
        if let Some(found) = matched[index] {
            used[found] = true;
        }
    }
    for (index, diagnostic) in result.iter().enumerate() {
        if !diagnostic.rule || matched[index].is_some() {
            continue;
        }
        let path: Option<String> = original(&diagnostic.path);
        matched[index] = first_unused(&before, &used, |earlier| {
            earlier.code == diagnostic.code
                && earlier.path == path
                && reduced(&earlier.message, &diagnostic.message)
        });
        if let Some(found) = matched[index] {
            used[found] = true;
        }
    }
    let (mut remaining, mut blocking) = (Vec::new(), Vec::new());
    for (diagnostic, found) in result.iter().zip(&matched) {
        if found.is_some() {
            remaining.push(diagnostic.clone());
        } else {
            blocking.push(diagnostic.clone());
        }
    }
    let worsened: BTreeSet<(&str, Option<String>)> = blocking
        .iter()
        .map(|diagnostic: &RefactorDiagnostic| {
            (diagnostic.code.as_str(), original(&diagnostic.path))
        })
        .collect();
    let rules_unchecked: bool = blocking.iter().any(|diagnostic| !diagnostic.rule);
    let resolved: Vec<RefactorDiagnostic> = before
        .iter()
        .zip(&used)
        .filter(|(diagnostic, used)| {
            !rules_unchecked
                && !**used
                && !worsened.contains(&(diagnostic.code.as_str(), diagnostic.path.clone()))
        })
        .map(|(diagnostic, _)| diagnostic.clone())
        .collect();
    BaselineComparison {
        before,
        remaining,
        resolved,
        blocking,
    }
}

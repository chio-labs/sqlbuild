//! Candidate rename mappings and their substituted queries.

use crate::planner_changes::constants::MAX_CANDIDATE_MAPPINGS;
use crate::planner_changes::models::NameSpan;

/// The name followed by every origin it was renamed from, breadth first.
pub(crate) fn lineage(name: &str, origins: &[(String, Vec<String>)]) -> Vec<String> {
    let mut seen: Vec<String> = vec![name.to_owned()];
    let mut index: usize = 0;
    while index < seen.len() {
        let current: String = seen[index].clone();
        if let Some((_, list)) = origins.iter().find(|(key, _)| *key == current) {
            for origin in list {
                if !seen.contains(origin) {
                    seen.push(origin.clone());
                }
            }
        }
        index += 1;
    }
    seen
}

/// `itertools.product(*choices)`, truncated to the first mappings tried.
pub(crate) fn product(choices: &[Vec<String>]) -> Vec<Vec<String>> {
    let mut combinations: Vec<Vec<String>> = vec![Vec::new()];
    for options in choices {
        let mut next: Vec<Vec<String>> = Vec::new();
        for prefix in &combinations {
            for option in options {
                if next.len() == MAX_CANDIDATE_MAPPINGS {
                    break;
                }
                let mut combination: Vec<String> = prefix.clone();
                combination.push(option.clone());
                next.push(combination);
            }
        }
        combinations = next;
    }
    combinations
}

/// The query with each span replaced by its mapped origin name.
pub(crate) fn substitute(
    characters: &[char],
    spans: &[NameSpan],
    mapping: &[(String, String)],
) -> String {
    let mut text: String = String::new();
    let mut copied_to: usize = 0;
    for span in spans {
        text.extend(&characters[copied_to.min(span.start)..span.start]);
        let replacement: &str = mapping
            .iter()
            .find(|(name, _)| *name == span.name)
            .map_or(span.name.as_str(), |(_, origin)| origin.as_str());
        text.push_str(replacement);
        copied_to = span.end;
    }
    text.extend(&characters[copied_to.min(characters.len())..]);
    text
}

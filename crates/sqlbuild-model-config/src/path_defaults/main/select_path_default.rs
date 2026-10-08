//! `select_path_default`: the nearest path-default key for a model path.

use crate::path_defaults::_helpers::matching::{
    is_wildcard, matches_prefix, segment_count, specificity,
};
use crate::path_defaults::constants::MODELS_PREFIX;
use crate::path_defaults::models::PathDefaultChoice;

/// Select the path default for a project-relative model path as Python does.
pub fn select_path_default(model_path: &str, keys: &[String]) -> PathDefaultChoice {
    let normalized = model_path.replace('\\', "/");
    let normalized = normalized
        .strip_prefix(MODELS_PREFIX)
        .unwrap_or(&normalized);
    let path_parts: Vec<&str> = normalized
        .split('/')
        .filter(|part| !part.is_empty())
        .collect();
    let mut matched: Vec<&String> = keys
        .iter()
        .filter(|key| matches_prefix(&path_parts, key))
        .collect();
    matched.sort();
    let mut literal = matched.iter().filter(|key| !is_wildcard(key)).peekable();
    if literal.peek().is_some() {
        let mut best: Option<&String> = None;
        for key in literal {
            if best.is_none_or(|current| segment_count(key) > segment_count(current)) {
                best = Some(key);
            }
        }
        return PathDefaultChoice::Selected(best.cloned());
    }
    let Some(best_score) = matched.iter().map(|key| specificity(key)).max() else {
        return PathDefaultChoice::Selected(None);
    };
    let mut best = matched.iter().filter(|key| specificity(key) == best_score);
    match (best.next(), best.next()) {
        (Some(key), None) => PathDefaultChoice::Selected(Some((*key).clone())),
        _ => PathDefaultChoice::Conflict,
    }
}

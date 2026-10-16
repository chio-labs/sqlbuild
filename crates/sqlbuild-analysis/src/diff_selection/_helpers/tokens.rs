//! One diff selector token resolved to the resources it names.

use std::collections::HashSet;
use std::convert::Infallible;

use sqlbuild_core::graph_walk::main::breadth_first_reach::breadth_first_reach;

use crate::diff_selection::constants::{
    EMPTY_SELECTOR_CODE, GRAPH_OPERATOR, INTERSECTION_SEPARATOR, MODEL_PATH_PREFIX,
    MODEL_PATH_ROOT, PATH_PREFIX, PATH_SEPARATORS, TAG_PREFIX, UNKNOWN_NAME_CODE,
    UNKNOWN_PATH_CODE, UNKNOWN_TAG_CODE,
};
use crate::diff_selection::errors::SelectorError;
use crate::diff_selection::models::DiffGraph;

/// Resources reachable from `starts` along `edges`, without the starts unless reached.
fn reachable(starts: &HashSet<usize>, edges: &[Vec<usize>]) -> HashSet<usize> {
    let mut visited: HashSet<usize> = HashSet::new();
    let Ok(()) = breadth_first_reach(starts.iter().copied(), None, &mut visited, |current| {
        Ok::<_, Infallible>(edges.get(*current).into_iter().flatten().copied())
    });
    visited
}

/// `keys` with their upstream and downstream closures when requested.
fn expanded(
    keys: HashSet<usize>,
    (upstream, downstream): (bool, bool),
    graph: &DiffGraph,
) -> HashSet<usize> {
    let mut result: HashSet<usize> = keys.clone();
    if upstream {
        result.extend(reachable(&keys, &graph.upstream));
    }
    if downstream {
        result.extend(reachable(&keys, &graph.downstream));
    }
    result
}

/// `_resolve_selector_token`.
pub(crate) fn resolve_token(
    token: &str,
    graph: &DiffGraph,
) -> Result<HashSet<usize>, SelectorError> {
    let parts: Vec<&str> = token.split(INTERSECTION_SEPARATOR).collect();
    if parts.len() > 1 {
        let mut resolved: Vec<HashSet<usize>> = Vec::with_capacity(parts.len());
        for part in parts {
            resolved.push(resolve_token(part, graph)?);
        }
        let mut parts = resolved.into_iter();
        let mut result: HashSet<usize> = parts.next().unwrap_or_default();
        for part in parts {
            result.retain(|key| part.contains(key));
        }
        return Ok(result);
    }
    let operators: (bool, bool) = (
        token.starts_with(GRAPH_OPERATOR),
        token.ends_with(GRAPH_OPERATOR),
    );
    let core: &str = token
        .trim_start_matches(GRAPH_OPERATOR)
        .trim_end_matches(GRAPH_OPERATOR);
    if core.is_empty() {
        return Err(SelectorError {
            message: "empty selector".to_owned(),
            code: EMPTY_SELECTOR_CODE,
        });
    }
    if let Some(tag) = core.strip_prefix(TAG_PREFIX) {
        let keys: HashSet<usize> = graph
            .tags
            .iter()
            .find(|(name, _)| name == tag)
            .map(|(_, keys)| keys.iter().copied().collect())
            .unwrap_or_default();
        if keys.is_empty() {
            return Err(SelectorError {
                message: format!("no models found with tag '{tag}'"),
                code: UNKNOWN_TAG_CODE,
            });
        }
        return Ok(expanded(keys, operators, graph));
    }
    if core.starts_with(PATH_PREFIX) || core.contains(PATH_SEPARATORS) {
        let normalized: String = core
            .strip_prefix(PATH_PREFIX)
            .unwrap_or(core)
            .replace('\\', "/");
        let mut path: &str = normalized.trim_matches('/');
        if path == MODEL_PATH_ROOT {
            path = "";
        } else if let Some(rest) = path.strip_prefix(MODEL_PATH_PREFIX) {
            path = rest;
        }
        let nested: String = format!("{path}/");
        let keys: HashSet<usize> = graph
            .paths
            .iter()
            .filter(|(_, folder)| folder == path || folder.starts_with(&nested))
            .map(|(key, _)| *key)
            .collect();
        if keys.is_empty() {
            return Err(SelectorError {
                message: format!("no models found under path '{path}'"),
                code: UNKNOWN_PATH_CODE,
            });
        }
        return Ok(expanded(keys, operators, graph));
    }
    let key: Option<usize> = graph
        .names
        .iter()
        .rev()
        .find(|(name, _)| name == core)
        .map(|(_, key)| *key);
    let Some(key) = key else {
        return Err(SelectorError {
            message: format!("unknown selector name '{core}'"),
            code: UNKNOWN_NAME_CODE,
        });
    };
    Ok(expanded(HashSet::from([key]), operators, graph))
}

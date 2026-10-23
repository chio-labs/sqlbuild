use std::collections::HashMap;

use crate::sql_macros::types::Walk;

/// The first cycle among SQL macros calling each other, as names from the first to itself again.
pub fn sql_macro_cycle(calls: &[(String, Vec<String>)]) -> Option<Vec<String>> {
    let graph: HashMap<&str, &[String]> = calls
        .iter()
        .map(|(name, called)| (name.as_str(), called.as_slice()))
        .collect();
    let mut finished: Vec<&str> = Vec::new();
    for (name, _) in calls {
        let (walk, cycle) = visit(name, &graph, (Vec::new(), finished));
        if cycle.is_some() {
            return cycle;
        }
        finished = walk.1;
    }
    None
}

fn visit<'a>(
    name: &'a str,
    graph: &HashMap<&'a str, &'a [String]>,
    walk: Walk<'a>,
) -> (Walk<'a>, Option<Vec<String>>) {
    let (mut path, mut finished) = walk;
    if let Some(position) = path.iter().position(|seen| *seen == name) {
        let mut cycle: Vec<String> = path[position..]
            .iter()
            .map(|seen| (*seen).to_owned())
            .collect();
        cycle.push(name.to_owned());
        return ((path, finished), Some(cycle));
    }
    if finished.contains(&name) {
        return ((path, finished), None);
    }
    path.push(name);
    for called in graph.get(name).copied().unwrap_or_default() {
        let (walk, cycle) = visit(called, graph, (path, finished));
        if cycle.is_some() {
            return (walk, cycle);
        }
        (path, finished) = walk;
    }
    let _ = path.pop();
    finished.push(name);
    ((path, finished), None)
}

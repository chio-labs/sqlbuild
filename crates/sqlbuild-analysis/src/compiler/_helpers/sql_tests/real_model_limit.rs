//! The compile error for a unit test that executes more real models than the project allows.

use std::collections::{BTreeSet, HashMap, VecDeque};

/// The project setting that bounds how many real models one unit test may execute.
pub(crate) const REAL_MODEL_LIMIT_KEY: &str = "unit_test_max_real_models";

/// One unit test's chain, measured against the configured real-model limit.
pub(crate) struct RealModelChain<'a> {
    pub(crate) test_name: &'a str,
    pub(crate) file_label: &'a str,
    pub(crate) roots: &'a [String],
    pub(crate) real_models: &'a [String],
    pub(crate) limit: usize,
}

/// The explanation of an oversized chain, or `None` when the chain is within the limit.
pub(crate) fn real_model_limit_message<F>(chain: &RealModelChain<'_>, inputs: F) -> Option<String>
where
    F: Fn(&str) -> Vec<String>,
{
    let count = chain.real_models.len();
    if count <= chain.limit {
        return None;
    }
    let roots: Vec<&String> = chain
        .roots
        .iter()
        .filter(|root| chain.real_models.contains(root))
        .collect();
    let paths = dependency_paths(&roots, &inputs);
    let width = chain.real_models.iter().map(String::len).max().unwrap_or(0);
    let mut lines: Vec<String> = vec![
        format!(
            "SQL unit test '{}' executes {count} real models (limit {}).",
            chain.test_name, chain.limit
        ),
        format!("  Test file:        {}", chain.file_label),
        format!(
            "  Model under test: {}",
            roots
                .iter()
                .map(|root| root.as_str())
                .collect::<Vec<_>>()
                .join(", ")
        ),
        String::new(),
        "Real models executed, and the dependency path that pulls each one in:".to_owned(),
    ];
    for model in chain.real_models.iter().rev() {
        let reason = match paths.get(model.as_str()) {
            Some(path) if path.len() == 1 => "model under test".to_owned(),
            Some(path) => path.join(" -> "),
            None => "read by the test".to_owned(),
        };
        lines.push(format!("  {model:<width$}  {reason}"));
    }
    lines.push(String::new());
    lines.push("Options:".to_owned());
    lines.extend(mock_advice(&roots, chain.real_models, &inputs));
    lines.extend(scenario_advice());
    lines.extend([
        "  3. Raise the limit in sqlbuild_project.toml (or sqlbuild_local.toml):".to_owned(),
        "       [settings]".to_owned(),
        format!("       {REAL_MODEL_LIMIT_KEY} = {count}"),
    ]);
    Some(lines.join("\n"))
}

/// Why a scenario may suit a multi-model check, as the second option.
fn scenario_advice() -> [String; 4] {
    [
        "  2. If this test checks behaviour across several models, consider a scenario".to_owned(),
        "     (tests/scenarios/). A unit test inlines every real model into one statement,"
            .to_owned(),
        "     so the warehouse compiles and optimises the whole chain at once; a scenario"
            .to_owned(),
        "     builds each model step by step, compiling each statement separately.".to_owned(),
    ]
}

/// The direct real inputs of each model under test, which a test mocks to cut the chain.
fn mock_advice<F>(roots: &[&String], real_models: &[String], inputs: &F) -> Vec<String>
where
    F: Fn(&str) -> Vec<String>,
{
    let mut seen: BTreeSet<String> = BTreeSet::new();
    let mut mocks: Vec<String> = Vec::new();
    for root in roots {
        for input in inputs(root) {
            let is_root = roots.iter().any(|candidate| **candidate == input);
            if !is_root && real_models.contains(&input) && seen.insert(input.clone()) {
                mocks.push(input);
            }
        }
    }
    if mocks.is_empty() {
        return vec![
            "  1. Mock models further up the paths above with __ref__<model> CTEs.".to_owned(),
        ];
    }
    let mut lines: Vec<String> =
        vec!["  1. Mock the direct inputs of the model under test to cut the chain:".to_owned()];
    for mock in mocks {
        lines.push(format!("       __ref__{mock} AS (SELECT ...)"));
    }
    lines
}

/// The shortest read path from a model under test to each real model, breadth first.
fn dependency_paths<F>(roots: &[&String], inputs: &F) -> HashMap<String, Vec<String>>
where
    F: Fn(&str) -> Vec<String>,
{
    let mut paths: HashMap<String, Vec<String>> = HashMap::new();
    let mut queue: VecDeque<String> = VecDeque::new();
    for root in roots {
        if !paths.contains_key(root.as_str()) {
            paths.insert((*root).clone(), vec![(*root).clone()]);
            queue.push_back((*root).clone());
        }
    }
    while let Some(model) = queue.pop_front() {
        let path = paths.get(&model).cloned().unwrap_or_default();
        for input in inputs(&model) {
            if paths.contains_key(&input) {
                continue;
            }
            let mut extended = path.clone();
            extended.push(input.clone());
            paths.insert(input.clone(), extended);
            queue.push_back(input);
        }
    }
    paths
}

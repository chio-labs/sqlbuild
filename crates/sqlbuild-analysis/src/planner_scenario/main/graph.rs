//! Infer scenario closure while preserving dependency and diagnostic order.

use crate::planner_scenario::models::{ScenarioGraphInput, ScenarioGraphOutput};

/// Infer required relations, cutting traversal at authored reference fixtures.
pub fn graph(input: &ScenarioGraphInput) -> ScenarioGraphOutput {
    let mut output = ScenarioGraphOutput::default();
    for (names, label) in [
        (&input.expected, "expects unknown model"),
        (&input.assertions, "assertion references unknown model"),
    ] {
        for name in names {
            if !input.models.contains_key(name) {
                output
                    .warnings
                    .push((format!("Scenario '{}' {label} '{name}'.", input.name), true));
            }
        }
    }
    if input.targets.is_empty() {
        output.warnings.push((format!(
            "Scenario '{}' has no target models. Add __expected__<model> or reference a model with __ref(...) inside an __assert__ CTE.", input.name
        ), true));
    }
    for (names, kind) in [
        (&input.refs, "model"),
        (&input.sources, "source"),
        (&input.seeds, "seed"),
    ] {
        for name in names {
            let exists = match kind {
                "model" => input.models.contains_key(name),
                "source" => input.project_sources.contains(name),
                _ => input.project_seeds.contains(name),
            };
            if !exists {
                output.warnings.push((
                    format!(
                        "Scenario '{}' provides fixture for unknown {kind} '{name}'.",
                        input.name
                    ),
                    true,
                ));
            }
        }
    }
    for target in &input.targets {
        output = walk(target, input, output);
    }
    for name in &output.sources {
        if !input.sources.contains(name) {
            output.warnings.push((format!(
                "Scenario '{}' requires source '{name}', but no fixture was provided. Add a CTE named __source__{} AS (...).",
                input.name, name.replace('.', "__")
            ), false));
        }
    }
    for name in &output.dbt_refs {
        if !input.dbt_refs.contains(name) {
            output.warnings.push((format!(
                "Scenario '{}' requires dbt ref '{name}', but no fixture was provided. Add a CTE named __dbt_ref__{name} AS (...).", input.name
            ), false));
        }
    }
    output.seed_fixtures = output
        .seeds
        .iter()
        .filter(|name| input.seeds.contains(name))
        .cloned()
        .collect();
    output
}

fn walk(
    name: &str,
    input: &ScenarioGraphInput,
    mut output: ScenarioGraphOutput,
) -> ScenarioGraphOutput {
    if input.refs.iter().any(|fixture| fixture == name) {
        output.refs.insert(name.to_owned());
        return output;
    }
    if output.models.contains(name) {
        return output;
    }
    let Some(deps) = input.models.get(name) else {
        return output;
    };
    output.models.insert(name.to_owned());
    for dep in deps {
        match dep.0.as_str() {
            "model" => {
                if input.refs.contains(&dep.1) {
                    output.refs.insert(dep.1.clone());
                } else if !input.models.contains_key(&dep.1) {
                    output.warnings.push((format!(
                        "Scenario '{}' requires model '{}', but it does not exist and no __ref__ fixture was provided.", input.name, dep.1
                    ), true));
                } else {
                    output = walk(&dep.1, input, output);
                }
            }
            "source" => {
                output.sources.insert(dep.1.clone());
            }
            "seed" => {
                output.seeds.insert(dep.1.clone());
            }
            "dbt_ref" => {
                output.dbt_refs.insert(dep.1.replace('.', "__"));
            }
            "udf" | "table_fn" if !output.functions.contains(dep) => {
                output.functions.push(dep.clone());
            }
            _ => {}
        }
    }
    output
}

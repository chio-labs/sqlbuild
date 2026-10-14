//! dbt execution arguments with SQLBuild's required dbt selectors merged in.

use crate::dbt_plan::constants::{DEFER_FLAG, RESOLVED_VALUE_FLAGS, SELECT_FLAG};

fn without_resolved_options(args: &[String]) -> Vec<String> {
    let mut stripped: Vec<String> = Vec::new();
    let mut index: usize = 0;
    while index < args.len() {
        let arg: &str = &args[index];
        if RESOLVED_VALUE_FLAGS.contains(&arg) {
            index += 2;
            continue;
        }
        if arg != DEFER_FLAG {
            stripped.push(arg.to_owned());
        }
        index += 1;
    }
    stripped
}

/// Routed args without resolved options, every `--select` list extended by the missing terms.
#[must_use]
pub fn merged_dbt_execution_args(routed_args: &[String], extra_terms: &[String]) -> Vec<String> {
    let args: Vec<String> = without_resolved_options(routed_args);
    if extra_terms.is_empty() {
        return args;
    }
    if !args.iter().any(|arg| arg == SELECT_FLAG) {
        let mut merged: Vec<String> = args;
        merged.push(SELECT_FLAG.to_owned());
        merged.extend(extra_terms.iter().cloned());
        return merged;
    }
    let mut merged: Vec<String> = Vec::new();
    let mut index: usize = 0;
    while index < args.len() {
        let token: &String = &args[index];
        merged.push(token.clone());
        index += 1;
        if token != SELECT_FLAG {
            continue;
        }
        while index < args.len() && !args[index].starts_with("--") {
            merged.push(args[index].clone());
            index += 1;
        }
        for term in extra_terms {
            if !merged.contains(term) {
                merged.push(term.clone());
            }
        }
    }
    merged
}

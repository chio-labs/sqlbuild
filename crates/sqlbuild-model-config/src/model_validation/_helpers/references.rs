//! `validate_model_references`, raising the error Python raises for the first bad reference.

use crate::errors::ConfigError;
use crate::model_validation::constants::{
    REF_KIND, SEED_KIND, SOURCE_KIND, TABLE_FUNCTION_KIND, UDF_KIND,
};
use crate::model_validation::models::{
    ModelReference, ModelValidationFacts, ProjectValidationFacts, ValidationStop,
};
use crate::model_validation::types::Check;

/// Check each reference in order; external dbt references and unknown kinds defer to Python.
pub(crate) fn check_references(
    facts: &ModelValidationFacts<'_>,
    project: &ProjectValidationFacts,
) -> Check {
    for reference in facts.references {
        if let Some(problem) = reference_problem(reference, project)? {
            return Err(ValidationStop::Error(ConfigError::compile(format!(
                "Model file {} {problem}",
                facts.relative_path
            ))));
        }
    }
    Ok(())
}

fn reference_problem(
    reference: &ModelReference,
    project: &ProjectValidationFacts,
) -> Result<Option<String>, ValidationStop> {
    let name = &reference.name;
    let model = project.models.contains(name);
    let seed = project.seeds.contains(name);
    let function = project.functions.contains(name);
    let table_function = project.table_functions.contains(name);
    Ok(match reference.kind.as_str() {
        REF_KIND if !model && seed => Some(format!(
            "references seed '{name}' with __ref(...). Use {} for seed references; __ref only \
             resolves models.",
            example_call("__seed", name)
        )),
        REF_KIND if !model => Some(format!("references unknown model '{name}'")),
        SEED_KIND if !seed && model => Some(format!(
            "references model '{name}' with __seed(...). Use {} for model references.",
            example_call("__ref", name)
        )),
        SEED_KIND if !seed => Some(format!("references unknown seed '{name}'")),
        SOURCE_KIND if !project.sources.contains(name) => {
            Some(format!("references unknown source '{name}'"))
        }
        UDF_KIND if !function => Some(format!("references unknown SQL function '{name}'")),
        UDF_KIND if table_function => Some(format!(
            "references table function '{name}' with __udf(); use __table_fn() in SQL contexts \
             that support table-valued functions"
        )),
        TABLE_FUNCTION_KIND if !function => {
            Some(format!("references unknown table function '{name}'"))
        }
        TABLE_FUNCTION_KIND if !table_function => Some(format!(
            "references scalar function '{name}' with __table_fn(); use __udf() for scalar UDFs"
        )),
        REF_KIND | SEED_KIND | SOURCE_KIND | UDF_KIND | TABLE_FUNCTION_KIND => None,
        _ => return Err(ValidationStop::Defer),
    })
}

/// Return `SqlReferenceKind.example_call(name, quote='"')`.
fn example_call(function: &str, name: &str) -> String {
    format!("{function}(\"{}\")", name.replace('"', "\"\""))
}

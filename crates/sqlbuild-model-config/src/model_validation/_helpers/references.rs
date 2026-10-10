//! `validate_model_references`, raising the error Python raises for the first bad reference.

use crate::errors::ConfigError;
use crate::model_validation::constants::{
    DBT_REF_KIND, REF_KIND, SEED_KIND, SOURCE_KIND, TABLE_FUNCTION_KIND, UDF_KIND,
};
use crate::model_validation::models::{
    ModelReference, ModelValidationFacts, ProjectValidationFacts, ValidationStop,
};
use crate::model_validation::types::Check;

/// Check each reference in order; a dbt reference stops where its resolver rejected it.
pub(crate) fn check_references(
    facts: &ModelValidationFacts<'_>,
    project: &ProjectValidationFacts,
) -> Check {
    for (index, reference) in facts.references.iter().enumerate() {
        if reference.kind == DBT_REF_KIND {
            if reference.externally_rejected {
                return Err(ValidationStop::External(index));
            }
            continue;
        }
        if let Some(problem) = reference_problem(reference, project) {
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
) -> Option<String> {
    let name = &reference.name;
    let model = project.models.contains(name);
    let seed = project.seeds.contains(name);
    let function = project.functions.contains(name);
    let table_function = project.table_functions.contains(name);
    match reference.kind.as_str() {
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
        _ => None,
    }
}

/// Return `SqlReferenceKind.example_call(name, quote='"')`.
fn example_call(function: &str, name: &str) -> String {
    format!("{function}(\"{}\")", name.replace('"', "\"\""))
}

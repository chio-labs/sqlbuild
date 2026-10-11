//! The problem with one reference a SQL function body makes.

use crate::functions::constants::{
    DBT_REF_KIND, REF_KIND, SEED_KIND, SOURCE_KIND, TABLE_FUNCTION_KIND, UDF_KIND,
};
use crate::functions::models::KnownResources;

/// What is wrong with the `kind` reference to `name`, or `None` when it resolves.
pub(crate) fn reference_problem(
    kind: &str,
    name: &str,
    known: &KnownResources<'_>,
) -> Option<String> {
    let function: bool = known.functions.contains(name);
    let table_function: bool = known.table_functions.contains(name);
    match kind {
        REF_KIND if !known.models.contains(name) && known.seeds.contains(name) => Some(format!(
            "references seed '{name}' with __ref(...). Use {} for seed references; __ref only \
             resolves models.",
            example_call("__seed", name)
        )),
        REF_KIND if !known.models.contains(name) => {
            Some(format!("references unknown model '{name}'"))
        }
        SEED_KIND if !known.seeds.contains(name) => {
            Some(format!("references unknown seed '{name}'"))
        }
        SOURCE_KIND if !known.sources.contains(name) => {
            Some(format!("references unknown source '{name}'"))
        }
        DBT_REF_KIND => Some(format!(
            "uses {} but dbt refs are not supported yet; support may be added in a future release",
            example_call("__dbt_ref", name)
        )),
        UDF_KIND | TABLE_FUNCTION_KIND if !function => {
            Some(format!("references unknown SQL function '{name}'"))
        }
        UDF_KIND if table_function => Some(format!(
            "references table function '{name}' with __udf(); use __table_fn()"
        )),
        TABLE_FUNCTION_KIND if !table_function => Some(format!(
            "references scalar function '{name}' with __table_fn(); use __udf() for scalar UDFs"
        )),
        _ => None,
    }
}

/// `SqlReferenceKind.example_call(name, quote='"')`.
fn example_call(function: &str, name: &str) -> String {
    format!("{function}(\"{}\")", name.replace('"', "\"\""))
}

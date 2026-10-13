//! Normalize a rendered dbt profile output into a SQLBuild connection.

use crate::dbt_profile::_helpers::adapters::{
    bigquery, databricks, duckdb, postgres, snowflake, sqlserver,
};
use crate::dbt_profile::_helpers::output::Output;
use crate::dbt_profile::errors::DbtProfileError;
use crate::dbt_profile::models::{NormalizedProfile, ProfileEntry};

/// The SQLBuild connection plan for a rendered profile output of type `adapter_type`.
pub fn normalize_dbt_profile(
    entries: &[ProfileEntry],
) -> Result<NormalizedProfile, DbtProfileError> {
    let output: Output<'_> = Output(entries);
    let adapter_type: String = output.text_at(output.index("type")).unwrap_or_default();
    match adapter_type.as_str() {
        "duckdb" => Ok(duckdb(&output)),
        "postgres" => Ok(postgres(&output)),
        "snowflake" => Ok(snowflake(&output)),
        "bigquery" => bigquery(&output),
        "databricks" => databricks(&output),
        "sqlserver" => sqlserver(&output),
        "motherduck" => Err(DbtProfileError(
            "dbt profile type 'motherduck' is not supported directly. Use a dbt-duckdb profile with a MotherDuck path after SQLBuild MotherDuck profile support lands."
                .to_owned(),
        )),
        _ => Err(DbtProfileError(format!(
            "dbt profile type '{}' is not supported by SQLBuild dbt-profile connection resolution yet. Currently supported: bigquery, databricks, duckdb, postgres, snowflake, sqlserver",
            if adapter_type.is_empty() { "<missing>" } else { adapter_type.as_str() }
        ))),
    }
}

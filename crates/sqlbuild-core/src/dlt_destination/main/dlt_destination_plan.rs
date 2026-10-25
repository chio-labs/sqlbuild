//! `dlt_destination_plan`: the dlt destination call for one adapter's connection.

use crate::dlt_destination::_helpers::credentials::{adapter_call, credentials, required};
use crate::dlt_destination::_helpers::request::{check_dataset_name, check_destination_keys};
use crate::dlt_destination::constants::{
    DUCKDB_ADAPTER, DUCKDB_DEFAULT_DATASET, SQLALCHEMY_FACTORY, SQLITE_ADAPTER, SQLITE_MAIN_DATASET,
};
use crate::dlt_destination::errors::DltDestinationError;
use crate::dlt_destination::models::{
    DltDataset, DltDestinationPlan, DltDestinationRequest, DltValue,
};

/// The dlt destination call for the request's adapter, connection and dataset.
pub fn dlt_destination_plan(
    request: &DltDestinationRequest<'_>,
) -> Result<DltDestinationPlan, DltDestinationError> {
    let adapter: &str = request.adapter;
    check_destination_keys(adapter, request.destination_keys)?;
    if adapter == DUCKDB_ADAPTER {
        let database: &str = required(request.connection, "database", DUCKDB_ADAPTER)?;
        return Ok(DltDestinationPlan {
            factory: DUCKDB_ADAPTER,
            arguments: credentials(DltValue::Text(database.to_owned())),
            dataset: if request.dataset_name.truthy {
                DltDataset::Given
            } else {
                DltDataset::Default(DUCKDB_DEFAULT_DATASET)
            },
        });
    }
    if adapter == SQLITE_ADAPTER {
        let path: &str = required(request.connection, "path", SQLITE_ADAPTER)?;
        return Ok(DltDestinationPlan {
            factory: SQLALCHEMY_FACTORY,
            arguments: credentials(DltValue::Text(format!("sqlite:///{path}"))),
            dataset: if request.dataset_name.truthy {
                DltDataset::Given
            } else {
                DltDataset::Default(SQLITE_MAIN_DATASET)
            },
        });
    }
    check_dataset_name(adapter, request.dataset_name)?;
    let Some((factory, arguments)) = adapter_call(adapter, request.connection)? else {
        return Err(DltDestinationError {
            message: format!("Adapter '{adapter}' does not support dlt integration loaders"),
        });
    };
    Ok(DltDestinationPlan {
        factory,
        arguments,
        dataset: DltDataset::Given,
    })
}

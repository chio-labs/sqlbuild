//! A dlt destination factory call and the facts it is built from.

use crate::loader_connection::models::LoaderConnection;

/// One argument value of a dlt destination factory call.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DltValue {
    Text(String),
    /// The connection's raw `port` setting, or `default` when unset.
    Port {
        default: i64,
    },
    Object(Vec<(&'static str, DltValue)>),
}

/// The dataset a dlt destination lands in.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DltDataset {
    /// The dataset name the caller gave.
    Given,
    Default(&'static str),
}

/// The caller's dataset name.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DltDatasetName {
    /// The name when it is a string.
    pub text: Option<String>,
    /// Python truthiness of the name.
    pub truthy: bool,
}

/// One `dlt.destinations.<factory>(**arguments, **options)` call and its dataset.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DltDestinationPlan {
    pub factory: &'static str,
    pub arguments: Vec<(&'static str, DltValue)>,
    pub dataset: DltDataset,
}

/// One adapter's connection, destination config keys and dataset name.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DltDestinationRequest<'a> {
    pub adapter: &'a str,
    pub connection: &'a LoaderConnection,
    /// The destination config's keys, each `None` when not a string.
    pub destination_keys: &'a [Option<String>],
    pub dataset_name: &'a DltDatasetName,
}

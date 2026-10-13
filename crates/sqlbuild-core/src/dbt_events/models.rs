//! dbt events as the stream reads them, and the node results it reports.

use std::collections::{HashMap, HashSet};

/// The `data.node_info` fields of one dbt event; absent or non-text values are `None`.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DbtEventNode {
    pub unique_id: Option<String>,
    pub resource_type: Option<String>,
    pub node_name: Option<String>,
    pub materialized: Option<String>,
    pub node_status: Option<String>,
    pub node_checksum: Option<String>,
    pub relation_name: Option<String>,
    pub database: Option<String>,
    pub schema: Option<String>,
}

/// The fields of one dbt JSON log line the stream reads.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DbtEvent {
    pub name: Option<String>,
    pub level: Option<String>,
    pub info_msg: Option<String>,
    pub data_msg: Option<String>,
    pub data_status: Option<String>,
    pub run_result_status: Option<String>,
    pub index: Option<i64>,
    pub total: Option<i64>,
    pub num_models: Option<i64>,
    pub execution_time: Option<f64>,
    pub node: DbtEventNode,
}

/// One warning or error dbt logged for a node.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DbtNodeMessage {
    pub level: String,
    pub message: String,
}

/// One dbt node start or final result.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DbtNodeResult {
    pub unique_id: String,
    pub resource_type: String,
    pub node_name: String,
    pub status: String,
    pub index: Option<i64>,
    pub total: Option<i64>,
    pub execution_time: Option<f64>,
    pub materialized: Option<String>,
    pub relation_name: Option<String>,
    pub database: Option<String>,
    pub schema: Option<String>,
    pub node_checksum: Option<String>,
    pub messages: Vec<DbtNodeMessage>,
}

/// What the stream has seen so far: buffered messages, started and finished nodes.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DbtStreamState {
    pub pending_messages: HashMap<String, Vec<DbtNodeMessage>>,
    pub recorded_unique_ids: HashSet<String>,
    pub started_indexes: HashMap<String, i64>,
    pub display_index: i64,
}

/// A node row to write: a start row, or a final result.
#[derive(Clone, Debug, PartialEq)]
pub struct DbtStreamRow {
    pub result: DbtNodeResult,
    pub display_index: i64,
    pub finished: bool,
}

/// How one event changes the output: a progress message, a row, or both.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DbtStreamUpdate {
    pub status_message: Option<String>,
    pub row: Option<DbtStreamRow>,
}

/// Where a node row sits: the stream counter, else dbt's own index and total.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct DbtRowPosition {
    pub display_index: Option<i64>,
    pub display_total: Option<i64>,
}

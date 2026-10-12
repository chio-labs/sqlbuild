//! Keys and lineage shapes of the DAG artifact inputs.

/// A mapping key as `json.dumps` writes it, or the message of the `TypeError` it raises.
pub type DagKey = Result<String, String>;

/// Column to `(upstream node, upstream column)` references.
pub type DagColumnLineage = Vec<(String, Vec<(String, String)>)>;

//! Keys and lineage shapes of the DAG artifact inputs.

use crate::python_values::models::PythonValue;

/// A Python value as `dataclasses.asdict` copies it, before `json.dumps` encodes it.
pub type DagValue = PythonValue;

/// Column to `(upstream node, upstream column)` references.
pub type DagColumnLineage = Vec<(String, Vec<(String, String)>)>;

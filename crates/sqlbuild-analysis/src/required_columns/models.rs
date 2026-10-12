//! A model's SQL references and the external columns its query reads.

/// One SQL reference of a model: its reference kind value and referenced name.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReferenceInput {
    /// `ref`, `source`, `seed`, `table_fn`, or another kind that has no lineage.
    pub kind: String,
    pub name: String,
}

/// One external column a query reads: the resource type value, resource and column.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct ColumnRead {
    pub resource_type: String,
    pub resource_name: String,
    pub column_name: String,
}

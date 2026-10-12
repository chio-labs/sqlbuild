//! Polyglot expression kinds and clause names the column-read walk recognises.

pub(crate) const KIND_ANNOTATED: &str = "annotated";
pub(crate) const KIND_COLUMN: &str = "column";
pub(crate) const KIND_SELECT: &str = "select";
pub(crate) const KIND_SUBQUERY: &str = "subquery";
pub(crate) const KIND_TABLE: &str = "table";
/// The set-operation kinds, whose branches combine column by column.
pub(crate) const SET_OPERATION_KINDS: [&str; 3] = ["union", "intersect", "except"];
/// Select clauses whose column references count as reads, in Python's order.
pub(crate) const CLAUSE_NAMES: [&str; 12] = [
    "cluster_by",
    "connect",
    "distinct_on",
    "distribute_by",
    "group_by",
    "having",
    "joins",
    "order_by",
    "qualify",
    "sort_by",
    "where_clause",
    "windows",
];
/// Clauses where an output alias wins over an input column of the same name.
pub(crate) const OUTPUT_ALIAS_FIRST_CLAUSES: [&str; 2] = ["order_by", "qualify"];
/// Clauses where an output alias is used only when no input column matches.
pub(crate) const OUTPUT_ALIAS_FALLBACK_CLAUSES: [&str; 4] =
    ["cluster_by", "group_by", "having", "sort_by"];
/// The prefix of the relation stub a table-function call is analysed as.
pub(crate) const TABLE_FUNCTION_STUB_PREFIX: &str = "__sqlbuild_table_function_";
/// The column name a star projection parses as.
pub(crate) const STAR: &str = "*";
pub(crate) const GENERIC_DIALECT: &str = "generic";

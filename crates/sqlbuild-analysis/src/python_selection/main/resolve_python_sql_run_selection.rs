use crate::graph::errors::SelectorError;
use crate::python_selection::_helpers::nodes::sql_names;
use crate::python_selection::_helpers::unified::run_selection;
use crate::python_selection::models::{
    NodeIndex, PythonSelectionGraph, RunSelection, SelectionContext, SqlSelectionGraph,
};

/// Python's `resolve_python_sql_run_selectors`: run selectors over SQL resources and Python nodes.
pub fn resolve_python_sql_run_selection(
    sql: SqlSelectionGraph<'_>,
    python: &PythonSelectionGraph,
    select: &[String],
    exclude: &[String],
) -> Result<RunSelection, SelectorError> {
    let context: SelectionContext<'_> = SelectionContext {
        sql,
        nodes: NodeIndex::new(python),
        sql_names: sql_names(sql.graph),
    };
    run_selection(&context, select, exclude)
}

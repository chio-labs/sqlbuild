//! The one-line `sqb dag` summary.

/// `DAG ready (<n> nodes, <e> edges, <c> checks)` and a newline.
#[must_use]
pub fn render_dag_summary((nodes, edges, checks): (usize, usize, usize)) -> String {
    format!("DAG ready ({nodes} nodes, {edges} edges, {checks} checks)\n")
}

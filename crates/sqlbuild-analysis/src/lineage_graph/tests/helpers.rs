use std::convert::Infallible;

use crate::lineage_graph::models::{EdgeKey, TreeLine};
use crate::lineage_graph::tests::test_types::StringTree;
use crate::lineage_graph::types::TreeVisitor;

/// A direct, high-confidence edge from `source.column` into `target.column`.
pub(crate) fn edge_key(source: (&str, &str), target: (&str, &str)) -> EdgeKey {
    EdgeKey {
        source_type: "model".to_owned(),
        source_name: source.0.to_owned(),
        source_column: source.1.to_owned(),
        target_model: target.0.to_owned(),
        target_column: target.1.to_owned(),
        transform: "direct".to_owned(),
        confidence: "high".to_owned(),
    }
}

impl TreeVisitor<&'static str, &'static str, Infallible> for StringTree {
    fn key(&mut self, node: &&'static str) -> Result<&'static str, Infallible> {
        Ok(node)
    }

    fn line(&mut self, line: TreeLine<'_, &'static str>) -> Result<(), Infallible> {
        let suffix: &str = if line.repeated { " (shown)" } else { "" };
        self.lines.push(format!(
            "{}{}{}{suffix}",
            line.prefix, line.branch, line.node
        ));
        Ok(())
    }

    fn children(&mut self, node: &&'static str) -> Result<Vec<&'static str>, Infallible> {
        Ok(self.children.get(node).cloned().unwrap_or_default())
    }
}

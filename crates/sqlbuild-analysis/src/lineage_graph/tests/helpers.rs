use crate::lineage_graph::models::EdgeKey;

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

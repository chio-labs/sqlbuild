use crate::dbt_manifest::models::{ManifestNode, NodeChecksum};

pub(super) fn node(text: &[(&str, &str)], checksum: NodeChecksum) -> ManifestNode {
    ManifestNode {
        text: text
            .iter()
            .map(|(key, value)| ((*key).to_owned(), (*value).to_owned()))
            .collect(),
        checksum,
        fqn: Some(vec![
            Some("analytics".to_owned()),
            Some("orders".to_owned()),
        ]),
        depends_on: vec!["model.a.b".to_owned(), String::new()],
    }
}

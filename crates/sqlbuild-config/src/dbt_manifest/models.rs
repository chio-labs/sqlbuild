//! dbt manifest node fields and the parsed models, sources and seeds.

/// A node `checksum` field.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub enum NodeChecksum {
    /// A string value.
    Text(String),
    /// An object with this string `checksum` member, when it has one.
    Nested(Option<String>),
    /// Missing or any other value.
    #[default]
    Other,
}

/// The fields of one manifest node that SQLBuild reads.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ManifestNode {
    /// `NODE_TEXT_FIELDS` whose value is a string, with that value.
    pub text: Vec<(String, String)>,
    pub checksum: NodeChecksum,
    /// `fqn` when it is a list: each item when it is a string.
    pub fqn: Option<Vec<Option<String>>>,
    /// The string items of `depends_on.nodes`.
    pub depends_on: Vec<String>,
}

/// A dbt model or snapshot node.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParsedModel {
    pub package_name: String,
    pub name: String,
    pub database: Option<String>,
    pub schema: Option<String>,
    pub alias: Option<String>,
    pub node_checksum: Option<String>,
    pub relation_name: String,
    pub fqn: Vec<String>,
    pub query_sql: String,
    pub depends_on: Vec<String>,
}

/// A dbt source node.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParsedSource {
    pub package_name: String,
    pub source_name: String,
    pub name: String,
    pub database: Option<String>,
    pub schema: Option<String>,
    pub identifier: Option<String>,
    pub relation_name: String,
}

/// A dbt seed node.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParsedSeed {
    pub package_name: String,
    pub name: String,
    pub database: Option<String>,
    pub schema: Option<String>,
    pub alias: Option<String>,
    pub relation_name: String,
}

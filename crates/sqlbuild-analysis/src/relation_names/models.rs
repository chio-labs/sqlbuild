//! Relations named in SQL, as Python's `RelationName` holds them.

/// One relation a statement names, with the qualifiers it spells.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RelationName {
    pub name: String,
    pub schema: Option<String>,
    pub database: Option<String>,
}

/// Relations in first-seen order and the casefolded temporary tables the SQL creates.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ExtractedRelations {
    pub relations: Vec<RelationName>,
    pub temporary: Vec<String>,
}

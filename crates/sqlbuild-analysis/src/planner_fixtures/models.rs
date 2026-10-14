//! Passive fixture schema and alignment facts.

/// One authoritative or inferred fixture column.
#[derive(Clone, Debug)]
pub struct FixtureColumn {
    pub name: String,
    pub folded_name: String,
    pub sql_type: Option<String>,
    pub nullable: Option<bool>,
}

/// A required column and the models reading it.
#[derive(Debug)]
pub struct RequiredColumn {
    pub name: String,
    pub folded_name: String,
    pub readers: Vec<String>,
}

/// Schema facts needed to align a partial fixture.
#[derive(Debug)]
pub struct AlignmentInput<'a> {
    pub supplied: &'a [FixtureColumn],
    pub metadata: &'a [FixtureColumn],
    pub required: &'a [RequiredColumn],
    pub star: bool,
    pub typed_nulls: bool,
}

/// Missing-column diagnostics and schema-ordered completion indices.
#[derive(Debug, Default)]
pub struct Alignment {
    pub diagnostics: Vec<String>,
    pub completed: Option<Vec<usize>>,
}

/// A supplied projection and its optional authoritative null type.
#[derive(Debug)]
pub struct SuppliedProjection {
    pub name: String,
    pub quoted: bool,
    pub expected_type: Option<String>,
}

/// Completed fixture inputs independent of adapter rendering.
#[derive(Debug)]
pub struct FixtureSqlInput<'a> {
    pub sql: &'a str,
    pub supplied: &'a [SuppliedProjection],
    pub typed_nulls: bool,
    pub completed: &'a [FixtureColumn],
}

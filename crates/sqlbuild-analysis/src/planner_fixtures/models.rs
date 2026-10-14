//! Passive fixture schema and alignment facts.

use std::collections::{BTreeSet, HashMap};

/// One upstream typed column identified by its resource and folded name.
#[derive(Debug)]
pub struct FixtureTypeRead {
    pub key: (String, String),
    pub column: String,
}

/// Direct lineage facts used to propagate fixture types.
#[derive(Debug)]
pub struct FixtureTypeProjection {
    pub output_column: String,
    pub upstream: Vec<FixtureTypeRead>,
}

/// One model's ordered direct projections and initial fixture types.
#[derive(Debug)]
pub struct FixtureTypeModel {
    pub key: (String, String),
    pub projections: Vec<FixtureTypeProjection>,
}

/// A known relation type map and the ordered additions inferred from lineage.
#[derive(Debug, Default)]
pub struct FixtureTypeState {
    pub known: HashMap<(String, String), HashMap<String, String>>,
    pub additions: Vec<(FixtureTypeRead, String)>,
}

/// Derived column names and known types for one fixture relation.
#[derive(Debug)]
pub struct FixtureSchema {
    pub authoritative_names: Option<BTreeSet<String>>,
    pub expected_types: Vec<(String, String)>,
}

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

//! Passive fixture schema and alignment facts.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

/// Local fixture schemas used by required-read aggregation.
#[derive(Debug)]
pub struct FixtureReadSchemas<'a> {
    pub keys: &'a HashSet<(String, String)>,
    pub authoritative: &'a HashMap<(String, String), HashSet<String>>,
    pub relations: &'a [FixtureStarRelation],
}

use crate::required_columns::models::ColumnRead;

use crate::planner_fixtures::types::FixtureReadReference;

/// The original SQL, complete references and dialect form the read cache key.
#[derive(Clone, Debug, Eq, Hash, PartialEq)]
pub struct FixtureReadKey {
    pub sql: String,
    pub references: Vec<FixtureReadReference>,
    pub dialect: Option<String>,
}

/// A bounded LRU of successful fixture read analyses.
#[derive(Debug, Default)]
pub struct FixtureReadCache {
    pub entries: HashMap<FixtureReadKey, (u64, Vec<ColumnRead>)>,
    pub recency: BTreeMap<u64, FixtureReadKey>,
    pub clock: u64,
    pub misses: u64,
}

/// A model's read evidence and star dependencies in planning order.
#[derive(Debug)]
pub struct FixtureReadModel {
    pub name: String,
    pub key: FixtureReadKey,
    pub high_confidence: Vec<ColumnRead>,
    pub stars: Vec<(String, String)>,
}

/// Required columns retain model and column insertion order.
#[derive(Debug, Default)]
pub struct FixtureReadRequirements {
    pub columns: Vec<((String, String), Vec<RequiredColumn>)>,
    pub stars: BTreeSet<(String, String)>,
    pub(crate) indices: HashMap<(String, String), usize>,
    pub(crate) column_indices: Vec<HashMap<String, usize>>,
}

/// One fixture dependency and the schema available to star analysis.
#[derive(Debug)]
pub struct FixtureStarRelation {
    pub key: (String, String),
    pub columns: Vec<FixtureColumn>,
    pub authoritative: bool,
}

/// One upstream typed column identified by its resource and folded name.
#[derive(Clone, Debug)]
pub struct FixtureTypeRead {
    pub key: (String, String),
    pub column: String,
}

/// Direct lineage facts used to propagate fixture types.
#[derive(Clone, Debug)]
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

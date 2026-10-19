//! Parsed YAML declaration entries whose leaves are the caller's own authored values.

use sqlbuild_model_config::header_metadata::models::ParsedAudit;

/// One declared column of a seed or schema entry.
#[derive(Clone, Debug, PartialEq)]
pub struct ParsedYamlColumn<N> {
    pub name: N,
    pub column_type: Option<N>,
    pub nullable: Option<N>,
    pub description: Option<N>,
    /// The authored mapping, or `None` for Python's empty default.
    pub meta: Option<N>,
    pub audits: Vec<ParsedAudit<N>>,
}

/// `na_values`: one list for every column, or a list per named column.
#[derive(Clone, Debug, PartialEq)]
pub enum ParsedNaValues<N> {
    List(Vec<N>),
    PerColumn(Vec<(N, Vec<N>)>),
}

/// A seed's `csv_settings`; each field holds the authored value or `None` when unset.
#[derive(Clone, Debug, PartialEq)]
pub struct ParsedCsvSettings<N> {
    pub delimiter: Option<N>,
    pub quotechar: Option<N>,
    pub doublequote: Option<N>,
    pub escapechar: Option<N>,
    pub skipinitialspace: Option<N>,
    pub lineterminator: Option<N>,
    pub encoding: Option<N>,
    pub na_values: Option<ParsedNaValues<N>>,
    pub keep_default_na: Option<N>,
}

/// One seed declaration of a `seeds/**/*.yml` file.
#[derive(Clone, Debug, PartialEq)]
pub struct ParsedSeedEntry<N> {
    pub name: N,
    pub description: Option<N>,
    pub database: Option<N>,
    pub schema: Option<N>,
    pub meta: Option<N>,
    pub tags: Vec<N>,
    /// The settings, or `None` when the entry declares none.
    pub csv_settings: Option<ParsedCsvSettings<N>>,
    pub columns: Vec<ParsedYamlColumn<N>>,
    pub audits: Vec<ParsedAudit<N>>,
}

/// A source freshness age policy; at least one bound is set.
#[derive(Clone, Debug, PartialEq)]
pub struct ParsedAgePolicy<N> {
    pub warn_after: Option<N>,
    pub error_after: Option<N>,
}

/// A source's freshness config, its strategy and value kind resolved as Python stores them.
#[derive(Clone, Debug, PartialEq)]
pub struct ParsedFreshness<N> {
    /// `adapter`, `column` or `sql`.
    pub strategy: &'static str,
    /// `timestamp`, `integer` or `string`.
    pub value_kind: Option<&'static str>,
    pub column: Option<N>,
    pub query: Option<N>,
    pub filter: Option<N>,
    pub lag_tolerance: Option<N>,
    pub age_policy: Option<ParsedAgePolicy<N>>,
}

/// A source-level `ingestr` loader; key lists hold Python's stripped strings.
#[derive(Clone, Debug, PartialEq)]
pub struct ParsedIngestrConfig<N> {
    pub source_uri: N,
    pub source_table: N,
    pub strategy: Option<N>,
    pub incremental_key: Option<N>,
    pub primary_key: Vec<String>,
    pub columns: Option<N>,
    pub extra_args: Vec<String>,
}

/// One dlt resource as `DltResourceConfig` stores it.
#[derive(Clone, Debug, PartialEq)]
pub struct ParsedDltResource<N> {
    pub name: N,
    pub dlt_name: N,
    pub schema: Option<N>,
    /// The resource entries the loader passes to dlt, in authored order.
    pub raw_config: Vec<(N, N)>,
    pub write_disposition: Option<N>,
    pub primary_key: Option<N>,
    pub merge_key: Option<N>,
    pub incremental: Option<N>,
}

/// A dlt source group's settings shared by the source entry of each resource.
#[derive(Clone, Debug, PartialEq)]
pub struct ParsedDltSource<N> {
    pub source_type: N,
    pub schema: Option<N>,
    pub config: N,
    /// The destination mapping, or `None` for Python's empty default.
    pub destination: Option<N>,
    pub resource: ParsedDltResource<N>,
    pub group_index: usize,
}

/// The declarative integration loader a source is managed by.
#[derive(Clone, Debug, PartialEq)]
pub enum ParsedIntegrationLoader<N> {
    Ingestr(ParsedIngestrConfig<N>),
    Dlt(Box<ParsedDltSource<N>>),
}

impl<N> ParsedIntegrationLoader<N> {
    /// The loader kind `IntegrationLoaderConfig` records.
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Ingestr(_) => "ingestr",
            Self::Dlt(_) => "dlt",
        }
    }
}

/// One source declaration of a `sources/*.yml` file.
#[derive(Clone, Debug, PartialEq)]
pub struct ParsedSourceEntry<N> {
    pub name: N,
    pub database: Option<N>,
    pub schema: Option<N>,
    pub table: Option<N>,
    /// Whether reads of the source add `FINAL`, so replacing engines return one row per key.
    pub read_final: bool,
    pub loader: Option<String>,
    pub managed: bool,
    pub integration_loader: Option<ParsedIntegrationLoader<N>>,
    pub freshness: Option<ParsedFreshness<N>>,
    /// `append`, `delete_insert`, `merge` or `table`.
    pub write_strategy: Option<&'static str>,
    pub load_batch_size: Option<N>,
    pub cursor_column: Option<N>,
    pub unique_key: Vec<String>,
    pub expression: Option<N>,
    pub description: Option<N>,
    /// The authored flag, or `True` implied by typed columns.
    pub type_enforcement: Option<bool>,
    pub contract: Option<N>,
    pub meta: Option<N>,
    pub columns: Vec<ParsedYamlColumn<N>>,
    pub audits: Vec<ParsedAudit<N>>,
}

impl<N> ParsedSourceEntry<N> {
    /// A source entry with only its name set, as Python's `SourceEntry` defaults.
    pub fn named(name: N) -> Self {
        Self {
            name,
            database: None,
            schema: None,
            table: None,
            read_final: false,
            loader: None,
            managed: false,
            integration_loader: None,
            freshness: None,
            write_strategy: None,
            load_batch_size: None,
            cursor_column: None,
            unique_key: Vec::new(),
            expression: None,
            description: None,
            type_enforcement: None,
            contract: None,
            meta: None,
            columns: Vec::new(),
            audits: Vec::new(),
        }
    }
}

use crate::assembly::project::models::InputRead;
use crate::assembly::project::types::ObjectKey;

/// `(name, database, schema)` of one authored seed.
pub(crate) type SeedSpec = (&'static str, Option<&'static str>, Option<&'static str>);
/// `(database, schema, logical database, logical schema)`.
pub(crate) type ExpectedNamespace = (
    Option<&'static str>,
    Option<&'static str>,
    Option<&'static str>,
    Option<&'static str>,
);

pub(crate) struct DepsTestCase {
    pub(crate) description: &'static str,
    /// `(kind, name, package)` references.
    pub(crate) references: &'static [(&'static str, &'static str, Option<&'static str>)],
    pub(crate) attached: Option<(&'static str, &'static str)>,
    /// None where Python rejects the audit.
    pub(crate) expected_deps: Option<&'static [(&'static str, &'static str)]>,
}

pub(crate) struct SeedTestCase {
    pub(crate) description: &'static str,
    pub(crate) seed: SeedSpec,
    /// `(database, schema, seed database, seed schema)` defaults.
    pub(crate) defaults: ExpectedNamespace,
    /// `(database, schema, loader schema)` of the selected target.
    pub(crate) target: Option<(
        Option<&'static str>,
        Option<&'static str>,
        Option<&'static str>,
    )>,
    /// None where Python raises or expands the target itself.
    pub(crate) expected_namespace: Option<ExpectedNamespace>,
}

pub(crate) struct SourceTestCase {
    pub(crate) description: &'static str,
    /// `(managed, database, schema)` of the authored source.
    pub(crate) source: (bool, Option<&'static str>, Option<&'static str>),
    pub(crate) target: Option<(
        Option<&'static str>,
        Option<&'static str>,
        Option<&'static str>,
    )>,
    /// Outer None where Python raises, inner None where the entry stays as authored.
    pub(crate) expected_namespace: Option<Option<(Option<&'static str>, Option<&'static str>)>>,
}

pub(crate) struct SyntaxTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) placeholders: &'static [(&'static str, &'static str)],
    /// None where native defers to Python.
    pub(crate) expected_valid: Option<bool>,
}

pub(crate) fn keys(values: &[(&str, &str)]) -> Vec<ObjectKey> {
    values
        .iter()
        .map(|(kind, name)| ((*kind).to_owned(), (*name).to_owned()))
        .collect()
}

pub(crate) struct EnvironmentTestCase {
    pub(crate) description: &'static str,
    pub(crate) seed: SeedSpec,
    /// Python's `os.environ.get` of each name.
    pub(crate) environment: &'static [(&'static str, Option<&'static str>)],
    /// None where Python raises.
    pub(crate) expected_schema: Option<&'static str>,
    pub(crate) expected_reads: Vec<InputRead>,
}

pub(crate) struct SyntaxBatchTestCase {
    pub(crate) description: &'static str,
    pub(crate) sqls: &'static [&'static str],
    /// None where native defers to Python.
    pub(crate) expected_valid: Option<bool>,
}

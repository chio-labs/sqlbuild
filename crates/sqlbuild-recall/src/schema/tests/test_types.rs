pub(crate) struct SqliteScriptTestCase {
    pub(crate) description: &'static str,
    pub(crate) runs: usize,
    pub(crate) expected_objects: usize,
    pub(crate) expected_failures: Vec<String>,
}

pub(crate) struct FragmentTestCase {
    pub(crate) description: &'static str,
    pub(crate) statement: String,
    pub(crate) expected_fragments: &'static [&'static str],
}

pub(crate) struct StatementSetTestCase {
    pub(crate) description: &'static str,
    pub(crate) statements: Vec<String>,
    pub(crate) required_fragments: &'static [&'static str],
    pub(crate) expected_count: usize,
}

pub(crate) struct AddColumnTestCase {
    pub(crate) description: &'static str,
    pub(crate) statement: String,
    pub(crate) expected_statement: &'static str,
}

pub(crate) struct UpgradeStatementsTestCase {
    pub(crate) description: &'static str,
    pub(crate) observed: crate::schema::models::ObservedSchema,
    pub(crate) dialect: crate::schema::models::Dialect,
    pub(crate) expected_count: usize,
    pub(crate) expected_prefixes: &'static [&'static str],
}

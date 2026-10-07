use crate::sql_references::models::ReferenceExtraction;
use crate::sql_scan::models::LexicalSyntax;

pub(crate) struct ExtractSqlReferencesTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) syntax: LexicalSyntax,
    pub(crate) expected_extraction: ReferenceExtraction,
}

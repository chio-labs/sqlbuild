use crate::snowflake_cost::models::QueryTag;

pub(crate) struct MetadataOnlyTestCase {
    pub(crate) description: &'static str,
    pub(crate) query_type: &'static str,
    pub(crate) query_text: Option<&'static str>,
    pub(crate) expected_metadata_only: bool,
}

pub(crate) struct QueryTagTestCase {
    pub(crate) description: &'static str,
    pub(crate) value: &'static str,
    pub(crate) expected_tag: Option<QueryTag>,
}

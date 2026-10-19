use crate::clickhouse::models::{ColumnEncoding, StoredRow};
use crate::store::errors::StoreErrorKind;

pub(crate) struct EncodingTestCase {
    pub(crate) description: &'static str,
    pub(crate) type_text: &'static str,
    pub(crate) expected_encoding: Option<(ColumnEncoding, bool)>,
}

pub(crate) struct RowBinaryTestCase {
    pub(crate) description: &'static str,
    pub(crate) columns: &'static [(&'static str, ColumnEncoding, bool)],
    pub(crate) expected_block: Result<(Vec<String>, Vec<u8>), String>,
}

pub(crate) struct ErrorKindTestCase {
    pub(crate) description: &'static str,
    pub(crate) message: &'static str,
    pub(crate) expected_kind: StoreErrorKind,
}

pub(crate) struct PlanTestCase {
    pub(crate) description: &'static str,
    pub(crate) stored: Vec<StoredRow>,
    pub(crate) expected_plan: (Vec<(&'static str, usize)>, usize),
}

pub(crate) struct LookupTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: Option<String>,
    pub(crate) expected_fragments: &'static [&'static str],
}

pub(crate) struct TtlTestCase {
    pub(crate) description: &'static str,
    pub(crate) create_query: &'static str,
    pub(crate) retention_days: u32,
    pub(crate) expected_stored_days: Option<Option<u64>>,
}

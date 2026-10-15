use crate::events::errors::StateSqlError;
use sqlbuild_cursor::algebra::models::LocalDateTime;

use crate::events::models::{
    ColumnEventKey, EventOrder, EventRelation, FingerprintKey, MoveEventKey, OldNameFactKey,
    OldNameHistoryIndexes, RecordedRenameKey, StateCell,
};

pub(crate) struct InsertTestCase {
    pub(crate) description: &'static str,
    pub(crate) cells: Vec<StateCell>,
    pub(crate) expected_sql: Result<String, StateSqlError>,
}

pub(crate) struct NewestMoveTestCase {
    pub(crate) description: &'static str,
    pub(crate) events: Vec<MoveEventKey>,
    pub(crate) relation: EventRelation,
    pub(crate) expected_index: Option<usize>,
}

pub(crate) struct NewestColumnTestCase {
    pub(crate) description: &'static str,
    pub(crate) events: Vec<ColumnEventKey>,
    pub(crate) columns: (&'static str, &'static str),
    pub(crate) expected_index: Option<usize>,
}

pub(crate) struct HistoryTestCase {
    pub(crate) description: &'static str,
    pub(crate) moves: Vec<EventOrder>,
    pub(crate) facts: Vec<OldNameFactKey>,
    pub(crate) expected_histories: Vec<OldNameHistoryIndexes>,
}

pub(crate) struct AliasesTestCase {
    pub(crate) description: &'static str,
    pub(crate) aliases: Vec<(String, String)>,
    pub(crate) expected_json: Option<String>,
}

pub(crate) struct DecodedAliasesTestCase {
    pub(crate) description: &'static str,
    pub(crate) raw: Option<&'static str>,
    pub(crate) expected_aliases: Vec<(String, String)>,
}

pub(crate) struct DecodedGrantsTestCase {
    pub(crate) description: &'static str,
    pub(crate) raw: Option<&'static str>,
    pub(crate) expected_grants: Option<Vec<String>>,
}

pub(crate) struct ReadSqlTestCase {
    pub(crate) description: &'static str,
    pub(crate) stored: Vec<String>,
    pub(crate) expected_sql: String,
}

pub(crate) struct GrantsTestCase {
    pub(crate) description: &'static str,
    pub(crate) grants: Option<Vec<String>>,
    pub(crate) expected_json: Option<String>,
}

pub(crate) struct RecordedRenamesTestCase {
    pub(crate) description: &'static str,
    pub(crate) events: Vec<RecordedRenameKey>,
    pub(crate) relation: EventRelation,
    pub(crate) since: LocalDateTime,
    pub(crate) expected_indexes: Vec<usize>,
}

pub(crate) struct NewestFingerprintTestCase {
    pub(crate) description: &'static str,
    pub(crate) fingerprints: Vec<FingerprintKey>,
    pub(crate) target: Option<EventRelation>,
    pub(crate) model_name: Option<&'static str>,
    pub(crate) expected_index: Option<usize>,
}

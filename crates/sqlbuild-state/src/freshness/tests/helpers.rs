use sqlbuild_cursor::algebra::models::{CivilDate, LocalDateTime};

use crate::freshness::errors::FreshnessError;
use crate::freshness::models::ComparableRecord;
use crate::freshness::tests::test_types::MinuteParser;
use crate::freshness::types::TimestampParser;

pub(crate) fn record(data_version: &str) -> ComparableRecord {
    ComparableRecord {
        data_version_hash: data_version.to_owned(),
        value_kind: "timestamp".to_owned(),
        data_version: Some(data_version.to_owned()),
    }
}

impl TimestampParser for MinuteParser {
    fn utc_timestamp(&self, text: &str) -> Result<LocalDateTime, FreshnessError> {
        let field = |range: std::ops::Range<usize>| text[range].parse::<u32>().unwrap_or(0);
        Ok(LocalDateTime {
            date: CivilDate {
                year: i64::from(field(0..4)),
                month: field(5..7),
                day: field(8..10),
            },
            hour: field(11..13),
            minute: field(14..16),
            second: 0,
            microsecond: 0,
        })
    }
}

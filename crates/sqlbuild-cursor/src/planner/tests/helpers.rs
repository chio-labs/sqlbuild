use crate::algebra::errors::CursorError;
use crate::algebra::models::{
    CivilDate, DurationSpan, LocalDateTime, Scalar, ScalarValue, Timestamp, ZoneOffset,
};
use crate::algebra::types::ZoneRules;
use crate::planner::tests::test_types::UtcZones;

pub(super) fn timestamp(month: u32, day: u32, hour: u32, minute: u32) -> Scalar {
    Scalar {
        handle: None,
        value: ScalarValue::Timestamp(Timestamp {
            local: LocalDateTime {
                date: CivilDate {
                    year: 2026,
                    month,
                    day,
                },
                hour,
                minute,
                second: 0,
                microsecond: 0,
            },
            fold: false,
            offset: ZoneOffset::Fixed(0),
            template: None,
            source_text: None,
        }),
    }
}

impl ZoneRules for UtcZones {
    fn to_utc(
        &self,
        _: usize,
        local: &LocalDateTime,
        _: bool,
    ) -> Result<LocalDateTime, CursorError> {
        Ok(*local)
    }

    fn utc_offset(&self, _: usize, _: &LocalDateTime, _: bool) -> Result<Option<i64>, CursorError> {
        Ok(Some(0))
    }
}

pub(super) fn days(days: i64) -> DurationSpan {
    DurationSpan {
        months: 0,
        days,
        hours: 0,
        minutes: 0,
        seconds: 0,
    }
}

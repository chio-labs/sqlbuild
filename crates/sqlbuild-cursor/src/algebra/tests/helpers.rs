use crate::algebra::errors::CursorError;
use crate::algebra::models::{
    CivilDate, LocalDateTime, Scalar, ScalarValue, Timestamp, ZoneOffset,
};
use crate::algebra::tests::test_types::NoZones;
use crate::algebra::types::ZoneRules;

impl ZoneRules for NoZones {
    fn to_utc(
        &self,
        _: usize,
        local: &LocalDateTime,
        _: bool,
    ) -> Result<LocalDateTime, CursorError> {
        Ok(*local)
    }

    fn utc_offset(&self, _: usize, _: &LocalDateTime, _: bool) -> Result<Option<i64>, CursorError> {
        Ok(None)
    }
}

pub(crate) fn civil(year: i64, month: u32, day: u32) -> CivilDate {
    CivilDate { year, month, day }
}

pub(crate) fn local(
    date: CivilDate,
    (hour, minute, second, microsecond): (u32, u32, u32, u32),
) -> LocalDateTime {
    LocalDateTime {
        date,
        hour,
        minute,
        second,
        microsecond,
    }
}

pub(crate) fn timestamp(local: LocalDateTime, offset: ZoneOffset) -> Scalar {
    Scalar {
        value: ScalarValue::Timestamp(Timestamp {
            local,
            fold: false,
            offset,
            template: None,
            source_text: None,
        }),
        handle: None,
    }
}

pub(crate) fn naive(year: i64, month: u32, day: u32, hour: u32) -> Scalar {
    timestamp(
        local(civil(year, month, day), (hour, 0, 0, 0)),
        ZoneOffset::Naive,
    )
}

pub(crate) fn date(year: i64, month: u32, day: u32) -> Scalar {
    Scalar {
        value: ScalarValue::Date(civil(year, month, day)),
        handle: None,
    }
}

pub(crate) fn integer(value: i128) -> Scalar {
    Scalar {
        value: ScalarValue::Integer(value),
        handle: None,
    }
}

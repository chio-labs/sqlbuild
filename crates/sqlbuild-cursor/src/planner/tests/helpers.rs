use crate::algebra::models::{
    CivilDate, LocalDateTime, Scalar, ScalarValue, Timestamp, ZoneOffset,
};

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

//! The time zone lookups an aware timestamp's caller supplies.

use crate::algebra::errors::CursorError;
use crate::algebra::models::LocalDateTime;

/// UTC conversion for zones whose offsets the algebra cannot compute itself.
pub trait ZoneRules {
    /// `value.astimezone(UTC).replace(tzinfo=None)` for the wall time in the `template` zone.
    fn to_utc(
        &self,
        template: usize,
        local: &LocalDateTime,
        fold: bool,
    ) -> Result<LocalDateTime, CursorError>;

    /// `value.utcoffset()` in microseconds, or `None` when the zone reports no offset.
    fn utc_offset(
        &self,
        template: usize,
        local: &LocalDateTime,
        fold: bool,
    ) -> Result<Option<i64>, CursorError>;
}

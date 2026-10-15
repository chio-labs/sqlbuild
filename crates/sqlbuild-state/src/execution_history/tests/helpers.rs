use sqlbuild_cursor::algebra::models::CivilDate;

use crate::execution_history::models::{FilterTime, ProjectionFact, RunFact, RunRow, RunStatus};
use crate::execution_history::types::UtcTime;

pub(crate) fn at(day: u32, microsecond: u32) -> UtcTime {
    UtcTime {
        date: CivilDate {
            year: 2026,
            month: 1,
            day,
        },
        hour: 0,
        minute: 0,
        second: 0,
        microsecond,
    }
}

pub(crate) fn bound(day: u32, is_utc: bool) -> FilterTime {
    FilterTime {
        instant: at(day, 0),
        is_utc,
    }
}

pub(crate) fn fact(storage_order: i64, run: Option<(&str, &str, &str)>) -> ProjectionFact {
    ProjectionFact {
        storage_order,
        cursor: format!("c{storage_order}"),
        received_at: at(u32::try_from(storage_order).unwrap_or(1), 0),
        run: run.map(|(run_id, invocation_id, event_type)| RunFact {
            run_id: run_id.to_owned(),
            invocation_id: invocation_id.to_owned(),
            event_type: event_type.to_owned(),
            occurred_at: at(10, 5),
        }),
    }
}

pub(crate) fn run_row(run_id: &str, created_day: u32, last: i64) -> RunRow {
    RunRow {
        run_id: run_id.to_owned(),
        invocation_id: "i".to_owned(),
        created_at: at(created_day, 0),
        status: RunStatus::Unknown,
        is_complete: false,
        last_event_cursor: format!("c{last}"),
        last_storage_order: last,
        command: None,
        target: None,
        environment: None,
        started_at: None,
        ended_at: None,
    }
}

pub(crate) fn completed(run: RunRow) -> RunRow {
    RunRow {
        status: RunStatus::Completed,
        is_complete: true,
        ended_at: Some(at(10, 5)),
        ..run
    }
}

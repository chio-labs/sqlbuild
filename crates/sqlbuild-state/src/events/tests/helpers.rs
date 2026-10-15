use sqlbuild_cursor::algebra::models::{CivilDate, LocalDateTime};

use crate::events::models::{
    ColumnEventKey, EventOrder, EventRelation, FingerprintKey, FingerprintOrder, MoveEventKey,
    OldNameFactKey, OldNameStep, RecordedRenameKey, StateCell, StateColumnType, StateValue,
};

pub(crate) fn cell(column: &str, column_type: StateColumnType, value: StateValue) -> StateCell {
    StateCell {
        column: column.to_owned(),
        column_type,
        value,
    }
}

pub(crate) fn relation(database: Option<&str>, schema: &str, name: &str) -> EventRelation {
    EventRelation {
        database: database.map(str::to_owned),
        schema: Some(schema.to_owned()),
        name: name.to_owned(),
    }
}

pub(crate) fn order(hour: u32, event_id: &str) -> EventOrder {
    EventOrder {
        created_at: LocalDateTime {
            date: CivilDate {
                year: 2026,
                month: 1,
                day: 1,
            },
            hour,
            minute: 0,
            second: 0,
            microsecond: 0,
        },
        event_id: event_id.to_owned(),
    }
}

pub(crate) fn moved(order: EventOrder, (origin, destination): (&str, &str)) -> MoveEventKey {
    MoveEventKey {
        order,
        origin: relation(None, "main", origin),
        destination: relation(None, "main", destination),
    }
}

pub(crate) fn renamed(order: EventOrder, (origin, destination): (&str, &str)) -> ColumnEventKey {
    ColumnEventKey {
        order,
        relation: relation(None, "main", "orders"),
        origin_column: origin.to_owned(),
        destination_column: destination.to_owned(),
    }
}

pub(crate) fn fact(
    order: EventOrder,
    migration_event_id: &str,
    step: OldNameStep,
) -> OldNameFactKey {
    OldNameFactKey {
        order,
        migration_event_id: migration_event_id.to_owned(),
        step,
    }
}

pub(crate) fn pairs(items: &[(&str, &str)]) -> Vec<(String, String)> {
    items
        .iter()
        .map(|(old, new)| ((*old).to_owned(), (*new).to_owned()))
        .collect()
}

pub(crate) fn recorded(
    order: EventOrder,
    relation: EventRelation,
    records_event: bool,
) -> RecordedRenameKey {
    RecordedRenameKey {
        order,
        relation,
        records_event,
    }
}

pub(crate) fn fingerprint(
    (timestamp, run_id): (&str, &str),
    node_name: &str,
    target: Option<EventRelation>,
) -> FingerprintKey {
    FingerprintKey {
        order: FingerprintOrder {
            timestamp: timestamp.to_owned(),
            run_id: run_id.to_owned(),
        },
        node_name: node_name.to_owned(),
        target,
    }
}
